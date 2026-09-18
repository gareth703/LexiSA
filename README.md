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
