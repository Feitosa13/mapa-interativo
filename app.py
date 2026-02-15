import re
import pandas as pd
import streamlit as st
import folium
from folium.plugins import HeatMap, MarkerCluster
from streamlit_folium import st_folium

# ✅ Seu link "Publicar na Web" (CSV)
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSkRLXhmtl4pogs_exuOvZYVctyVFksBQC-KwUkKLXQa0GRZIedH9CORgQc0cgEJbOpBNrTvZR8T1l6/pub?output=csv"

st.set_page_config(page_title="Mapa de Calor - Postos", layout="wide")

@st.cache_data(ttl=60)
def load_data(url: str) -> pd.DataFrame:
    df = pd.read_csv(url)
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def parse_coord(val) -> float:
    s = str(val).strip()
    if s == "" or s.lower() == "nan":
        return float("nan")
    s = s.replace(",", ".")
    if s.count(".") > 1:  # ex: -13.010.079 -> -13.010079
        neg = s.startswith("-")
        s2 = s[1:] if neg else s
        parts = s2.split(".")
        s = ("-" if neg else "") + parts[0] + "." + "".join(parts[1:])
    s = re.sub(r"[^0-9\.\-]", "", s)
    try:
        return float(s)
    except:
        return float("nan")

df = load_data(SHEET_CSV_URL)

# ✅ SEUS NOMES DE COLUNA
col_posto = "posto"
col_lat = "lat"
col_lon = "long"
col_reg = "registros"

# validação rápida
need = [col_posto, col_lat, col_lon, col_reg]
missing = [c for c in need if c not in df.columns]
if missing:
    st.error(f"Faltando coluna(s): {missing}")
    st.write("Colunas encontradas:", df.columns.tolist())
    st.stop()

df[col_lat] = df[col_lat].apply(parse_coord)
df[col_lon] = df[col_lon].apply(parse_coord)
df[col_reg] = pd.to_numeric(df[col_reg], errors="coerce").fillna(0)

df = df.dropna(subset=[col_lat, col_lon])

st.title("Mapa de calor (satélite) — Postos x Registros")

with st.sidebar:
    st.header("Filtros")
    min_r = int(df[col_reg].min())
    max_r = int(df[col_reg].max())
    r_range = st.slider("Faixa de registros", min_r, max_r, (min_r, max_r))
    show_markers = st.checkbox("Mostrar pontos clicáveis", True)
    heat_radius = st.slider("Raio do heatmap", 10, 80, 35)
    heat_blur = st.slider("Blur do heatmap", 10, 80, 25)
    zoom = st.slider("Zoom inicial", 10, 18, 13)

df_f = df[(df[col_reg] >= r_range[0]) & (df[col_reg] <= r_range[1])]

center = [
    float(df_f[col_lat].mean()) if len(df_f) else float(df[col_lat].mean()),
    float(df_f[col_lon].mean()) if len(df_f) else float(df[col_lon].mean())
]

m = folium.Map(location=center, zoom_start=zoom, control_scale=True, tiles=None)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles © Esri",
    name="Satélite",
    overlay=False,
    control=True,
).add_to(m)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Rótulos",
    overlay=True,
    control=True,
    opacity=0.9,
).add_to(m)

heat = df_f[[col_lat, col_lon, col_reg]].values.tolist()
HeatMap(heat, radius=heat_radius, blur=heat_blur, max_zoom=17, name="Mapa de calor").add_to(m)

if show_markers:
    cluster = MarkerCluster(name="Postos (clicáveis)").add_to(m)
    for _, r in df_f.iterrows():
        posto = str(r[col_posto]).strip()
        reg = int(r[col_reg]) if pd.notna(r[col_reg]) else 0
        popup = folium.Popup(
            f"<b>Posto:</b> {posto}<br><b>Registros:</b> {reg}<br><b>Coords:</b> {r[col_lat]:.6f},{r[col_lon]:.6f}",
            max_width=350
        )
        folium.CircleMarker(
            location=[r[col_lat], r[col_lon]],
            radius=6,
            tooltip=f"{posto} ({reg})",
            popup=popup,
            fill=True
        ).add_to(cluster)

folium.LayerControl(collapsed=False).add_to(m)
st_folium(m, use_container_width=True, height=700)

st.caption("Atualização automática: lê o CSV publicado no Google Sheets (cache ~60s).")
