from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
REFRESH_MS = 5000


@st.cache_data(ttl=5, show_spinner=False)
def _get(api_base_url: str, path: str, params: dict[str, Any] | None = None):
    url = api_base_url.rstrip("/") + path
    with httpx.Client(timeout=10.0) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def _safe_get(api_base_url: str, path: str, params: dict[str, Any] | None = None):
    try:
        return _get(api_base_url, path, params=params), None
    except Exception as exc:
        return None, str(exc)


st.set_page_config(page_title="Store Intelligence", layout="wide")
st.title("Store Intelligence Dashboard")

# Auto-refresh every 5 seconds (simple, dependency-free)
st.markdown(
    f"""
    <meta http-equiv="refresh" content="{int(REFRESH_MS/1000)}">
    """,
    unsafe_allow_html=True,
)
st.caption(f"Auto-refreshing every {int(REFRESH_MS/1000)} seconds")

with st.sidebar:
    st.subheader("Settings")
    api_base_url = st.text_input("FastAPI base URL", value=API_BASE_URL)
    store_id = st.text_input("Store ID", value="store-1")
    camera_id = st.text_input("Camera ID (optional)", value="")
    lookback_hours = st.slider("Lookback window (hours)", min_value=1, max_value=72, value=24)

now = datetime.now(timezone.utc)
start_ts = now - timedelta(hours=int(lookback_hours))

camera_id = camera_id.strip() or None

# ---- Fetch data from FastAPI ----
metrics, metrics_err = _safe_get(api_base_url, f"/stores/{store_id}/metrics")
funnel, funnel_err = _safe_get(api_base_url, f"/stores/{store_id}/funnel")
anomalies, anomalies_err = _safe_get(api_base_url, f"/stores/{store_id}/anomalies")

events_params: dict[str, Any] = {
    "start": start_ts.isoformat(),
    "end": now.isoformat(),
    "limit": 10000,
}
if camera_id:
    events_params["camera_id"] = camera_id

events, events_err = _safe_get(api_base_url, "/v1/events", params=events_params)

if metrics_err or funnel_err or anomalies_err or events_err:
    with st.expander("Connection / API errors", expanded=False):
        if metrics_err:
            st.error(f"/stores/{{store_id}}/metrics: {metrics_err}")
        if funnel_err:
            st.error(f"/stores/{{store_id}}/funnel: {funnel_err}")
        if anomalies_err:
            st.error(f"/stores/{{store_id}}/anomalies: {anomalies_err}")
        if events_err:
            st.error(f"/v1/events: {events_err}")

# ---- Layout ----
st.subheader("Overview")
top1, top2, top3 = st.columns(3)

unique_visitors = int(metrics.get("unique_visitors", 0)) if isinstance(metrics, dict) else 0
conversion_rate = float(metrics.get("conversion_rate", 0.0)) if isinstance(metrics, dict) else 0.0
queue_depth = int(metrics.get("queue_depth", 0)) if isinstance(metrics, dict) else 0

with top1:
    st.metric("Total Visitors", value=f"{unique_visitors:,}")
with top2:
    st.metric("Conversion Rate", value=f"{conversion_rate * 100.0:.1f}%")
with top3:
    st.metric("Queue Depth", value=f"{queue_depth:,}")

mid1, mid2 = st.columns([2, 1])

with mid1:
    st.subheader("Funnel")
    stages = funnel.get("stages") if isinstance(funnel, dict) else None
    df_stages = pd.DataFrame(stages) if isinstance(stages, list) else pd.DataFrame()
    if not df_stages.empty and {"stage", "count"}.issubset(df_stages.columns):
        fig = px.funnel(df_stages, x="count", y="stage")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No funnel data")

with mid2:
    st.subheader("Active Anomalies")
    if isinstance(anomalies, list) and anomalies:
        df_anom = pd.DataFrame(anomalies)
        # Keep it compact
        show_cols = [c for c in ["severity", "type", "description", "suggested_action"] if c in df_anom.columns]
        st.dataframe(df_anom[show_cols], use_container_width=True, hide_index=True)
    else:
        st.success("No active anomalies")

st.subheader("Zone Heatmap")

df_events = pd.DataFrame(events) if isinstance(events, list) else pd.DataFrame()
if not df_events.empty and {"store_id", "timestamp", "event_type"}.issubset(df_events.columns):
    df_events = df_events[df_events["store_id"] == store_id]
    df_zone = df_events[(df_events["zone_id"].notna()) & (df_events["event_type"].isin(["zone_enter", "zone_dwell"]))]
    if not df_zone.empty:
        df_zone = df_zone.copy()
        df_zone["timestamp"] = pd.to_datetime(df_zone["timestamp"], utc=True, errors="coerce")
        df_zone = df_zone[df_zone["timestamp"].notna()]
        df_zone["hour"] = df_zone["timestamp"].dt.floor("h")
        grp = df_zone.groupby(["zone_id", "hour"], dropna=False).size().reset_index(name="visits")
        pivot = grp.pivot(index="zone_id", columns="hour", values="visits").fillna(0).astype(int)
        if not pivot.empty:
            fig = px.imshow(
                pivot,
                aspect="auto",
                labels={"x": "Hour", "y": "Zone", "color": "Visits"},
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No zone activity in selected window")
    else:
        st.info("No zone events found in selected window")
else:
    st.info("No events data")

