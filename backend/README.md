# Image-to-IMDB — Backend

FastAPI service that extracts 13 IMDB product-master attributes from uploaded
images using a hybrid pipeline: barcode decoder + **Gemini Flash** structured
output + Open Food Facts enrichment + deterministic normalization.

Includes JWT authentication, per-session S3 image storage, AI-powered
duplicate detection at upload time, and CSV/XLSX export.

## Pipeline

```
preprocess → barcode decode → Gemini Flash VLM → Open Food Facts enrichment
           → normalize → build ITEM_NAME → confidence / needs_review → persist
```

Each image produces one `ItemRecord`. Multiple images uploaded together share
an `ExtractionSession`. Every field carries `confidence` (0–1), `source`
(`barcode_decoder` / `vlm` / `external_lookup` / `generated` / `human`), and
a `needs_review` flag.

## Output columns

`ITEM_NAME · BARCODE · MANUFACTURER · BRAND · WEIGHT · PACKAGING_TYPE ·
COUNTRY · VARIANT · TYPE · FRAGRANCE_FLAVOR · PROMOTION · ADDONS · TAGLINE`

- **ITEM_NAME** is generated from a fixed template (`services/normalize.py`).
- **WEIGHT** is rendered (e.g. `250G`) from split `weight_value` + `weight_unit`.
- `?include_meta=true` on the export endpoint appends `CATEGORY_TYPE` and `NEEDS_REVIEW`.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env    # then fill in GEMINI_API_KEY and JWT_SECRET
alembic upgrade head    # apply DB migrations
uvicorn app.main:app --reload
```

Interactive API docs: http://localhost:8000/docs

> **Linux:** install `libzbar0` for barcode decoding (`sudo apt install libzbar0`).
> The app runs without it — barcode decoding is skipped gracefully.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | _(required)_ | Google AI Studio key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Model name |
| `GEMINI_TIMEOUT_SECONDS` | `60` | Per-request timeout |
| `JWT_SECRET` | _(required)_ | Sign access + refresh tokens |
| `DATABASE_URL` | `sqlite:///./imdb.db` | SQLAlchemy connection string |
| `AWS_ACCESS_KEY_ID` | _(optional)_ | S3 image storage |
| `AWS_SECRET_ACCESS_KEY` | _(optional)_ | S3 image storage |
| `AWS_REGION` | `us-east-1` | S3 region |
| `S3_BUCKET` | `gdssmaverickdata` | Target bucket |
| `S3_PREFIX` | `uploads` | Key prefix inside bucket |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `MAX_UPLOAD_FILES` | `20` | Max images per request (cost guard) |
| `MAX_UPLOAD_MB` | `10` | Max image size in MB |
| `AUTO_CREATE_TABLES` | `true` | Create tables on startup (dev only) |
| `ENVIRONMENT` | `development` | Set `production` to enforce stricter checks |

## API

All routes are under `/api/v1`. `/health` is at the root for probes.
Routes except `/api/v1/auth/*` and `/health` require `Authorization: Bearer <token>`.

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Get access + refresh tokens (rate-limited) |
| POST | `/api/v1/auth/refresh` | Rotate tokens |
| GET | `/api/v1/auth/me` | Current user profile |
| POST | `/api/v1/extract` | Upload images → extract + persist + AI dedup check |
| GET | `/api/v1/records` | List all records (brand / category / needs_review / date filters) |
| PATCH | `/api/v1/records/{id}` | Save human edits (updates confidence to 1.0) |
| DELETE | `/api/v1/records/{id}` | Delete a record |
| POST | `/api/v1/records/dedup` | Find duplicate candidates across all records |
| POST | `/api/v1/records/merge` | Merge two records (keeps best-confidence fields) |
| GET | `/api/v1/export` | Download CSV or XLSX (`?format=csv\|xlsx&session_id=N`) |
| GET | `/health` | Readiness probe |

### POST `/api/v1/extract` response

```json
{
  "session_id": 7,
  "records": [ { ...RecordOut } ],
  "dedup_candidates": [
    {
      "record_id": 12,
      "duplicate_of": 3,
      "score": 0.97,
      "reason": "Same brand and product name (AI analysis)",
      "matched_fields": ["ai_analysis"]
    }
  ]
}
```

`dedup_candidates` is populated by an AI dedup call immediately after
extraction — Gemini compares the new records against everything already in the
database and returns matches above a 0.70 confidence threshold. The frontend
surfaces these as a plain-language duplicate warning in the Review step.

## AI duplicate detection

`services/ai_dedup.py` runs on every upload:

1. **Pre-filter (free):** exact barcode matches are returned immediately as
   certain duplicates. Records with brand fuzzy-score ≥ 50% or matching
   `category_type` are shortlisted (up to 15) for the AI step.
2. **Gemini call:** the new record's fields and the shortlist are sent to
   Gemini Flash with a structured prompt. The model decides which (if any)
   represent the same physical SKU — considering brand aliases, weight unit
   differences, OCR noise, and product line distinctions.
3. Results above 0.70 confidence are returned as `MergeCandidate` objects.

The manual "Find Duplicates" scan in the Records page uses the fast fuzzy
matcher (`services/dedup.py`) for bulk scanning across all records.

## S3 image storage

Every uploaded image is stored in the `gdssmaverickdata` S3 bucket at
`uploads/{user_id}/{session_id}/{filename}` before being passed to the VLM.
The S3 key is saved on the `ItemRecord`. Extraction proceeds normally if S3 is
unavailable — `s3_key` is `null` on the record.

## Database migrations

Schema is versioned with Alembic.

```bash
alembic upgrade head                          # apply all pending migrations
alembic revision --autogenerate -m "change"   # generate after a model change
alembic current                               # show applied revision
alembic downgrade -1                          # roll back one step
```

`AUTO_CREATE_TABLES=true` (default) also runs `create_all` on startup for local
dev. Set it `false` in production and manage schema with `alembic upgrade head`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest              # 51 tests; no network / no Gemini key (VLM is mocked)
pytest --cov=app    # with coverage
```

Covers: auth + rate limiting, upload validation, records CRUD, dedup/merge,
export headers, ITEM_NAME template, barcode checksums, and Gemini schema
constraints.

## Project layout

```
app/
  main.py             App factory, CORS, router wiring
  config.py           Pydantic settings (reads .env)
  database.py         SQLAlchemy engine, session, init_db
  core/
    security.py       JWT encode/decode, bcrypt
    deps.py           get_current_user FastAPI dependency
  models/
    user.py           User
    session.py        ExtractionSession
    record.py         ItemRecord (13 IMDB fields + s3_key + confidence/source)
  schemas/
    auth.py           Login/register/token schemas
    imdb.py           VLMExtraction, RecordOut, RecordUpdate, MergeCandidate, ExtractResponse
  services/
    preprocess.py     Downscale + JPEG normalisation (Pillow)
    barcode.py        ZBar barcode decoder
    vlm.py            Gemini Flash structured extraction (with retry backoff)
    enrichment.py     Open Food Facts barcode lookup
    normalize.py      Canonicalise fields, parse weight, build ITEM_NAME
    pipeline.py       Orchestrates the full per-image pipeline
    ai_dedup.py       AI-powered duplicate detection (pre-filter + Gemini call)
    dedup.py          Fast fuzzy duplicate scan (RapidFuzz) for bulk/manual use
    export.py         CSV + XLSX generation (pandas + openpyxl)
    storage.py        Async S3 upload (boto3 in thread executor)
  routers/
    auth.py           /auth/* routes
    extract.py        POST /extract — pipeline + S3 + AI dedup
    records.py        GET/PATCH/DELETE /records, dedup, merge
    export.py         GET /export
alembic/
  versions/           Migration scripts
```
