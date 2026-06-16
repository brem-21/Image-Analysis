# Image-to-IMDB

Automates retail product data entry. Upload product images (front, back, side angles) — the AI extracts all 13 Item Master Database (IMDB) attributes, saves them to PostgreSQL, and lets you review, edit, and export a submission-ready CSV/XLSX.

---

## Architecture

```
Image-Analysis-Frontend/     React 19 + TypeScript + Vite + Tailwind CSS v4
Image-Analysis/backend/      FastAPI + SQLAlchemy + PostgreSQL + Alembic
Image-Analysis/              Docker Compose (postgres + pgadmin + backend)
```

The frontend communicates with the backend over a single REST boundary (`/api/v1`).  
With `VITE_API_BASE_URL` set the app is fully live; without it, OpenAI or Gemini
can be called directly from the browser as a fallback.

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
| pgAdmin | http://localhost:5050 | `admin@imdb.local` / `admin` |
| PostgreSQL | localhost:5432 | `imdb` / `imdb_pass` |

> **pgAdmin first connection:** sign in → the *IMDB Postgres* server is pre-registered in the sidebar → click it → enter password `imdb_pass`.

Schema migrations run automatically on container start via `alembic upgrade head`.

### Start the frontend separately

```bash
cd Image-Analysis-Frontend
npm install
npm run dev       # http://localhost:5173
```

---

## Quick start — local development (no Docker)

### Backend

```bash
cd Image-Analysis/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Minimum required keys in .env:
#   JWT_SECRET, OPENROUTER_API_KEY (or OPENAI_API_KEY or GEMINI_API_KEY)
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd Image-Analysis-Frontend
npm install
# .env already contains VITE_API_BASE_URL=http://localhost:8000
npm run dev       # http://localhost:5173
```

---

## Environment variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | Yes | Long random string for signing tokens |
| `OPENROUTER_API_KEY` | Recommended | Primary VLM provider |
| `OPENAI_API_KEY` | Optional | Secondary VLM fallback |
| `GEMINI_API_KEY` | Optional | Tertiary VLM fallback |
| `DATABASE_URL` | Yes | `postgresql://user:pass@host:5432/db` (overridden by Docker Compose) |
| `AWS_ACCESS_KEY_ID` | Optional | S3 image storage |
| `AWS_SECRET_ACCESS_KEY` | Optional | S3 image storage |
| `AWS_REGION` | Optional | S3 region (default `us-east-1`) |
| `S3_BUCKET` | Optional | S3 bucket name |

VLM extraction tries providers in order: **OpenRouter → OpenAI → Gemini**.  
At least one key must be set or extraction will fail.

### Frontend (`Image-Analysis-Frontend/.env`)

| Variable | Description |
|----------|-------------|
| `VITE_API_BASE_URL` | Backend URL (e.g. `http://localhost:8000`). Leave empty to use browser-direct AI. |
| `VITE_OPENAI_API_KEY` | Browser-direct OpenAI fallback (only used when `VITE_API_BASE_URL` is empty) |
| `VITE_GEMINI_API_KEY` | Browser-direct Gemini fallback (only used when `VITE_API_BASE_URL` is empty) |

---

## How it works

1. **Register / Sign in** — every session is authenticated with JWT (access + refresh tokens, 30-minute expiry).

2. **Upload images** — select the image angle from a dropdown (Front, Back, Left Side, Right Side, Label, etc.) then browse or drag-and-drop images. Files sharing the same name prefix (e.g. `S1234_front.jpg`, `S1234_back.jpg`) are grouped automatically into one product row. Up to 20 images per batch; 3–4 angles per product is recommended.

3. **AI extraction** — each product's images are sent together to the VLM with a structured prompt. The model returns all 13 IMDB fields plus per-field confidence scores (0–1). A dedicated barcode decoder runs first; Open Food Facts enriches validated barcodes with authoritative data. The extraction pipeline runs in a thread pool so it never blocks the API server.

4. **Duplicate detection** — immediately after extraction the backend compares new records against existing ones using fuzzy field matching and an AI cross-check. If a match is found, the Review step shows: *"[Product] was already entered on [date] with ID #[id]"* with options to merge or continue.

5. **Review & edit** — low-confidence and expected-but-empty fields are highlighted in amber. Every edit is saved back to the database in real time via `PATCH /api/v1/records/{id}`.

6. **Records browser** — the Records tab lists all records, filterable by brand, category, and review status. Records can be edited or deleted inline. A "Find Duplicates" scan can be run at any time.

7. **Export** — download the full record set (or a session subset) as **CSV** or **XLSX**. Column names and order match the ground-truth submission format exactly:

   `ITEM_NAME · BARCODE · MANUFACTURER · BRAND · WEIGHT · PACKAGING TYPE · COUNTRY · VARIANT · TYPE · FRAGRANCE_FLAVOR · PROMOTION · ADDONS · TAGLINE`

---

## IMDB columns

| Column | Description | Example |
|--------|-------------|---------|
| `ITEM_NAME` | Full descriptive product name | `BLUE BAND 250G TUB SPREAD` |
| `BARCODE` | Numeric barcode as printed | `6034000482027` |
| `MANUFACTURER` | Legal manufacturer name | `UPFIELD` |
| `BRAND` | Brand name on packaging | `BLUE BAND` |
| `WEIGHT` | Net weight/volume with unit | `250G`, `500ML`, `1.5 KG` |
| `PACKAGING TYPE` | Container form | `TUB`, `GLASS JAR`, `SACHET`, `BOTTLE` |
| `COUNTRY` | Country of manufacture | `GHANA` |
| `VARIANT` | Product variant | `ORIGINAL`, `LOW FAT` |
| `TYPE` | Short product type | `MARGARINE`, `MAYONNAISE`, `DETERGENT` |
| `FRAGRANCE_FLAVOR` | Flavour or fragrance | `STRAWBERRY`, `LEMON` |
| `PROMOTION` | On-pack promotional text | `50% OFF`, `BUY 1 GET 1` |
| `ADDONS` | Bundled add-ons / free gifts | `SPOON INCLUDED` |
| `TAGLINE` | Marketing slogan | `SPREAD FOR BREAD` |

---

## S3 image storage

Uploaded images are saved to S3 at `uploads/{user_id}/{session_id}/{filename}`.  
Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `backend/.env` to activate.  
Extraction works normally without S3 — `s3_key` on the record will be `null`.

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
├── docker-compose.yml          # PostgreSQL + pgAdmin + backend
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
        └── services/           # vlm, pipeline, ai_dedup, export, normalize

Image-Analysis-Frontend/
├── src/
│   ├── api/                    # HTTP client, OpenAI/Gemini direct services
│   ├── components/
│   │   ├── auth/               # login/register + transition overlay
│   │   ├── upload/             # dropzone, angle selector, product groups
│   │   ├── review/             # field editor, product card, dedup panel
│   │   ├── export/             # column picker, data preview, download
│   │   └── records/            # records browser, edit modal
│   ├── store/                  # AppStore (products/extraction state), AuthStore
│   ├── lib/                    # grouping, export, confidence helpers
│   └── types/                  # IMDB field types
└── .env                        # VITE_API_BASE_URL, optional direct-AI keys
```
