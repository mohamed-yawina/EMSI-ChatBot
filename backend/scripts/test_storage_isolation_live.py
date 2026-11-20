"""Explicit, two-user Supabase Storage isolation check.

Default invocation is an offline preparation/dry run. Live mode is guarded by
project and account confirmations. Service-role credentials are used only to
seed and clean two unique test objects; every RLS assertion uses the two normal
user access tokens.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
BUCKET = "chat-uploads"
SIGNED_URL_TTL_SECONDS = 5
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/h00AAAAASUVORK5CYII="
)


class SafeRequestError(RuntimeError):
    """An HTTP failure without URL, headers, body, or credential details."""


@dataclass(frozen=True)
class UserSession:
    label: str
    token: str
    user_id: str
    expected_email: str


def _encoded_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in path.split("/"))


def _request(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    try:
        return client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        # Do not include the exception string: it may contain a signed URL.
        raise SafeRequestError(type(exc).__name__) from None


def _headers(publishable_key: str, token: str) -> dict[str, str]:
    return {
        "apikey": publishable_key,
        "Authorization": f"Bearer {token}",
    }


def _result(label: str, response: httpx.Response, *, success: bool) -> bool:
    passed = response.is_success if success else not response.is_success
    outcome = "PASS" if passed else "FAIL"
    print(f"[{outcome}] {label} (HTTP {response.status_code})")
    return passed


def _denied(label: str, response: httpx.Response) -> bool:
    # Do not treat conflicts or server errors as proof of an RLS denial.
    passed = response.status_code in {400, 401, 403, 404, 406}
    print(f"[{'PASS' if passed else 'FAIL'}] {label} (HTTP {response.status_code})")
    return passed


def _storage_object_url(project_url: str, path: str) -> str:
    return f"{project_url.rstrip('/')}/storage/v1/object/{BUCKET}/{_encoded_path(path)}"


def _load_session(
    client: httpx.Client,
    project_url: str,
    publishable_key: str,
    label: str,
) -> UserSession:
    expected_email = input(f"Expected email for test user {label}: ").strip()
    token = getpass.getpass(f"Paste access token for test user {label} (hidden): ").strip()
    if not expected_email or not token:
        raise SafeRequestError(f"Missing account confirmation for user {label}.")

    response = _request(
        client,
        "GET",
        f"{project_url.rstrip('/')}/auth/v1/user",
        headers=_headers(publishable_key, token),
    )
    if not response.is_success:
        raise SafeRequestError(
            f"Could not validate test user {label} (HTTP {response.status_code})."
        )
    try:
        identity = response.json()
        user_id = str(identity["id"])
        actual_email = str(identity["email"]).casefold()
    except (ValueError, KeyError, TypeError):
        raise SafeRequestError(f"Invalid identity response for test user {label}.") from None
    if actual_email != expected_email.casefold():
        raise SafeRequestError(f"Test user {label} does not match the confirmed account.")
    print(f"[OK] Test user {label} session validated; account value is not logged.")
    return UserSession(label, token, user_id, expected_email)


def _signed_url(project_url: str, response: httpx.Response) -> str:
    try:
        value = response.json().get("signedURL") or response.json().get("signedUrl")
    except (ValueError, AttributeError):
        value = None
    if not isinstance(value, str) or not value:
        raise SafeRequestError("Storage did not return a signed URL.")
    if value.startswith("https://"):
        parsed = urlsplit(value)
        expected = urlsplit(project_url)
        if parsed.scheme != "https" or parsed.netloc != expected.netloc:
            raise SafeRequestError("Storage returned a signed URL for an unexpected host.")
        return value
    if value.startswith("/storage/v1/"):
        return f"{project_url.rstrip('/')}{value}"
    if value.startswith("/"):
        return f"{project_url.rstrip('/')}/storage/v1{value}"
    return f"{project_url.rstrip('/')}/storage/v1/{value}"


def run_live() -> int:
    load_dotenv(ROOT / ".env", override=False)
    project_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    parsed_project = urlsplit(project_url)
    if parsed_project.scheme != "https" or not parsed_project.hostname:
        print("Live mode requires SUPABASE_URL to be an HTTPS project URL.", file=sys.stderr)
        return 2
    if not publishable_key or not service_role_key:
        print(
            "Live mode requires SUPABASE_PUBLISHABLE_KEY and backend-only "
            "SUPABASE_SERVICE_ROLE_KEY in the root .env.",
            file=sys.stderr,
        )
        return 2

    project_ref = parsed_project.hostname.split(".", 1)[0]
    print("LIVE MODE: two real Supabase users and Storage will be contacted.")
    print("Two unique objects will be created, then deleted through Storage API.")
    if input(f"Type project ref '{project_ref}' to confirm the target: ").strip() != project_ref:
        print("Project confirmation did not match; no requests were made.")
        return 2
    if input("Type RUN STORAGE SECURITY TESTS to continue: ").strip() != "RUN STORAGE SECURITY TESTS":
        print("Live test confirmation did not match; no requests were made.")
        return 2

    timeout = httpx.Timeout(15.0, connect=8.0)
    run_prefix = f"__mission21_5_{uuid4().hex}"
    failures = 0
    created: list[tuple[UserSession, str]] = []

    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        try:
            user_a = _load_session(client, project_url, publishable_key, "A")
            user_b = _load_session(client, project_url, publishable_key, "B")
            if user_a.user_id == user_b.user_id:
                raise SafeRequestError("The two test sessions resolve to the same user.")

            print("[OK] User A and user B are distinct authenticated identities.")
            path_a = f"{user_a.user_id}/{run_prefix}/a.png"
            path_b = f"{user_b.user_id}/{run_prefix}/b.png"
            admin_headers = {
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": "image/png",
                "x-upsert": "false",
            }

            # Privileged setup is not used for any authorization assertion.
            for user, path in ((user_a, path_a), (user_b, path_b)):
                seeded = _request(
                    client,
                    "POST",
                    _storage_object_url(project_url, path),
                    headers=admin_headers,
                    content=PNG_BYTES,
                )
                if not _result(f"Seed isolated test object for user {user.label}", seeded, success=True):
                    failures += 1
                    raise SafeRequestError("Could not seed test objects; stopping safely.")
                created.append((user, path))

            # A and B can each read their own object, but not the other's.
            for owner, other, own_path, other_path in (
                (user_a, user_b, path_a, path_b),
                (user_b, user_a, path_b, path_a),
            ):
                own_read = _request(
                    client, "GET", _storage_object_url(project_url, own_path),
                    headers=_headers(publishable_key, owner.token),
                )
                failures += not _result(
                    f"{owner.label} reads own image", own_read, success=True
                )
                if own_read.is_success and own_read.content != PNG_BYTES:
                    print(f"[FAIL] {owner.label} own image bytes match seeded PNG")
                    failures += 1
                elif own_read.is_success:
                    print(f"[PASS] {owner.label} own image bytes match seeded PNG")

                cross_read = _request(
                    client, "GET", _storage_object_url(project_url, other_path),
                    headers=_headers(publishable_key, owner.token),
                )
                failures += not _denied(
                    f"{owner.label} cannot read user {other.label} image",
                    cross_read,
                )

                cross_delete = _request(
                    client, "DELETE", _storage_object_url(project_url, other_path),
                    headers=_headers(publishable_key, owner.token),
                )
                failures += not _denied(
                    f"{owner.label} cannot delete user {other.label} image",
                    cross_delete,
                )
                remains = _request(
                    client, "GET", _storage_object_url(project_url, other_path),
                    headers=_headers(publishable_key, other.token),
                )
                if not remains.is_success or remains.content != PNG_BYTES:
                    print(f"[FAIL] User {other.label} image remains intact after cross-delete attempt")
                    failures += 1
                else:
                    print(f"[PASS] User {other.label} image remains intact after cross-delete attempt")

                # The bucket is intentionally backend-upload-only: even an
                # owner's direct client upload/overwrite must be rejected.
                own_upload = _request(
                    client, "POST", _storage_object_url(project_url, own_path),
                    headers={
                        **_headers(publishable_key, owner.token),
                        "Content-Type": "image/png",
                        "x-upsert": "false",
                    },
                    content=PNG_BYTES,
                )
                failures += not _denied(
                    f"{owner.label} direct client upload is denied",
                    own_upload,
                )

                own_overwrite = _request(
                    client, "POST", _storage_object_url(project_url, own_path),
                    headers={
                        **_headers(publishable_key, owner.token),
                        "Content-Type": "image/png",
                        "x-upsert": "true",
                    },
                    content=b"different-test-payload",
                )
                failures += not _denied(
                    f"{owner.label} direct overwrite is denied",
                    own_overwrite,
                )

                cross_upload = _request(
                    client, "POST", _storage_object_url(project_url, other_path),
                    headers={
                        **_headers(publishable_key, owner.token),
                        "Content-Type": "image/png",
                        "x-upsert": "false",
                    },
                    content=PNG_BYTES,
                )
                failures += not _denied(
                    f"{owner.label} upload into user {other.label} path is denied",
                    cross_upload,
                )

                cross_overwrite = _request(
                    client, "POST", _storage_object_url(project_url, other_path),
                    headers={
                        **_headers(publishable_key, owner.token),
                        "Content-Type": "image/png",
                        "x-upsert": "true",
                    },
                    content=b"cross-user-overwrite-attempt",
                )
                failures += not _denied(
                    f"{owner.label} cannot overwrite user {other.label} image",
                    cross_overwrite,
                )

                unchanged = _request(
                    client, "GET", _storage_object_url(project_url, own_path),
                    headers=_headers(publishable_key, owner.token),
                )
                if not unchanged.is_success or unchanged.content != PNG_BYTES:
                    print(f"[FAIL] {owner.label} image remains unchanged after upload attempts")
                    failures += 1
                else:
                    print(f"[PASS] {owner.label} image remains unchanged after upload attempts")

                signed_other = _request(
                    client,
                    "POST",
                    f"{project_url}/storage/v1/object/sign/{BUCKET}/{_encoded_path(other_path)}",
                    headers={
                        **_headers(publishable_key, owner.token),
                        "Content-Type": "application/json",
                    },
                    json={"expiresIn": SIGNED_URL_TTL_SECONDS},
                )
                failures += not _denied(
                    f"{owner.label} cannot sign user {other.label} image URL",
                    signed_other,
                )

            # Verify short-lived URLs through the real Storage signing API.
            for owner, own_path in ((user_a, path_a), (user_b, path_b)):
                signed = _request(
                    client,
                    "POST",
                    f"{project_url}/storage/v1/object/sign/{BUCKET}/{_encoded_path(own_path)}",
                    headers={
                        **_headers(publishable_key, owner.token),
                        "Content-Type": "application/json",
                    },
                    json={"expiresIn": SIGNED_URL_TTL_SECONDS},
                )
                if not _result(f"{owner.label} creates own short-lived signed URL", signed, success=True):
                    failures += 1
                    continue
                signed_url = _signed_url(project_url, signed)
                immediate = _request(client, "GET", signed_url)
                failures += not _result(
                    f"{owner.label} signed URL works before expiry", immediate, success=True
                )
                if immediate.is_success and immediate.content != PNG_BYTES:
                    print(f"[FAIL] {owner.label} signed URL returns the expected image")
                    failures += 1
                else:
                    print(f"[PASS] {owner.label} signed URL returns the expected image")
                time.sleep(SIGNED_URL_TTL_SECONDS + 2)
                expired = _request(client, "GET", signed_url)
                failures += not _denied(
                    f"{owner.label} signed URL is rejected after expiry",
                    expired,
                )
                # Never print or persist the signed URL.
                del signed_url
        except SafeRequestError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            failures += 1
        finally:
            # Clean up only the exact objects created by this run. Try owner
            # authorization first; service role is a last-resort cleanup only.
            for owner, path in created:
                deleted = _request(
                    client,
                    "DELETE",
                    _storage_object_url(project_url, path),
                    headers=_headers(publishable_key, owner.token),
                )
                if deleted.is_success or deleted.status_code == 404:
                    print(f"[CLEANUP] Removed this run's object for user {owner.label} via Storage API.")
                    continue
                admin_deleted = _request(
                    client,
                    "DELETE",
                    _storage_object_url(project_url, path),
                    headers={"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"},
                )
                if admin_deleted.is_success or admin_deleted.status_code == 404:
                    print(f"[CLEANUP] Owner cleanup was denied; removed this run's object for user {owner.label} via privileged Storage API.")
                else:
                    print(f"[CLEANUP ERROR] Could not remove this run's object for user {owner.label} (HTTP {admin_deleted.status_code}).", file=sys.stderr)
                    failures += 1

    print(f"Live Storage checks finished: {failures} failure(s).")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run real Storage API checks after project/account confirmations.",
    )
    args = parser.parse_args()
    if not args.live:
        load_dotenv(ROOT / ".env", override=False)
        required = (
            "SUPABASE_URL",
            "SUPABASE_PUBLISHABLE_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        )
        configured = {name: bool(os.getenv(name, "").strip()) for name in required}
        print("OFFLINE PREPARATION ONLY — no network requests were made.")
        print("Required .env settings present:")
        for name, present in configured.items():
            print(f"  {name}: {'configured' if present else 'missing'}")
        print("Planned: seed two unique objects, exercise A/B RLS with user JWTs, then clean exact paths via Storage API.")
        print("Run with --live only against a confirmed non-production/test project and disposable accounts.")
        return 0
    return run_live()


if __name__ == "__main__":
    raise SystemExit(main())
