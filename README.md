# EMSI-ChatBot

EMSI-ChatBot is a document-grounded assistant for the EMSI brochure. It combines a Flutter Web/Android client with a FastAPI backend, Qdrant retrieval, BGE-M3 text embeddings, optional CLIP image search, and Groq Cloud generation.

The application is designed to answer from retrieved brochure passages, return document/page references, and keep short conversational context on the client. It does not automatically create or re-index Qdrant collections when the backend starts.

## Features

- Text retrieval from the `emsi_text` Qdrant collection with BGE-M3 and a hybrid semantic/lexical ranking policy.
- Optional Groq Cloud generation from a bounded set of retrieved brochure passages.
- Server-validated PDF citations based on Qdrant `source` and `page` metadata.
- Optional image retrieval from `emsi_images` with CLIP; image search is off by default.
- Memory-conscious CPU model workers, RAM checks, serialized heavy work, and a safe fallback path.
- Client-managed conversation history, limited to five user/assistant exchanges and reset by “New conversation”.
- Flutter Material 3 interface for Web and Android.

## Technology

| Area | Technology |
|---|---|
| Client | Flutter, Dart, `http`, `url_launcher` |
| API | FastAPI, Uvicorn, Pydantic |
| Text retrieval | BGE-M3, Sentence Transformers, Qdrant |
| Image retrieval | CLIP through Transformers, Qdrant |
| Answer generation | Groq Cloud over HTTPS (`GROQ_MODEL` configuration) |
| Local services | Docker Compose, Qdrant |

## Architecture

```text
Flutter Web / Android
        | POST /api/chat (question, options, bounded history)
        v
FastAPI
  |-- BGE-M3 (CPU) -> retrieval/ranking -> Qdrant: emsi_text
  |       `-> selected passages + question/context -> Groq Cloud (optional)
  `-- if include_images=true: release/check text-model memory
          -> CLIP (CPU) -> Qdrant: emsi_images -> local /images assets
```

Docker Compose starts Qdrant only. FastAPI and Flutter run as separate processes. Qdrant uses the named Docker volume `qdrant_storage`.

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

Flutter keeps up to ten messages (five exchanges) for the active conversation and sends them with each request. “New conversation” clears this client-side history. FastAPI validates and bounds the history but does not maintain a shared per-user conversation store. Requests with history bypass the simple in-process answer cache so a context-free cached answer is not reused for a follow-up.

## Citations and grounding safeguards

- PDF page and source values come from Qdrant metadata, not generated passage indices.
- Unverified citation markers are removed or not returned as sources.
- Campus-specific course claims require explicit documentary evidence linking the campus and offering; separate mentions are not sufficient.
- The assistant should state when the retrieved brochure passages do not answer the question.
- These checks reduce citation and grounding errors but cannot guarantee that every generated sentence is correct. Check cited PDF pages during a formal demonstration, especially where the source PDF has complex columns or layout.

## Windows installation

Prerequisites: Windows PowerShell, Python 3.11, Docker Desktop with Compose v2, Flutter SDK, and (for Android) Android Studio or a connected device. The complete Windows guide is [docs/INSTALLATION_WINDOWS.md](docs/INSTALLATION_WINDOWS.md).

The repository intentionally excludes the brochure PDF and generated `data/processed` assets. Before running the full RAG locally, place an authorized copy of `Brochure-EMSI.pdf` at `data/documents/Brochure-EMSI.pdf`, provide the prepared local assets as described in [data/README.md](data/README.md), and ensure the expected Qdrant collections are provisioned. No indexing is performed by the commands below.

### Configure Groq

From the project root:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `GROQ_API_KEY` and `GROQ_MODEL` in the local `.env` file. The model name is configurable; choose one available to your Groq account. Never put the key in Flutter, source control, screenshots, or shared command history.

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

### Start Flutter

```powershell
Set-Location .\mobile
flutter pub get
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

For a standard Android emulator, use `--dart-define=API_BASE_URL=http://10.0.2.2:8000`. For a physical device, use the PC's private-LAN address and allow access only on a trusted private network. The backend launcher binds to `0.0.0.0:8000` for local-device access; do not expose the API or Qdrant to the public Internet.

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

Other implemented routes include `GET /`, `GET /health`, `GET /api/cache/stats`, `GET /api/images`, and `POST /api/chat/test`. See FastAPI's `/docs` for the live schema. `/api/chat/test` checks the request/response path without running the full RAG.

## Tests

The backend tests use mocks for Groq, retrieval, citations, memory policies, and image search. They are intended to run without loading BGE-M3 or CLIP:

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m pip install pytest
..\.venv\Scripts\python.exe -m pytest tests -q
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
- The API currently has no authentication and allows cross-origin requests. Keep it on a trusted development network; it is not configured as a public production service.
- Python requirements and the Qdrant Docker image tag are not pinned to exact versions, so clean installs may vary over time.
- The `/health` endpoint is a process check, not an end-to-end readiness check.

## Future work

- Pin and regularly review dependency and container versions.
- Add deployment-grade authentication, restricted CORS, and readiness checks before any shared or public deployment.
- Document a reproducible, authorized data-preparation and Qdrant-provisioning workflow.
- Capture genuine application screenshots and add them to `docs/screenshots/` after local review.

## Project documentation

- [Windows installation guide](docs/INSTALLATION_WINDOWS.md)
- [Demonstration guide](DEMO.md)
- [Corpus and local data notes](data/README.md)
- [Screenshot checklist](docs/screenshots/README.md)
