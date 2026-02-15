import io
import re
import numpy as np
import pandas as pd
import streamlit as st
import requests
import folium
from folium.plugins import HeatMap
from folium.features import DivIcon
from streamlit_folium import st_folium

st.set_page_config(page_title="Mapa de Ocorrências (Satélite)", layout="wide")

# ✅ LINKS FIXOS (Google Sheets publicado)
POSTOS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRVklJXAZVXK0GQYS5HbR6mSynqbvxoEIjgJbcIyZR7SZU-jud4peyg2_VBNcq8zmBHF472JGtZBC9R/pub?gid=0&single=true&output=csv"
OCORR_URL  = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRVklJXAZVXK0GQYS5HbR6mSynqbvxoEIjgJbcIyZR7SZU-jud4peyg2_VBNcq8zmBHF472JGtZBC9R/pub?gid=164488321&single=true&output=csv"


# ----------------- Helpers -----------------
def parse_coord(val) -> float:
    """Aceita -13.010079 / -13,010079 / -13.010.079"""
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


def build_weight(agg: pd.DataFrame, mode: str, cap_pct: float, gamma: float) -> pd.Series:
    base = agg["registros"].astype(float).copy()

    if cap_pct < 100:
        cap = float(np.nanpercentile(base.values, cap_pct))
        base = base.clip(upper=cap)

    if mode == "Bruto":
        peso = base
    elif mode == "Log":
        peso = np.log1p(base)
    elif mode == "Raiz":
        peso = np.sqrt(base)
    elif mode == "Gamma":
        mx = float(base.max()) if float(base.max()) > 0 else 1.0
        norm = base / mx
        peso = np.power(norm, 1.0 / max(gamma, 0.1))
    else:
        peso = np.log1p(base)

    return peso.fillna(0.0)


def add_count_label(map_obj, lat, lon, text):
    """Número total no centro do círculo (visível sem clique)."""
    folium.Marker(
        location=[lat, lon],
        icon=DivIcon(
            icon_size=(30, 30),
            icon_anchor=(15, 15),
            html=f"""
            <div style="
                font-size:12px;
                font-weight:800;
                color:white;
                text-align:center;
                text-shadow: 0 0 3px rgba(0,0,0,0.95);
            ">{text}</div>
            """
        ),
    ).add_to(map_obj)


def add_postos_label(map_obj, lat, lon, text):
    """
    Rótulo com nomes dos postos daquele ponto (visível sem clique),
    posicionado levemente abaixo do marcador.
    """
    folium.Marker(
        location=[lat, lon],
        icon=DivIcon(
            icon_size=(280, 26),
            icon_anchor=(140, -2),  # âncora acima => texto aparece "abaixo" do ponto
            html=f"""
            <div style="
                font-size:11px;
                font-weight:800;
                color:white;
                text-align:center;
                text-shadow: 0 0 3px rgba(0,0,0,0.95);
                background: rgba(0,0,0,0.25);
                padding: 2px 8px;
                border-radius: 8px;
                display:inline-block;
                max-width: 280px;
                overflow:hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            ">{text}</div>
            """
        ),
    ).add_to(map_obj)


def format_postos_label(postos_list, max_names=3):
    """Mostra até max_names e acrescenta +N para não poluir."""
    nomes = [p for p in postos_list if str(p).strip()]
    if not nomes:
        return ""
    if len(nomes) <= max_names:
        return " | ".join(nomes)
    shown = nomes[:max_names]
    return " | ".join(shown) + f"  +{len(nomes) - max_names}"


# ----------------- UI -----------------
st.title("Mapa de Ocorrências (satélite) — Postos x Registros")

with st.sidebar:
    st.header("Atualização")
    force_refresh = st.button("Atualizar agora (ignorar cache)")

    st.header("Heatmap (sensibilidade)")
    weight_mode = st.selectbox("Modo de peso", ["Log", "Bruto", "Raiz", "Gamma"], index=0)
    cap_pct = st.slider("Cap (percentil do topo)", 80, 100, 95, help="95 = corta outliers acima do p95")
    gamma = st.slider("Gamma (apenas no modo Gamma)", 0.6, 3.0, 1.7, 0.1)

    heat_radius = st.slider("Raio do heatmap", 10, 80, 25)
    heat_blur = st.slider("Blur do heatmap", 5, 80, 15)
    zoom = st.slider("Zoom inicial", 10, 18, 13)

    st.header("Camadas")
    show_points = st.checkbox("Mostrar ponto (popup agrupado)", True)
    # ✅ DESLIGADO POR PADRÃO
    show_counts = st.checkbox("Mostrar número total no mapa", False)
    # ✅ DESLIGADO POR PADRÃO
    show_postos_names = st.checkbox("Mostrar nomes dos postos no mapa", False)
    max_names = st.slider("Qtd. nomes no rótulo", 1, 8, 3)

if force_refresh:
    read_published_csv.clear()

# ----------------- Load -----------------
try:
    postos = read_published_csv(POSTOS_URL)
    ocorr = read_published_csv(OCORR_URL)
except Exception as e:
    st.error("Erro lendo os CSVs publicados. Confirme que os links abrem CSV no navegador.")
    st.exception(e)
    st.stop()

# ----------------- Validate columns -----------------
need_postos = {"posto", "lat", "long"}
need_ocorr = {"posto", "natureza", "datahora"}

if not need_postos.issubset(set(postos.columns)):
    st.error(f"POSTOS precisa ter colunas: {sorted(list(need_postos))}. Encontradas: {postos.columns.tolist()}")
    st.stop()

if not need_ocorr.issubset(set(ocorr.columns)):
    st.error(f"OCORRÊNCIAS precisa ter colunas: {sorted(list(need_ocorr))}. Encontradas: {ocorr.columns.tolist()}")
    st.stop()

# ----------------- Normalize / parse -----------------
postos["posto"] = postos["posto"].astype(str).str.strip()
postos["lat"] = postos["lat"].apply(parse_coord)
postos["long"] = postos["long"].apply(parse_coord)
postos = postos.dropna(subset=["lat", "long"])

ocorr["posto"] = ocorr["posto"].astype(str).str.strip()
ocorr["natureza"] = ocorr["natureza"].astype(str).str.strip()

# datahora BR: "13/02/2026 09:04"
ocorr["datahora"] = pd.to_datetime(ocorr["datahora"], dayfirst=True, errors="coerce")
ocorr = ocorr.dropna(subset=["datahora"])

# ----------------- Join occurrences to coords -----------------
df = ocorr.merge(postos[["posto", "lat", "long"]], on="posto", how="left")
missing = int(df["lat"].isna().sum())
if missing:
    st.warning(f"{missing} ocorrência(s) com 'posto' não cadastrado na aba POSTOS (ficaram sem lat/long).")
    df = df.dropna(subset=["lat", "long"])

# ----------------- Filters: período (com hora) e natureza -----------------
with st.sidebar:
    st.header("Filtro por período (com hora)")
    min_dt = df["datahora"].min().to_pydatetime()
    max_dt = df["datahora"].max().to_pydatetime()

    dt_ini = st.datetime_input("Início", value=min_dt)
    dt_fim = st.datetime_input("Fim", value=max_dt)

    st.header("Natureza")
    naturas = sorted(df["natureza"].dropna().unique().tolist())
    natureza_sel = st.multiselect("Natureza (opcional)", options=naturas, default=[])

if dt_ini > dt_fim:
    st.error("Início não pode ser maior que Fim.")
    st.stop()

df_f = df[(df["datahora"] >= pd.to_datetime(dt_ini)) & (df["datahora"] <= pd.to_datetime(dt_fim))]
if natureza_sel:
    df_f = df_f[df_f["natureza"].isin(natureza_sel)]

if df_f.empty:
    st.warning("Sem dados com os filtros atuais.")
    st.stop()

# ----------------- Aggregate: 1 ponto por coordenada -----------------
agg_total = (
    df_f.groupby(["lat", "long"])
    .size()
    .reset_index(name="registros")
)
agg_total["peso"] = build_weight(agg_total, weight_mode, cap_pct, gamma)

by_posto = (
    df_f.groupby(["lat", "long", "posto"])
    .size()
    .reset_index(name="registros_posto")
    .sort_values(["lat", "long", "registros_posto"], ascending=[True, True, False])
)

by_nat = (
    df_f.groupby(["lat", "long", "natureza"])
    .size()
    .reset_index(name="registros_nat")
    .sort_values(["lat", "long", "registros_nat"], ascending=[True, True, False])
)

# ----------------- Map -----------------
center = [float(agg_total["lat"].mean()), float(agg_total["long"].mean())]
m = folium.Map(location=center, zoom_start=zoom, control_scale=True, tiles=None)

# Satélite
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles © Esri",
    name="Satélite",
    overlay=False,
    control=True,
).add_to(m)

# Rótulos
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Rótulos",
    overlay=True,
    control=True,
    opacity=0.9,
).add_to(m)

# Heatmap sensível
heat = agg_total[["lat", "long", "peso"]].values.tolist()
HeatMap(heat, radius=heat_radius, blur=heat_blur, max_zoom=17, name="Mapa de calor").add_to(m)

# Pontos agregados + (opcionais) rótulos e contagens
for _, row in agg_total.iterrows():
    lat, lon = float(row["lat"]), float(row["long"])
    total = int(row["registros"])

    # popup (agrupado por coordenada)
    if show_points:
        postos_here = by_posto[(by_posto["lat"] == lat) & (by_posto["long"] == lon)]
        nat_here = by_nat[(by_nat["lat"] == lat) & (by_nat["long"] == lon)].head(8)

        postos_list = "<br>".join(
            [f"• {p['posto']} — {int(p['registros_posto'])}" for _, p in postos_here.iterrows()]
        ) or "—"

        nat_list = "<br>".join(
            [f"• {n['natureza']} — {int(n['registros_nat'])}" for _, n in nat_here.iterrows()]
        ) or "—"

        popup_html = f"""
        <div style="font-family: Arial; font-size: 13px; line-height: 1.35; width: 330px;">
          <b>Total no ponto:</b> {total}<br><br>
          <b>Postos neste local:</b><br>{postos_list}<br><br>
          <b>Principais naturezas (top 8):</b><br>{nat_list}
        </div>
        """

        folium.CircleMarker(
            location=[lat, lon],
            radius=10,
            tooltip=f"Total: {total}",
            popup=folium.Popup(popup_html, max_width=420),
            fill=True,
        ).add_to(m)

    # número visível (desligado por padrão)
    if show_counts:
        add_count_label(m, lat, lon, str(total))

    # nomes dos postos visíveis (desligado por padrão)
    if show_postos_names:
        postos_here = by_posto[(by_posto["lat"] == lat) & (by_posto["long"] == lon)]
        label = format_postos_label(postos_here["posto"].tolist(), max_names=max_names)
        if label:
            add_postos_label(m, lat, lon, label)

folium.LayerControl(collapsed=False).add_to(m)

st_folium(m, use_container_width=True, height=720)
st.caption("Atualiza lendo os CSVs publicados (cache ~60s). Use 'Atualizar agora' para forçar recarga.")
