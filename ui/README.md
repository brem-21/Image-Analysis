# Image-to-IMDB — Streamlit Test UI

A Streamlit app to exercise the backend end-to-end: log in, upload product
images, run extraction, review/edit the 10 IMDB fields, find & apply merge
suggestions, and download the CSV/Excel product-master file.

## Run

1. **Start the backend first** (see `../backend/README.md`):
   ```powershell
   cd ..\backend
   .\.venv\Scripts\Activate.ps1
   uvicorn app.main:app --reload     # http://localhost:8000
   ```

2. **Start the UI** (reuses the backend venv, or make a fresh one):
   ```powershell
   cd ..\ui
   ..\backend\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
   # or:  pip install -r requirements.txt  &&  streamlit run streamlit_app.py
   ```

3. In the sidebar: set the **Backend URL** (default `http://localhost:8000`),
   **Register**, then **Login**.

## Tabs

| Tab | What it tests |
|-----|---------------|
| **📤 Extract** | Upload image(s) → `POST /extract`; shows values + per-field confidence + source, and the ⚠️ needs-review / 🛑 extraction-failed flags |
| **📋 Records & Edit** | `GET /records` with filters; **scanned image shown beside the fields**, per-field confidence colour-flags (🟢🟡🔴), **canonical dropdowns** for packaging/category/variant, **🔄 re-scan** (`POST /records/{id}/rescan`, keeps human edits), edit → `PATCH` (only changed fields become source=human), and **bulk approve/delete** (`/records/bulk-approve`, `/records/bulk-delete`) |
| **🕘 History** | `GET /sessions` — past scan batches with counts; drill into a batch's items |
| **🔁 Dedup & Merge** | `POST /records/dedup` (per-user) and `POST /records/merge` |
| **⬇️ Export** | `GET /export?format=csv\|xlsx` with a download button + preview |

## Notes
- The **Extract** tab needs a valid `GEMINI_API_KEY` in the backend `.env`.
  All other tabs work without it.
- `api.py` is a thin reusable client — handy for scripts/tests too.
