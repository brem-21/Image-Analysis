"""Streamlit test UI for the AI-Driven Image-to-IMDB backend.

Run:  streamlit run streamlit_app.py
Drives the full flow: login -> upload images -> extract -> review/edit ->
dedup/merge -> export.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from api import APIError, IMDBClient

st.set_page_config(page_title="Image-to-IMDB Tester", page_icon="📦", layout="wide")

IMDB_FIELDS = [
    "item_name", "barcode", "manufacturer", "brand", "weight_value", "weight_unit",
    "packaging_type", "country_of_origin", "variant_type", "fragrance_flavor",
    "promotion", "addons", "tagline", "category_type",
]
WEIGHT_UNITS = ["", "g", "kg", "mg", "ml", "l", "oz", "lb", "unit"]

# --- session state ---------------------------------------------------------
ss = st.session_state
ss.setdefault("token", None)
ss.setdefault("email", None)
ss.setdefault("base_url", "http://localhost:8000")
ss.setdefault("last_session_id", None)


def client() -> IMDBClient:
    return IMDBClient(ss.base_url, token=ss.token)


def confidence_badge(records: list[dict]) -> pd.DataFrame:
    """Flatten records into a display dataframe with a review flag."""
    rows = []
    for r in records:
        row = {"id": r["id"], "session_id": r.get("session_id")}
        for f in IMDB_FIELDS:
            row[f] = r.get(f)
        row["needs_review"] = r.get("needs_review")
        rows.append(row)
    return pd.DataFrame(rows)


# --- sidebar: connection + auth -------------------------------------------
with st.sidebar:
    st.header("⚙️ Connection")
    ss.base_url = st.text_input("Backend URL", ss.base_url)

    if st.button("Check health", use_container_width=True):
        try:
            st.success(f"Backend: {client().health()}")
        except Exception as e:  # noqa: BLE001
            st.error(f"Unreachable: {e}")

    st.divider()
    st.header("🔐 Authentication")

    if ss.token:
        st.success(f"Logged in as **{ss.email}**")
        if st.button("Log out", use_container_width=True):
            ss.token = None
            ss.email = None
            st.rerun()
    else:
        email = st.text_input("Email", "dev@test.com")
        password = st.text_input("Password", "password123", type="password")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Register", use_container_width=True):
                try:
                    client().register(email, password)
                    st.success("Registered — now log in.")
                except APIError as e:
                    st.error(e.detail)
        with col_b:
            if st.button("Login", type="primary", use_container_width=True):
                try:
                    c = client()
                    c.login(email, password)
                    ss.token = c.token
                    ss.email = email
                    st.rerun()
                except APIError as e:
                    st.error(e.detail)

st.title("📦 Image-to-IMDB Backend Tester")

if not ss.token:
    st.info("👈 Register and log in from the sidebar to begin.")
    st.stop()

tab_extract, tab_records, tab_dedup, tab_export = st.tabs(
    ["📤 Extract", "📋 Records & Edit", "🔁 Dedup & Merge", "⬇️ Export"]
)

# --- Extract tab -----------------------------------------------------------
with tab_extract:
    st.subheader("Upload product image(s)")
    label = st.text_input("Batch label (optional)", "")
    uploads = st.file_uploader(
        "Drop one or more product images",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
    )
    if uploads:
        st.image([u for u in uploads], width=160, caption=[u.name for u in uploads])

    if st.button("🚀 Extract IMDB attributes", type="primary", disabled=not uploads):
        files = [(u.name, u.getvalue(), u.type or "image/jpeg") for u in uploads]
        try:
            with st.spinner("Running hybrid pipeline (barcode + Gemini Flash + enrichment)…"):
                resp = client().extract(files, label=label)
            ss.last_session_id = resp["session_id"]
            st.success(f"Extracted {len(resp['records'])} record(s) — session #{resp['session_id']}")
            for rec in resp["records"]:
                flag = "⚠️ needs review" if rec.get("needs_review") else "✅"
                with st.expander(f"{flag}  Record #{rec['id']} — {rec.get('item_name') or 'Unnamed'}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Values**")
                        st.json({f: rec.get(f) for f in IMDB_FIELDS})
                    with c2:
                        st.markdown("**Confidence**")
                        st.json(rec.get("confidence", {}))
                        st.markdown("**Source**")
                        st.json(rec.get("source", {}))
        except APIError as e:
            st.error(f"Extract failed: {e.detail}")

# --- Records & Edit tab ----------------------------------------------------
with tab_records:
    st.subheader("Your records")
    colf1, colf2, colf3 = st.columns(3)
    f_brand = colf1.text_input("Filter: brand", "")
    f_cat = colf2.text_input("Filter: category", "")
    f_review = colf3.selectbox("Needs review?", ["All", "true", "false"])

    review_param = None if f_review == "All" else (f_review == "true")
    try:
        records = client().list_records(brand=f_brand, category_type=f_cat, needs_review=review_param)
    except APIError as e:
        records = []
        st.error(e.detail)

    if not records:
        st.info("No records yet. Extract some on the Extract tab.")
    else:
        st.dataframe(confidence_badge(records), use_container_width=True, hide_index=True)

        st.markdown("### ✏️ Edit a record")
        ids = [r["id"] for r in records]
        sel = st.selectbox("Record id", ids)
        rec = next(r for r in records if r["id"] == sel)

        with st.form(f"edit_{sel}"):
            cols = st.columns(2)
            edited = {}
            for i, f in enumerate(IMDB_FIELDS):
                target = cols[i % 2]
                if f == "weight_unit":
                    cur = rec.get(f) or ""
                    edited[f] = target.selectbox(f, WEIGHT_UNITS, index=WEIGHT_UNITS.index(cur) if cur in WEIGHT_UNITS else 0)
                elif f == "weight_value":
                    edited[f] = target.number_input(f, value=float(rec.get(f) or 0.0), step=1.0)
                else:
                    edited[f] = target.text_input(f, rec.get(f) or "")

            colsave, coldel = st.columns(2)
            save = colsave.form_submit_button("💾 Save edits", type="primary", use_container_width=True)
            delete = coldel.form_submit_button("🗑️ Delete record", use_container_width=True)

        if save:
            payload = {}
            for f, v in edited.items():
                if f == "weight_value":
                    payload[f] = v or None
                elif f == "weight_unit":
                    payload[f] = v or None
                else:
                    payload[f] = v or None
            try:
                client().update_record(sel, payload)
                st.success("Saved. Fields you changed are now source=human, confidence=1.0.")
                st.rerun()
            except APIError as e:
                st.error(e.detail)

        if delete:
            try:
                client().delete_record(sel)
                st.success(f"Deleted record #{sel}.")
                st.rerun()
            except APIError as e:
                st.error(e.detail)

# --- Dedup & Merge tab -----------------------------------------------------
with tab_dedup:
    st.subheader("Duplicate / merge suggestions")
    st.caption("Exact barcode match (score 1.0) or fuzzy brand + product name, scoped to your account.")
    only_last = st.checkbox("Limit to last extraction batch", value=False)
    sid = ss.last_session_id if only_last else None

    if st.button("🔎 Find duplicates", type="primary"):
        try:
            result = client().dedup(session_id=sid)
            cands = result.get("candidates", [])
            if not cands:
                st.info("No duplicate candidates found.")
            else:
                st.dataframe(pd.DataFrame(cands), use_container_width=True, hide_index=True)
                ss["dedup_candidates"] = cands
        except APIError as e:
            st.error(e.detail)

    cands = ss.get("dedup_candidates", [])
    if cands:
        st.markdown("### Apply a merge")
        labels = [f"merge #{c['record_id']} → keep #{c['duplicate_of']}  (score {c['score']}, {c['reason']})" for c in cands]
        pick = st.selectbox("Choose a suggestion", range(len(cands)), format_func=lambda i: labels[i])
        chosen = cands[pick]
        if st.button("🔗 Merge selected"):
            try:
                merged = client().merge(keep_id=chosen["duplicate_of"], merge_id=chosen["record_id"])
                st.success(f"Merged into record #{merged['id']}.")
                ss["dedup_candidates"] = []
                st.rerun()
            except APIError as e:
                st.error(e.detail)

# --- Export tab ------------------------------------------------------------
with tab_export:
    st.subheader("Export product-master file")
    fmt = st.radio("Format", ["csv", "xlsx"], horizontal=True)
    only_last_e = st.checkbox("Only last batch", value=False, key="exp_last")
    sid_e = ss.last_session_id if only_last_e else None

    if st.button("Generate export", type="primary"):
        try:
            content = client().export(fmt=fmt, session_id=sid_e)
            mime = "text/csv" if fmt == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            st.download_button(
                f"⬇️ Download imdb_export.{fmt}",
                data=content,
                file_name=f"imdb_export.{fmt}",
                mime=mime,
            )
            if fmt == "csv":
                st.dataframe(pd.read_csv(pd.io.common.BytesIO(content)), use_container_width=True, hide_index=True)
        except APIError as e:
            st.error(e.detail)
