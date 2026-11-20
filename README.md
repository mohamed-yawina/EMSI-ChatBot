# EMSI-ChatBot

EMSI-ChatBot is a document-grounded assistant for the EMSI brochure. It combines a Flutter Web/Android client with a FastAPI backend, Qdrant retrieval, BGE-M3 text embeddings, optional CLIP image search, and Groq Cloud generation.

The application is designed to answer from retrieved brochure passages, return document/page references, and keep short conversational context on the client. It does not automatically create or re-index Qdrant collections when the backend starts.

## Features

- Text retrieval from the `emsi_text` Qdrant collection with BGE-M3 and a hybrid semantic/lexical ranking policy.
- Optional Groq Cloud generation from a bounded set of retrieved brochure passages.
- Server-validated PDF citations based on Qdrant `source` and `page` metadata.
- Optional image retrieval from `emsi_images` with CLIP; image search is off by default.
- Memory-conscious CPU model workers, RAM checks, serialized heavy work, and a safe fallback path.
- Anonymous V1 keeps five exchanges in Flutter; authenticated V2 stores conversations and messages in Supabase PostgreSQL.
- Flutter Material 3 interface for Web and Android.

## Technology

| Area | Technology |
|---|---|
| Client | Flutter, Dart, `http`, `url_launcher`, `supabase_flutter` |
| API | FastAPI, Uvicorn, Pydantic |
| Text retrieval | BGE-M3, Sentence Transformers, Qdrant |
| Image retrieval | CLIP through Transformers, Qdrant |
| Answer generation | Groq Cloud over HTTPS (`GROQ_MODEL` configuration) |
| Local services | Docker Compose, Qdrant |

## Architecture

```text
Flutter Web / Android
        |-- Supabase Auth (email/password, confirmation and recovery)
        |-- GET /api/users/me (verified bearer JWT)
        |-- POST /api/chat (V1 anonymous compatibility)
        `-- POST /api/conversations/{id}/chat (verified JWT; persistent V2)
                    |
                    v
FastAPI
  |-- Supabase JWKS signature and claim verification for protected account routes
  |-- Server-side persistence adapter for authenticated conversations
  |-- Supabase PostgreSQL conversation/message tables with client RLS
  |-- BGE-M3 (CPU) -> retrieval/ranking -> Qdrant: emsi_text
  |       `-> selected passages + question/context -> Groq Cloud (optional)
  `-- if include_images=true: release/check text-model memory
          -> CLIP (CPU) -> Qdrant: emsi_images -> local /images assets
```

Docker Compose can run Qdrant, FastAPI and Flutter Web together. Qdrant data is stored in a named volume; the current default volume name preserves the volume created by the earlier Qdrant-only Compose configuration in this project directory.

## RAG request flow

1. FastAPI receives the question, `use_llm`, `include_images`, and optional conversation history.
2. The conversation helper resolves follow-up references into a standalone retrieval query. The original question and bounded history remain available to generation.
3. BGE-M3 embeds the retrieval query on CPU. The retriever queries Qdrant and ranks candidates using the existing semantic and lexical signals.
4. A limited set of relevant passages is sent to Groq when `use_llm=true`. The prompt treats passages as the factual evidence; history helps interpret the question but is not evidence.
5. Citation markers are resolved against retrieved Qdrant metadata. The API returns only verifiable source/page references.
6. If image search is explicitly enabled, the backend checks that BGE-M3 can be released and memory is sufficient before using CLIP. If safety checks fail, image retrieval is deferred while the text response can still be returned.

The backend expects already-provisioned Qdrant collections named `emsi_text` and `emsi_images`. Startup checks for them and does not index data.

## Multimodal image search

Image search is optional and disabled by default (`include_images=false`). Enabling it allows CLIP to retrieve indexed brochure images from `emsi_images`; FastAPI serves local image assets under `/images`. The returned image metadata is taken from indexed records. A missing asset or insufficient memory can result in no images; the client should not infer that an image exists when the API returns an empty list.

## Conversation memory

Anonymous V1 keeps up to ten messages (five exchanges) in Flutter and sends them with `POST /api/chat`; the server does not keep cross-request anonymous history. Authenticated V2 loads the last ten persisted user/assistant messages (five exchanges) from the selected, owner-checked Supabase conversation for each request. The server does not use a global per-user memory cache, and saved assistant messages are context only, never documentary evidence. A new V2 conversation starts with no previous exchange; signing back in restores the saved display and bounded follow-up context. Stateful RAG requests bypass the simple in-process answer cache.

## Citations and grounding safeguards

- PDF page and source values come from Qdrant metadata, not generated passage indices.
- Unverified citation markers are removed or not returned as sources.
- Campus-specific course claims require explicit documentary evidence linking the campus and offering; separate mentions are not sufficient.
- The assistant should state when the retrieved brochure passages do not answer the question.
- These checks reduce citation and grounding errors but cannot guarantee that every generated sentence is correct. Check cited PDF pages during a formal demonstration, especially where the source PDF has complex columns or layout.

## Windows installation

For the native workflow, use Windows PowerShell, Python 3.11, Docker Desktop with Compose v2 for Qdrant, and Flutter SDK. Android Studio or a connected device is needed only for Android. For the Docker-only workflow, Docker Desktop with Compose v2 is required; Flutter and Python run in containers. The complete Windows guide is [docs/INSTALLATION_WINDOWS.md](docs/INSTALLATION_WINDOWS.md).

The repository intentionally excludes the brochure PDF and generated `data/processed` assets. Before running the full RAG locally, place an authorized copy of `Brochure-EMSI.pdf` at `data/documents/Brochure-EMSI.pdf`, provide the prepared local assets as described in [data/README.md](data/README.md), and ensure the expected Qdrant collections are provisioned. No indexing is performed by the commands below.

## Docker Compose demo (Windows)

Requirements: Docker Desktop with Linux containers and Compose v2. The Flutter build stage uses `forthecommunity/flutter:3.50.0` (Dart 3.14.0), satisfying the project SDK constraints in `pubspec.yaml` and `pubspec.lock`. The first build downloads the CPU-only PyTorch dependencies and Flutter build image; the first BGE-M3/CLIP query downloads model weights into a persistent Docker cache. No model is loaded and no Qdrant collection is created or reindexed during `docker compose up`.

1. Ensure the existing local assets are present at `data/processed/Brochure-EMSI/images`. FastAPI mounts `data/processed` read-only so image URLs continue to resolve inside the backend container.
2. Create `.env` from `.env.example` only if it does not already exist, then set the real backend Groq and Supabase values locally. Compose passes server credentials only to FastAPI. Flutter receives only `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `FLUTTER_API_BASE_URL` as build-time Dart defines; never put a service-role key in a Dart define.
3. Check `QDRANT_VOLUME_NAME` before the first start. The default, `emsi-chatbot_qdrant_storage`, reuses the named volume from the former Qdrant-only Compose setup when it was launched from this project directory. If the existing volume has a different name, set `QDRANT_VOLUME_NAME` in `.env` to that exact name. Do not change it to a new name to work around missing collections: that would start with an empty database.
4. Start the stack from the repository root:

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:6333/collections
```

Open Flutter Web at `http://localhost:8080`; API requests from the browser use `FLUTTER_API_BASE_URL` (default `http://localhost:8000`), not the Compose-only hostname. For access from another device, set that variable to the PC's reachable LAN address, adjust the local-only port bindings deliberately, and allow only the required trusted network in Windows Firewall. Qdrant and FastAPI are bound to loopback by default.

Compose waits for FastAPI's healthcheck, which checks both `/health` and the existing `emsi_text` / `emsi_images` collections before starting the Web container. If the backend stays unhealthy, inspect `docker compose logs backend qdrant`; check the volume name, collection names, `.env`, and local processed image files. BGE-M3 and CLIP use CPU, are not loaded simultaneously, and keep Hugging Face weights in the `huggingface_cache` volume. Compose limits are conservative defaults (`7g` backend, `2g` Qdrant); Docker Desktop must be allowed enough memory for these limits plus Windows itself. Lower them only with awareness that a lower BGE container memory limit can prevent persistent mode and make retrieval slower.

Stop containers without deleting data:

```powershell
docker compose down
```

This keeps both named volumes. **Do not use `docker compose down -v`** for normal shutdown. Rebuild/start with `docker compose up -d --build`. Useful diagnostics are `docker compose logs -f backend`, `docker compose logs -f qdrant`, `docker stats`, and `docker volume ls`.

### Reuse or migrate existing Qdrant data safely

The Compose file explicitly names the existing project volume by default; verify the actual old volume with `docker volume ls` before starting. If the current Qdrant data lives in another Docker named volume, set `QDRANT_VOLUME_NAME` to that existing volume name so Compose mounts it directly. Do not delete, rename, or recreate it. If Qdrant currently uses a host folder or a different running server, keep that source intact and use Qdrant collection snapshots to transfer into a separately named destination volume; take and verify a backup first, and restore only into an empty destination. Do not copy a live Qdrant storage directory and do not restore over the existing collections. The current environment could not inspect Docker volumes because Docker Engine access was denied, so confirm the volume name on Windows before first startup.

### Configure Groq

From the project root:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `GROQ_API_KEY` and `GROQ_MODEL` in the local `.env` file. The model name is configurable; choose one available to your Groq account. Never put the key in Flutter, source control, screenshots, or shared command history.

### Environment variables and secret boundaries

| Variable | Used by | Purpose |
|---|---|---|
| `GROQ_API_KEY` | FastAPI only | Authenticates text and Vision API requests. |
| `GROQ_MODEL` | FastAPI only | Selects the configured text generation model. |
| `GROQ_VISION_MODEL` | FastAPI only | Selects the configured image question answering model. |
| `VISION_MAX_UPLOAD_BYTES` | FastAPI only | Bounds uploaded image size; backend validation also checks actual image format and dimensions. |
| `SUPABASE_URL` | FastAPI and Flutter Web build | Project endpoint used for Auth, persistence and private Storage. |
| `SUPABASE_PUBLISHABLE_KEY` | Flutter Web build | Public client key; it is not an authorization boundary. |
| `SUPABASE_SERVICE_ROLE_KEY` | FastAPI only | Privileged backend persistence/Storage operations. Never pass it as a Dart define or build argument. |
| `FLUTTER_API_BASE_URL` | Flutter Web build | Browser-reachable FastAPI address. Defaults to `http://localhost:8000`, not the internal Compose hostname. |
| `QDRANT_VOLUME_NAME` | Docker Compose | Existing named volume to reuse. Verify its exact name before changing it. |
| `BACKEND_MEMORY_LIMIT`, `QDRANT_MEMORY_LIMIT` | Docker Compose | Container memory ceilings; leave adequate memory for Windows and Docker Desktop. |

`.env` and `.env.*` are ignored by Git (with `.env.example` retained). Docker builds exclude `.env` and do not copy it into either image; Compose injects it at FastAPI runtime. Flutter Web necessarily contains the Supabase URL and publishable key in its client bundle, but must never contain Groq or service-role credentials.

### Start Qdrant and FastAPI

```powershell
docker compose up -d qdrant
docker compose ps
py -3.11 -m venv backend\.venv
& .\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\backend\start_backend.ps1
```

The virtual environment and dependency installation are one-time setup steps. If `backend\.venv` already exists and works, skip its creation and installation. The backend launcher checks Qdrant and the two expected collections; it will stop with guidance if they are missing. It does not index the brochure.

Check the basic HTTP health endpoint in another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

This endpoint confirms only that the API process responds; it does not test Qdrant or Groq. Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

### Supabase Auth configuration

Email/password registration, email confirmation, sign-in, password recovery, session restoration and sign-out are handled by the official Flutter Supabase SDK. FastAPI exposes `GET /api/users/me` for a protected profile check. It verifies bearer JWT signatures against the project's JWKS and validates issuer, `authenticated` audience, expiry and subject. No password is stored by this application. The existing `POST /api/chat` remains anonymous for V1 compatibility; this is not suitable for exposing publicly without a separate deployment/security review.

1. Create a Supabase project and enable email/password under **Authentication → Sign In / Providers**. Enable email confirmation.
2. In **Authentication → URL Configuration**, allow the exact local Web origin (for example `http://localhost:5000`) and the Android callback `com.emsi.chatbot://login-callback/`. For a deployed Web app, allow its HTTPS origin and use HTTPS.
3. Configure an asymmetric project signing key (ES256 or RS256), since FastAPI obtains public verification keys from JWKS. The verifier intentionally rejects symmetric HS256 tokens because no public verification key is available in JWKS.
4. Set `SUPABASE_URL` and the server-only `SUPABASE_SERVICE_ROLE_KEY` in the backend `.env`. The service-role credential is used only by FastAPI's persistence adapter after it verifies the user's JWT and conversation ownership; it is never sent to Flutter. Pass only the project URL and **publishable** client key to Flutter with Dart defines. Never use a service-role or secret key in Flutter.

Example from `mobile/` (replace placeholders with your own project values):

```powershell
flutter run -d chrome --web-port 5000 `
  --dart-define=API_BASE_URL=http://127.0.0.1:8000 `
  --dart-define=SUPABASE_URL=https://your-project-ref.supabase.co `
  --dart-define=SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_project_key
```

The publishable key is client configuration, not an authorization boundary. Browser sessions are persisted by the SDK; protect the Web origin from XSS and review the session-storage threat model before production deployment. Persistent conversations require the Mission 20 migration and a backend-only service-role key. See [Mission 20 Supabase setup](docs/MISSION20_SUPABASE_SETUP.md). The migration has not been applied automatically.

### Persistent conversations (Mission 20)

After applying `supabase/migrations/20261118_mission20_conversations.sql`, authenticated Flutter clients use the user's Supabase session and RLS for conversation CRUD, history reads, dashboard summaries, and user-message insertion. Assistant messages are accepted from FastAPI only: the endpoint verifies the Supabase JWT, checks conversation ownership, then uses a server-only `SUPABASE_SERVICE_ROLE_KEY` to persist the RAG result and verified sources. This key is never included in a Flutter build. RLS protects direct client access; FastAPI's verified JWT and owner checks protect its privileged assistant writes.

The endpoint `POST /api/conversations/{conversation_id}/chat` accepts `{question, request_id, use_llm, include_images}` and returns the existing `{answer, sources, images}` shape. It persists the user's question before generation, uses a stable request UUID for retry deduplication, and loads no more than five prior exchanges from that same conversation. Existing `POST /api/chat` remains unchanged and anonymous for V1 compatibility. Anonymous history is not imported into an account.

### User-uploaded images and Vision (Mission 21)

Authenticated users can attach one JPEG, PNG, or WebP image (5 MiB maximum) and ask about its visible content. Flutter sends a multipart request to `POST /api/conversations/{conversation_id}/vision`; FastAPI validates the actual image format/dimensions and the Supabase JWT, verifies conversation ownership, stores the file in private Supabase Storage, calls the separately configured Groq Vision model, and persists the image reference with the user message. Uploaded files are never placed in the public brochure image directory and original filenames are not used as storage paths. Restored messages use one-hour signed Storage URLs scoped by Supabase RLS.

Configure backend-only `GROQ_VISION_MODEL` and `VISION_MAX_UPLOAD_BYTES` in `.env` (see `.env.example`). `GROQ_MODEL` remains the text-only RAG configuration. The example vision model is `qwen/qwen3.8-27b`; verify availability for the Groq account. Run `supabase/migrations/20261119_mission21_private_chat_uploads.sql` manually to create the private bucket and policies. The migration, real Storage RLS, and live provider account have not been validated against a connected Supabase/Groq project. Setup steps and the manual two-user check are in [Mission 21 setup](docs/MISSION21_VISION_SETUP.md).

Image questions use a separate vision request. If the question explicitly asks about the EMSI brochure/documents, the existing text RAG runs as a separately labeled check and only its returned sources are attached. The model's visual observations are not presented as facts from the brochure. CLIP remains for brochure-image retrieval; it is not used to answer questions about uploaded pictures.

The dashboard/sidebar provide per-user statistics, recent conversations, title search, archive/favorite filters, rename, delete and restore. The SQL migration is additive and does not touch Qdrant. It must be reviewed and applied manually in the intended Supabase project before these features can be used. Live migration, authentication and two-user RLS behavior have not been validated in this checkout.

### Start Flutter

```powershell
Set-Location .\mobile
flutter pub get
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:8000 `
  --dart-define=SUPABASE_URL=https://<project-ref>.supabase.co `
  --dart-define=SUPABASE_PUBLISHABLE_KEY=<publishable-client-key>
```

For a standard Android emulator, replace the API URL with `http://10.0.2.2:8000` and pass the same two Supabase client defines. For a physical device, use the PC's private-LAN address and allow access only on a trusted private network. The backend launcher binds to `0.0.0.0:8000` for local-device access; do not expose the API or Qdrant to the public Internet. Never pass `SUPABASE_SERVICE_ROLE_KEY` to Flutter.

## API

### `POST /api/chat`

Request:

```json
{
  "question": "Which campuses are mentioned in the brochure?",
  "use_llm": true,
  "include_images": false,
  "history": []
}
```

Response contract:

```json
{
  "answer": "Answer grounded in retrieved passages.",
  "sources": [
    {"source": "Brochure-EMSI.pdf", "page": 4, "score": 0.82}
  ],
  "images": []
}
```

`question` is required and limited to 1–1000 characters. `use_llm` and `include_images` default to `false` at the API. `history` contains `user`/`assistant` messages and is limited to ten messages, with each message limited to 1200 characters.

Other implemented routes include `GET /`, `GET /health`, `GET /api/cache/stats`, `GET /api/images`, `POST /api/chat/test`, authenticated `GET /api/users/me`, authenticated `POST /api/conversations/{conversation_id}/chat`, and authenticated multipart `POST /api/conversations/{conversation_id}/vision`. The persistent chat and vision routes require the Mission 20 database migration; uploads also require the Mission 21 private Storage migration and server-only key. Conversation listing/CRUD is performed by Flutter through Supabase PostgREST under RLS. See FastAPI's `/docs` for the live API schema. `/api/chat/test` checks the request/response path without running the full RAG.

## Tests

The backend tests use mocks for Groq, retrieval, citations, memory policies, and image search. They are intended to run without loading BGE-M3 or CLIP:

```powershell
& .\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
```

Flutter checks, from the `mobile` directory:

```powershell
flutter analyze
flutter test
```

## Known limitations

- This source checkout does not include the brochure or generated corpus assets. Users must have authorization to provide and process the source material locally.
- The backend requires pre-existing Qdrant collections and matching indexed data; setup does not create or populate them.
- Initial local model loading may take time and memory. BGE-M3 and CLIP are CPU-based and are not intended to remain loaded simultaneously. Image search can be deferred by safety checks.
- Groq requires network access and a valid local API key/model configuration. Selected document excerpts and bounded conversation history are sent to Groq for generation.
- `GET /api/users/me` and `POST /api/conversations/{id}/chat` require Supabase authentication; `POST /api/chat` remains anonymous for compatibility. CORS is permissive. Keep the API on a trusted development network; it is not configured as a public production service.
- Persistent conversations require the Mission 20 migration and a backend-only `SUPABASE_SERVICE_ROLE_KEY`; two-user RLS behavior still needs live validation.
- Python requirements and the Qdrant Docker image tag are not pinned to exact versions, so clean installs may vary over time.
- The `/health` endpoint is a process check, not an end-to-end readiness check.
- Docker Compose adds a backend readiness check for both FastAPI and the expected Qdrant collections; it does not test Groq, Supabase, authentication, or a complete chat request.
- Automated backend tests use mocks for external APIs and model workers. They do not prove live Supabase Auth, PostgreSQL RLS, private Storage isolation, Groq availability, or browser/device networking.
- CLIP retrieves visual candidates; similarity alone does not establish an image's identity or meaning. Vision responses can misread image contents and should be checked during a demonstration.
- Uploaded images are stored privately in Supabase Storage and sent to the configured Groq Vision provider for analysis. Review provider/data handling requirements before using personal or confidential images.
- The local project volume and model cache have no automatic backup/restore policy. Keep a verified Qdrant snapshot and do not use `docker compose down -v` as routine cleanup.

## Future work

- Pin and regularly review dependency and container versions.
- Restrict CORS and harden deployment before any shared or public deployment; add backup, retention and recovery procedures for persistent conversations.
- Document a reproducible, authorized data-preparation and Qdrant-provisioning workflow.
- Capture genuine application screenshots and add them to `docs/screenshots/` after local review.

## Project documentation

- [Windows installation guide](docs/INSTALLATION_WINDOWS.md)
- [Soutenance and demonstration guide](docs/SOUTENANCE.md)
- [Corpus and local data notes](data/README.md)
- [Screenshot checklist](docs/screenshots/README.md)
