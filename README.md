# Image-to-IMDB

Automates retail product data entry. Upload product images — the AI extracts
all 13 Item Master Database (IMDB) attributes, saves them to a database, and
lets you review, edit, and export a submission-ready CSV/XLSX.

## Architecture

```
Image-Analysis-Frontend/     React 19 + TypeScript + Vite + Tailwind CSS v4
Image-Analysis/backend/      FastAPI + SQLAlchemy + Gemini Flash + SQLite
```

The frontend communicates with the backend over a single REST boundary
(`/api/v1`). With `VITE_API_BASE_URL` set the app is fully live; without it,
Gemini Flash can be called directly from the browser via `VITE_GEMINI_API_KEY`.

## Quick start

### Backend

```bash
cd Image-Analysis/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# edit .env — set GEMINI_API_KEY and JWT_SECRET at minimum
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd Image-Analysis-Frontend
# requires Node 20+ (use nvm: nvm use 20)
npm install
# .env already contains VITE_API_BASE_URL=http://localhost:8000
npm run dev       # http://localhost:5173
```

## How it works

1. **Register / Sign in** — every session is authenticated with JWT.
2. **Upload** — drag and drop product images (up to 20 per batch). Images are
   grouped into products by filename prefix (3–4 angles per product).
3. **AI extraction** — each image is sent to Gemini Flash with a structured
   prompt; the model returns all 13 IMDB fields plus per-field confidence scores.
   A dedicated barcode decoder runs first; Open Food Facts enriches validated
   barcodes with authoritative data.
4. **Duplicate detection** — immediately after extraction the backend asks
   Gemini to compare the new records against everything already in the database.
   If a match is found, the Review step shows a plain-language message:
   _"[Product] was already entered on [date] with ID #[id]. Verify records to
   confirm, or continue with this extraction."_
5. **Review & edit** — low-confidence fields are highlighted. Every edit is
   saved back to the database in real time via `PATCH /api/v1/records/{id}`.
6. **Records browser** — the Records tab shows all records across all users,
   filterable by brand, category, date range, and review status. Records can be
   edited or deleted inline. A "Find Duplicates" scan can be run at any time.
7. **Export** — download the full record set (or a session subset) as CSV or
   XLSX directly from the backend.

## Images are stored in S3

Uploaded images are saved to the `gdssmaverickdata` S3 bucket at
`uploads/{user_id}/{session_id}/{filename}`. Set `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` in `backend/.env` to activate. Extraction works
normally without them — `s3_key` on the record will be `null`.

## Services

| Directory | README |
|---|---|
| `Image-Analysis/backend/` | [Backend README](backend/README.md) |
| `Image-Analysis-Frontend/` | [Frontend README](../Image-Analysis-Frontend/README.md) |
