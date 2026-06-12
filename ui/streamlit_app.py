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
ss.setdefault("canonical", None)

# Fields edited via canonical dropdowns (keeps naming centralized).
CANONICAL_FIELDS = ["packaging_type", "category_type", "variant_type"]


def client() -> IMDBClient:
    return IMDBClient(ss.base_url, token=ss.token)


def get_canonical() -> dict:
    if ss.canonical is None:
        try:
            ss.canonical = client().canonical()
        except APIError:
            ss.canonical = {}
    return ss.canonical


def conf_emoji(conf) -> str:
    if conf is None:
        return "⬜"
    if conf >= 0.7:
        return "🟢"
    if conf >= 0.4:
        return "🟡"
    return "🔴"


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


def show_record_image(record_id: int, width: int = 280) -> None:
    try:
        img = client().get_record_image(record_id)
        st.image(img, width=width, caption=f"scanned image · record #{record_id}")
    except APIError:
        st.caption("🖼️ No stored image for this record.")


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

tab_extract, tab_records, tab_history, tab_dedup, tab_export = st.tabs(
    ["📤 Extract", "📋 Records & Edit", "🕘 History", "🔁 Dedup & Merge", "⬇️ Export"]
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
            records = resp["records"]
            st.success(f"Extracted {len(records)} record(s) — session #{resp['session_id']}")

            failed = [r for r in records if r.get("vlm_error")]
            if failed:
                st.error(
                    f"⚠️ Gemini extraction failed for {len(failed)} of {len(records)} image(s) — "
                    "only barcode/decoded fields were filled. See per-record details below."
                )

            for rec in records:
                err = rec.get("vlm_error")
                if err:
                    flag = "🛑 extraction failed"
                elif rec.get("needs_review"):
                    flag = "⚠️ needs review"
                else:
                    flag = "✅"
                expanded = bool(err)
                with st.expander(f"{flag}  Record #{rec['id']} — {rec.get('item_name') or 'Unnamed'}", expanded=expanded):
                    if err:
                        st.error(f"**Gemini (VLM) error:** {err}")
                        st.caption(
                            "Non-VLM fields (e.g. barcode) may still be present. "
                            "If this is a 503/overload, retry; or switch GEMINI_MODEL to a stable model."
                        )
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
        records = client().list_records(brand=f_brand, category_type=f_cat, needs_review=review_param, limit=200)
    except APIError as e:
        records = []
        st.error(e.detail)

    if not records:
        st.info("No records yet. Extract some on the Extract tab.")
    else:
        n_review = sum(1 for r in records if r.get("needs_review"))
        m1, m2 = st.columns(2)
        m1.metric("Records shown", len(records))
        m2.metric("⚠️ Needs review", n_review)
        st.dataframe(confidence_badge(records), use_container_width=True, hide_index=True)

        # --- Bulk actions (review queue) ---
        st.markdown("#### ✅ Bulk actions")
        labels = {r["id"]: f"#{r['id']} · {r.get('item_name') or r.get('brand') or 'Unnamed'}" for r in records}
        picked = st.multiselect("Select records", list(labels), format_func=lambda i: labels[i])
        bcol1, bcol2 = st.columns(2)
        if bcol1.button("Approve selected", disabled=not picked, use_container_width=True):
            try:
                res = client().bulk_approve(picked)
                st.success(f"Approved {res['affected']} record(s).")
                st.rerun()
            except APIError as e:
                st.error(e.detail)
        if bcol2.button("🗑️ Delete selected", disabled=not picked, use_container_width=True):
            try:
                res = client().bulk_delete(picked)
                st.success(f"Deleted {res['affected']} record(s).")
                st.rerun()
            except APIError as e:
                st.error(e.detail)

        # --- Single-record review & edit ---
        st.markdown("### ✏️ Review & edit a record")
        ids = [r["id"] for r in records]
        sel = st.selectbox("Record id", ids, format_func=lambda i: labels[i])
        rec = next(r for r in records if r["id"] == sel)
        conf, src = rec.get("confidence", {}), rec.get("source", {})
        canonical = get_canonical()

        img_col, edit_col = st.columns([1, 1.4])
        with img_col:
            show_record_image(sel)
            if st.button("🔄 Re-scan image", use_container_width=True,
                         help="Re-run the pipeline on the stored image. Your manual edits are kept."):
                try:
                    client().rescan(sel)
                    st.success("Re-scanned. Human-edited fields were preserved.")
                    st.rerun()
                except APIError as e:
                    st.error(e.detail)
            st.markdown("**Field confidence**")
            for f in IMDB_FIELDS:
                if rec.get(f) not in (None, ""):
                    st.markdown(f"{conf_emoji(conf.get(f))} `{f}` — {rec.get(f)}  ·  _{src.get(f, '—')}_")

        with edit_col:
            edited = {}
            for f in IMDB_FIELDS:
                if f == "weight_unit":
                    opts = canonical.get("weight_unit", WEIGHT_UNITS)
                    opts = [""] + [o for o in opts if o]
                    cur = rec.get(f) or ""
                    edited[f] = st.selectbox(f, opts, index=opts.index(cur) if cur in opts else 0, key=f"e_{sel}_{f}")
                elif f == "weight_value":
                    edited[f] = st.number_input(f, value=float(rec.get(f) or 0.0), step=1.0, key=f"e_{sel}_{f}")
                elif f in CANONICAL_FIELDS:
                    cur = rec.get(f) or ""
                    opts = [""] + sorted(set(canonical.get(f, []) + ([cur] if cur else [])))
                    edited[f] = st.selectbox(f, opts, index=opts.index(cur) if cur in opts else 0, key=f"e_{sel}_{f}")
                else:
                    edited[f] = st.text_input(f, rec.get(f) or "", key=f"e_{sel}_{f}")

            colsave, coldel = st.columns(2)
            if colsave.button("💾 Save edits", type="primary", use_container_width=True, key=f"save_{sel}"):
                # Send only fields the user actually changed → those become source=human.
                payload = {}
                for f, v in edited.items():
                    new = (v or None) if not isinstance(v, (int, float)) else (v or None)
                    old = rec.get(f) or None
                    if f == "weight_value":
                        old = float(old) if old is not None else None
                        new = float(v) if v else None
                    if new != old:
                        payload[f] = new
                if not payload:
                    st.info("No changes to save.")
                else:
                    try:
                        client().update_record(sel, payload)
                        st.success(f"Saved {len(payload)} change(s) — now source=human.")
                        st.rerun()
                    except APIError as e:
                        st.error(e.detail)
            if coldel.button("🗑️ Delete record", use_container_width=True, key=f"del_{sel}"):
                try:
                    client().delete_record(sel)
                    st.success(f"Deleted record #{sel}.")
                    st.rerun()
                except APIError as e:
                    st.error(e.detail)

# --- History tab -----------------------------------------------------------
with tab_history:
    st.subheader("Scan history")
    st.caption("Every upload is a batch. Browse past scans and drill into their items.")
    try:
        sessions = client().list_sessions()
    except APIError as e:
        sessions = []
        st.error(e.detail)

    if not sessions:
        st.info("No scans yet. Upload images on the Extract tab.")
    else:
        table = [
            {
                "session": s["id"],
                "label": s["label"] or "—",
                "scanned_at": s["created_at"],
                "items": s["item_count"],
                "needs_review": s["needs_review_count"],
            }
            for s in sessions
        ]
        st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

        ids = [s["id"] for s in sessions]
        labels = {s["id"]: (s["label"] or f"session #{s['id']}") for s in sessions}
        chosen = st.selectbox("View items in scan", ids, format_func=lambda i: f"{labels[i]} (#{i})")
        if chosen:
            try:
                items = client().list_records(session_id=chosen, limit=200)
                if items:
                    st.dataframe(confidence_badge(items), use_container_width=True, hide_index=True)
                else:
                    st.info("This scan has no items (all may have been deleted or merged).")
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
