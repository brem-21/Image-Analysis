# Image-to-IMDB

Automates retail product data entry. Upload product images (front, back, side angles) — the AI extracts all 13 Item Master Database (IMDB) attributes, saves them to PostgreSQL, and lets you review, edit, and export a submission-ready CSV/XLSX.

---

## Architecture

```
Image-Analysis-Frontend/     React 19 + TypeScript + Vite + Tailwind CSS v4
Image-Analysis/backend/      FastAPI + SQLAlchemy + PostgreSQL + Alembic
Image-Analysis/              Docker Compose (postgres + pgadmin + backend)
```

The frontend communicates with the backend over a single REST boundary (`/api/v1`). The Vite dev server proxies all `/api` requests to the backend, avoiding any CORS configuration in the browser.

---

## Quick start — Docker (recommended)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine with the Compose plugin.

```bash
git clone <repo-url>
cd Image-Analysis

# Start PostgreSQL, pgAdmin, and the FastAPI backend
docker compose up --build
```

| Service | URL | Credentials |
|---------|-----|-------------|
| FastAPI backend | http://localhost:8000 | — |
| pgAdmin | http://localhost:5052 | `admin@admin.com` / `admin` |
| PostgreSQL | localhost:5434 | `imdb` / `imdb_pass` |

> **pgAdmin:** sign in → the *IMDB Postgres* server is pre-registered in the sidebar → click it → enter password `imdb_pass`.

Schema migrations run automatically on container start via `alembic upgrade head`.

### Start the frontend

```bash
cd Image-Analysis-Frontend
npm install
npm run dev       # http://localhost:5173
```

The Vite dev proxy forwards `/api/*` requests to `http://127.0.0.1:8000`, so no additional configuration is needed.

---

## Quick start — local development (no Docker)

### Backend

```bash
cd Image-Analysis/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Apply migrations (requires a running Postgres — start Docker Compose first)
alembic upgrade head

# Start the backend
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd Image-Analysis-Frontend
npm install
npm run dev       # http://localhost:5173
```

---

## Environment variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | Yes | Long random string for signing tokens |
| `OPENROUTER_API_KEY` | Recommended | Primary VLM provider (OpenRouter) |
| `OPENAI_API_KEY` | Optional | Secondary VLM fallback (direct OpenAI) |
| `DATABASE_URL` | Yes | `postgresql://imdb:imdb_pass@localhost:5434/imdb` |
| `AWS_ACCESS_KEY_ID` | Optional | S3 image storage |
| `AWS_SECRET_ACCESS_KEY` | Optional | S3 image storage |
| `AWS_REGION` | Optional | S3 region (default `us-east-1`) |
| `S3_BUCKET` | Optional | S3 bucket name |

VLM extraction tries providers in order: **OpenRouter → OpenAI**. At least one key must be set.

When running inside Docker, `DATABASE_URL` is overridden by the `environment:` block in `docker-compose.yml` to use the internal `postgres` hostname.

### Frontend (`Image-Analysis-Frontend/.env`)

| Variable | Description |
|----------|-------------|
| `VITE_USE_BACKEND` | Set `true` to route extraction through the FastAPI backend (recommended) |
| `VITE_API_BASE_URL` | Leave empty when using the Vite proxy. Set to a full URL only for static deployments against a remote backend |
| `VITE_OPENAI_API_KEY` | Browser-direct OpenAI fallback (only used when `VITE_USE_BACKEND` is not `true`) |

---

## How it works

1. **Register / Sign in** — every session is authenticated with JWT (access + refresh tokens, 30-minute expiry).

2. **Upload images** — select the image angle from a dropdown (Front, Back, Left Side, Right Side, Label/Tag, etc.) then browse or drag-and-drop. Files sharing the same filename prefix (e.g. `S1234_front.jpg`, `S1234_back.jpg`) are grouped automatically into one product row. Up to 20 images per batch.

3. **AI extraction** — all images for a product are sent together to the VLM. The model scans every part of each image (front panel, back, sides, small print, shelf tag) and fills as many fields as possible from what is actually printed on the packaging — it does not guess. Per-field confidence scores (0–1) are returned alongside the values. A barcode decoder runs first; Open Food Facts enriches validated barcodes with authoritative data. Results from multiple angles are merged — the highest-confidence value per field wins — and saved as **one record per product upload**.

4. **Duplicate detection** — after extraction the backend compares new records against existing ones using fuzzy field matching and an AI cross-check via OpenRouter. Matches are surfaced in the Review step with an option to merge or keep both.

5. **Review & edit** — low-confidence and expected-but-empty fields are highlighted in amber. Every edit is saved back to the database in real time via `PATCH /api/v1/records/{id}`.

6. **Records browser** — the Records tab lists all saved records, filterable by brand, category, and review status. Records can be edited or deleted inline. A "Find Duplicates" scan can be run at any time.

7. **Export** — download the full record set (or a session subset) as **CSV** or **XLSX**. Column names and order match the ground-truth submission format exactly:

   `ITEM_NAME · BARCODE · MANUFACTURER · BRAND · WEIGHT · PACKAGING TYPE · COUNTRY · VARIANT · TYPE · FRAGRANCE_FLAVOR · PROMOTION · ADDONS · TAGLINE`

---

## IMDB columns

| Column | Description | Example |
|--------|-------------|---------|
| `ITEM_NAME` | Full descriptive product name (auto-generated) | `BLUE BAND 250G TUB SPREAD` |
| `BARCODE` | Numeric barcode decoded from image | `6034000482027` |
| `MANUFACTURER` | Legal manufacturer name | `UPFIELD` |
| `BRAND` | Brand name on packaging | `BLUE BAND` |
| `WEIGHT` | Net weight/volume with unit | `250G`, `500ML`, `1.5 KG` |
| `PACKAGING TYPE` | Container form | `TUB`, `GLASS JAR`, `SACHET`, `BOTTLE` |
| `COUNTRY` | Country of manufacture | `GHANA` |
| `VARIANT` | Product variant | `ORIGINAL`, `LOW FAT` |
| `TYPE` | Short product type (shelf-tag style) | `MARGARINE`, `MAYONNAISE`, `DETERGENT` |
| `FRAGRANCE_FLAVOR` | Flavour or fragrance | `STRAWBERRY`, `LEMON` |
| `PROMOTION` | On-pack promotional text | `50% OFF`, `BUY 1 GET 1` |
| `ADDONS` | Bundled add-ons / free gifts | `SPOON INCLUDED` |
| `TAGLINE` | Marketing slogan | `SPREAD FOR BREAD` |

`SEGMENT_TYPE` is extracted and exported as an extra column after the 13 required fields.

---

## S3 image storage

Uploaded images are saved to S3 at `uploads/{user_id}/{session_id}/{filename}`. The primary angle's key is stored on the record; all uploaded angles are written to S3.  
Set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `S3_BUCKET` in `backend/.env` to activate. Extraction works normally without S3 — `s3_key` on the record will be `null`.

---

## Database migrations

Schema is managed with **Alembic**. In Docker, `alembic upgrade head` runs automatically on every container start. For local development:

```bash
cd Image-Analysis/backend
source .venv/bin/activate

# Apply all pending migrations
alembic upgrade head

# Create a new migration after changing a model
alembic revision --autogenerate -m "describe your change"
```

---

## Project structure

```
Image-Analysis/
├── docker-compose.yml          # PostgreSQL (5434) + pgAdmin (5052) + backend (8000)
├── pgadmin/
│   └── servers.json            # pre-registers IMDB Postgres in pgAdmin
└── backend/
    ├── Dockerfile
    ├── entrypoint.sh           # runs migrations then starts uvicorn
    ├── requirements.txt
    ├── .env                    # secrets (not committed)
    ├── alembic/                # schema migration history
    └── app/
        ├── main.py
        ├── config.py
        ├── database.py
        ├── models/
        ├── routers/            # auth, extract, records, export
        ├── schemas/
        └── services/
            ├── vlm_openai.py   # OpenRouter / OpenAI vision extraction
            ├── pipeline.py     # orchestrates barcode → VLM → enrich → normalize
            ├── ai_dedup.py     # OpenRouter-powered duplicate detection
            ├── export.py       # CSV / XLSX export
            └── normalize.py    # field canonicalization

Image-Analysis-Frontend/
├── vite.config.ts              # Vite proxy: /api/* → http://127.0.0.1:8000
├── src/
│   ├── api/                    # HTTP client, OpenAI browser-direct fallback
│   ├── components/
│   │   ├── auth/               # login / register + transition overlay
│   │   ├── upload/             # dropzone, angle selector, product groups
│   │   ├── review/             # field editor, product card, dedup panel
│   │   ├── export/             # column picker, data preview, download
│   │   └── records/            # records browser, edit modal
│   ├── store/                  # AppStore (products/extraction state), AuthStore
│   ├── lib/                    # grouping, export, confidence helpers
│   └── types/                  # IMDB field types
└── .env                        # VITE_USE_BACKEND=true, optional direct-AI keys
```
