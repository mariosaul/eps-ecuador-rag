"""Streamlit dashboard for the EPS Ecuador RAG platform.

Provides an interactive interface combining Power BI visualizations,
AI-powered chat with RAG, and dynamic province/sector data cards.

Usage:
    streamlit run app/dashboard.py
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
from collections import Counter

from src.config import Config
from src.database import MongoDBConnection
from src.ai.vector_search import search_organizations
from src.ai.assistant import (
    detect_provinces,
    detect_sector,
    build_prompt,
    generate_response,
)


# ── Page Configuration ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="EPS Ecuador - IA Dashboard",
    layout="wide",
    page_icon="📊",
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&display=swap');
    h1, h2, h3, h4, p.title {
        font-family: 'Playfair Display', 'Georgia', 'Times New Roman', serif !important;
        font-weight: 700;
    }
    .main { background-color: #0e1117; color: white; }
    .stMetric {
        background-color: #1e2130;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #30363d;
        margin-bottom: 10px;
    }
    [data-testid="stMetricValue"] {
        font-size: 32px;
        font-family: 'Playfair Display', serif;
        color: #00d4ff;
    }
    </style>
""", unsafe_allow_html=True)


# ── Data Loading ─────────────────────────────────────────────────────────────
@st.cache_resource
def load_data():
    """Load province statistics and organization data."""
    with MongoDBConnection() as db:
        provinces = list(db[Config.COLLECTION_PROVINCES].find({}, {"_id": 0}))
        df_provinces = pd.DataFrame(provinces)

        orgs = list(db[Config.COLLECTION_ORGS].find(
            {"embedding_vector": {"$exists": True}},
            {
                "_id": 0, "nombre": 1, "clase": 1, "grupo": 1,
                "sector": 1, "tipo_organizacion": 1, "resumen_ia": 1,
                "embedding_vector": 1, "detalles_fijos": 1,
            },
        ))
        df_orgs = pd.DataFrame(orgs)

    return df_provinces, df_orgs


@st.cache_resource
def load_org_stats():
    """Load aggregate organization statistics."""
    with MongoDBConnection() as db:
        collection = db[Config.COLLECTION_ORGS]
        stats = {
            "total": collection.count_documents({}),
            "por_sector": {},
            "por_clase": {},
            "por_tipo": {},
        }
        for key in ["sector", "clase", "tipo_organizacion"]:
            pipeline = [
                {"$group": {"_id": f"${key}", "cantidad": {"$sum": 1}}},
                {"$sort": {"cantidad": -1}},
            ]
            target = "por_tipo" if key == "tipo_organizacion" else f"por_{key}"
            for item in collection.aggregate(pipeline):
                if item["_id"]:
                    stats[target][item["_id"]] = item["cantidad"]

    return stats


# ── Load Data ────────────────────────────────────────────────────────────────
df_provinces, df_orgs = load_data()
stats_orgs = load_org_stats()


# ── Header & Power BI ────────────────────────────────────────────────────────
st.title("Plataforma de Consultoría Inteligente y Caracterización Territorial de la EPS")
st.markdown("---")

if Config.POWERBI_EMBED_URL:
    st.subheader("🌐 Vista General del Mercado (Power BI)")
    st.components.v1.iframe(Config.POWERBI_EMBED_URL, height=600, scrolling=True)
    st.markdown("---")


# ── AI Section ───────────────────────────────────────────────────────────────
st.header("Inteligencia Artificial (EPS Ecuador)")

col_chat, col_metrics = st.columns([1, 0.8])

if "messages" not in st.session_state:
    st.session_state.messages = []


# ── Context Detection ────────────────────────────────────────────────────────
detected_provinces: list[str] = []
detected_province: str | None = None
detected_sector: str | None = None
found_orgs: list[dict] = []

if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_query = st.session_state.messages[-1]["content"].lower()
    detected_provinces = detect_provinces(last_query, df_provinces["PROV_RES"].unique().tolist())

    if detected_provinces:
        detected_province = detected_provinces[0]

    found_orgs = search_organizations(last_query, limit=5)
    if found_orgs:
        detected_sector = detect_sector(found_orgs)


# ── Chat Panel ───────────────────────────────────────────────────────────────
with col_chat:
    st.subheader("💬 CHAT (puede equivocarse !!!)")
    chat_container = st.container(height=600)

    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    if prompt := st.chat_input("Ej: Compara Guayas y Pichincha"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()

    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with chat_container:
            with st.chat_message("assistant"):
                query = st.session_state.messages[-1]["content"]

                # Build province context
                if detected_provinces:
                    province_ctx = "DATOS DE PROVINCIAS:\n"
                    for p in detected_provinces:
                        row = df_provinces[df_provinces["PROV_RES"] == p]
                        if not row.empty:
                            province_ctx += row.iloc[0].get("resumen_ia", "") + "\n\n"
                else:
                    df_real = df_provinces[df_provinces["PROV_RES"] != "OTRA/EXTRANJERO"]
                    df_sorted = df_real.sort_values("porcentaje_incursion", ascending=True)
                    province_ctx = "TABLA NUMÉRICA ORDENADA:\n"
                    for _, r in df_sorted.iterrows():
                        province_ctx += (
                            f"{r['PROV_RES']}: incursion={r.get('porcentaje_incursion')}% | "
                            f"socios={int(r.get('total_socios_seps', 0))} | "
                            f"pobreza={r.get('porcentaje_pobreza')}% | "
                            f"edad={float(r.get('edad_promedio', 0)):.1f}\n"
                        )

                # Build org context
                org_ctx = ""
                if found_orgs:
                    org_ctx = "ORGANIZACIONES RELACIONADAS:\n"
                    for org in found_orgs:
                        org_ctx += (
                            f"- grupo={org.get('grupo', 'N/A')} | "
                            f"clase={org.get('clase', 'N/A')} | "
                            f"sector={org.get('sector', 'N/A')}\n"
                        )

                final_prompt = build_prompt(query, province_ctx, org_ctx)

                # Stream response
                full_response = ""
                response_placeholder = st.empty()

                with st.spinner("Consultando SEPS..."):
                    try:
                        stream = generate_response(final_prompt, stream=True, max_tokens=500)
                        for chunk in stream:
                            full_response += chunk["response"]
                            response_placeholder.markdown(full_response + "▌")
                        response_placeholder.markdown(full_response)
                    except Exception as e:
                        st.error(f"Error: {e}")

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                })


# ── Metrics Panel ────────────────────────────────────────────────────────────
with col_metrics:
    st.subheader("📊 Ficha de Datos")

    if detected_province:
        st.info(f"📍 Información detectada: **{detected_province}**")
        row = df_provinces[df_provinces["PROV_RES"] == detected_province].iloc[0]

        c1, c2 = st.columns(2)
        c1.metric("Total Socios", f"{int(row['total_socios_seps']):,}")
        c2.metric("Incursión EPS", f"{row['porcentaje_incursion']}%")

        c3, c4 = st.columns(2)
        c3.metric("Pobreza", f"{row['porcentaje_pobreza']}%")
        c4.metric("Edad Promedio", f"{float(row['edad_promedio']):.1f}")

        st.markdown(f"**Nivel de Inclusión:** {row['clasificacion_inclusion']}")
        st.markdown(f"**Nivel de Pobreza:** {row['nivel_pobreza']}")

    elif detected_sector:
        st.success(f"🏢 Enfoque en Sector: **{detected_sector}**")
        total_s = stats_orgs["por_sector"].get(detected_sector, 0)

        c1, c2 = st.columns(2)
        c1.metric("Organizaciones", f"{total_s:,}")
        c2.metric("Peso en el Sector", f"{total_s / stats_orgs['total'] * 100:.1f}%")

        st.write("**Clases frecuentes en este sector:**")
        sector_classes = [o["clase"] for o in found_orgs if o.get("sector") == detected_sector]
        for c in set(sector_classes):
            st.markdown(f"- {c}")

    else:
        st.warning(
            "Menciona una provincia o sector en el chat para "
            "visualizar las tarjetas de indicadores."
        )

    st.markdown("---")
    st.write("**KPIs Generales (Ecuador)**")
    c1, c2 = st.columns(2)
    c1.metric("Total Orgs", f"{stats_orgs['total']:,}")
    c2.metric("Provincias", "24")
