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
