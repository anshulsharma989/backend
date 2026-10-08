# 🛠️ Setup Guide

Complete steps to install, configure, run, and verify the Educator app on a local machine. Written for macOS (your current setup); Linux notes are included where commands differ.

---

## 1. Prerequisites

| Tool | Why | Install (macOS) |
|---|---|---|
| **Docker Desktop** | Runs PostgreSQL (+ pgvector), and optionally everything else | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| **Python 3.12+** | Backend runtime | `brew install python@3.12` (or use the system Python if ≥ 3.12) |
| **Ollama** | Local LLM | `brew install ollama` |
| **Tesseract** *(optional)* | OCR for scanned PDFs | `brew install tesseract tesseract-lang` |

Check versions:

```bash
docker --version        # any recent version
python3 --version       # must be 3.12+
ollama --version
tesseract --version     # optional; only for scanned books
```

**Hardware:** ~16 GB RAM recommended. The LLM (`qwen2.5:7b`) uses ~6 GB; the embedding model (`bge-m3`) runs on CPU. Disk: ~12 GB for models + Docker images.

> **Linux:** install Docker Engine + Compose plugin, `python3.12`, Ollama via `curl -fsSL https://ollama.com/install.sh | sh`, and `sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin`.

---

## 2. One-Time Setup

### 2.1 Open the project

Everything (code, config, Docker setup, docs) lives in the `backend/` directory — run all commands from here:

```bash
cd ~/Projects/ai/personal/educator/backend
```

### 2.2 Create your environment file

```bash
cp .env.example .env
```

The defaults work out of the box for local development. Open `.env` if you want to change the LLM model, chunk sizes, etc. (every setting is documented inline).

### 2.3 Start PostgreSQL (with pgvector)

```bash
docker compose up -d db
```

Verify it's healthy:

```bash
docker compose ps        # db should show "healthy"
```

Tables, the pgvector extension, and the vector index are owned by Alembic migrations (`migrations/versions/`) and applied automatically the first time the app or CLI runs — no manual SQL needed. You can also apply them explicitly: `alembic upgrade head`.

### 2.4 Start Ollama and pull the LLM

Run Ollama **natively** on macOS (Docker can't use Apple's GPU, so native is much faster):

```bash
ollama serve &                 # or just launch the Ollama app
ollama pull qwen2.5:7b         # ~4.7 GB download, one time
```

Low-RAM machine? Use a smaller model instead:

```bash
ollama pull qwen2.5:3b
# then in .env: OLLAMA_MODEL=qwen2.5:3b
```

### 2.5 Set up the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs FastAPI, SQLAlchemy, pgvector, Alembic, PyMuPDF, sentence-transformers (pulls in PyTorch — the largest install), and the rest. Takes a few minutes the first time.

> **Note:** the first time you ingest a document, the `bge-m3` embedding model (~2 GB) downloads automatically from Hugging Face and is cached for all future runs.

### 2.6 Apply migrations and seed initial data

```bash
python -m app.cli seed
```

This applies any pending Alembic migrations (schema structure) and then seeds `Grade 6`–`Grade 12` with a default subject list (`Mathematics`, `Science`, `English`, `Hindi`, `Social Science`) — safe to re-run any time, existing rows are left alone. It does **not** create an admin or student account unless `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD` and/or `SEED_STUDENT_EMAIL`/`SEED_STUDENT_PASSWORD` are set in `.env` (see §6) — for a real admin account, use the interactive `python -m app.cli create-admin` instead (§3.4); real students should sign up and get approved normally.

---

## 3. Run It

Always work from `backend/` with the venv active:

```bash
cd ~/Projects/ai/personal/educator/backend && source .venv/bin/activate
```

### 3.1 Ingest a book (CLI)

```bash
python -m app.cli ingest ~/books/physics9.pdf \
    --title "Physics Part 1" \
    --subject Physics \
    --grade 9 \
    --language en        # en | hi | mixed
```

Supported formats: **pdf** (digital and scanned), **csv**, **docx**, **txt**, **md**.

List what's ingested:

```bash
python -m app.cli docs
```

### 3.2 Ask a question (CLI)

```bash
python -m app.cli ask "What is Newton's first law?" --grade 9
```

You'll get an answer grounded in the book plus a sources table (book, subject, page). Hindi questions work the same way — the answer comes back in Hindi.

### 3.3 Interactive chat & quiz (Phase 2)

```bash
# Chat with memory — follow-ups like "give me an example of it" work.
# Answers stream token by token. Type 'exit' to quit.
python -m app.cli chat --grade 9

# Generate a quiz from the ingested books
python -m app.cli quiz --grade 9 --num-questions 5
```

### 3.4 Run the API server

```bash
uvicorn app.main:app --reload
```

- Interactive API docs (Swagger UI): **http://localhost:8000/docs**
- Health check: `curl http://localhost:8000/health`

Bootstrap an admin, then log in — every route below except `/health`, `/grades`, `/auth/signup`, and `/auth/login` requires the resulting Bearer token:

```bash
python -m app.cli create-admin   # prompts for email/password/full name

TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "admin@example.com", "password": "..."}' | jq -r .access_token)

# Create a grade/subject (or use the ones `ingest` auto-created from the CLI)
curl -s -X POST http://localhost:8000/admin/grades -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d '{"name": "Grade 9"}'
curl -s http://localhost:8000/grades   # find the grade_id

# Upload (ingestion runs in the background)
curl -F file=@physics9.pdf -F title="Physics Part 1" -F grade_id=1 -F subject_id=1 \
     -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/admin/documents

# Poll status until "ready"  (queued → processing → ready | failed)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/documents/1

# Ask (grade_id here is honored because the caller is an admin; a logged-in
# student's grade is always taken from their own account instead)
curl -X POST http://localhost:8000/ask \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"question": "What is Newton'\''s first law?", "grade_id": 1}'

# Chat with memory (reuse the returned conversation_id for follow-ups)
curl -X POST http://localhost:8000/chat/ask \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"question": "What is inertia?", "grade_id": 1}'

# Streaming chat (SSE events: start → token… → done)
curl -N -X POST http://localhost:8000/chat/ask/stream \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"question": "What is inertia?", "grade_id": 1}'

# Rate an answer (message_id from the chat response)
curl -X POST http://localhost:8000/chat/messages/2/feedback \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"rating": 1}'

# Quiz + analytics
curl -X POST http://localhost:8000/quiz -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d '{"grade_id": 1, "num_questions": 5}'
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/analytics
```

A student signs up via `POST /auth/signup` (`{email, password, full_name, grade_id}`), lands in `pending` status, and can't log in until you approve them: `GET /admin/users/pending` then `POST /admin/users/{id}/approve` (both admin-only, same Bearer token as above).

### 3.5 Run the web app (React frontend)

Requires Node.js 18+ (`node --version`). In a second terminal:

```bash
cd ~/Projects/ai/personal/educator/frontend
npm install        # first time only
npm run dev        # → http://localhost:5173
```

Open **http://localhost:5173**. You'll land on a login/signup screen first:

- **Sign up** as a student (pick your grade) — the account is created as `pending` and can't log in yet.
- **Log in** as the admin you bootstrapped with `create-admin`, open the **Admin** tab's "Pending users" panel, and approve the new student.
- Log back in as the approved student to see the **Chat** and **Quiz** tabs (no Admin tab — that's role-gated).

Tabs, once logged in:
- **Chat** — streaming answers with memory, source chips, 👍/👎 feedback. Grade is fixed to your account (shown read-only); pick an optional subject filter before the first message (filters are fixed per conversation; use "+ New chat" to change them).
- **Quiz** — generate multiple-choice quizzes from the ingested books and answer them interactively.
- **Admin** (admin accounts only) — upload books (grade/subject pickers, live ingestion status), manage the grades/subjects catalog, approve/reject pending signups, and see analytics.

The dev server proxies `/api/*` to the backend on port 8000, so both must be running. Note: `frontend/.npmrc` pins the public npm registry so a corporate registry in `~/.npmrc` doesn't interfere.

---

## 4. Alternative: Everything in Docker

If you prefer a single command (slower LLM answers on macOS — no GPU in Docker):

```bash
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:7b
```

- API: http://localhost:8000/docs
- Logs: `docker compose logs -f api`
- Stop: `docker compose down` (data survives in Docker volumes; `down -v` wipes it)

To use natively-running Ollama with the dockerized API, set in `docker-compose.yml`'s api service: `OLLAMA_BASE_URL: http://host.docker.internal:11434`.

---

## 5. Daily Start / Stop

Once set up, a normal working session is just:

```bash
# Start (from backend/)
docker compose up -d db
ollama serve &                          # if not already running
source .venv/bin/activate
uvicorn app.main:app --reload

# Stop
# Ctrl+C the server, then:
docker compose stop db
```

---

## 6. Configuration Reference (.env)

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | local docker Postgres | SQLAlchemy URL |
| `EMBEDDING_PROVIDER` | `sentence_transformers` | or `ollama` |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | multilingual EN + HI |
| `EMBEDDING_DIM` | `1024` | **must match the model**; re-ingest all docs after changing model |
| `LLM_PROVIDER` | `ollama` | or `claude` |
| `OLLAMA_MODEL` | `qwen2.5:7b` | `qwen2.5:3b` for low RAM |
| `ANTHROPIC_API_KEY` | — | only for `LLM_PROVIDER=claude` |
| `CLAUDE_MODEL` | `claude-opus-5` | |
| `CHUNK_SIZE_CHARS` / `CHUNK_OVERLAP_CHARS` | `3200` / `400` | tune if answers miss context |
| `TOP_K` | `6` | chunks retrieved per question |
| `UPLOAD_DIR` | `./data/uploads` | where uploaded files are stored |
| `JWT_SECRET_KEY` | — | **required**; generate with `openssl rand -hex 32`. Rotating it invalidates all existing tokens |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_EXPIRE_MINUTES` | `10080` (7 days) | how long a login session lasts |
| `CORS_ORIGINS` | `http://localhost:5173` | comma-separated list; add any other frontend origin you serve from |
| `HF_HUB_OFFLINE` | `false` | set `true` after the embedding model is cached once, to skip Hugging Face Hub freshness checks on every startup |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` / `SEED_ADMIN_NAME` | — | optional; only read by `python -m app.cli seed`, to script-create an admin in a fresh environment. Leave unset and use `create-admin` interactively otherwise |
| `SEED_STUDENT_EMAIL` / `SEED_STUDENT_PASSWORD` / `SEED_STUDENT_NAME` / `SEED_STUDENT_GRADE` | — | optional; only read by `python -m app.cli seed`, to script-create an already-*approved* student (bypasses signup+approval) for local testing |

### Switching to Claude

```bash
# in .env
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
```

Restart the server. Nothing else changes — ingestion, retrieval, and citations all stay the same.

---

## 7. Verify the Setup

Run through this checklist after first-time setup:

```bash
# 1. Postgres is up
docker compose ps                                   # db: healthy

# 2. Ollama responds
curl -s http://localhost:11434/api/tags | head -c 200   # lists pulled models

# 3. API is up
curl http://localhost:8000/health                   # {"status":"ok"}

# 4. Migrations applied + grades/subjects seeded
python -m app.cli seed                              # "Grades created: 7, subjects created: 35" on first run
curl -s http://localhost:8000/grades                # should list Grade 6..Grade 12

# 5. End-to-end: ingest any small PDF, then ask something from it
python -m app.cli ingest sample.pdf --title Sample --grade "Grade 9"
python -m app.cli ask "…a question the PDF answers…" --grade "Grade 9"

# 6. Auth: bootstrap an admin and confirm login works
python -m app.cli create-admin
curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" \
     -d '{"email": "...", "password": "..."}'   # should return an access_token
```

If the answer cites the right page and login returns a token, the whole pipeline works.

---

## 8. Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `connection refused` to Postgres | `docker compose up -d db`; check `docker compose ps` shows healthy. Port 5432 already in use? Stop the other Postgres or change the port mapping in `docker-compose.yml` **and** `DATABASE_URL`. |
| `connection refused` to `localhost:11434` | Ollama isn't running — `ollama serve` (or open the Ollama app). |
| First `ingest` hangs for a while | It's downloading the `bge-m3` embedding model (~2 GB) from Hugging Face. One time only. |
| First `ask` after startup is slow | Ollama loads the model into RAM on first use (~30–60 s); subsequent questions are much faster. |
| Answers are slow (>60 s) on CPU | Use `qwen2.5:3b`, or run Ollama natively instead of in Docker (macOS). |
| Scanned PDF ingests but finds no text | Install Tesseract + language packs (`brew install tesseract tesseract-lang`), then delete and re-ingest the document. |
| `Unsupported file type` on upload | Only pdf/csv/docx/txt/md for now. Convert, or add a parser (see README §7 extensibility points). |
| Answer says "couldn't find this in your books" | Check the document status is `ready` (`python -m app.cli docs`) and the grade matches the grade the document was ingested with. |
| Changed `EMBEDDING_MODEL` and search broke | Query and document vectors must come from the same model. Update `EMBEDDING_DIM`, drop the DB volume (`docker compose down -v && docker compose up -d db`), let migrations re-apply on next startup (or run `alembic upgrade head`), re-seed (`python -m app.cli seed`), and re-ingest. |
| `alembic.util.exc.CommandError` / migration fails to apply | Check `docker compose ps` shows `db: healthy` first — migrations need a live DB connection. If a migration was half-applied, inspect `alembic_version` in Postgres and the specific error; as a last resort in local dev, reset the volume (`docker compose down -v && docker compose up -d db`) and let it reapply from scratch. |
| Document status is `failed` | `python -m app.cli docs` or `GET /admin/documents/{id}` — the `error` field has the reason. |
| `401 Not authenticated` on any API call | Missing/expired `Authorization: Bearer <token>` header — log in again via `POST /auth/login`. |
| `403 Your account is awaiting admin approval` | Expected for a freshly signed-up student — have an admin run `POST /admin/users/{id}/approve`. |
| Can't log in / no admin exists yet | Run `python -m app.cli create-admin` to bootstrap the first account — signup alone never creates an approved user. |
| Switched a signed-up student's email/password and can't log in | There's no password-reset flow yet; have an admin delete and re-signup the account, or update `password_hash` directly for now. |

---

## 9. Where Things Live

| Path (inside `backend/`) | What |
|---|---|
| `app/` | All application code (see README §7 for the map) |
| `migrations/versions/` | Alembic migrations — the source of truth for table structure |
| `alembic.ini` | Alembic config; DB URL is overridden at runtime from `.env`, not hardcoded here |
| `app/seed.py` | Idempotent seed data (grades/subjects/dev admin) — run via `python -m app.cli seed` |
| `.env` | Your local configuration (created from `.env.example`) |
| `.venv/` | Python virtual environment |
| `data/uploads/` | Files uploaded via the API (venv runs) |
| Docker volumes `pgdata`, `ollama`, `appdata` | Database, LLM models, uploads/HF cache (Docker runs) |
| `~/.cache/huggingface/` | Embedding model cache (venv runs) |
