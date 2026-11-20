# Mission 21 — Private image uploads and Vision

## Architecture

Flutter uses `image_picker` (Android gallery and Web file chooser), checks the
5 MiB client limit and image signatures, then submits multipart data to the
authenticated FastAPI route:

`POST /api/conversations/{conversation_id}/vision`

FastAPI verifies the Supabase JWT and conversation owner, bounds and decodes the
image with Pillow, stores it in the private `chat-uploads` Storage bucket using
the backend-only `SUPABASE_SERVICE_ROLE_KEY`, calls Groq's vision-capable model,
and stores the user and assistant messages in the existing `messages` table.
The original filename is never used in the storage path. Paths are generated
from the verified user, conversation and idempotency UUIDs.

The normal `POST /api/chat` and authenticated `/chat` routes remain unchanged.
Vision requests use a separate configurable model; `GROQ_MODEL` (currently the
text model) is never assumed to support image inputs. The documented Groq vision
model example is `qwen/qwen3.8-27b`. Verify that this model is enabled for the
intended Groq account before setting it. See [Groq Vision documentation](https://console.groq.com/docs/vision).

Questions that explicitly mention the EMSI brochure/documents run the existing
text RAG as a separate, labeled check. Only its returned citations are included
in `sources`; visual observations are labeled separately and are not treated as
brochure facts. Image-only answers have no PDF citations.

## Configuration

Backend `.env`:

```dotenv
GROQ_VISION_MODEL=qwen/qwen3.8-27b
VISION_MAX_UPLOAD_BYTES=5242880
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=server_only_placeholder
GROQ_API_KEY=server_only_placeholder
```

Do not put either server key in Flutter. The server accepts only JPEG, PNG and
WebP. The default and maximum upload size is 5 MiB; image dimensions are limited
to 25 million pixels. The Groq HTTP call has a 60 second timeout. Empty,
corrupt, oversized and unsupported data is rejected before Vision processing.

## Supabase setup

1. Review and run `supabase/migrations/20261119_mission21_private_chat_uploads.sql`
   in the intended project's SQL Editor. It creates/locks a private bucket and
   adds owner-scoped policies. It does not alter conversations or Qdrant.
2. Confirm `chat-uploads` is private and its MIME allowlist is JPEG, PNG and
   WebP with a 5 MiB limit.
3. In Storage policies, inspect all existing policies on `storage.objects`.
   The migration adds a restrictive owner-scope guard for this bucket so broad
   permissive policies cannot grant cross-user access. Confirm with two real
   authenticated accounts; this checkout has no live-project credentials.
4. Restart FastAPI after configuring the backend-only keys.
5. Set `GROQ_VISION_MODEL` to a vision model enabled for the account. Do not
   change `GROQ_MODEL` for the existing text RAG.

The message JSON stores the bucket, randomized storage path, MIME type and
content digest. On restore, Flutter asks Storage for an owner-authorized signed
URL valid for one hour. Conversation deletion first removes the database rows,
then attempts to delete its owned Storage objects. A cleanup failure is shown
explicitly; periodically inspect the bucket for orphaned files (for example,
after account deletion or failed client cleanup).

### Manual two-user Storage/RLS check

1. Sign in as test user A and upload a small image into a test conversation.
   Confirm a row appears only in A's conversation and an object exists under
   `A_UUID/<conversation UUID>/<request UUID>.<ext>` in the private bucket.
2. Restore the conversation as A; confirm Flutter obtains a short-lived signed
   URL and the image loads. Verify the returned object URL is not a public URL.
3. Sign in as user B. Attempt to list/read A's object, create a signed URL for
   A's path and delete A's object. Each operation must be denied.
4. Upload as B and confirm B can read only B's object. Delete B's conversation
   and confirm its object is removed. Repeat with A.
5. Attempt an upload without a JWT and with an expired JWT; expect HTTP 401.

Run these checks with normal authenticated sessions/publishable client key,
never `service_role`; service-role requests bypass RLS and do not validate it.
For Flutter Web, if the browser reports a Storage CORS error while loading a
signed URL, allow only the exact development/production frontend origins in the
project's Storage CORS configuration and retest; do not make the bucket public.

### Reproducible real Storage isolation script

`backend/scripts/test_storage_isolation_live.py` defaults to offline preparation
and makes no network calls. It reports only whether the required root `.env`
settings exist. Use the explicit `--live` option only with a confirmed
non-production test project and two disposable, distinct accounts. It prompts
for each account's expected email and access token; tokens are entered hidden,
validated through Supabase Auth, and never printed. Do not pass tokens or keys
on the command line.

The script creates two objects under a unique `__mission21_5_<uuid>` segment.
Because this bucket is backend-upload-only, the backend-only
`SUPABASE_SERVICE_ROLE_KEY` is used locally just to seed those fresh test
objects and as a targeted cleanup fallback. It is never used for the RLS
assertions: reads, cross-user access attempts, signed URL creation, direct
upload/overwrite attempts and cross-user deletion all use the two normal user
JWTs with `SUPABASE_PUBLISHABLE_KEY`. Thus the privileged setup is not treated
as evidence of client authorization. The script deletes only the two exact
objects it created, through the Storage HTTP API; it never issues SQL deletes.

The expected policy behavior is that direct client uploads and overwrites are
denied, including for the owner's own path, because uploads go through the
authenticated FastAPI backend. The checks cover owner reads, cross-user read,
signing and delete denials, unchanged seeded objects after hostile write
attempts, and a signed URL that works before its short expiry and fails after.
The live checks require internet access and a configured Supabase test project.

## Local setup and validation

From the project root in PowerShell:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd mobile
flutter pub get
flutter analyze
flutter test
cd ..\backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

The vision route, storage policies and actual Groq account access require
separate live validation. Unit/integration tests must mock both Supabase Storage
and Groq and must not claim that live RLS or provider access passed.
