# LexiSA

LexiSA is a full-stack contract intelligence MVP for South African SMMEs. It ships with a demo Master Services Agreement so the workbench is useful before a Gemini key is configured.

## Run the backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add GEMINI_API_KEY to .env when available
# Add your Laws.Africa sandbox token as LAWS_AFRICA_API_TOKEN
uvicorn main:app --reload
```

The API runs at `http://localhost:8000`.

## Run the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Set `NEXT_PUBLIC_API_URL` if the API is not running on the default port.

## Product notes

- Flash is used for extraction, categorisation and Q&A. The backend leaves a clear extension point for Pro redline drafting while keeping MVP redlines deterministic and cost-conscious.
- Demo mode uses local SA benchmark rules for CPA section 56, POPIA section 21, unlimited indemnity/background IP, and overseas dispute resolution.
- Uploads accept PDF and DOCX. Gemini responses are requested as JSON when `GEMINI_API_KEY` is configured.
- Laws.Africa Knowledge Base retrieval is enabled with `LAWS_AFRICA_API_TOKEN` and defaults to `legislation-za`. Create a sandbox token at `https://platform.laws.africa/api-keys/`. The token stays server-side in `backend/.env`.
- The AI assistant uses Laws.Africa results as authoritative context and renders source links for inspection. Without a token, it continues using the local demo rules and Gemini fallback.
- SQLite initializes automatically as `backend/lexisa.db`. It stores the seeded SA SMME risk rules and analysis JSON for uploaded contracts. Run `python database.py` from `backend` to initialize it manually.
- Vector rule search is available through `backend/ingest_rules.py` and `backend/test_vector_search.py`. Install `sqlite-vec`, run `python ingest_rules.py` to embed the analysis rules with Gemini (the current default is `models/gemini-embedding-001`, configurable with `GEMINI_EMBEDDING_MODEL`), then run `python test_vector_search.py` to verify semantic matching. Embeddings are requested at 768 dimensions for the local `vec0` table.
- Test the Laws.Africa rules-engine query with `python test_laws_africa_rules.py`. Manage sandbox API keys in the [Laws.Africa Platform](https://platform.laws.africa/).
- Phase 2 checkpoints run from `backend`: `python tests/test_parser.py`, `python tests/test_segmenter.py`, `python tests/test_matcher.py`, and `python tests/test_analyzer.py`. Uploaded contracts now run through `pdfplumber`/`python-docx`, clause segmentation, sqlite-vec matching, and structured Gemini analysis with a local fallback.
- The rules engine is defined in `backend/data/smme_rules_matrix.json`. It contains creation triggers and contract analysis triggers, and the API and SQLite seed load it automatically on startup.
- Evaluate creation rules with `POST /api/v1/evaluate-creation-rules` using fields such as `processes_personal_data`, `counterparty_type`, `contract_value_zar`, and `governing_jurisdiction`.

## Phase 3: conversational RAG, redlining, and export

- Every upload/demo fetch now persists the full contract text and clauses (not just the analysis) to SQLite and returns a `contract_id`, which the chat, redline, and export endpoints all key off.
- Stateful RAG chat: `POST /api/v1/contracts/{contract_id}/chat` grounds answers in the stored contract, a static SA legal primer (CPA, POPIA, BCEA, AFSA), and persisted multi-turn history (`chat_messages` table). It enforces a strict latency budget (Gemini capped at 1s, Laws.Africa at 0.2s via `request_options`/socket timeouts) with an instant, correctly-cited deterministic fallback if either is slow — real Gemini calls that take 2-17s cannot otherwise meet a sub-2-second UX.
- `GEMINI_CHAT_MODEL` defaults to `gemini-3.1-flash-lite`. The plan's specified `gemini-1.5-flash` and this repo's prior `gemini-2.5-flash` default are both retired from the live API; override the env var if your account has a different available model.
- Redlining: `POST /api/v1/redlines/accept` and `POST /api/v1/redlines/custom` write to `contract_redlines` and are idempotent — original clause text is never destructively overwritten, so `GET /api/v1/contracts/{contract_id}` always overlays the latest accepted wording onto the pristine clauses. `GET /api/v1/contracts/{contract_id}/redlines` lists raw redline state.
- PDF export: `GET /api/v1/contracts/{contract_id}/export-pdf` (via `backend/services/pdf_exporter.py`, `reportlab`) writes a redlined PDF to `backend/exports/` with an Executive SMME Compliance Summary page, a green sidebar + bold text on accepted clauses, and an attorney sign-off block.
- Cost guardrails: `backend/middleware/cost_controller.py` tracks Gemini token usage (`token_usage_log` table, populated from `response.usage_metadata` in `chat_rag.py`) and returns HTTP 429 on `/chat` and `/upload-contract` once `DAILY_TOKEN_LIMIT` (default 200,000) is hit for the day. Explicit prompt caching (`CachedContent.create`) is only attempted once a system prompt exceeds ~32k estimated tokens, matching Gemini's real minimum cacheable size; cache hits/misses and per-turn token counts (including `cached_content_token_count`) are logged via the `lexisa.chat_rag` logger.
- Frontend: `frontend/lib/api.ts` is the typed API client (`uploadAndAnalyzeContract`, `sendChatMessage`, `acceptRedline`, `submitCustomRedline`, `downloadRedlinedPDF`, `fetchContract`). The workbench UI in `frontend/app/page.tsx` accepts redlines against the live backend (one-way — there is no unaccept endpoint), updates clause text in the left panel in real time, shows a typing indicator and dynamic follow-up suggestions in chat, and downloads the redlined PDF via a Blob.
- Phase 3 checkpoints run from `backend`: `python tests/test_chat.py`, `python tests/test_redliner.py`, `python tests/test_exporter.py`, and `python tests/test_cost_controller.py`.
