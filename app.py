import io
import re
import numpy as np
import pandas as pd
import streamlit as st
import requests
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

st.set_page_config(page_title="Mapa de Ocorrências (Satélite)", layout="wide")

POSTOS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRVklJXAZVXK0GQYS5HbR6mSynqbvxoEIjgJbcIyZR7SZU-jud4peyg2_VBNcq8zmBHF472JGtZBC9R/pub?gid=0&single=true&output=csv"
OCORR_URL  = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRVklJXAZVXK0GQYS5HbR6mSynqbvxoEIjgJbcIyZR7SZU-jud4peyg2_VBNcq8zmBHF472JGtZBC9R/pub?gid=164488321&single=true&output=csv"


# ----------------- Helpers -----------------
def parse_coord(val) -> float:
    s = str(val).strip()
    if s == "" or s.lower() == "nan":
        return float("nan")
    s = s.replace(",", ".")
    if s.count(".") > 1:
        neg = s.startswith("-")
        s2 = s[1:] if neg else s
        parts = s2.split(".")
        s = ("-" if neg else "") + parts[0] + "." + "".join(parts[1:])
    s = re.sub(r"[^0-9\.\-]", "", s)
    try:
        return float(s)
    except:
        return float("nan")


@st.cache_data(ttl=60)
def read_published_csv(url: str) -> pd.DataFrame:
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, allow_redirects=True)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def build_weight(agg: pd.DataFrame) -> pd.Series:
    # mantém o modo que vinha funcionando melhor
    return np.log1p(agg["registros"]).fillna(0.0)


def format_postos_label(postos_list, max_names=3):
    nomes = [str(p).strip() for p in postos_list if str(p).strip()]
    if not nomes:
        return ""
    if len(nomes) <= max_names:
        return " | ".join(nomes)
    shown = nomes[:max_names]
    return " | ".join(shown) + f"  +{len(nomes) - max_names}"


def make_permanent_tooltip_html(label_postos: str, total: int, show_postos: bool, show_total: bool) -> str:
    parts = []
    if show_total:
        parts.append(str(total))
    if show_postos and label_postos:
        parts.append(label_postos)
    return " | ".join(parts)


# ----------------- UI -----------------
st.title("Mapa de Ocorrências (satélite) — Postos x Registros")

with st.sidebar:
    st.header("Atualização")
    force_refresh = st.button("Atualizar agora (ignorar cache)")

    heat_radius = st.slider("Raio do heatmap", 10, 80, 25)
    heat_blur = st.slider("Blur do heatmap", 5, 80, 15)
    zoom = st.slider("Zoom inicial", 10, 18, 13)

    st.header("Camadas")
    show_points = st.checkbox("Mostrar ponto (popup)", True)

    # começam desligados
    show_total_on_map = st.checkbox("Mostrar total no mapa", False)
    show_postos_on_map = st.checkbox("Mostrar nomes dos postos", False)

    max_names = st.slider("Qtd. nomes no rótulo", 1, 10, 4)

if force_refresh:
    read_published_csv.clear()

# ----------------- Load -----------------
try:
    postos = read_published_csv(POSTOS_URL)
    ocorr = read_published_csv(OCORR_URL)
except Exception as e:
    st.error("Erro lendo os CSVs publicados.")
    st.exception(e)
    st.stop()

# ----------------- Validate -----------------
postos["posto"] = postos["posto"].astype(str).str.strip()
postos["lat"] = postos["lat"].apply(parse_coord)
postos["long"] = postos["long"].apply(parse_coord)
postos = postos.dropna(subset=["lat", "long"])

ocorr["posto"] = ocorr["posto"].astype(str).str.strip()
ocorr["natureza"] = ocorr["natureza"].astype(str).str.strip()
ocorr["datahora"] = pd.to_datetime(ocorr["datahora"], dayfirst=True, errors="coerce")
ocorr = ocorr.dropna(subset=["datahora"])

df = ocorr.merge(postos[["posto", "lat", "long"]], on="posto", how="left")
df = df.dropna(subset=["lat", "long"])

# ----------------- Aggregate -----------------
agg_total = df.groupby(["lat", "long"]).size().reset_index(name="registros")
agg_total["peso"] = build_weight(agg_total)

by_posto = (
    df.groupby(["lat", "long", "posto"])
    .size()
    .reset_index(name="registros_posto")
    .sort_values(["lat", "long", "registros_posto"], ascending=[True, True, False])
)

# ----------------- Map -----------------
center = [float(agg_total["lat"].mean()), float(agg_total["long"].mean())]
m = folium.Map(location=center, zoom_start=zoom, control_scale=True, tiles=None)

# Satélite
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles © Esri",
    name="Satélite",
).add_to(m)

# Rótulos
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Rótulos",
    overlay=True,
).add_to(m)


# ----------------- CSS PCBA -----------------
PCBA_TOOLTIP_CSS = """
<style>
.leaflet-tooltip.pcba-tooltip{
    background: rgba(55,55,55,0.88) !important;
    border: 2px solid #000 !important;
    box-shadow: none !important;
    color: #FFD200 !important;
    padding: 4px 10px !important;
    border-radius: 8px !important;
    font-weight: 900 !important;
    font-family: Arial, sans-serif !important;
    font-size: 12px !important;
}
.leaflet-tooltip.pcba-tooltip:before,
.leaflet-tooltip.pcba-tooltip:after{
    display: none !important;
}
</style>
"""
m.get_root().header.add_child(folium.Element(PCBA_TOOLTIP_CSS))


# ----------------- Heatmap -----------------
heat = agg_total[["lat", "long", "peso"]].values.tolist()
HeatMap(heat, radius=heat_radius, blur=heat_blur).add_to(m)


# ----------------- Points -----------------
for _, row in agg_total.iterrows():
    lat, lon = float(row["lat"]), float(row["long"])
    total = int(row["registros"])

    postos_here = by_posto[(by_posto["lat"] == lat) & (by_posto["long"] == lon)]
    label_postos = format_postos_label(postos_here["posto"].tolist(), max_names=max_names)

    tooltip = None
    if show_total_on_map or show_postos_on_map:
        tooltip = folium.Tooltip(
            make_permanent_tooltip_html(label_postos, total, show_postos_on_map, show_total_on_map),
            permanent=True,
            sticky=False,
            direction="bottom",
            offset=(0, 14),
            class_name="pcba-tooltip"
        )

    if show_points:
        folium.CircleMarker(
            location=[lat, lon],
            radius=10,
            tooltip=tooltip,
            fill=True,
        ).add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

st_folium(m, use_container_width=True, height=720)
