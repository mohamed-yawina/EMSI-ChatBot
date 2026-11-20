# Mission 20 — Supabase conversations setup

This guide configures persistent user conversations for EMSI-ChatBot V2. It does not run the migration for you. The SQL is additive and is not applied to any project by the application startup.

## What was added

- `public.conversations` and `public.messages`, owned by a Supabase Auth user UUID.
- Row Level Security policies and restricted grants for authenticated client operations.
- `public.conversation_summaries` and `public.get_my_dashboard_stats()` for per-user dashboard data.
- Authenticated FastAPI endpoint `POST /api/conversations/{conversation_id}/chat`.
- Flutter dashboard, search, favorites, archive/restore, rename, delete, and persistent chat history.

The anonymous V1 `POST /api/chat` route and its response shape remain available. V1's in-memory Flutter conversation history is not migrated into Supabase.

## Trust model and server key

Flutter uses the official Supabase client with the project URL and publishable key. RLS applies to those direct client requests. Clients may create/read/update/delete only their own conversations and read or insert their own **user** messages. They have no direct `DELETE` privilege on messages; deleting an owned conversation cascades to its messages. Client updates are denied for messages, and client inserts with `role=assistant` are denied. A narrowly scoped `SECURITY DEFINER` insert trigger advances only the parent conversation's `updated_at`; direct client timestamp updates are not granted.

FastAPI independently verifies the Supabase access-token signature and claims, takes the owner ID only from the verified token subject, and checks conversation ownership before using a backend-only `SUPABASE_SERVICE_ROLE_KEY` to save assistant output. The service-role key bypasses RLS, so the backend adapter is a trusted security boundary: keep the key only in the backend environment, restrict server access, rotate it if exposed, and never include it in Flutter, logs, command history, screenshots, or client responses. The RLS smoke test below deliberately uses non-privileged user JWTs and does not treat service-role requests as proof of RLS.

## 1. Create a non-production test project

In Supabase, create or select a project dedicated to development/testing. In **Authentication → Providers**, enable email/password. Create two confirmed test accounts (A and B) using the dashboard or the configured email flow. Do not use real user accounts for the RLS deletion test; it creates and permanently deletes its own test conversation.

In **Authentication → URL Configuration**, allow the exact local Web callback/origin and the Android redirect configured by the app. The Flutter Android callback is `com.emsi.chatbot://login-callback/`. Configure project signing to an asymmetric JWKS-supported algorithm (ES256 or RS256) for FastAPI JWT verification. Use HTTPS for non-local deployments.

## 2. Review and apply the SQL migration

Open `supabase/migrations/20261118_mission20_conversations.sql`, review it, then paste and run it once in **Supabase Dashboard → SQL Editor** for the intended non-production project. It creates/updates these application objects only:

- `public.conversations`
- `public.messages`
- `public.conversation_summaries`
- `public.get_my_dashboard_stats()`
- timestamp trigger and RLS policies

It does not alter `auth.users`, Qdrant, embeddings, brochure records, or existing conversation data. Do not run it against production before backup and review. The migration has **not** been run as part of this code task.

The migration is transactional and contains no `DROP TABLE`, `TRUNCATE`, or row deletion. Re-running it against the same Mission 20 schema retains conversation data and re-establishes the intended triggers, policies, and grants. It removes all existing RLS policies on these two dedicated tables before recreating owner policies, because permissive policies combine with OR. Do not apply it to tables already used by another feature without reviewing those policies. A preflight checks expected columns/types, named constraints, and the identity sequence; a mismatch aborts the transaction for manual review. `CREATE IF NOT EXISTS` alone would not reconcile schema drift.

Verify objects and policies in the SQL Editor:

```sql
select table_name
from information_schema.tables
where table_schema = 'public'
  and table_name in ('conversations', 'messages', 'conversation_summaries')
order by table_name;

select schemaname, tablename, policyname, cmd, roles
from pg_policies
where schemaname = 'public'
  and tablename in ('conversations', 'messages')
order by tablename, cmd, policyname;

select relname, relrowsecurity
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and relname in ('conversations', 'messages');
```

Expected: RLS is enabled on both tables; conversation policies scope by `auth.uid()`; message insert policy accepts only `role='user'`; message client updates and deletes are denied. The dashboard view uses PostgreSQL 15+ `security_invoker` behavior. Do not use a service-role SQL/API request to validate these policies.

## 3. Configure environment

Copy `.env.example` to `.env`. Set these values locally:

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=<publishable-client-key>
SUPABASE_SERVICE_ROLE_KEY=<server-only-service-role-key>
```

Find the URL and publishable key in the project's API settings. Copy the service-role/secret key only into the protected backend `.env` or deployment secret store. Never place it in Flutter Dart defines. `.env` is git-ignored; keep `.env.example` placeholders fictitious. FastAPI loads `.env` from the repository root.

## 4. Run locally on Windows

From repository root, start the existing Qdrant service and then FastAPI:

```powershell
docker compose up -d qdrant
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\backend\start_backend.ps1
```

Do not start the backend until the existing model and Qdrant requirements for the full RAG demo are ready. The persistent route itself does not change model loading, but an actual chat request calls the existing RAG pipeline.

In a second PowerShell window:

```powershell
Set-Location .\mobile
flutter pub get
flutter run -d chrome --web-port 5000 `
  --dart-define=API_BASE_URL=http://127.0.0.1:8000 `
  --dart-define=SUPABASE_URL=https://<project-ref>.supabase.co `
  --dart-define=SUPABASE_PUBLISHABLE_KEY=<publishable-client-key>
```

For a standard Android emulator, use `--dart-define=API_BASE_URL=http://10.0.2.2:8000`; supply the same Supabase URL and publishable key. These are public client settings; no service-role key belongs in the command.

Sign in, create a conversation, send a question, and confirm that the conversation and its two messages appear in the sidebar/dashboard. Sign out, sign back in, reopen it, and check the saved messages and source/page references. Repeat with account B and verify that A's conversation never appears. A full chat persistence demonstration also invokes RAG/Groq and should be scheduled when those services are available.

## 5. Validate RLS with two users

After applying the migration, run the included script from repository root in Windows PowerShell 5.1:

```powershell
.\supabase\scripts\test_rls.ps1
```

Enter the project URL, publishable key, and credentials for the two confirmed **test** accounts when prompted. The script logs only pass/fail results and HTTP status codes, not access tokens or passwords. It creates a temporary conversation as A and deletes it at the end. It checks that message insertion advances `updated_at`, the client cannot directly edit timestamps, B cannot read, modify, delete, or insert messages into A's records, and A cannot directly delete a message or forge an assistant message through the client. It also checks that anonymous reads fail and A's conversation deletion cascades to messages. Use only a disposable test project/account pair.

This live script has not been run from this workspace. Mocked backend tests do not prove the real Supabase policies are correctly installed.

## 6. Automated tests

From the repository root:

```powershell
& .\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
Set-Location .\mobile
flutter analyze
flutter test
```

Backend tests mock JWKS, PostgREST and the RAG function; they make no Supabase or Groq calls and load no BGE-M3/CLIP model. Flutter tests use a fake conversation repository and mock HTTP. These tests validate code paths, not live auth, email delivery, RLS, deployment CORS, or database backup/restore.

## Troubleshooting

- **401 on authenticated chat:** sign in again; check that FastAPI's `SUPABASE_URL` matches the Flutter project and the bearer token has not expired.
- **503 persistent storage not configured:** set the backend-only `SUPABASE_SERVICE_ROLE_KEY` and restart FastAPI. Never add it to Flutter.
- **Database relation/policy error:** confirm the migration was applied to the same project as the URL and inspect the RLS policies above.
- **Dashboard shows an error:** inspect Supabase table/view grants and RLS as a normal authenticated user, then check network connectivity. Do not temporarily disable RLS.
- **Email confirmation/recovery does not return to the app:** check the exact Supabase allowed redirect URLs and provider email settings.
- **Chat saves the question but reports a retryable error:** retry using the UI's retry action, which reuses the same request ID. The server deduplicates messages; if no assistant result exists, RAG may run again.
- **CORS in a deployed Web app:** current FastAPI CORS is permissive for local V1 compatibility and is not production hardened. Do not expose the server publicly until origins and deployment security are reviewed.

