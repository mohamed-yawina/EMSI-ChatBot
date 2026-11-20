# EMSI-ChatBot V2 Roadmap

**Status (updated after Mission 20 implementation):** Supabase Auth and its JWKS-protected profile route are implemented. Mission 20 adds an additive conversations/messages migration, client RLS policies, authenticated persistent chat, and Flutter dashboard/history CRUD. The migration has not been applied to a live Supabase project; live auth, cross-user RLS, and persistence-after-relogin remain deployment validations. Uploads, cloud vision, export/regeneration, and persistent preferences remain proposals.

## 1. V1 architecture observed in the repository

### Client

- Flutter Web and Android start in `mobile/lib/main.dart` and use a single stateful `ChatScreen` (`mobile/lib/screens/chat_screen.dart`).
- Reusable UI is already separated into `AppSidebar`, `WelcomePanel`, `ChatComposer`, `ChatMessageBubble`, `SourceReferences`, `ImageGallery`, and `MarkdownContent` under `mobile/lib/widgets/`.
- `AppTheme` defines light and dark Material 3 themes in `mobile/lib/theme/app_theme.dart`, using the green EMSI-inspired palette.
- `ChatApiService` sends `POST /api/chat`, parses `answer`, `sources`, and `images`, and uses `API_BASE_URL` with Web and Android Emulator defaults.
- `ConversationMemory` lives in the Flutter model layer. It bounds memory to ten messages (five exchanges); the screen resets it for a new conversation. It is process/UI state, not permanent storage.
- The current widget tests exercise the chat request, memory reset/limit, optional image search, and responsive UI. The project context reports 62 passing backend tests; this roadmap does not rerun them.

### FastAPI and RAG

`backend/app/main.py` currently defines the Pydantic request/response schemas and these routes:

| Existing route | Current role |
|---|---|
| `GET /` | Basic welcome response |
| `GET /health` | Process-level health response; not an end-to-end readiness check |
| `POST /api/chat` | Existing text RAG, optional Groq generation and optional indexed-image search |
| `GET /api/cache/stats` | In-process cache counters |
| `GET /api/images` | Lists local brochure image assets |
| `POST /api/chat/test` | Lightweight client/API contract check |
| `/images/*` static mount | Serves local processed brochure image files |

FastAPI exposes `GET /api/users/me` and the Mission 20 `POST /api/conversations/{id}/chat` as Supabase-authenticated routes. `POST /api/chat` and other V1 routes still accept anonymous requests to preserve compatibility. Mission 20 adds owner-scoped conversation/message records and dashboard summary data; uploads and persistent settings are not implemented. CORS currently allows all origins without credentials.

The text flow resolves conversational references in `backend/app/rag/conversation.py`, embeds and retrieves with BGE-M3 through `backend/app/rag/`, ranks Qdrant results from `emsi_text`, and can call `backend/app/services/groq_service.py`. The service receives selected passages rather than the whole brochure; citation markers are checked against Qdrant `source` and `page` metadata. Request history is bounded and is not stored globally by FastAPI. Stateless text results and image results use process-local caches.

Brochure-image search is a separate optional path: CLIP searches `emsi_images`; the isolated CLIP path first requests confirmed BGE-M3 release and a sufficient RAM check. The code pins both model worker paths to CPU and serializes heavy chat work with a lock. These safeguards are existing V1 behavior to preserve.

`backend/app/api/auth.py` contains the protected identity dependency and `backend/app/security/supabase_jwt.py` validates token signatures and claims. There are no SQLAlchemy entities or Alembic migrations: Mission 20 uses a versioned Supabase SQL migration and PostgREST. The migration and live RLS have not yet been applied/validated.

### V1 implications for migration

- V1 conversations are not available for server-side migration: the history exists only in the running Flutter conversation state and is cleared by “New conversation”. Do not promise import of old conversations unless a separate export/import source is created.
- Qdrant collections and existing embeddings must remain unchanged. PostgreSQL is for accounts and application records, not a replacement for the brochure vector collections.
- The existing `POST /api/chat` JSON contract must keep working during a staged V2 rollout.

## 2. Proposed V2 architecture

```text
Flutter Web / Android
  |-- Auth/session client, dashboard, saved conversation list, settings
  |-- Existing RAG chat contract and verified source display
  `-- Upload reference (private asset ID), not a public file path
          |
          v
FastAPI
  |-- Authentication and owner-scoped authorization
  |-- PostgreSQL repositories: users, sessions, conversations, messages, assets
  |-- Existing RAG service -> BGE-M3 -> Qdrant emsi_text -> Groq text generation
  |-- Existing optional brochure image retrieval -> CLIP -> Qdrant emsi_images
  `-- User image analysis -> configurable cloud vision provider (separate capability)
          |
          +--> PostgreSQL (application data)
          +--> private image storage (outside static /images mount)
          +--> Qdrant (existing brochure indexes, unchanged)
          `--> configured Groq/vision HTTPS APIs
```

Use SQLAlchemy 2.x with Alembic and PostgreSQL for durable application data. Use Supabase Auth as the identity provider: Flutter uses the official `supabase_flutter` SDK, while FastAPI verifies access-token signatures against the project's public JWKS and validates issuer, audience, expiry and subject. Do not implement password storage, login endpoints, refresh-token tables, or a second JWT issuer in this application. Keep route handlers thin and put persistence, authorization, image storage, and conversation orchestration in services/repositories. Keep the current synchronous FastAPI route style initially unless measured need justifies an async database refactor.

Keep the current RAG implementation behind a service boundary so persistence can call it without rewriting ranking, citations, RAM controls, or model workers. Existing routes remain compatible. Authenticated conversation routes can wrap the same RAG response and persist a user message and assistant result as one application-level operation.

### Vision and RAM policy

Use a separately configured cloud vision API for images uploaded by users. Do not assume that the currently configured text model supports image input; implement a provider interface with explicit capability/configuration checks and a clear unavailable response. Select a vision provider/model only after confirming account availability, image-input support, privacy terms, and cost limits.

The uploaded-image analysis path must not cause BGE-M3 and local CLIP to coexist. Prefer sending a bounded, validated image to the cloud vision provider and continue using the existing memory-gated CLIP path only for indexed brochure-image retrieval when requested. If a V2 use case needs both paths during one request, sequence them with the existing release/RAM gates or defer one path. Never bypass the current checks.

## 3. Proposed database schema

Use UUID primary keys, UTC timestamps, foreign keys, explicit indexes, and database-level uniqueness/length constraints. Names below are logical design; actual SQLAlchemy names may follow project conventions.

| Table | Proposed fields and constraints | Purpose |
|---|---|---|
| Supabase identity | Supabase-managed `auth.users` identity; the application does not copy passwords or session tokens into its database. | Account identity. |
| `user_profiles` (optional) | `id` UUID FK to Supabase `auth.users.id`, display-only profile fields and timestamps | Optional application profile. Apply RLS using `auth.uid()` and never store credentials. |
| `user_preferences` | `user_id` unique FK to Supabase identity, `theme`, `include_images_default` (default false), `locale`, `updated_at` | Per-account UI preferences. Do not store secrets or arbitrary unvalidated settings. |
| `conversations` | `id`, `owner_id`, `title`, `created_at`, `updated_at`, `archived_at` nullable | Conversation container and ownership boundary. Index `(owner_id, updated_at)` and archive state. |
| `messages` | `id`, `conversation_id`, `role`, `content`, `created_at`, `favorite`, optional `reply_to_id`/regeneration group, `sources` JSONB, `images` JSONB, optional safe model/config metadata | Ordered user and assistant turns. Preserve source/page snapshots returned by the API so old citations do not depend on a later retrieval. Index `(conversation_id, created_at)` and favorite state. |
| `uploaded_assets` | `id`, `owner_id`, private `storage_key`, sanitized `original_name`, detected `mime_type`, `byte_size`, `sha256`, `created_at`, optional `deleted_at`/retention state | Private metadata for user-uploaded images. Never expose a raw filesystem path or public static URL. |

Messages should be reachable only through a conversation owned by the current user. A duplicated `owner_id` on child rows is optional; if used for efficient enforcement, maintain it with a composite FK/constraint and still verify the conversation owner. Add database indexes for all owner-scoped list and lookup paths. Full-text search can begin with PostgreSQL `tsvector`/GIN over conversation titles and message text; do not start with a separate search service.

Do not place uploaded image bytes in JSONB. Store files in a private local directory outside `data/processed` and outside FastAPI's static mount for an initial single-host deployment, behind a storage interface. A future object store can implement the same interface. Add retention and orphan-cleanup rules before enabling uploads broadly.

## 4. Proposed API surface

These routes are proposals, not current routes. Keep the existing `POST /api/chat` response contract (`answer`, `sources`, `images`) available throughout migration.

### Authentication and account

| Proposed route | Role |
|---|---|
| Supabase Auth SDK | Flutter performs email/password registration, login, email confirmation, recovery and logout directly with Supabase Auth. |
| `GET /api/users/me` | Implemented: verify the Supabase bearer token using project JWKS and return its authenticated subject and optional email. |
| `PATCH /api/users/me` | Update allowed profile fields; password change should verify the current password. |
| `GET /api/users/me/settings`, `PATCH /api/users/me/settings` | Read/update validated preferences. |

### Conversations and messages

| Proposed route | Role |
|---|---|
| `GET /api/conversations?q=&archived=` | List only the authenticated user's conversations; support title/message search and archive filtering with pagination. |
| `POST /api/conversations` | Create an empty conversation, optionally with a validated title. |
| `GET /api/conversations/{conversation_id}` | Get an owner-scoped conversation and its paginated messages. |
| `PATCH /api/conversations/{conversation_id}` | Rename and/or archive/unarchive. |
| `DELETE /api/conversations/{conversation_id}` | Delete an owned conversation and its messages according to a documented retention policy. |
| `POST /api/conversations/{conversation_id}/messages` | Submit a question, optional uploaded-asset IDs and image-search setting; call the existing RAG service and persist the result. |
| `POST /api/conversations/{conversation_id}/messages/{message_id}/regenerate` | Regenerate a prior assistant turn using the original question and bounded context; save a new revision/assistant message rather than silently overwriting audit history. |
| `PATCH /api/conversations/{conversation_id}/messages/{message_id}` | Toggle a favorite only for an owned message. |
| `GET /api/conversations/{conversation_id}/export` | Export an owned conversation in a documented format with citations and safe metadata. |

### User image uploads

| Proposed route | Role |
|---|---|
| `POST /api/uploads` | Authenticated multipart upload with strict image validation; return an opaque asset ID and safe metadata, never a storage path. |
| `DELETE /api/uploads/{asset_id}` | Delete an owned asset where retention rules allow. |

An upload ID can be included in the conversation message request. Enforce ownership when resolving every ID. The API should not accept arbitrary external image URLs from clients; that avoids SSRF and uncontrolled third-party fetches.

## 5. Authentication and security design

- Supabase Auth handles password verification and session issuance. The application stores no passwords and implements no custom refresh-token rotation.
- FastAPI verifies Supabase access-token signatures using a strict asymmetric algorithm allowlist and the project's public JWKS, then validates `exp`, issuer, audience and subject. Never log bearer tokens. Revisit supported algorithms if the Supabase project signing configuration changes.
- Flutter receives only the project's publishable client key. Never place a service-role or secret key in client code. Require HTTPS outside localhost and configure exact confirmation/recovery redirects in the Supabase dashboard.
- Supabase Flutter's default session persistence differs by platform (browser storage on Web and platform storage on mobile). Review the threat model for the deployment; browser XSS can access client-side sessions. PKCE is enabled, but it does not eliminate XSS risk. A hardened production web deployment may require a server-side session/BFF design.
- Current client behavior: `supabase_flutter` manages session persistence and refresh (browser storage on Web and SDK platform storage on Android), with PKCE selected. Browser-readable session storage remains exposed to same-origin XSS; apply CSP/XSS controls and assess a BFF with HttpOnly cookies before production if the deployment threat model requires it. Verify Android storage behavior for the target release; do not hand-roll refresh handling.
- Every conversation, message, favorite, export, and uploaded-asset query must include the authenticated owner boundary. A UUID is not authorization. Return 404 for inaccessible IDs where that avoids resource enumeration.
- Add rate limits and abuse controls for registration, login, refresh, uploads, Groq, and vision calls. Add lockout/backoff without creating an easy denial-of-service vector.
- Restrict CORS to configured client origins when credentials are enabled. Add CSRF defenses for cookie-authenticated requests. Keep TLS mandatory outside localhost.
- Validate upload size before reading fully; allow only explicitly supported raster formats, inspect file signatures rather than trusting extension/MIME, reject SVG and malformed/polyglot files, randomize storage names, strip EXIF, and never serve private assets from the public `/images` mount. Add quotas, timeouts, retention, and malware scanning appropriate to deployment.
- Vision requests transmit user-provided images to a cloud provider. Disclose this in UI, obtain a clear user action/consent, minimize retention, bound image dimensions/bytes, and document provider data handling. Do not log image bytes, base64, prompts containing personal data, or provider credentials.
- Treat both brochure text and image contents as untrusted instructions. Preserve the current evidence-only RAG/citation validation; a vision description is contextual input, not proof about brochure facts.

## 6. Flutter V2 organization

Keep the existing reusable chat widgets and introduce feature-oriented folders gradually rather than replacing the UI in one step:

```text
mobile/lib/
  app/                 app shell, routing, auth gate, theme mode
  core/                API client, token/session handling, common errors
  features/
    auth/               login, registration, session state
    dashboard/          personal overview and recent conversations
    conversations/      list/search/archive/detail/message composer
    settings/           account and app preferences
    uploads/            image picker, preview, upload progress/removal
  models/               shared DTOs/domain models
  services/             API/repository adapters (migrate from current services gradually)
  theme/                green EMSI-inspired light/dark Material 3 tokens
  widgets/              shared buttons, loading, empty/error states
```

Current reusable pieces to retain/adapt: `ChatMessageBubble`, `SourceReferences`, `ImageGallery`, `MarkdownContent`, `ChatComposer`, `WelcomePanel`, and responsive `AppSidebar`. Change the existing blue/teal palette to a reviewed green identity in a dedicated UI mission; verify official brand colors/assets rather than inventing official logo use. Preserve citations and optional brochure image search.

Proposed screens:

1. Auth gate and login/register forms.
2. Dashboard with recent conversations and simple personal counts based on the user's records.
3. Responsive conversation workspace: desktop sidebar/list plus chat; mobile drawer and conversation list route.
4. Settings for account, theme, image-search preference, and session/logout controls.
5. Upload review state in the composer: preview, remove, upload progress, unsupported/oversize feedback.

Do not add a complex state-management dependency until the authenticated session and multiple screens demonstrate a concrete need. A small repository/service layer plus a scoped notifier/controller is sufficient for the first rollout. Add routing only when the screen flow is defined.

## 7. Dependency plan

Add dependencies only in the missions that use them, pin compatible versions after reviewing current Python/Flutter constraints, and update lockfiles. These are candidates to evaluate, not installation instructions for this planning phase.

### Backend candidates

- `sqlalchemy` 2.x — ORM and transaction handling.
- `alembic` — schema migrations.
- `psycopg` (v3) — PostgreSQL driver.
- `PyJWT[crypto]` — implemented for signed Supabase access-token validation against JWKS; no password-hashing dependency is needed in this application.
- `PyJWT[crypto]` (or a reviewed equivalent) — signed access JWT validation.
- `python-multipart` — FastAPI multipart uploads.
- `email-validator` only if using Pydantic `EmailStr`.
- Existing `httpx` can serve the configured vision provider with explicit timeouts; do not add an SDK unless it materially improves safe provider integration.
- Optional development tools: pytest fixtures already used, plus a PostgreSQL test service/container only when available and lightweight. Never point integration tests at production data.

### Flutter candidates

- Reassess Supabase SDK storage on Web/Android for the target threat model; avoid introducing a second token-storage/refresh layer.
- Image picker/file selection support after the upload API contract is fixed.
- A router package only if route transitions justify it. Do not add state-management infrastructure pre-emptively.

## 8. Strategy and mission breakdown

Each mission should be separately reviewable, preserve the current chat route, avoid model/data changes, and include acceptance tests before proceeding.

### Mission 17.1 — V2 decisions and service boundaries

- Confirm deployment topology, supported account policy, data retention, browser/mobile token transport, PostgreSQL availability, image limits, and vision-provider privacy/cost.
- Add only architecture/configuration boundaries and documentation where needed; no account feature yet.
- **Acceptance:** existing API schema and current tests remain unchanged/passing; a decision record documents deployment and threat model; no secrets or database migrations are introduced.

### Mission 17.2 — PostgreSQL foundation

- Add SQLAlchemy configuration, database session lifecycle, base metadata, Alembic configuration, optional `user_profiles`, preferences, conversation/message/asset schema, and indexes. Reference Supabase `auth.users.id`; do not create application password or auth-session tables.
- Use a separate development/test database. Add health/readiness distinction without exposing database credentials.
- **Acceptance:** migration upgrade and downgrade are tested against a disposable PostgreSQL database; startup remains backward compatible; profiles reference Supabase user UUIDs and RLS is verified; no Qdrant collections or embeddings change.

### Mission 17.3 — Authentication and account settings

- Configure Supabase Auth email/password confirmation and recovery redirects, Flutter AuthGate, and the FastAPI JWKS verifier/current-user dependency. Extend authorization to future data APIs, and define production CORS/rate limiting. Registration, login, logout, recovery UI and `GET /api/users/me` are implemented; real project verification remains required.
- **Acceptance:** automated tests cover invalid/expired/tampered signatures and claims, missing bearer tokens, authorization dependencies, and no secret leakage. A separate test project verifies registration, confirmation, recovery redirects and session lifecycle. Anonymous V1 chat remains available until an explicit deprecation decision.

### Mission 17.4 — Persistent conversation CRUD

- Implement owner-scoped conversation and message persistence; list/search, rename, archive/unarchive, delete, favorites, and export.
- Store verified source/page metadata with assistant messages. Never use saved assistant responses as evidence in a future RAG request.
- **Acceptance:** two-user tests prove that guessing another user's IDs cannot read, edit, favorite, export, or delete their records; search/archive/pagination and cascade/retention policy are tested.

### Mission 17.5 — Authenticated chat integration

- Add authenticated conversation message submission and regeneration using the existing RAG service. Keep `POST /api/chat` and its response fields compatible during rollout.
- Persist the user question and assistant result, but continue sending only bounded conversation context and selected document passages to Groq. Keep citation validation in place.
- **Acceptance:** existing RAG tests pass; authenticated chat persists atomically or marks a clear failed state; regeneration creates a revision; saved context cannot be mixed across accounts; history and cache policies are tested.

### Mission 17.6 — Flutter authenticated dashboard and history

- Extend the green Material 3 app and existing Supabase AuthGate/Profile with dashboard, conversation list/search, CRUD actions, preferences, and session controls. Reuse current chat/source/gallery widgets.
- **Acceptance:** Web and Android auth screens, profile and logout have mocked widget tests; a live non-production project verifies confirmation, recovery, redirects and session restore. Remaining conversation features are owner-scoped and responsive; existing chat contract remains compatible.

### Mission 17.7 — Secure user image uploads and cloud vision

- Add private storage and upload lifecycle, ownership checks, size/MIME/signature validation, quotas, and provider abstraction. Choose a vision-capable cloud model only after provider/account validation; never assume the V1 text model accepts images.
- Add Flutter preview/progress/remove controls and clear cloud-processing consent.
- **Acceptance:** tests mock the provider and cover supported/unsupported/malformed/oversize files, path traversal, cross-user asset access, provider timeout/quota/error, and no public URL leakage. No local vision model is loaded and no BGE-M3/CLIP coexistence is allowed.

### Mission 17.8 — Response controls and release hardening

- Add account-data export, regeneration UX, conversation favorites, rate/usage limits, backups/restore documentation, observability with redaction, and deployment security review.
- **Acceptance:** exported data is owner-scoped; rate/timeout and provider failures are understandable; restore is tested on a non-production copy; all V1 citations, anti-hallucination, memory, RAM, and optional CLIP tests pass.

## 9. Test strategy

### Backend

- Unit-test Supabase JWT signature/claims and failure modes, owner filters, conversation state transitions, and upload validators. Supabase account lifecycle is tested with a dedicated non-production project, separately from mocked CI tests.
- API-test all auth and CRUD routes with at least two users; include IDOR/ownership attempts for every resource type.
- Test PostgreSQL behavior and Alembic using an isolated disposable database. Keep fast service tests on mocks.
- Preserve all existing RAG tests, including citations, campus-specific evidence, out-of-scope answers, history bounds, cache bypass for history, CLIP memory gates, and sanitized Groq/Qdrant errors.
- Test persistent-message citations and ensure regeneration cannot manufacture unverified sources.
- Mock Groq text and vision HTTP calls; no unit test should make paid external calls.

### Flutter

- Test login/register errors, session expiry/logout, token refresh behavior, dashboard loading, empty/error states, search/archive/rename/delete/favorite, and owner-scoped API client behavior.
- Test conversation pagination and five-exchange context formation from persisted messages without treating assistant text as proof.
- Test image preview/upload/remove, progress, invalid types/sizes, and cloud-processing consent.
- Retain responsive tests at phone/desktop sizes, theme checks, Markdown, citations, image gallery, new conversation, and network retry.
- Run `flutter analyze` and `flutter test` on supported CI/Windows before each release mission.

### System / operational

- Test migrations on an empty disposable database and backup/restore on a non-production copy.
- Verify Qdrant collections remain unchanged and still pass the current retrieval contract.
- Verify the application refuses requests for another user's conversation or asset.
- Confirm rate limits, CORS/CSRF, TLS assumptions, key redaction, retention and deletion behavior.
- Load-test only after the memory and cloud quotas are agreed; do not benchmark BGE-M3 and CLIP simultaneously.

## 10. Principal risks and mitigations

| Risk | Severity | Mitigation / decision needed |
|---|---|---|
| Cross-account data exposure (IDOR) | Critical | Enforce owner scope in repository queries and test every resource with two users; UUIDs are not authorization. |
| Token theft or browser session exposure | High | Use HTTPS, PKCE, a restrictive CSP and XSS controls; review SDK storage behavior and adopt a server-side session/BFF if the threat model requires HttpOnly cookies. Supabase owns refresh lifecycle. |
| Public API is unauthenticated and currently permissive CORS | High for deployment | Restrict CORS and bind/firewall appropriately as part of auth deployment; do not expose current V1 directly to the Internet. |
| Upload malware, parser exploits, path traversal, storage exhaustion | High | Signature validation, size/quota limits, randomized private storage keys, no static mount, scanning/retention, isolated image processing. |
| User images sent to a third party | High privacy/cost impact | Explicit consent, supported-model verification, retention/provider review, payload/time/call limits, no image logging. |
| Vision model may not be available or image-capable under existing Groq configuration | Medium/high | Separate provider/model configuration and capability check; use a compatible cloud vision API only after validation; clear fallback. |
| Persisted answers can outlive or diverge from source corpus | Medium | Snapshot verified source/page citations, store safe provenance, rerun retrieval for regeneration, distinguish saved answer from current evidence. |
| Migration breaks V1 contract or loses ephemeral histories | Medium | Additive schema/routes, maintain `/api/chat`, no promise of V1 history migration, feature flag and rollback plan. |
| Database availability and backups | High for durable history | Health/readiness, backups, restore tests, retention and deletion plan before calling history permanent. |
| Model RAM pressure on 15 GB PC | High | Keep BGE-M3/CLIP mutually exclusive under current gates; use cloud vision for uploads; serialize heavy work and retain CPU/RAM constraints. |
| Password reset/email adds an unplanned dependency | Medium | Decide whether required for initial V2; otherwise clearly document admin-assisted recovery until email delivery/security is designed. |

## 11. Migration and rollout strategy

1. Keep Qdrant and its two brochure collections untouched. Do not rebuild vectors or change embedding models as part of V2 persistence.
2. Use additive PostgreSQL tables and Alembic revisions. Back up the target database before schema changes; test upgrades and downgrades only on disposable copies first.
3. Deploy the database and migrations before enabling authenticated UI. Initially create a separate empty V2 data store; V1 in-memory Flutter histories have no durable source to import.
4. Preserve `POST /api/chat` request/response compatibility. Introduce authenticated `/api/conversations/...` routes incrementally and reuse the same validated RAG service.
5. Use a feature flag or staged client release so V1 users can continue the current flow while V2 authentication is validated. Define how an existing anonymous chat transitions to a newly created conversation; do not silently attach it to the wrong account.
6. Add secure storage, CORS/CSRF, provider configuration, and backup/restore procedures before production data is stored.
7. Roll out image upload and cloud vision only after owner checks, storage quotas, consent UI, provider capability, and deletion lifecycle pass review.

## 12. Decisions required before implementation

- Is V2 for a single academic demo host or a multi-user public deployment? This changes TLS, account verification, deployment secrets, backups, rate limits, and monitoring requirements.
- Should registration be open, invitation-only, or administrator-created? Is email verification/password reset in scope?
- Which exact cloud vision provider and model are available to the project account, and what image-retention/privacy terms are acceptable?
- What maximum upload size, formats, quota per account, retention period, and deletion semantics should apply?
- Should conversation deletion permanently remove records immediately, or use a retention/soft-delete period? Are exports JSON, Markdown, or both?
- How long should access/refresh sessions live, and should web use secure cookies while Android uses secure storage?
- Which PostgreSQL hosting/backups are available, and what is the recovery target for saved conversations?
- Which official EMSI color/logo guidance may be used for the green visual refresh?

## 13. Mission 20 implementation status

- **Implemented in code:** additive SQL migration for `conversations` and `messages`, composite owner relationship, RLS policies, restricted client grants, dashboard summary view/RPC, backend-only persistence adapter, and authenticated chat endpoint. Existing `/api/chat` remains the anonymous V1 path.
- **Implemented in Flutter:** persistent repository using the Supabase client, dashboard statistics/recent chats, recent/archive/favorite views, title search, pagination, rename/delete/archive/restore/favorite actions, persisted message reload, and authenticated chat requests with retry request IDs.
- **Trust boundary:** authenticated clients may create user-role messages only. FastAPI verifies the JWT and conversation ownership, then uses a server-only service-role key for assistant messages. Service-role requests do not prove RLS behavior.
- **Not yet validated live:** migration execution, email/session integration against the intended project, two-user RLS script, persistence after app restart, and deployment CORS/TLS/backups.
- **Not implemented:** uploaded-user-image vision, export, regeneration, persistent settings/preferences, and admin/support tooling.

See [Mission 20 Supabase setup](MISSION20_SUPABASE_SETUP.md) for migration review and manual validation steps. Do not mark Supabase persistence production-ready until the migration and non-privileged two-user RLS check succeed on a disposable project.
