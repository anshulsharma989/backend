# 📚 Educator — Ask Your Books

An AI-powered learning assistant that lets students ask questions in natural language — **in English or Hindi** — and get answers **grounded in their own course books**, not generic internet knowledge. Admins upload study material (PDF, CSV, DOCX, scanned books, etc.), the system converts it into a searchable knowledge base, and a local LLM answers student questions using only the material available **for their grade**, with citations back to the source pages.

**Confirmed decisions:**
- **Languages:** English + Hindi (questions, answers, and book content)
- **Scanned books:** supported from day one via OCR
- **Access control:** students see only content for their grade
- **Hosting:** local machine for now (enough RAM available); cloud later
- **Voice input:** planned for a future phase

---

## 1. How It Works (The Big Picture)

This is a **RAG (Retrieval-Augmented Generation)** application. Instead of fine-tuning an LLM on the books (expensive, slow, hard to update), we:

1. **Ingest** — Admin uploads a document. We extract the text, split it into small overlapping "chunks" (e.g., 500–1000 tokens each), and convert each chunk into an **embedding** (a vector of numbers that captures its meaning).
2. **Store** — Chunks + embeddings are saved in a vector database, tagged with metadata (book, subject, grade, chapter, page number).
3. **Retrieve** — When a student asks a question, we embed the question the same way and find the top-K most semantically similar chunks from the database.
4. **Generate** — We build a prompt containing the retrieved chunks as *context* plus the student's question, and send it to the LLM. The LLM is instructed to answer **only from the provided context** and cite sources.
5. **Answer** — The student gets the answer, with references like *"Physics Part 1, Chapter 3, Page 42"*, so they can verify and read more.

```
                        ┌─────────────── ADMIN FLOW ───────────────┐
                        │                                          │
  Admin ──upload──▶ [PDF/CSV/DOCX] ──▶ Text Extraction ──▶ Chunking ──▶ Embedding Model
                                                                              │
                                                                              ▼
                                                                      ┌──────────────┐
                                                                      │  Vector DB   │
                                                                      │  (pgvector)  │
                                                                      └──────┬───────┘
                        ┌─────────────── STUDENT FLOW ──────────────┐        │
                        │                                           │        │
  Student ──question──▶ API ──▶ Embed question ──▶ Similarity search ◀───────┘
                         │                              │
                         │                              ▼
                         │                     Top-K relevant chunks
                         │                              │
                         │                              ▼
                         │                  ┌────────────────────────┐
                         │                  │  LLM (Ollama locally,  │
                         ◀──── answer ──────│  Claude API later)     │
                              + citations   └────────────────────────┘
```

---

## 2. Core Features

### Phase 1 (MVP — Web)
- **Admin portal**
  - Upload documents: PDF (digital **and scanned** — OCR built in), CSV, DOCX, TXT, Markdown
  - Organize by *Grade → Subject → Book → Chapter* with metadata (language: English/Hindi)
  - View ingestion status (queued → processing → ready / failed)
  - Delete/re-upload documents (re-indexes automatically)
- **Student portal**
  - Ask questions in a chat-style interface, **in English or Hindi**
  - Sees only subjects/books assigned to their grade (**grade-based access control**)
  - Scope questions to a subject or a specific book (or search all their grade's books)
  - Answers with **source citations** (book, chapter, page)
  - Chat history per student
  - "I don't know" behavior — if the answer isn't in the books, the app says so instead of hallucinating
- **Auth & roles** — Admin, Student (each student has a grade; Teacher role reserved for later)

### Phase 2 (Enhancements)
- Streaming answers (token-by-token, like ChatGPT)
- Follow-up questions with conversation memory
- Feedback (👍/👎) on answers to measure quality
- Quiz generation from chapters ("test me on Chapter 4")
- Analytics dashboard for admins (most-asked questions, weak topics per grade)

### Phase 3 (Scale, Mobile & Voice)
- **Mobile apps (Android/iOS)** — the backend is a clean REST API from day one, so mobile is purely a new frontend. Recommended: **React Native (Expo)** to reuse web React skills and share code.
- **Voice input** — student speaks the question, app transcribes it (Whisper handles both English and Hindi very well, runs locally) and feeds it into the same Q&A pipeline. Optionally read answers aloud with TTS. Works on web (mic API) and shines on mobile.
- Swap local LLM → **Claude API** behind the same interface (one config change)
- Cloud deployment when moving beyond the local machine

---

## 3. Architecture

### 3.1 Components

```
┌───────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React)                         │
│   Admin Dashboard          │          Student Chat UI             │
└───────────────┬───────────────────────────────┬───────────────────┘
                │            REST / SSE          │
┌───────────────▼───────────────────────────────▼───────────────────┐
│                     BACKEND API (FastAPI, Python)                  │
│  Auth (JWT) │ Upload API │ Q&A API │ Admin API │ History API      │
└───────┬───────────────┬───────────────────────┬───────────────────┘
        │               │                       │
        ▼               ▼                       ▼
┌───────────────┐ ┌───────────────┐   ┌──────────────────────────┐
│ Ingestion     │ │ PostgreSQL    │   │ LLM Service (abstracted) │
│ Worker        │ │ + pgvector    │   │ • Ollama (now)           │
│ (Celery/RQ +  │ │ users, docs,  │   │ • Claude API (later)     │
│  Redis queue) │ │ chunks,       │   │                          │
│ parse→chunk→  │ │ embeddings,   │   │ Embeddings:              │
│ embed→store   │ │ chat history  │   │ • BGE / nomic-embed      │
└───────┬───────┘ └───────────────┘   └──────────────────────────┘
        │
        ▼
┌───────────────┐
│ File Storage  │
│ local disk →  │
│ S3/MinIO later│
└───────────────┘
```

### 3.2 Key design decisions

| Decision | Choice | Why |
|---|---|---|
| Ingestion runs async | Background worker + queue | Parsing/embedding a 500-page PDF takes minutes; the upload API must return immediately and report progress |
| One database | PostgreSQL + pgvector | Users, documents, chat history, AND vector search in one place — less infra to run than a separate vector DB (Pinecone/Chroma). Easy to scale later |
| LLM behind an interface | `LLMProvider` abstraction | `answer(question, context) -> str`. Ollama implementation now; Claude implementation later is a ~50-line class + API key, zero changes elsewhere |
| Grade enforced at retrieval | Vector search always filters by the student's grade | Access control lives in the backend query, not the UI — a student can never retrieve chunks from another grade's books even via the API |
| Multilingual by design | Multilingual embedding model + multilingual LLM | One index handles English and Hindi books; a Hindi question can even match an English chunk (and vice versa) because embeddings are cross-lingual |
| API-first backend | REST + JWT | The future mobile app consumes the exact same API — no backend rework |
| Citations mandatory | Chunks carry page/chapter metadata | Students must be able to verify answers in the book; also builds trust with schools |

### 3.3 The ingestion pipeline (the "convert into context" step)

This is the part you asked for help with. Per uploaded file:

1. **Parse** — extract raw text
   - PDF (digital) → `PyMuPDF` (fast, keeps page numbers); fallback to `unstructured` for messy layouts
   - PDF (scanned) → **OCR** per page. Auto-detected: if a page has no extractable text, it's rasterized and run through OCR. Use **Tesseract** with `eng+hin` language packs (or **PaddleOCR** if Hindi accuracy needs a boost — both handle Devanagari)
   - CSV → each row (or row-group) becomes a chunk with column headers as context
   - DOCX/TXT/MD → `python-docx` / plain read
2. **Clean** — strip headers/footers, fix broken hyphenation, normalize whitespace; for OCR output, fix common recognition noise
3. **Chunk** — split into ~800-token chunks with ~150-token overlap, preferring paragraph/section boundaries (`RecursiveCharacterTextSplitter` style). Overlap prevents answers from being cut in half at chunk edges.
4. **Embed** — run each chunk through a **multilingual** embedding model:
   - `BAAI/bge-m3` — excellent English + Hindi quality, cross-lingual (a Hindi question matches English content and vice versa), runs locally
5. **Store** — insert chunk text + vector + metadata `{doc_id, grade, book, subject, chapter, page, language}` into pgvector

### 3.4 The Q&A pipeline

1. Embed the student's question with the **same** embedding model
2. Vector similarity search (cosine), **always filtered by the student's grade**, plus their selected subject/book → top 5–8 chunks
3. (Optional, Phase 2) Re-rank chunks with a cross-encoder for better precision
4. Build the prompt:

   ```
   You are a helpful tutor. Answer the student's question using ONLY the
   context below. If the answer is not in the context, say "I couldn't find
   this in your books." Answer in the same language the student asked in
   (English or Hindi). Cite the book and page for each fact. Explain at a
   level appropriate for the student's grade.

   Context:
   [chunk 1 — Physics Part 1, Ch 3, p.42] ...
   [chunk 2 — Physics Part 1, Ch 3, p.43] ...

   Question: {student question}
   ```

5. Send to LLM → return answer + the source list to the UI

---

## 4. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Web frontend | **React + Vite + TypeScript**, Tailwind CSS | Chat UI + admin dashboard. shadcn/ui for components |
| Backend API | **Python 3.12 + FastAPI** | Best ecosystem for document parsing & ML; async; auto OpenAPI docs |
| Background jobs | **Celery** (or RQ) + **Redis** | Async ingestion pipeline |
| Database | **PostgreSQL 16 + pgvector** | Relational data + vector search in one DB |
| ORM / migrations | SQLAlchemy + Alembic | |
| Document parsing | PyMuPDF, unstructured, python-docx, pandas | Per-format parsers behind one interface |
| OCR (scanned books) | **Tesseract (`eng` + `hin`)**, PaddleOCR as fallback | Auto-applied to pages with no extractable text; both support Devanagari |
| Embeddings | **`BAAI/bge-m3`** (sentence-transformers) | Multilingual + cross-lingual (English ↔ Hindi), runs locally |
| Local LLM | **Ollama** running **`qwen2.5:7b`** (recommended) or `llama3.1:8b` | qwen2.5 has notably better Hindi than llama; both fit comfortably in local RAM |
| Speech-to-text (future, voice) | **Whisper** (`faster-whisper`, local) | Strong English and Hindi transcription; feeds the same Q&A pipeline |
| Future LLM | **Claude API** (model configurable, default `claude-opus-5`) | Already implemented — swap in via `LLM_PROVIDER=claude` |
| Auth | JWT (FastAPI + `python-jose`), bcrypt | |
| File storage | Local disk (MVP) → S3/MinIO | |
| Deployment | Docker Compose (MVP) | One command spins up api, worker, db, redis, ollama, web |
| Mobile (future) | React Native (Expo) | Reuses the same REST API and React knowledge |

---

## 5. Data Model (simplified)

```
users          (id, name, email, password_hash, role [admin|student],
                grade,                          -- students: drives access control
                created_at)
grades         (id, name)                       -- e.g. "Class 6" ... "Class 12"
subjects       (id, grade_id, name)
documents      (id, subject_id, title, file_path, file_type,
                language [en|hi|mixed], is_scanned,
                status [queued|processing|ready|failed], uploaded_by, created_at)
chunks         (id, document_id, content, embedding vector(1024),  -- bge-m3
                chapter, page_number, chunk_index, language)
conversations  (id, user_id, subject_id, title, created_at)
messages       (id, conversation_id, role [user|assistant], content,
                sources jsonb, created_at)
feedback       (id, message_id, rating, comment)        -- Phase 2
```

Access control rule: every retrieval query joins `chunks → documents → subjects → grades` and filters by the requesting student's grade. Admins see everything.

---

## 6. API Sketch

```
POST   /auth/register            POST   /auth/login

# Admin
POST   /admin/documents          # multipart upload (grade, subject, language) → doc_id, status=queued
GET    /admin/documents          # list with ingestion status
DELETE /admin/documents/{id}     # removes doc + its chunks
GET    /admin/documents/{id}/status
POST   /admin/grades             # manage grades & subjects
POST   /admin/subjects

# Student (all responses scoped to the student's grade automatically)
POST   /chat/ask                 # {question, subject_id?, document_id?, conversation_id?}
                                 # → {answer, sources[], conversation_id}
GET    /chat/conversations
GET    /chat/conversations/{id}/messages

GET    /subjects                 # subjects/books for the student's grade only
```

---

## 7. Project Structure

```
educator/
├── backend/                    # ← everything lives here for now
│   ├── app/
│   │   ├── main.py             # FastAPI app
│   │   ├── cli.py              # terminal: ingest / ask / docs
│   │   ├── core/config.py      # all settings via env vars
│   │   ├── db.py               # engine, sessions, pgvector init
│   │   ├── models/             # SQLAlchemy models (Document, Chunk)
│   │   ├── api/routes.py       # /ask, /admin/documents, /health
│   │   └── services/
│   │       ├── ingestion/
│   │       │   ├── parsers/    # pdf (+OCR), csv, docx, txt/md — registry-based
│   │       │   ├── chunker.py  # recursive splitter with overlap
│   │       │   └── pipeline.py # parse → chunk → embed → store
│   │       ├── embeddings/     # provider interface: sentence-transformers | ollama
│   │       ├── llm/            # provider interface: ollama | claude
│   │       ├── retrieval.py    # pgvector search (grade filter enforced here)
│   │       └── qa.py           # RAG orchestration + citations
│   ├── docker-compose.yml      # postgres + ollama + api
│   ├── .env.example            # copy to .env
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── README.md / SETUP.md
│   └── data/uploads/           # uploaded files
└── frontend/                   # React app (M3) — will sit alongside backend/
```

**Extensibility points** (each is an interface + a factory switch, no other code changes):
- **New file format** → add a parser file in `services/ingestion/parsers/` with `@register_parser("ext")`
- **New embedding model/backend** → implement `EmbeddingProvider`, set `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL`/`EMBEDDING_DIM` (re-ingest after switching — vectors must come from one model)
- **New LLM** → implement `LLMProvider`, set `LLM_PROVIDER` (Claude is already implemented: `LLM_PROVIDER=claude` + API key)
- **New language** → covered by `bge-m3` embeddings + the prompt's answer-in-question-language rule; for languages needing OCR, add the Tesseract language pack and extend `OCR_LANGUAGES`

---

## 8. Getting Started (M1 walking skeleton — implemented ✅)

> 📖 **Full setup guide:** see [SETUP.md](SETUP.md) for detailed prerequisites, configuration reference, verification checklist, and troubleshooting. Below is the short version.

### Option A: run locally with a venv (recommended on macOS)

Ollama runs natively (uses Apple Metal — much faster than in Docker); Postgres runs in Docker.

```bash
cd backend

# 1. Start Postgres (with pgvector)
docker compose up -d db

# 2. Start Ollama natively and pull the model
brew install ollama            # if not installed
ollama serve &                 # or run the Ollama app
ollama pull qwen2.5:7b

# 3. Set up Python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 4. (Optional, for scanned PDFs) OCR support
brew install tesseract tesseract-lang

# 5. Ingest a book and ask a question — the first run downloads the
#    bge-m3 embedding model (~2 GB, one time)
python -m app.cli ingest ~/books/physics9.pdf --title "Physics Part 1" --subject Physics --grade 9
python -m app.cli ask "What is Newton's first law?" --grade 9

# 6. Or run the API
uvicorn app.main:app --reload    # then open http://localhost:8000/docs
```

### Option B: everything in Docker

```bash
cd backend
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:7b
# API at http://localhost:8000/docs (interactive Swagger UI)
```

### API quick reference

```bash
# Upload a book (ingestion runs in the background; poll status)
curl -F file=@physics9.pdf -F title="Physics Part 1" -F subject=Physics -F grade=9 \
     http://localhost:8000/admin/documents
curl http://localhost:8000/admin/documents/1        # status: queued → processing → ready

# Ask a question
curl -X POST http://localhost:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "What is Newton'\''s first law?", "grade": "9"}'
```

### Switching to Claude later

```bash
# in .env
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-opus-5     # configurable
```

---

## 9. Roadmap

| Milestone | Scope | Status |
|---|---|---|
| **M1 — Walking skeleton** | Docker Compose; FastAPI + Postgres + Ollama wired; ingest a PDF → ask a question (CLI + API), get a grounded answer with citations | ✅ **Done** |
| **M2 — Ingestion** | Upload API ✅, PDF/CSV/DOCX/TXT parsers ✅, OCR for scanned PDFs ✅, status tracking ✅ — remaining: move background ingestion to Celery + Redis for durability | 🟡 Mostly done |
| **M3 — Student chat** | React chat UI, conversation history, streaming answers (English + Hindi) | ⬜ |
| **M4 — Auth & grades** | JWT auth, roles, grade-based access control tied to student accounts, admin dashboard for grades/subjects/documents | ⬜ |
| **M5 — Polish** | Feedback buttons, better chunking/re-ranking, quiz generation | ⬜ |
| **M6 — Claude option** | Claude provider ✅ (already implemented — flip `LLM_PROVIDER=claude`) | ✅ Done early |
| **M7 — Mobile & voice** | React Native app on the existing API; Whisper-based voice questions (EN + HI), optional spoken answers | ⬜ |

---

## 10. Running Locally (Hardware Notes)

Everything runs on your local machine — no cloud needed for now:

- **LLM**: `qwen2.5:7b` quantized (Q4) via Ollama uses ~6 GB RAM; with 16 GB+ total you're comfortable. Answers take a few seconds on CPU; a GPU makes it much faster.
- **Embeddings**: `bge-m3` runs on CPU; ingestion of a large book takes a few minutes (done in the background, so nothing blocks).
- **OCR**: Tesseract is CPU-only and light; scanned books just take longer to ingest than digital ones.
- **Everything via Docker Compose**: `postgres + redis + api + worker + ollama + web` in one `docker-compose up`.
- When you outgrow the local machine, the same compose stack moves to any Linux VM unchanged.

---

## 11. Decisions Log

| Question | Decision |
|---|---|
| Languages | **English + Hindi** — multilingual embeddings (`bge-m3`) and LLM (`qwen2.5`); answer in the language the student asked in |
| Scanned books | **Supported in MVP** — OCR (Tesseract `eng+hin`) auto-applied to pages without extractable text |
| Access control | **By grade** — enforced in the retrieval query on the backend, not just hidden in the UI |
| Hosting | **Local machine** for now (sufficient RAM); Docker Compose makes the later move to a VM trivial |
| Voice | **Future phase** — Whisper (local) for English/Hindi speech-to-text, reusing the same Q&A pipeline |

Still open (fine to decide later):
1. **Answer style** — strictly book-only, or may the LLM add general explanation around book content?
2. **Scale** — rough number of students/books (matters only when leaving the local machine)
```

---

*Built as a learning-first project: every phase produces something usable, and each layer (parsing, retrieval, LLM) can be swapped independently as the project grows.*
