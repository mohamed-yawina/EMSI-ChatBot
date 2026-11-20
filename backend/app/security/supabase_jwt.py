"""Cryptographically verify Supabase access tokens with the project JWKS."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

import httpx
import jwt


ALLOWED_ASYMMETRIC_ALGORITHMS = frozenset({"ES256", "RS256"})
JWKS_CACHE_SECONDS = 300
JWKS_TIMEOUT_SECONDS = 5.0
JWT_LEEWAY_SECONDS = 30


class SupabaseConfigurationError(RuntimeError):
    """The project URL is missing or malformed."""


class SupabaseJWKSUnavailable(RuntimeError):
    """The project's JWKS could not be fetched or parsed."""


class SupabaseTokenInvalid(ValueError):
    """The bearer token is malformed, untrusted, expired, or has bad claims."""


@dataclass(frozen=True)
class SupabaseIdentity:
    subject: str
    email: str | None


def _validated_project_url(project_url: str) -> str:
    normalized = project_url.strip().rstrip("/")
    parsed = urlparse(normalized)
    local_http = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not (local_http and parsed.scheme == "http"))
    ):
        raise SupabaseConfigurationError("SUPABASE_URL must be a project HTTPS URL.")
    return normalized


class SupabaseJWKSVerifier:
    """Verify JWT signatures and required Supabase claims using a cached JWKS."""

    def __init__(
        self,
        project_url: str,
        *,
        client: httpx.Client | None = None,
        cache_seconds: int = JWKS_CACHE_SECONDS,
    ) -> None:
        self.project_url = _validated_project_url(project_url)
        self.issuer = f"{self.project_url}/auth/v1"
        self.jwks_url = f"{self.issuer}/.well-known/jwks.json"
        self._http = client or httpx.Client(
            timeout=JWKS_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        self._cache_seconds = max(0, cache_seconds)
        self._keys: list[dict] = []
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def _load_jwks(self, *, force_refresh: bool = False) -> list[dict]:
        with self._lock:
            if not force_refresh and self._keys and time.monotonic() < self._expires_at:
                return self._keys
            try:
                response = self._http.get(self.jwks_url)
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise SupabaseJWKSUnavailable(
                    "Unable to retrieve Supabase signing keys."
                ) from exc

            keys = body.get("keys") if isinstance(body, dict) else None
            if not isinstance(keys, list) or not keys or not all(
                isinstance(item, dict) for item in keys
            ):
                raise SupabaseJWKSUnavailable("Supabase returned an invalid JWKS.")

            self._keys = keys
            self._expires_at = time.monotonic() + self._cache_seconds
            return self._keys

    def _find_public_key(self, kid: str, algorithm: str, *, refresh: bool) -> object | None:
        keys = self._load_jwks(force_refresh=refresh)
        for jwk_data in keys:
            if jwk_data.get("kid") != kid:
                continue
            if jwk_data.get("use") not in (None, "sig"):
                continue
            key_ops = jwk_data.get("key_ops")
            if isinstance(key_ops, list) and "verify" not in key_ops:
                continue
            if jwk_data.get("alg") not in (None, algorithm):
                continue
            try:
                return jwt.PyJWK.from_dict(jwk_data, algorithm=algorithm).key
            except (jwt.PyJWTError, TypeError, ValueError):
                continue
        return None

    def verify(self, token: str) -> SupabaseIdentity:
        if not token or len(token) > 16_384:
            raise SupabaseTokenInvalid("Invalid bearer token.")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise SupabaseTokenInvalid("Invalid bearer token.") from exc

        algorithm = header.get("alg")
        kid = header.get("kid")
        if algorithm not in ALLOWED_ASYMMETRIC_ALGORITHMS or not isinstance(kid, str):
            raise SupabaseTokenInvalid("Unsupported Supabase token signing key.")

        public_key = self._find_public_key(kid, algorithm, refresh=False)
        if public_key is None:
            # A signing-key rotation may have reached the issuer before the local cache.
            public_key = self._find_public_key(kid, algorithm, refresh=True)
        if public_key is None:
            raise SupabaseTokenInvalid("Unknown Supabase token signing key.")

        try:
            claims = jwt.decode(
                token,
                key=public_key,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=self.issuer,
                leeway=JWT_LEEWAY_SECONDS,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise SupabaseTokenInvalid("Invalid or expired Supabase access token.") from exc

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise SupabaseTokenInvalid("Supabase token has no valid subject.")
        email = claims.get("email")
        return SupabaseIdentity(
            subject=subject,
            email=email if isinstance(email, str) else None,
        )


@lru_cache(maxsize=1)
def get_supabase_verifier() -> SupabaseJWKSVerifier:
    project_url = os.getenv("SUPABASE_URL", "").strip()
    if not project_url:
        raise SupabaseConfigurationError("SUPABASE_URL is not configured.")
    return SupabaseJWKSVerifier(project_url)
