# Image-to-IMDB Backend

FastAPI backend that auto-fills the 10 IMDB product-master attributes from a
product image using a **hybrid pipeline**: dedicated barcode decoder +
**Gemini Flash** (structured JSON output) + Open Food Facts enrichment +
deterministic normalization. Records are scoped per authenticated user.

## The 10 IMDB attributes
`barcode, category_type, segment_type, manufacturer, brand, product_name,
weight_value + weight_unit, packaging_type, country_of_origin, promo_message`

Each field carries `confidence`, `source` (`barcode_decoder` / `vlm` /
`external_lookup` / `human`), and a `needs_review` flag.

## Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then set GEMINI_API_KEY and JWT_SECRET
uvicorn app.main:app --reload
```

Interactive API docs: http://localhost:8000/docs

> **Note:** `pyzbar` needs the native ZBar library. On Windows it ships with the
> wheel; on Linux install `libzbar0`. If ZBar is missing the app still runs —
> barcode decoding is skipped gracefully and the VLM fills the rest.

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/register` | Create a user |
| POST | `/auth/login` | Get access + refresh tokens |
| POST | `/auth/refresh` | Rotate tokens |
| GET | `/auth/me` | Current user |
| POST | `/extract` | Upload image(s) → IMDB records |
| GET | `/records` | List records (filter brand/category/needs_review/session) |
| PATCH | `/records/{id}` | Save human edits |
| DELETE | `/records/{id}` | Delete a record |
| POST | `/records/dedup` | Merge suggestions (per user) |
| POST | `/records/merge` | Apply a merge |
| GET | `/export?format=csv\|xlsx` | Download product-master file |

All routes except `/auth/*` and `/health` require `Authorization: Bearer <token>`.

## Architecture

```
preprocess → barcode decode → Gemini Flash → enrichment
           → normalize → confidence/needs_review → persist (per user)
```

See `../ROADMAP.md` for the full plan and judging-criteria mapping.

## Layout
```
app/
  main.py            app factory, CORS, router wiring
  config.py          env settings
  database.py        engine, session, init_db
  core/              security (JWT/bcrypt), deps (get_current_user)
  models/            User, ExtractionSession, ItemRecord
  schemas/           Pydantic: auth + IMDB/pipeline
  services/          preprocess, barcode, vlm, enrichment, pipeline, normalize, dedup, export
  routers/           auth, extract, records, export
```
