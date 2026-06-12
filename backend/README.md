# Image-to-IMDB Backend

FastAPI backend that auto-fills the 10 IMDB product-master attributes from a
product image using a **hybrid pipeline**: dedicated barcode decoder +
**Gemini Flash** (structured JSON output) + Open Food Facts enrichment +
deterministic normalization. Records are scoped per authenticated user.

## Output columns (export format)
`ITEM_NAME, BARCODE, MANUFACTURER, BRAND, WEIGHT, PACKAGING_TYPE, COUNTRY,
VARIANT_TYPE, FRAGRANCE_FLAVOR, PROMOTION, ADDONS, TAGLINE`

- **ITEM_NAME** is *generated* from a fixed template (see
  `services/normalize.py::build_item_name`) — this is the centralized-naming logic.
- **WEIGHT** is rendered (`250G`) from the internally-split `weight_value` + `weight_unit`.
- `?include_meta=true` appends internal extras `CATEGORY_TYPE, NEEDS_REVIEW`.

Each field carries `confidence`, `source` (`barcode_decoder` / `vlm` /
`external_lookup` / `generated` / `human`), and a `needs_review` flag.

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

All feature routes are under the **`/api/v1`** prefix (configurable via `API_PREFIX`).
`/health` stays at the root for probes.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/auth/register` | Create a user |
| POST | `/api/v1/auth/login` | Get access + refresh tokens (rate-limited) |
| POST | `/api/v1/auth/refresh` | Rotate tokens |
| GET | `/api/v1/auth/me` | Current user |
| POST | `/api/v1/extract` | Upload image(s) → IMDB records (validated: type/size/count) |
| GET | `/api/v1/records` | List records — filters + `limit`/`offset` (returns `X-Total-Count`) |
| PATCH | `/api/v1/records/{id}` | Save human edits |
| DELETE | `/api/v1/records/{id}` | Delete a record |
| POST | `/api/v1/records/dedup` | Merge suggestions (per user) |
| POST | `/api/v1/records/merge` | Apply a merge |
| GET | `/api/v1/export?format=csv\|xlsx` | Download product-master file |
| GET | `/health` | Readiness probe (checks DB) |

All routes except `/api/v1/auth/*` and `/health` require `Authorization: Bearer <token>`.

### Operational guards
- **Upload limits / cost guard:** `MAX_UPLOAD_FILES`, `MAX_UPLOAD_MB`, `ALLOWED_IMAGE_TYPES` (each image is a paid VLM call).
- **Login rate-limit:** `LOGIN_MAX_ATTEMPTS` per `LOGIN_WINDOW_SECONDS` per IP.
- **JWT secret:** startup refuses to boot in `ENVIRONMENT=production` if `JWT_SECRET` is unset/default.
- **Pagination:** `DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE`.

## Database migrations (Alembic)

Schema is versioned with Alembic — no more dropping the DB on changes.

```powershell
# apply all migrations (run before first start in production)
alembic upgrade head

# after changing a model, generate a migration, then review it
alembic revision --autogenerate -m "describe change"
alembic upgrade head

alembic current      # show applied revision
alembic downgrade -1 # roll back one
```

- Alembic reads `DATABASE_URL` from your `.env` (via `app.config`), so set it first.
- **Dev convenience:** `AUTO_CREATE_TABLES=true` makes the app `create_all` on
  startup (handy for local/tests). **In production set it `false`** and let
  `alembic upgrade head` own the schema.

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
