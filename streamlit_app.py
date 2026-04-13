"""
EFE Sur | KPIs e Iniciativas - Gerencia de Pasajeros
=====================================================
Refactorización completa:
  - Eliminadas importaciones y definiciones duplicadas
  - Precálculo único de entry_bucket / exit_bucket
  - infer_station_path reemplazado por orden_trazado cuando disponible
  - normalize_text vectorizado para columnas completas
  - Bug corregido en classify_status (división por cero)
  - od_linea no se muta tras el filtrado inicial
  - Nuevas vistas: Matriz OD, Sankey OD, Tendencia con regresión, Detección de anomalías
  - CSS centralizado con dict de variables
"""

# =========================================================
# IMPORTACIONES (sin duplicados)
# =========================================================
import unicodedata
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================
st.set_page_config(
    page_title="EFE Sur | KPIs e Iniciativas - Gerencia de Pasajeros",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================================================
# PALETA DE COLORES (definida UNA sola vez)
# =========================================================
COLORS = {
    "EFE_BLUE":  "#002857",
    "EFE_RED":   "#FF0016",
    "EFE_WHITE": "#FFFFFF",
    "BG_LIGHT":  "#F4F6F8",
    "BORDER":    "#D9E1E8",
    "TEXT_MAIN": "#1F2937",
    "TEXT_MUTED":"#6B7280",
    "SUCCESS":   "#0F766E",
    "WARNING":   "#D97706",
    "DANGER":    "#B91C1C",
}

# Aliases locales para compatibilidad con plotly
EFE_BLUE  = COLORS["EFE_BLUE"]
EFE_RED   = COLORS["EFE_RED"]
EFE_WHITE = COLORS["EFE_WHITE"]
TEXT_MAIN = COLORS["TEXT_MAIN"]
TEXT_MUTED= COLORS["TEXT_MUTED"]
SUCCESS   = COLORS["SUCCESS"]
WARNING   = COLORS["WARNING"]
DANGER    = COLORS["DANGER"]
BORDER    = COLORS["BORDER"]

RURAL_SERVICES = ["Laja Talcahuano", "Tren Araucanía", "Llanquihue Puerto Montt"]

# =========================================================
# ESTILOS CSS (centralizado con dict de variables)
# =========================================================
_CSS_TEMPLATE = """
<style>
.stApp {{
    background:
        radial-gradient(circle at top left, rgba(0,40,87,0.05) 0%, rgba(0,40,87,0.00) 22%),
        linear-gradient(180deg, #F7F9FC 0%, #EEF3F8 100%);
    color: {TEXT_MAIN};
}}
header[data-testid="stHeader"],
div[data-testid="stToolbar"],
div[data-testid="stDecoration"],
div[data-testid="stStatusWidget"],
div[data-testid="collapsedControl"],
section[data-testid="stSidebar"] {{ display: none !important; }}
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; height: 0; }}

.block-container {{
    padding-top: 0.35rem; padding-bottom: 0.8rem;
    padding-left: 1.4rem; padding-right: 1.4rem;
}}
.hero-shell {{
    background: linear-gradient(135deg,rgba(255,255,255,0.97) 0%,rgba(245,249,253,0.97) 100%);
    border: 1px solid #DDE6EF; border-radius: 28px;
    padding: 0.95rem 1.1rem 0.9rem; box-shadow: 0 18px 44px rgba(0,40,87,0.08);
    margin-bottom: 0.5rem;
}}
.hero-kicker {{
    display: inline-block; background: rgba(0,40,87,0.08); color: {EFE_BLUE};
    border: 1px solid rgba(0,40,87,0.10); font-size: 0.72rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.08em;
    padding: 0.35rem 0.65rem; border-radius: 999px; margin-bottom: 0.5rem;
}}
.main-title {{
    font-size: 2.35rem; font-weight: 850; color: {EFE_BLUE};
    margin-top: 0.05rem; margin-bottom: 0.18rem; line-height: 1.08;
}}
.subtitle {{ font-size: 0.94rem; color: {TEXT_MUTED}; margin-top: 0.25rem; }}
.hero-side-note {{ color: {TEXT_MUTED}; font-size: 0.82rem; margin-top: 0.35rem; }}
.section-shell {{
    background: rgba(255,255,255,0.96); border: 1px solid #DFE7EF;
    border-radius: 24px; padding: 0.9rem 0.95rem 0.85rem;
    box-shadow: 0 10px 26px rgba(0,40,87,0.06); margin: 0.25rem 0 0.8rem;
}}
.section-title {{
    font-size: 1.06rem; font-weight: 800; color: {EFE_BLUE};
    margin-top: 0; margin-bottom: 0.5rem;
}}
.section-subtitle {{ font-size: 0.86rem; color: {TEXT_MUTED}; margin-top: -0.3rem; margin-bottom: 0.5rem; }}
.efe-card {{
    background: linear-gradient(180deg,#FFFFFF 0%,#FCFDFE 100%);
    border: 1px solid #DCE5EE; border-radius: 20px;
    padding: 0.9rem 0.95rem 0.8rem; box-shadow: 0 12px 28px rgba(0,40,87,0.06);
    min-height: 136px; transition: transform 0.16s ease, box-shadow 0.16s ease;
    margin-bottom: 0.45rem;
}}
.efe-card:hover {{ transform: translateY(-2px); box-shadow: 0 16px 34px rgba(0,40,87,0.10); }}
.efe-card-title {{ font-size: 0.88rem; color: {TEXT_MUTED}; margin-bottom: 0.45rem; font-weight: 600; }}
.efe-card-value {{ font-size: 2.0rem; font-weight: 850; color: {EFE_BLUE}; line-height: 1.05; margin-bottom: 0.18rem; }}
.efe-card-meta {{ font-size: 0.92rem; color: {TEXT_MAIN}; margin-bottom: 0.22rem; }}
.efe-card-delta {{ font-size: 0.92rem; font-weight: 700; }}
.efe-observation {{
    background: #FFF7ED; border: 1px solid #FED7AA; border-radius: 14px;
    padding: 0.72rem 0.88rem; font-size: 0.84rem; color: {TEXT_MAIN};
    margin-top: 0.25rem; line-height: 1.38;
}}
.efe-observation strong {{ color: {WARNING}; }}
.efe-observation-empty {{
    background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 14px;
    padding: 0.72rem 0.88rem; font-size: 0.84rem; color: {TEXT_MAIN};
    margin-top: 0.25rem; line-height: 1.38;
}}
.efe-observation-empty strong {{ color: {SUCCESS}; }}
.service-title {{
    font-size: 1.05rem; font-weight: 850; color: {EFE_BLUE};
    margin: 0.15rem 0 0.75rem; padding-bottom: 0.45rem; border-bottom: 2px solid #E6EDF5;
}}
.map-note {{
    background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 16px;
    padding: 0.78rem 0.95rem; font-size: 0.85rem; color: {TEXT_MAIN};
    margin-bottom: 0.55rem; line-height: 1.4;
}}
.toolbar-panel {{
    background: rgba(255,255,255,0.96); border: 1px solid #DFE7EF;
    border-radius: 22px; padding: 0.7rem 0.9rem; margin: 0.08rem 0 0.55rem;
    box-shadow: 0 10px 24px rgba(0,40,87,0.06);
}}
.filters-summary {{ color: {TEXT_MAIN}; font-size: 0.93rem; margin-top: 0.1rem; line-height: 1.4; }}
.filters-summary strong {{ color: {EFE_BLUE}; }}
.filter-chip-row {{ display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.4rem; }}
.filter-chip {{
    display: inline-flex; align-items: center; gap: 0.35rem;
    padding: 0.38rem 0.7rem; border-radius: 999px;
    background: #F1F5F9; border: 1px solid #D8E2EC;
    color: {EFE_BLUE}; font-size: 0.8rem; font-weight: 700;
}}
.filter-chip.soft {{ background: #EEF4FB; }}
.nav-panel {{
    background: rgba(255,255,255,0.97); border: 1px solid #DFE7EF;
    border-radius: 22px; padding: 0.65rem 0.85rem 0.2rem;
    margin: 0.08rem 0 0.6rem; box-shadow: 0 12px 26px rgba(0,40,87,0.08);
    backdrop-filter: blur(10px);
}}
.sticky-nav-anchor {{ display: block; height: 0; margin: 0; padding: 0; }}
div[data-testid="stVerticalBlock"]:has(.sticky-nav-anchor) {{
    position: sticky; top: 0.35rem; z-index: 999;
    background: linear-gradient(180deg,rgba(247,249,252,0.99) 0%,rgba(247,249,252,0.96) 85%,rgba(247,249,252,0.0) 100%);
    padding-top: 0.2rem; padding-bottom: 0.15rem;
}}
.content-panel {{ background: transparent; animation: fadeSlideIn 0.22s ease-out; }}
@keyframes fadeSlideIn {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
div[data-baseweb="select"] > div {{
    border-radius: 16px !important; border-color: #D7E0EA !important;
    background: rgba(255,255,255,0.98) !important; min-height: 48px !important;
    box-shadow: none !important;
}}
div[data-testid="stMetric"] {{
    background: linear-gradient(180deg,#FFFFFF 0%,#FCFDFE 100%);
    border: 1px solid #DFE7EF; padding: 0.7rem 0.85rem;
    border-radius: 18px; box-shadow: 0 10px 24px rgba(0,40,87,0.05);
}}
div[data-testid="stPlotlyChart"] {{
    background: rgba(255,255,255,0.98); border: 1px solid #DFE7EF;
    border-radius: 22px; padding: 0.3rem;
    box-shadow: 0 10px 24px rgba(0,40,87,0.05); margin-bottom: 0.18rem;
}}
.stButton > button, .stDownloadButton > button {{
    border-radius: 999px !important; border: 1px solid #D7E0EA !important;
    background: #FFFFFF !important; color: {EFE_BLUE} !important; font-weight: 700 !important;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
    border-color: {EFE_BLUE} !important; box-shadow: 0 8px 18px rgba(0,40,87,0.08);
}}
</style>
"""

st.markdown(_CSS_TEMPLATE.format(**COLORS), unsafe_allow_html=True)


# =========================================================
# UTILIDADES — texto y formato
# =========================================================

def normalize_text(text: str) -> str:
    """Normaliza un string individual eliminando acentos y pasando a minúsculas."""
    text = "" if text is None else str(text)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").strip().lower()


def normalize_series(series: pd.Series) -> pd.Series:
    """
    Versión vectorizada de normalize_text para columnas completas.
    Evita .apply(normalize_text) fila a fila.
    """
    return (
        series.fillna("")
        .astype(str)
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("ascii")
        .str.strip()
        .str.lower()
    )


def format_service_id(value) -> str:
    if pd.isna(value):
        return "-"
    try:
        vf = float(value)
        return str(int(vf)) if vf.is_integer() else f"{vf:g}"
    except Exception:
        return str(value).strip()


def is_occupancy_rate_kpi(kpi_name: str) -> bool:
    name = normalize_text(kpi_name)
    return "tasa" in name and "ocupacion" in name


def maybe_scale_percent(value):
    if pd.isna(value):
        return value
    try:
        value = float(value)
    except Exception:
        return value
    return value * 100 if abs(value) <= 1.5 else value


def fmt_number(value, unit="", kpi_name=None) -> str:
    if pd.isna(value):
        return "-"
    if unit == "%" or is_occupancy_rate_kpi(kpi_name or ""):
        value = maybe_scale_percent(value)
    if unit == "CLP":
        return f"$ {value:,.0f}".replace(",", ".")
    if unit == "%" or is_occupancy_rate_kpi(kpi_name or ""):
        return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")
    if unit == "pax":
        return f"{value:,.0f}".replace(",", ".")
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(value) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pax(value) -> str:
    if pd.isna(value):
        return "-"
    return f"{float(value):,.0f}".replace(",", ".")


def fmt_fuga_pct(value) -> str:
    if pd.isna(value):
        return "-"
    return fmt_pct(maybe_scale_percent(value))


def periodo_to_date(value):
    value = "" if value is None else str(value).strip()
    if not value:
        return pd.NaT
    if len(value) == 7:
        value += "-01"
    return pd.to_datetime(value, errors="coerce")


def periodo_to_label(value) -> str:
    meses = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
              7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}
    dt = periodo_to_date(value)
    if pd.isna(dt):
        return str(value)
    return f"{meses.get(int(dt.month), str(dt.month))}-{str(dt.year)[2:]}"


def safe_to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


# =========================================================
# UTILIDADES — clasificación y estado
# =========================================================

def classify_status(value, meta, higher_is_better: bool = True) -> str:
    """
    Corregido: maneja meta=0 y value=0 sin división por cero.
    """
    if pd.isna(meta) or pd.isna(value):
        return "ok"
    if meta == 0 and value == 0:
        return "ok"
    if meta == 0:
        return "ok"
    if higher_is_better:
        ratio = value / meta
    else:
        ratio = meta / value if value != 0 else 0.0
    if ratio >= 1:
        return "ok"
    if ratio >= 0.95:
        return "alerta"
    return "critico"


def status_color(status: str) -> str:
    return {
        "ok":          SUCCESS,
        "alerta":      WARNING,
        "critico":     DANGER,
        "Planificada": TEXT_MUTED,
        "En curso":    EFE_BLUE,
        "Atrasada":    DANGER,
        "Finalizada":  SUCCESS,
        "Pausada":     WARNING,
    }.get(str(status).strip(), TEXT_MUTED)


# =========================================================
# UTILIDADES — filtros (helper compartido, sin duplicación)
# =========================================================

def _filter_diff_items(sel, total, label, soft=False) -> str | None:
    """Retorna chip HTML si hay diferencia entre selección y total."""
    if len(sel) != len(total):
        cls = "filter-chip soft" if soft else "filter-chip"
        return f"<span class='{cls}'>{label}: {len(sel)}</span>"
    return None


def build_filter_chip_row(servicios_sel, servicios_lista,
                           estados_ini_sel, estados_ini,
                           prioridades_sel, prioridades,
                           responsables_sel, responsables) -> str:
    chips = [
        _filter_diff_items(servicios_sel, servicios_lista, "Servicios"),
        _filter_diff_items(estados_ini_sel, estados_ini, "Estados", soft=True),
        _filter_diff_items(prioridades_sel, prioridades, "Prioridades"),
        _filter_diff_items(responsables_sel, responsables, "Responsables", soft=True),
    ]
    chips = [c for c in chips if c]
    if not chips:
        chips = ["<span class='filter-chip soft'>Sin filtros adicionales</span>"]
    return "<div class='filter-chip-row'>" + "".join(chips) + "</div>"


def summarize_active_filters(servicios_sel, servicios_lista,
                              estados_ini_sel, estados_ini,
                              prioridades_sel, prioridades,
                              responsables_sel, responsables) -> str:
    parts = []
    if len(servicios_sel) != len(servicios_lista):
        parts.append(f"Servicios: {len(servicios_sel)}/{len(servicios_lista)}")
    if len(estados_ini_sel) != len(estados_ini):
        parts.append(f"Estados: {len(estados_ini_sel)}/{len(estados_ini)}")
    if len(prioridades_sel) != len(prioridades):
        parts.append(f"Prioridades: {len(prioridades_sel)}/{len(prioridades)}")
    if len(responsables_sel) != len(responsables):
        parts.append(f"Responsables: {len(responsables_sel)}/{len(responsables)}")
    return " · ".join(parts) if parts else "Sin filtros adicionales"


# =========================================================
# UTILIDADES — UI helpers
# =========================================================

def option_selector(label, options, key, default=None, horizontal=True):
    if not options:
        return None
    if default is None or default not in options:
        default = options[0]
    try:
        selected = st.pills(label, options=options, selection_mode="single",
                            default=default, key=key)
        return selected if selected is not None else default
    except Exception:
        idx = options.index(default)
        return st.radio(label, options=options, index=idx,
                        key=f"{key}_radio", horizontal=horizontal)


def render_kpi_card(title, value, meta, delta_text, status):
    color = status_color(status)
    st.markdown(f"""
    <div class="efe-card" style="border-left:6px solid {color};">
        <div class="efe-card-title">{title}</div>
        <div class="efe-card-value">{value}</div>
        <div class="efe-card-meta">{meta}</div>
        <div class="efe-card-delta" style="color:{color};">{delta_text}</div>
    </div>""", unsafe_allow_html=True)


def render_observation_box(observacion):
    txt = "" if observacion is None else str(observacion).strip()
    if not txt or txt.lower() == "nan":
        st.markdown("<div class='efe-observation-empty'><strong>Observación:</strong> Sin observaciones</div>",
                    unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='efe-observation'><strong>Observación:</strong> {txt}</div>",
                    unsafe_allow_html=True)


def validate_columns(df: pd.DataFrame, required_cols: list, label: str) -> list:
    """Retorna lista de columnas faltantes (no llama st.stop())."""
    return [c for c in required_cols if c not in df.columns]


# =========================================================
# UTILIDADES — estaciones y trazado
# =========================================================

def infer_station_path(df_map: pd.DataFrame) -> pd.DataFrame:
    """
    Ordena estaciones geográficamente usando orden_trazado si existe.
    Solo recurre al algoritmo nearest-neighbor cuando no hay orden_trazado.
    """
    route_df = df_map.dropna(subset=["latitud", "longitud"]).copy()
    if len(route_df) < 2:
        return route_df

    # Usar columna de orden oficial si está disponible
    if "orden_trazado" in route_df.columns and route_df["orden_trazado"].notna().any():
        return route_df.sort_values("orden_trazado").copy()

    # Fallback: nearest-neighbor (O(n²) aceptable para n pequeño < 50 estaciones)
    coords = route_df[["latitud", "longitud"]].astype(float).to_numpy()

    def dist_sq(i, j):
        return (coords[i][0]-coords[j][0])**2 + (coords[i][1]-coords[j][1])**2

    max_pair, max_d = (0, 1), -1.0
    for i in range(len(coords)):
        for j in range(i+1, len(coords)):
            d = dist_sq(i, j)
            if d > max_d:
                max_d = d
                max_pair = (i, j)

    start = min(max_pair, key=lambda idx: (coords[idx][1], coords[idx][0]))
    unvisited = set(range(len(coords)))
    order = [start]
    unvisited.remove(start)
    while unvisited:
        current = order[-1]
        nxt = min(unvisited, key=lambda idx: dist_sq(current, idx))
        order.append(nxt)
        unvisited.remove(nxt)

    return route_df.iloc[order].copy()


def resolve_station_order_from_reference(activity_df: pd.DataFrame, station_ref: pd.DataFrame) -> list:
    if activity_df.empty:
        return []
    if station_ref is None or station_ref.empty:
        return (activity_df
                .sort_values(["total","estacion"], ascending=[False, True])["estacion"]
                .tolist())

    route_df = station_ref[["estacion","latitud","longitud"]].dropna().copy()
    if route_df.empty:
        return (activity_df
                .sort_values(["total","estacion"], ascending=[False, True])["estacion"]
                .tolist())

    inferred = infer_station_path(route_df)
    ordered = inferred["estacion"].dropna().astype(str).tolist()
    extras = [x for x in activity_df["estacion"].astype(str).tolist() if x not in ordered]
    return ordered + extras


def compute_map_bounds(df_map: pd.DataFrame) -> dict:
    lat_min = float(df_map["latitud"].min())
    lat_max = float(df_map["latitud"].max())
    lon_min = float(df_map["longitud"].min())
    lon_max = float(df_map["longitud"].max())
    lat_pad = max((lat_max - lat_min) * 0.18, 0.015)
    lon_pad = max((lon_max - lon_min) * 0.65, 0.04)
    return dict(west=lon_min-lon_pad, east=lon_max+lon_pad,
                south=lat_min-lat_pad, north=lat_max+lat_pad)


def prepare_od_station_reference(service_name: str, od_subset: pd.DataFrame,
                                   stations_df: pd.DataFrame) -> pd.DataFrame:
    if stations_df is None or stations_df.empty or "estacion" not in stations_df.columns:
        return pd.DataFrame()

    ref = stations_df.copy()
    if "activa" in ref.columns:
        ref = ref[ref["activa"] == 1].copy()
    if "servicio" in ref.columns:
        ref = ref[ref["servicio"].astype(str) == str(service_name)].copy()

    # Vectorizado (antes era .apply(normalize_text) fila a fila)
    ref["station_key"] = normalize_series(ref["estacion"])
    ref["latitud"]  = pd.to_numeric(ref["latitud"],  errors="coerce")
    ref["longitud"] = pd.to_numeric(ref["longitud"], errors="coerce")
    ref = ref.dropna(subset=["latitud","longitud"]).copy()

    if od_subset is not None and not od_subset.empty:
        od_keys = set(
            normalize_series(od_subset["origen"].dropna().astype(str)).tolist() +
            normalize_series(od_subset["destino"].dropna().astype(str)).tolist()
        )
        ref = ref[ref["station_key"].isin(od_keys)].copy()

    return ref.drop_duplicates(subset=["station_key"]).copy()


# =========================================================
# UTILIDADES — tiempo / periodos operacionales
# =========================================================

def classify_operational_period(ts) -> str | None:
    if pd.isna(ts):
        return None
    h = ts.hour + ts.minute / 60.0
    if  6 <= h <  9: return "Punta Mañana"
    if  9 <= h < 17: return "Valle"
    if 17 <= h < 21: return "Punta Tarde"
    return "Fuera de periodo"


def get_time_bucket_series(timestamp_series: pd.Series, granularity: str) -> pd.Series:
    ts = pd.to_datetime(timestamp_series, errors="coerce")
    if granularity == "Periodos operacionales":
        return ts.apply(classify_operational_period)
    hours = 1 if granularity == "Bloques de 1 hora" else 2
    start = ts.dt.floor(f"{hours}h")
    end   = start + pd.Timedelta(hours=hours)
    labels = start.dt.strftime("%H:%M") + "-" + end.dt.strftime("%H:%M")
    return labels.where(start.notna(), None)


def get_bucket_order(bucket_values: list, granularity: str) -> list:
    values = [v for v in bucket_values if pd.notna(v)]
    if granularity == "Periodos operacionales":
        ordered = ["Punta Mañana", "Valle", "Punta Tarde", "Fuera de periodo"]
        return [v for v in ordered if v in set(values)]

    def sort_key(label):
        try:
            hh, mm = str(label).split("-")[0].split(":")
            return int(hh), int(mm)
        except Exception:
            return (99, 99)

    return sorted(list(dict.fromkeys(values)), key=sort_key)


# =========================================================
# CONFIGURACIÓN DE SERVICIOS
# =========================================================

PROFILE_SERVICE_CONFIG = {
    "Biotren": {
        "folder_candidates": ["perfil_bt", ".perfil-bt", ".perfil_bt"],
        "description": "Formato base implementado para Biotren.",
    },
    "Tren Araucanía": {
        "folder_candidates": ["perfil_ta", "perfil_tren_araucania"],
        "description": "Preparado para futura incorporación del formato de perfil de carga.",
    },
    "Laja Talcahuano": {
        "folder_candidates": ["perfil_lt", "perfil_laja_talcahuano"],
        "description": "Preparado para futura incorporación del formato de perfil de carga.",
    },
    "Llanquihue Puerto Montt": {
        "folder_candidates": ["perfil_lpm", "perfil_llanquihue_puerto_montt"],
        "description": "Preparado para futura incorporación del formato de perfil de carga.",
    },
}

OD_SERVICE_CONFIG = {
    "Biotren": {
        "folder_candidates": ["od_bt", ".od_bt"],
        "description": "Base transaccional OD para analizar entradas, salidas y patrones horarios por estación.",
    },
}


def _resolve_folder(service_name: str, config_dict: dict, data_path: Path) -> tuple[list, str]:
    """Devuelve (csv_files, folder_path_str) buscando candidatos del config."""
    base = Path(__file__).resolve().parent
    config = config_dict.get(service_name, {})
    folder_names = config.get("folder_candidates", [])
    folder_name_default = folder_names[0] if folder_names else "data"

    for folder_name in folder_names:
        for root in [base, data_path]:
            candidate = root / folder_name
            if candidate.exists() and candidate.is_dir():
                files = sorted(candidate.glob("*.csv"))
                if files:
                    return list(files), str(candidate)

    fallback = data_path / folder_name_default
    return [], str(fallback)


# =========================================================
# CARGA DE DATOS
# =========================================================

def get_repo_data_path() -> Path:
    base = Path(__file__).resolve().parent
    for folder in [base / "data", base / "datos", base]:
        if all((folder / f).exists() for f in ["kpis.csv", "iniciativas.csv", "personas.csv"]):
            return folder
    st.error("No se encontraron kpis.csv, iniciativas.csv y personas.csv. "
             "Ubíquelos en la raíz del proyecto o en una carpeta llamada data.")
    st.stop()


@st.cache_data
def load_data():
    data_path = get_repo_data_path()

    kpis        = pd.read_csv(data_path / "kpis.csv")
    iniciativas = pd.read_csv(data_path / "iniciativas.csv")
    personas    = pd.read_csv(data_path / "personas.csv")

    servicios_path = data_path / "servicios.csv"
    servicios = pd.read_csv(servicios_path) if servicios_path.exists() else pd.DataFrame()

    estaciones_path = data_path / "estaciones.csv"
    estaciones = pd.read_csv(estaciones_path) if estaciones_path.exists() else pd.DataFrame()

    afluencia_path = data_path / "afluencia_estacion.csv"
    afluencia_estacion = pd.read_csv(afluencia_path) if afluencia_path.exists() else pd.DataFrame()

    # Validaciones con reporte, no st.stop() agresivo
    required_kpis = ["id_kpi","nombre","categoria","servicio","valor","meta","unidad","periodo","variacion_pct","estado"]
    missing_kpis = validate_columns(kpis, required_kpis, "kpis.csv")
    if missing_kpis:
        st.error(f"kpis.csv: columnas faltantes → {', '.join(missing_kpis)}")
        st.stop()

    required_ini = ["id_iniciativa","nombre","responsable_id","servicio","estado","avance_pct","fecha_inicio","fecha_fin","prioridad"]
    missing_ini = validate_columns(iniciativas, required_ini, "iniciativas.csv")
    if missing_ini:
        st.error(f"iniciativas.csv: columnas faltantes → {', '.join(missing_ini)}")
        st.stop()

    required_per = ["id_persona","nombre","cargo","area","activo"]
    missing_per = validate_columns(personas, required_per, "personas.csv")
    if missing_per:
        st.error(f"personas.csv: columnas faltantes → {', '.join(missing_per)}")
        st.stop()

    # Tipos numéricos
    for col in ["valor","meta","variacion_pct"]:
        kpis[col] = pd.to_numeric(kpis[col], errors="coerce")
    if "orden" in kpis.columns:
        kpis["orden"] = pd.to_numeric(kpis["orden"], errors="coerce")

    iniciativas["avance_pct"]   = pd.to_numeric(iniciativas["avance_pct"], errors="coerce")
    iniciativas["fecha_inicio"] = safe_to_datetime(iniciativas["fecha_inicio"]).dt.date
    iniciativas["fecha_fin"]    = safe_to_datetime(iniciativas["fecha_fin"]).dt.date

    personas["activo"] = pd.to_numeric(personas["activo"], errors="coerce").fillna(0).astype(int)
    if "orden" in personas.columns:
        personas["orden"] = pd.to_numeric(personas["orden"], errors="coerce")

    if not servicios.empty:
        if "activo" in servicios.columns:
            servicios["activo"] = pd.to_numeric(servicios["activo"], errors="coerce").fillna(0).astype(int)
        if "orden" in servicios.columns:
            servicios["orden"] = pd.to_numeric(servicios["orden"], errors="coerce")

    if not estaciones.empty:
        for col in ["latitud","longitud","orden_trazado"]:
            if col in estaciones.columns:
                estaciones[col] = pd.to_numeric(estaciones[col], errors="coerce")
        if "activa" in estaciones.columns:
            estaciones["activa"] = pd.to_numeric(estaciones["activa"], errors="coerce").fillna(0).astype(int)

    if not afluencia_estacion.empty:
        for col in ["entradas","meta_entradas","perdida_pax","fuga_pct"]:
            if col in afluencia_estacion.columns:
                afluencia_estacion[col] = pd.to_numeric(afluencia_estacion[col], errors="coerce")

    return kpis, iniciativas, personas, servicios, estaciones, afluencia_estacion, data_path


@st.cache_data
def load_profile_service_data(service_name: str, data_path_str: str):
    data_path = Path(data_path_str)
    required_cols = ["fecha","linea","direccion","servicio","estacion",
                     "t_arr_est","t_dep_est","capacidad_tren","D_bajadas",
                     "B_embarque","L_out_abordo"]

    csv_files, folder_path = _resolve_folder(service_name, PROFILE_SERVICE_CONFIG, data_path)
    if not csv_files:
        return pd.DataFrame(), folder_path, required_cols, [], "no_data"

    frames, loaded = [], []
    for f in csv_files:
        try:
            temp = pd.read_csv(f)
            temp["archivo_origen"] = f.name
            frames.append(temp)
            loaded.append(f.name)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(), folder_path, required_cols, loaded, "read_error"

    perfil_df = pd.concat(frames, ignore_index=True)
    missing = [c for c in required_cols if c not in perfil_df.columns]
    if missing:
        return perfil_df, folder_path, missing, loaded, "unsupported_format"

    perfil_df["fecha"]      = pd.to_datetime(perfil_df["fecha"], errors="coerce").dt.date
    perfil_df["linea"]      = perfil_df["linea"].fillna("").astype(str).str.strip()
    perfil_df["direccion"]  = perfil_df["direccion"].fillna("").astype(str).str.strip()
    perfil_df["estacion"]   = perfil_df["estacion"].fillna("").astype(str).str.strip()
    perfil_df["servicio_label"] = perfil_df["servicio"].apply(format_service_id)

    for tc in ["t_arr_est","t_dep_est"]:
        perfil_df[tc] = pd.to_datetime(perfil_df[tc], errors="coerce")

    for col in ["capacidad_tren","A_llegadas_anden","D_bajadas","Demanda_anden",
                "Capacidad_disponible","B_embarque","R_quedados","Q_out_cola",
                "L_in_abordo","L_out_abordo"]:
        if col in perfil_df.columns:
            perfil_df[col] = pd.to_numeric(perfil_df[col], errors="coerce")

    return perfil_df.dropna(subset=["fecha"]).copy(), folder_path, [], loaded, "ok"


@st.cache_data
def load_od_service_data(service_name: str, data_path_str: str):
    data_path = Path(data_path_str)
    required_cols = ["origen","destino","linea","t_entrada_viaje","t_salida_viaje"]

    csv_files, folder_path = _resolve_folder(service_name, OD_SERVICE_CONFIG, data_path)
    if not csv_files:
        return pd.DataFrame(), folder_path, required_cols, [], "no_data"

    frames, loaded = [], []
    for f in csv_files:
        try:
            temp = pd.read_csv(f, low_memory=False)
            temp["archivo_origen"] = f.name
            frames.append(temp)
            loaded.append(f.name)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(), folder_path, required_cols, loaded, "read_error"

    od_df = pd.concat(frames, ignore_index=True)
    missing = [c for c in required_cols if c not in od_df.columns]
    if missing:
        return od_df, folder_path, missing, loaded, "unsupported_format"

    for col in ["origen","destino","linea","direccion"]:
        if col not in od_df.columns:
            od_df[col] = ""
        od_df[col] = od_df[col].fillna("").astype(str).str.strip()

    od_df["t_entrada_viaje"] = pd.to_datetime(od_df["t_entrada_viaje"], errors="coerce")
    od_df["t_salida_viaje"]  = pd.to_datetime(od_df["t_salida_viaje"],  errors="coerce")

    od_df["fecha"] = (
        pd.to_datetime(od_df["dia_proceso"], errors="coerce").dt.date
        if "dia_proceso" in od_df.columns
        else od_df["t_entrada_viaje"].dt.date
    )

    if "servicio_final" in od_df.columns:
        od_df["servicio_label"] = od_df["servicio_final"].apply(format_service_id)
    elif "servicio" in od_df.columns:
        od_df["servicio_label"] = od_df["servicio"].apply(format_service_id)
    else:
        od_df["servicio_label"] = "-"

    for col in ["tarjeta_id","viaje_idx"]:
        if col in od_df.columns:
            od_df[col] = pd.to_numeric(od_df[col], errors="coerce")

    return od_df.dropna(subset=["fecha"]).copy(), folder_path, [], loaded, "ok"


# =========================================================
# GRÁFICOS — KPIs y evolución
# =========================================================

def scale_kpi_dataframe_for_display(df: pd.DataFrame, kpi_name: str,
                                     value_columns=("valor",)) -> pd.DataFrame:
    df = df.copy()
    if is_occupancy_rate_kpi(kpi_name):
        for col in value_columns:
            if col in df.columns:
                df[col] = df[col].apply(maybe_scale_percent)
    return df


def build_line_chart(df: pd.DataFrame, title: str, color=None, line_dash=None,
                     height=340, unit=None, kpi_name=None, boxed_values=True) -> go.Figure:
    plot_df = df.copy()
    plot_df["periodo_date"]  = plot_df["periodo"].apply(periodo_to_date)
    plot_df = plot_df.sort_values(["periodo_date","periodo"])
    plot_df["periodo_label"] = plot_df["periodo"].apply(periodo_to_label)
    category_order = list(dict.fromkeys(plot_df["periodo_label"].dropna().tolist()))
    plot_df["valor_label"] = plot_df["valor"].apply(lambda v: fmt_number(v, unit or "", kpi_name))

    fig = px.line(plot_df, x="periodo_label", y="valor", color=color,
                  line_dash=line_dash, markers=True, title=title)
    fig.update_traces(marker=dict(size=9), line=dict(width=3))
    fig.update_layout(
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20), height=height,
        legend_title_text="", font=dict(color=TEXT_MAIN),
        title_font=dict(size=16, color=EFE_BLUE), hovermode="x unified",
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=category_order, showgrid=False)
    fig.update_yaxes(title="", gridcolor="#E8EEF4", zeroline=False)

    if boxed_values and not plot_df.empty:
        annot_cols = ["periodo_label","valor","valor_label"]
        if color and color in plot_df.columns:
            annot_cols.append(color)
        for _, row in plot_df[annot_cols].iterrows():
            xshift = 0
            if color and color in plot_df.columns:
                xshift = 10 if len(str(row[color])) % 2 == 0 else -10
            fig.add_annotation(
                x=row["periodo_label"], y=row["valor"], text=row["valor_label"],
                showarrow=False, yshift=18, xshift=xshift,
                font=dict(size=10, color=EFE_BLUE),
                bgcolor="rgba(255,255,255,0.92)", bordercolor=BORDER,
                borderwidth=1, borderpad=3, align="center",
            )
    return fig


def build_trend_line_chart(df: pd.DataFrame, kpi_name: str, unit: str | None,
                            service_name: str) -> go.Figure:
    """
    Nuevo: evolución histórica con línea de tendencia via regresión lineal (numpy.polyfit).
    """
    plot_df = df.copy()
    plot_df["periodo_date"]  = plot_df["periodo"].apply(periodo_to_date)
    plot_df = plot_df.dropna(subset=["periodo_date","valor"]).sort_values("periodo_date")
    plot_df["periodo_label"] = plot_df["periodo"].apply(periodo_to_label)
    if len(plot_df) < 2:
        return build_line_chart(plot_df, f"{kpi_name} — {service_name}", height=370,
                                unit=unit, kpi_name=kpi_name)

    x_num = np.arange(len(plot_df))
    y_vals = plot_df["valor"].to_numpy(dtype=float)
    coeffs = np.polyfit(x_num, y_vals, 1)
    trend  = np.polyval(coeffs, x_num)
    plot_df["tendencia"] = trend

    category_order = list(dict.fromkeys(plot_df["periodo_label"].dropna().tolist()))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=plot_df["periodo_label"], y=plot_df["valor"],
        mode="lines+markers", name="Valor real",
        line=dict(color=EFE_BLUE, width=3), marker=dict(size=9),
        hovertemplate="<b>%{x}</b><br>Valor: %{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=plot_df["periodo_label"], y=plot_df["tendencia"],
        mode="lines", name="Tendencia",
        line=dict(color=EFE_RED, width=2, dash="dash"),
        hovertemplate="<b>%{x}</b><br>Tendencia: %{y:,.2f}<extra></extra>",
    ))
    direction = "▲ Creciente" if coeffs[0] > 0 else "▼ Decreciente"
    fig.update_layout(
        title=f"{kpi_name} — {service_name} · Tendencia: {direction}",
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20), height=370,
        font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=category_order, showgrid=False)
    fig.update_yaxes(title="", gridcolor="#E8EEF4", zeroline=False)
    return fig


def detect_anomalies(df: pd.DataFrame, kpi_name: str, service_name: str,
                      unit: str | None) -> go.Figure:
    """
    Nuevo: marca períodos donde el valor se desvía más de 2σ de la media histórica.
    """
    plot_df = df.copy()
    plot_df["periodo_date"]  = plot_df["periodo"].apply(periodo_to_date)
    plot_df = plot_df.dropna(subset=["periodo_date","valor"]).sort_values("periodo_date")
    plot_df["periodo_label"] = plot_df["periodo"].apply(periodo_to_label)
    if len(plot_df) < 3:
        fig = go.Figure()
        fig.update_layout(title="Insuficientes datos para detección de anomalías",
                          plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, height=300)
        return fig

    mu   = plot_df["valor"].mean()
    sigma= plot_df["valor"].std()
    plot_df["anomaly"] = (plot_df["valor"] - mu).abs() > 2 * sigma
    normal = plot_df[~plot_df["anomaly"]]
    anomal = plot_df[ plot_df["anomaly"]]

    category_order = list(dict.fromkeys(plot_df["periodo_label"].dropna().tolist()))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=plot_df["periodo_label"], y=plot_df["valor"],
        mode="lines", name="Valor", line=dict(color=EFE_BLUE, width=2),
    ))
    fig.add_trace(go.Scatter(
        x=normal["periodo_label"], y=normal["valor"],
        mode="markers", name="Normal", marker=dict(color=EFE_BLUE, size=8),
    ))
    fig.add_trace(go.Scatter(
        x=anomal["periodo_label"], y=anomal["valor"],
        mode="markers", name="Anomalía (±2σ)", marker=dict(color=EFE_RED, size=12, symbol="x"),
        hovertemplate="<b>%{x}</b><br>Valor: %{y:,.2f} ⚠️<extra></extra>",
    ))
    # Banda ±2σ
    category_arr = category_order
    fig.add_hrect(y0=mu - 2*sigma, y1=mu + 2*sigma,
                  fillcolor="rgba(0,40,87,0.05)", line_width=0, annotation_text="±2σ")
    fig.update_layout(
        title=f"Detección de anomalías — {kpi_name} ({service_name})",
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20), height=340,
        font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=category_order, showgrid=False)
    fig.update_yaxes(title="", gridcolor="#E8EEF4", zeroline=False)
    return fig


# =========================================================
# GRÁFICOS — Estaciones y mapa
# =========================================================

def build_station_map(valid_map_df: pd.DataFrame) -> go.Figure:
    plot_df = valid_map_df.copy()
    if plot_df.empty:
        fig = go.Figure()
        fig.update_layout(margin=dict(l=0,r=0,t=0,b=0), height=700)
        return fig

    plot_df["latitud"]  = pd.to_numeric(plot_df["latitud"],  errors="coerce")
    plot_df["longitud"] = pd.to_numeric(plot_df["longitud"], errors="coerce")
    plot_df = plot_df.dropna(subset=["latitud","longitud"]).copy()
    if plot_df.empty:
        fig = go.Figure()
        fig.update_layout(margin=dict(l=0,r=0,t=0,b=0), height=700)
        return fig

    plot_df["label_mapa"]    = plot_df["estacion"].fillna("").astype(str).str.strip()
    plot_df["entradas"]      = pd.to_numeric(plot_df.get("entradas"),      errors="coerce").fillna(0)
    plot_df["meta_entradas"] = pd.to_numeric(plot_df.get("meta_entradas"), errors="coerce")

    afluencia = plot_df["entradas"]
    if len(afluencia) > 1 and float(afluencia.max()) > float(afluencia.min()):
        plot_df["marker_size"] = 10 + ((afluencia - afluencia.min()) /
                                        (afluencia.max() - afluencia.min())) * 18
    else:
        plot_df["marker_size"] = 14

    bounds = compute_map_bounds(plot_df.rename(columns={"latitud":"lat_float","longitud":"lon_float"})
                                 if "lat_float" not in plot_df.columns
                                 else plot_df)
    # Si compute_map_bounds necesita lat_float/lon_float, usamos copia renombrada
    lat_min = float(plot_df["latitud"].min()); lat_max = float(plot_df["latitud"].max())
    lon_min = float(plot_df["longitud"].min()); lon_max = float(plot_df["longitud"].max())
    lat_pad = max((lat_max-lat_min)*0.18, 0.015)
    lon_pad = max((lon_max-lon_min)*0.70, 0.04)
    bounds  = dict(west=lon_min-lon_pad, east=lon_max+lon_pad,
                   south=lat_min-lat_pad, north=lat_max+lat_pad)

    fig = go.Figure()
    fig.add_trace(go.Scattermapbox(
        lat=plot_df["latitud"].astype(float),
        lon=plot_df["longitud"].astype(float),
        mode="markers+text",
        text=plot_df["label_mapa"],
        textposition="top right",
        textfont=dict(size=12, color=EFE_BLUE, family="Arial, sans-serif"),
        marker=dict(size=plot_df["marker_size"], color=EFE_BLUE,
                    opacity=0.88, sizemode="diameter"),
        customdata=plot_df[["estacion","entradas","meta_entradas"]].fillna(""),
        hovertemplate=("<b>%{customdata[0]}</b><br>"
                       "Afluencia: %{customdata[1]:,.0f}<br>"
                       "Meta: %{customdata[2]:,.0f}<extra></extra>"),
        showlegend=False,
    ))
    fig.update_layout(
        mapbox=dict(
            style="white-bg",
            layers=[dict(sourcetype="raster",
                         source=["https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"],
                         below="traces")],
            bounds=bounds,
        ),
        margin=dict(l=0,r=0,t=0,b=0), height=700, showlegend=False,
    )
    return fig


# =========================================================
# GRÁFICOS — Perfil de carga
# =========================================================

def get_station_order_from_profile(df: pd.DataFrame) -> list:
    if df.empty or "estacion" not in df.columns:
        return []
    temp = df.copy()
    temp["event_time"] = temp["t_arr_est"].fillna(temp["t_dep_est"])
    temp["estacion"] = temp["estacion"].fillna("").astype(str).str.strip()
    temp = temp[temp["estacion"] != ""]
    if temp.empty:
        return []
    if temp["event_time"].notna().any():
        order = (temp.groupby("estacion", as_index=False)["event_time"]
                 .min().sort_values(["event_time","estacion"]))["estacion"].tolist()
    else:
        order = temp["estacion"].tolist()
    return list(dict.fromkeys(order))


def build_perfil_carga_chart(service_df: pd.DataFrame, titulo: str) -> go.Figure:
    plot_df = service_df.copy()
    station_order = get_station_order_from_profile(plot_df)
    if station_order:
        plot_df["estacion"] = pd.Categorical(plot_df["estacion"],
                                              categories=station_order, ordered=True)
        plot_df = plot_df.sort_values("estacion")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=plot_df["estacion"], y=plot_df["B_embarque"], name="Suben",
                         marker_color=EFE_BLUE,
                         hovertemplate="<b>%{x}</b><br>Suben: %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Bar(x=plot_df["estacion"], y=plot_df["D_bajadas"], name="Bajan",
                         marker_color=EFE_RED,
                         hovertemplate="<b>%{x}</b><br>Bajan: %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=plot_df["estacion"], y=plot_df["L_out_abordo"],
                              mode="lines+markers", name="A bordo",
                              line=dict(color=SUCCESS, width=3), marker=dict(size=8),
                              hovertemplate="<b>%{x}</b><br>A bordo: %{y:,.0f}<extra></extra>"))

    cap = pd.to_numeric(plot_df.get("capacidad_tren"), errors="coerce")
    if cap.notna().any():
        capacidad = float(cap.dropna().iloc[0])
        fig.add_trace(go.Scatter(x=plot_df["estacion"], y=[capacidad]*len(plot_df),
                                  mode="lines", name="Capacidad",
                                  line=dict(color=TEXT_MUTED, width=2, dash="dash"),
                                  hovertemplate="Capacidad: %{y:,.0f}<extra></extra>"))

    fig.update_layout(
        title=titulo, plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=55,b=20), height=460, barmode="group",
        font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=station_order or None)
    fig.update_yaxes(title="Pasajeros")
    return fig


def build_perfil_abordo_comparativo_chart(day_df: pd.DataFrame, titulo: str) -> go.Figure:
    plot_df = day_df.copy()
    if plot_df.empty:
        fig = go.Figure()
        fig.update_layout(title=titulo, plot_bgcolor=EFE_WHITE,
                          paper_bgcolor=EFE_WHITE, height=520)
        return fig

    plot_df["event_time"] = plot_df["t_arr_est"].fillna(plot_df["t_dep_est"])
    station_order = get_station_order_from_profile(plot_df)
    if station_order:
        plot_df["estacion"] = pd.Categorical(plot_df["estacion"],
                                              categories=station_order, ordered=True)

    servicio_order = (plot_df.groupby("servicio_label", as_index=False)["event_time"]
                      .min().sort_values(["event_time","servicio_label"])
                      ["servicio_label"].astype(str).tolist())
    if servicio_order:
        plot_df["servicio_label"] = pd.Categorical(plot_df["servicio_label"],
                                                    categories=servicio_order, ordered=True)

    plot_df = plot_df.sort_values(["servicio_label","estacion","event_time"])
    fig = px.line(plot_df, x="estacion", y="L_out_abordo", color="servicio_label",
                  markers=True, category_orders={"estacion": station_order,
                                                  "servicio_label": servicio_order},
                  title=titulo)
    fig.update_traces(mode="lines+markers", line=dict(width=2), marker=dict(size=6),
                      hovertemplate="<b>%{x}</b><br>Servicio: %{fullData.name}<br>A bordo: %{y:,.0f}<extra></extra>")
    fig.update_layout(
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=55,b=20), height=560,
        font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
        legend_title_text="Servicio", hovermode="x unified",
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.01),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=station_order or None)
    fig.update_yaxes(title="Pasajeros a bordo")
    return fig


# =========================================================
# GRÁFICOS — OD
# =========================================================

def build_od_events(day_df: pd.DataFrame, entry_col: str, exit_col: str) -> pd.DataFrame:
    """
    Recibe columnas bucket precalculadas para evitar recómputo.
    """
    entries = day_df[["origen", entry_col]].copy()
    entries.columns = ["estacion","bucket"]
    entries["tipo"] = "Entradas"

    exits = day_df[["destino", exit_col]].copy()
    exits.columns = ["estacion","bucket"]
    exits["tipo"] = "Salidas"

    events = pd.concat([entries, exits], ignore_index=True)
    events["estacion"] = events["estacion"].fillna("").astype(str).str.strip()
    events = events[events["estacion"] != ""].dropna(subset=["bucket"]).copy()
    return events


def build_station_period_activity(day_df: pd.DataFrame,
                                    entry_col: str, exit_col: str,
                                    bucket_sel: str) -> pd.DataFrame:
    """
    Refactorizado: recibe columnas bucket precalculadas.
    """
    entries = (
        day_df[day_df[entry_col] == bucket_sel]
        .groupby("origen", as_index=False).size()
        .rename(columns={"origen":"estacion","size":"entradas"})
    )
    exits = (
        day_df[day_df[exit_col] == bucket_sel]
        .groupby("destino", as_index=False).size()
        .rename(columns={"destino":"estacion","size":"salidas"})
    )
    activity = entries.merge(exits, how="outer", on="estacion")
    if activity.empty:
        return pd.DataFrame(columns=["estacion","entradas","salidas","total","balance"])
    activity["entradas"] = pd.to_numeric(activity["entradas"], errors="coerce").fillna(0)
    activity["salidas"]  = pd.to_numeric(activity["salidas"],  errors="coerce").fillna(0)
    activity["total"]   = activity["entradas"] + activity["salidas"]
    activity["balance"] = activity["entradas"] - activity["salidas"]
    activity["estacion"] = activity["estacion"].fillna("").astype(str).str.strip()
    activity = activity[activity["estacion"] != ""].copy()
    return activity.sort_values(["total","estacion"], ascending=[False,True]).reset_index(drop=True)


def build_station_hourly_overview_chart(day_df: pd.DataFrame, station_order=None) -> go.Figure:
    # Usar columnas precalculadas si existen
    temp = day_df.copy()
    if "entry_bucket" not in temp.columns:
        temp["entry_bucket"] = get_time_bucket_series(temp["t_entrada_viaje"], "Bloques de 1 hora")
    if "exit_bucket" not in temp.columns:
        temp["exit_bucket"] = get_time_bucket_series(temp["t_salida_viaje"], "Bloques de 1 hora")

    entries = (temp.dropna(subset=["entry_bucket"])
               .groupby(["entry_bucket","origen"], as_index=False).size()
               .rename(columns={"entry_bucket":"hora","origen":"estacion","size":"entradas"}))
    exits   = (temp.dropna(subset=["exit_bucket"])
               .groupby(["exit_bucket","destino"], as_index=False).size()
               .rename(columns={"exit_bucket":"hora","destino":"estacion","size":"salidas"}))

    hourly = entries.merge(exits, how="outer", on=["hora","estacion"])
    if hourly.empty:
        fig = go.Figure()
        fig.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, height=420)
        return fig

    hourly["entradas"] = pd.to_numeric(hourly["entradas"], errors="coerce").fillna(0)
    hourly["salidas"]  = pd.to_numeric(hourly["salidas"],  errors="coerce").fillna(0)
    hourly["total"]    = hourly["entradas"] + hourly["salidas"]
    hourly["estacion"] = hourly["estacion"].fillna("").astype(str).str.strip()
    hourly = hourly[hourly["estacion"] != ""].copy()

    hour_order = get_bucket_order(hourly["hora"].dropna().tolist(), "Bloques de 1 hora")
    if station_order:
        keep   = [s for s in station_order if s in set(hourly["estacion"].astype(str))]
        extras = [s for s in sorted(hourly["estacion"].astype(str).unique().tolist()) if s not in keep]
        station_order = keep + extras
    else:
        station_order = (hourly.groupby("estacion")["total"].sum()
                         .sort_values(ascending=False).index.tolist())

    fig = go.Figure()
    for estacion in station_order:
        sdf = hourly[hourly["estacion"].astype(str) == str(estacion)].copy()
        if sdf.empty:
            continue
        if hour_order:
            sdf["hora"] = pd.Categorical(sdf["hora"], categories=hour_order, ordered=True)
            sdf = sdf.sort_values("hora")
        fig.add_trace(go.Scatter(
            x=sdf["hora"], y=sdf["total"], mode="lines+markers", name=str(estacion),
            line=dict(width=2), marker=dict(size=6),
            hovertemplate="<b>%{fullData.name}</b><br>%{x}<br>Movimientos: %{y:,.0f}<extra></extra>",
        ))

    fig.update_layout(
        title="Movimientos por hora y estación",
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=55,b=20), height=440,
        font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(title="Hora", tickangle=-90, categoryorder="array",
                     categoryarray=hour_order or None)
    fig.update_yaxes(title="Movimientos")
    return fig


def build_od_heatmap(events_df: pd.DataFrame, bucket_order: list,
                      heatmap_mode: str) -> go.Figure:
    if events_df.empty:
        fig = go.Figure()
        fig.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, height=420)
        return fig

    plot_df = events_df.copy()
    if heatmap_mode != "Movimientos totales":
        plot_df = plot_df[plot_df["tipo"] == heatmap_mode].copy()

    agg = (plot_df.groupby(["estacion","bucket"], as_index=False)
           .size().rename(columns={"size":"cantidad"}))
    if agg.empty:
        fig = go.Figure()
        fig.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, height=420)
        return fig

    station_order = (agg.groupby("estacion")["cantidad"].sum()
                     .sort_values(ascending=False).index.tolist())
    pivot = (agg.pivot(index="estacion", columns="bucket", values="cantidad")
             .fillna(0).reindex(index=station_order))
    if bucket_order:
        pivot = pivot.reindex(columns=[c for c in bucket_order if c in pivot.columns])

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
        colorscale="Blues",
        hovertemplate="<b>%{y}</b><br>%{x}<br>Transacciones: %{z:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Mapa de calor | {heatmap_mode}",
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=55,b=20),
        height=max(420, 120 + 26*len(pivot.index)),
        font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
    )
    return fig


def build_full_od_matrix(day_df: pd.DataFrame, title: str) -> go.Figure:
    """
    Nuevo: Matriz OD completa origen × destino con volumen de viajes.
    """
    agg = (day_df.groupby(["origen","destino"], as_index=False)
           .size().rename(columns={"size":"viajes"}))
    if agg.empty:
        fig = go.Figure()
        fig.update_layout(title=title, plot_bgcolor=EFE_WHITE,
                          paper_bgcolor=EFE_WHITE, height=420)
        return fig

    origs = sorted(agg["origen"].unique().tolist())
    dests = sorted(agg["destino"].unique().tolist())
    pivot = agg.pivot(index="origen", columns="destino", values="viajes").fillna(0)
    pivot = pivot.reindex(index=origs, columns=dests, fill_value=0)

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
        colorscale="Blues", reversescale=False,
        hovertemplate="<b>%{y} → %{x}</b><br>Viajes: %{z:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=55,b=20),
        height=max(500, 80 + 22*len(origs)),
        font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
        xaxis_title="Destino", yaxis_title="Origen",
    )
    return fig


def build_calendar_heatmap(day_df: pd.DataFrame, title: str) -> go.Figure:
    """
    Nuevo: Heatmap día de semana × hora para detectar estacionalidad semanal.
    """
    temp = day_df.copy()
    temp["t_entrada_viaje"] = pd.to_datetime(temp["t_entrada_viaje"], errors="coerce")
    temp = temp.dropna(subset=["t_entrada_viaje"]).copy()
    temp["dow"]  = temp["t_entrada_viaje"].dt.day_name()
    temp["hora"] = temp["t_entrada_viaje"].dt.hour

    agg = temp.groupby(["dow","hora"]).size().reset_index(name="viajes")
    if agg.empty:
        fig = go.Figure()
        fig.update_layout(title=title, plot_bgcolor=EFE_WHITE, height=380)
        return fig

    dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    dow_labels = {"Monday":"Lun","Tuesday":"Mar","Wednesday":"Mié",
                   "Thursday":"Jue","Friday":"Vie","Saturday":"Sáb","Sunday":"Dom"}
    agg["dow_label"] = agg["dow"].map(dow_labels).fillna(agg["dow"])
    dow_labels_ord = [dow_labels.get(d, d) for d in dow_order if d in agg["dow"].unique()]

    pivot = (agg.pivot(index="dow_label", columns="hora", values="viajes")
             .fillna(0).reindex(index=dow_labels_ord))

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=[f"{h:02d}:00" for h in pivot.columns.tolist()],
        y=pivot.index.tolist(), colorscale="Blues",
        hovertemplate="<b>%{y} %{x}</b><br>Viajes: %{z:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title=title, plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=55,b=20), height=380,
        font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
        xaxis_title="Hora del día", yaxis_title="Día de la semana",
    )
    return fig


def build_sankey_od(day_df: pd.DataFrame, title: str, top_n: int = 15) -> go.Figure:
    """
    Nuevo: Diagrama de Sankey para los top_n pares OD más frecuentes.
    """
    agg = (day_df.groupby(["origen","destino"], as_index=False)
           .size().rename(columns={"size":"viajes"})
           .sort_values("viajes", ascending=False).head(top_n))
    if agg.empty:
        fig = go.Figure()
        fig.update_layout(title=title, paper_bgcolor=EFE_WHITE, height=420)
        return fig

    all_nodes = list(dict.fromkeys(agg["origen"].tolist() + agg["destino"].tolist()))
    node_idx  = {n: i for i, n in enumerate(all_nodes)}

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15, thickness=20,
            label=all_nodes,
            color=[EFE_BLUE]*len(all_nodes),
        ),
        link=dict(
            source=agg["origen"].map(node_idx).tolist(),
            target=agg["destino"].map(node_idx).tolist(),
            value=agg["viajes"].tolist(),
            color=[f"rgba(0,40,87,0.3)"]*len(agg),
        ),
    )])
    fig.update_layout(
        title=title, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=55,b=20), height=480,
        font=dict(color=TEXT_MAIN, size=11), title_font=dict(color=EFE_BLUE, size=16),
    )
    return fig


def build_station_flow_chart(flow_df: pd.DataFrame, bucket_order: list,
                               station_name: str, granularity: str) -> go.Figure:
    plot_df = flow_df.copy()
    if bucket_order:
        plot_df["bucket"] = pd.Categorical(plot_df["bucket"], categories=bucket_order, ordered=True)
        plot_df = plot_df.sort_values("bucket")

    fig = go.Figure()
    for tipo, color in [("Entradas", EFE_BLUE), ("Salidas", EFE_RED)]:
        temp = plot_df[plot_df["tipo"] == tipo]
        fig.add_trace(go.Bar(x=temp["bucket"], y=temp["cantidad"], name=tipo,
                             marker_color=color,
                             hovertemplate=f"<b>%{{x}}</b><br>{tipo}: %{{y:,.0f}}<extra></extra>"))

    total_temp = plot_df.groupby("bucket", as_index=False)["cantidad"].sum()
    if bucket_order:
        total_temp["bucket"] = pd.Categorical(total_temp["bucket"], categories=bucket_order, ordered=True)
        total_temp = total_temp.sort_values("bucket")

    fig.add_trace(go.Scatter(x=total_temp["bucket"], y=total_temp["cantidad"],
                              mode="lines+markers", name="Total",
                              line=dict(color=SUCCESS, width=3), marker=dict(size=8),
                              hovertemplate="<b>%{x}</b><br>Total: %{y:,.0f}<extra></extra>"))
    fig.update_layout(
        title=f"{station_name} | {granularity}", plot_bgcolor=EFE_WHITE,
        paper_bgcolor=EFE_WHITE, margin=dict(l=20,r=20,t=55,b=20), height=430,
        barmode="group", font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=bucket_order or None)
    fig.update_yaxes(title="Transacciones")
    return fig


def build_station_activity_bar_chart(activity_df: pd.DataFrame, station_order: list,
                                      bucket_label: str) -> go.Figure:
    plot_df = activity_df.copy()
    if station_order:
        plot_df["estacion"] = pd.Categorical(plot_df["estacion"], categories=station_order, ordered=True)
        plot_df = plot_df.sort_values("estacion")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=plot_df["estacion"], y=plot_df["entradas"], name="Entradas",
                         marker_color=EFE_BLUE,
                         hovertemplate="<b>%{x}</b><br>Entradas: %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Bar(x=plot_df["estacion"], y=plot_df["salidas"], name="Salidas",
                         marker_color=EFE_RED,
                         hovertemplate="<b>%{x}</b><br>Salidas: %{y:,.0f}<extra></extra>"))
    fig.update_layout(
        title=f"Entradas y salidas por estación | {bucket_label}",
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=55,b=20), height=430, barmode="group",
        font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=station_order or None)
    fig.update_yaxes(title="Transacciones")
    return fig


def build_station_activity_map(activity_df: pd.DataFrame, station_ref: pd.DataFrame,
                                 selected_station: str, bucket_label: str) -> go.Figure | None:
    if activity_df.empty or station_ref is None or station_ref.empty:
        return None

    plot_df = activity_df.copy()
    plot_df["station_key"] = normalize_series(plot_df["estacion"])
    map_df = plot_df.merge(
        station_ref[["estacion","station_key","latitud","longitud"]],
        how="left", on="station_key",
        suffixes=("_actividad","_ref"),
    )
    if "estacion_actividad" in map_df.columns:
        map_df["estacion"] = map_df["estacion_actividad"]
    map_df = map_df.dropna(subset=["latitud","longitud"]).copy()
    if map_df.empty:
        return None

    if len(map_df) > 1 and float(map_df["total"].max()) > float(map_df["total"].min()):
        map_df["marker_size"] = 11 + ((map_df["total"] - map_df["total"].min()) /
                                       (map_df["total"].max() - map_df["total"].min())) * 18
    else:
        map_df["marker_size"] = 14

    map_df["is_selected"]   = map_df["estacion"].astype(str) == str(selected_station)
    map_df["label_mapa"]    = map_df["estacion"].astype(str)
    map_df["balance_label"] = map_df["balance"].apply(lambda x: f"{x:,.0f}".replace(",","."))

    lat_min = float(map_df["latitud"].min()); lat_max = float(map_df["latitud"].max())
    lon_min = float(map_df["longitud"].min()); lon_max = float(map_df["longitud"].max())
    lat_pad = max((lat_max-lat_min)*0.18, 0.015)
    lon_pad = max((lon_max-lon_min)*0.65, 0.04)

    fig = go.Figure()
    cmin = float(map_df["balance"].min()); cmax = float(map_df["balance"].max())
    if cmax == cmin: cmax = cmin + 1

    base_df = map_df[~map_df["is_selected"]].copy()
    if not base_df.empty:
        fig.add_trace(go.Scattermapbox(
            lat=base_df["latitud"].astype(float), lon=base_df["longitud"].astype(float),
            mode="markers+text", text=base_df["label_mapa"], textposition="top right",
            textfont=dict(size=11, color=EFE_BLUE, family="Arial, sans-serif"),
            marker=dict(size=base_df["marker_size"], color=base_df["balance"],
                        colorscale="RdBu", cmin=cmin, cmax=cmax, opacity=0.9, sizemode="diameter",
                        colorbar=dict(title="Balance<br>Entradas - Salidas")),
            customdata=base_df[["estacion","entradas","salidas","total","balance_label"]].values,
            hovertemplate=("<b>%{customdata[0]}</b><br>"
                           "Entradas: %{customdata[1]:,.0f}<br>"
                           "Salidas: %{customdata[2]:,.0f}<br>"
                           "Movimientos: %{customdata[3]:,.0f}<br>"
                           "Balance: %{customdata[4]}<extra></extra>"),
            showlegend=False,
        ))

    sel_df = map_df[map_df["is_selected"]].copy()
    if not sel_df.empty:
        fig.add_trace(go.Scattermapbox(
            lat=sel_df["latitud"].astype(float), lon=sel_df["longitud"].astype(float),
            mode="markers+text", text=sel_df["label_mapa"], textposition="top right",
            textfont=dict(size=12, color=EFE_BLUE, family="Arial, sans-serif"),
            marker=dict(size=(sel_df["marker_size"]+5).tolist(), color=WARNING,
                        opacity=0.95, sizemode="diameter"),
            customdata=sel_df[["estacion","entradas","salidas","total","balance_label"]].values,
            hovertemplate=("<b>%{customdata[0]}</b><br>"
                           "Entradas: %{customdata[1]:,.0f}<br>"
                           "Salidas: %{customdata[2]:,.0f}<br>"
                           "Balance: %{customdata[4]}<extra></extra>"),
            showlegend=False,
        ))

    fig.update_layout(
        title=f"Actividad georreferenciada | {bucket_label}",
        mapbox=dict(
            style="white-bg",
            layers=[dict(sourcetype="raster",
                         source=["https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"],
                         below="traces")],
            bounds=dict(west=lon_min-lon_pad, east=lon_max+lon_pad,
                        south=lat_min-lat_pad, north=lat_max+lat_pad),
        ),
        margin=dict(l=0,r=0,t=45,b=0), height=430,
        paper_bgcolor=EFE_WHITE, font=dict(color=TEXT_MAIN),
        title_font=dict(color=EFE_BLUE, size=16),
    )
    return fig


def build_od_connection_map(destinos_df: pd.DataFrame, origenes_df: pd.DataFrame,
                              station_ref: pd.DataFrame, selected_station: str,
                              bucket_label: str, title_text: str | None = None) -> go.Figure | None:
    if station_ref is None or station_ref.empty:
        return None

    ref = station_ref.copy()
    ref["station_key"] = ref["station_key"].astype(str)
    station_key = normalize_text(selected_station)
    node_df = ref[ref["station_key"] == station_key].copy()
    if node_df.empty:
        return None

    node = node_df.iloc[0]
    all_markers = ref.copy()
    all_markers["label_mapa"] = all_markers["estacion"].astype(str)

    def scale_width(series, min_w=1.5, max_w=6.0):
        if len(series) == 0:
            return []
        smin, smax = float(series.min()), float(series.max())
        if smax <= smin:
            return [3.0] * len(series)
        return [min_w + ((float(v)-smin)/(smax-smin))*(max_w-min_w) for v in series]

    fig = go.Figure()

    if destinos_df is not None and not destinos_df.empty:
        dest_plot = destinos_df.copy()
        dest_plot["station_key"] = normalize_series(dest_plot["destino"])
        dest_plot = dest_plot.merge(ref[["station_key","latitud","longitud","estacion"]],
                                    how="left", on="station_key")
        dest_plot = dest_plot.dropna(subset=["latitud","longitud"]).copy()
        widths = scale_width(dest_plot["viajes"])
        for (_, row), w in zip(dest_plot.iterrows(), widths):
            fig.add_trace(go.Scattermapbox(
                lat=[float(node["latitud"]), float(row["latitud"])],
                lon=[float(node["longitud"]), float(row["longitud"])],
                mode="lines", line=dict(width=w, color=EFE_BLUE), opacity=0.65,
                hovertemplate=f"<b>{selected_station}</b> → <b>{row['destino']}</b><br>Viajes: {int(row['viajes']):,}".replace(",",".") + "<extra></extra>",
                showlegend=False,
            ))

    if origenes_df is not None and not origenes_df.empty:
        ori_plot = origenes_df.copy()
        ori_plot["station_key"] = normalize_series(ori_plot["origen"])
        ori_plot = ori_plot.merge(ref[["station_key","latitud","longitud","estacion"]],
                                   how="left", on="station_key")
        ori_plot = ori_plot.dropna(subset=["latitud","longitud"]).copy()
        widths = scale_width(ori_plot["viajes"])
        for (_, row), w in zip(ori_plot.iterrows(), widths):
            fig.add_trace(go.Scattermapbox(
                lat=[float(row["latitud"]), float(node["latitud"])],
                lon=[float(row["longitud"]), float(node["longitud"])],
                mode="lines", line=dict(width=w, color=EFE_RED), opacity=0.6,
                hovertemplate=f"<b>{row['origen']}</b> → <b>{selected_station}</b><br>Viajes: {int(row['viajes']):,}".replace(",",".") + "<extra></extra>",
                showlegend=False,
            ))

    marker_sizes = [15 if est == str(selected_station) else 9
                    for est in all_markers["estacion"].astype(str).tolist()]
    marker_colors = [WARNING if est == str(selected_station) else EFE_BLUE
                     for est in all_markers["estacion"].astype(str).tolist()]

    fig.add_trace(go.Scattermapbox(
        lat=all_markers["latitud"].astype(float), lon=all_markers["longitud"].astype(float),
        mode="markers+text", text=all_markers["label_mapa"], textposition="top right",
        textfont=dict(size=11, color=EFE_BLUE),
        marker=dict(size=marker_sizes, color=marker_colors, opacity=0.88, sizemode="diameter"),
        hovertemplate="<b>%{text}</b><extra></extra>", showlegend=False,
    ))

    lat_min = float(all_markers["latitud"].min()); lat_max = float(all_markers["latitud"].max())
    lon_min = float(all_markers["longitud"].min()); lon_max = float(all_markers["longitud"].max())
    lat_pad = max((lat_max-lat_min)*0.18, 0.015)
    lon_pad = max((lon_max-lon_min)*0.65, 0.04)

    fig.update_layout(
        title=title_text or f"Relaciones OD desde/hacia {selected_station} | {bucket_label}",
        mapbox=dict(
            style="white-bg",
            layers=[dict(sourcetype="raster",
                         source=["https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"],
                         below="traces")],
            bounds=dict(west=lon_min-lon_pad, east=lon_max+lon_pad,
                        south=lat_min-lat_pad, north=lat_max+lat_pad),
        ),
        margin=dict(l=0,r=0,t=45,b=0), height=470,
        paper_bgcolor=EFE_WHITE, font=dict(color=TEXT_MAIN),
        title_font=dict(color=EFE_BLUE, size=16),
    )
    return fig


def build_top_od_bar_chart(df: pd.DataFrame, category_col: str,
                             title: str, color: str) -> go.Figure | None:
    if df is None or df.empty:
        return None
    plot_df = df.copy().head(10).sort_values("viajes", ascending=True)
    fig = go.Figure(go.Bar(
        x=plot_df["viajes"], y=plot_df[category_col], orientation="h",
        marker_color=color,
        text=plot_df["viajes"].apply(lambda x: f"{int(x):,}".replace(",",".")),
        textposition="outside",
        hovertemplate="%{y}<br>Viajes: %{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title=title, plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=50,b=20), height=320,
        font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
    )
    fig.update_xaxes(title="Viajes")
    return fig


# =========================================================
# CARGA INICIAL
# =========================================================
kpis, iniciativas, personas, servicios, estaciones, afluencia_estacion, data_path = load_data()

# =========================================================
# PREPARACIÓN DE DATOS
# =========================================================
personas_activas = personas[personas["activo"] == 1].copy()

iniciativas = iniciativas.merge(
    personas_activas[["id_persona","nombre"]],
    how="left", left_on="responsable_id", right_on="id_persona",
)
# Renombrar columnas con sufijos del merge de forma robusta
if "nombre_y" in iniciativas.columns:
    iniciativas = iniciativas.rename(columns={"nombre_y":"responsable"})
if "nombre_x" in iniciativas.columns:
    iniciativas = iniciativas.rename(columns={"nombre_x":"nombre_iniciativa"})
elif "nombre" in iniciativas.columns and "responsable" not in iniciativas.columns:
    iniciativas = iniciativas.rename(columns={"nombre":"responsable"})
if "nombre" in iniciativas.columns and "nombre_iniciativa" not in iniciativas.columns:
    iniciativas = iniciativas.rename(columns={"nombre":"nombre_iniciativa"})
if "responsable" not in iniciativas.columns:
    iniciativas["responsable"] = "-"
if "nombre_iniciativa" not in iniciativas.columns:
    iniciativas["nombre_iniciativa"] = "-"

today = date.today()
iniciativas["vencida"] = iniciativas["fecha_fin"].apply(
    lambda x: (x is not None) and pd.notna(x) and x < today)
iniciativas["critica"] = iniciativas.apply(
    lambda r: (str(r["estado"]).strip() == "Atrasada") or
              (bool(r["vencida"]) and str(r["estado"]).strip() != "Finalizada"),
    axis=1,
)

if not servicios.empty and "servicio" in servicios.columns:
    servicios_activos = servicios.copy()
    if "activo" in servicios_activos.columns:
        servicios_activos = servicios_activos[servicios_activos["activo"] == 1]
    if "orden" in servicios_activos.columns:
        servicios_activos = servicios_activos.sort_values("orden")
    servicios_lista = servicios_activos["servicio"].dropna().astype(str).tolist()
else:
    servicios_lista = sorted(kpis["servicio"].dropna().astype(str).unique().tolist())

periodos = sorted(kpis["periodo"].dropna().astype(str).unique().tolist())
default_period_index = len(periodos) - 1 if periodos else 0

# =========================================================
# ENCABEZADO
# =========================================================
st.markdown("<div class='hero-shell'>", unsafe_allow_html=True)
hero_left, hero_right = st.columns([4.8, 1.55])

with hero_left:
    logo_col, title_col = st.columns([0.9, 4.6])
    with logo_col:
        for logo_path in [Path(__file__).resolve().parent / "assets" / "logoefe-azul.png",
                          Path(__file__).resolve().parent / "logoefe-azul.png"]:
            if logo_path.exists():
                st.image(str(logo_path), use_container_width=True)
                break
    with title_col:
        st.markdown("<div class='hero-kicker'>Seguimiento ejecutivo</div>", unsafe_allow_html=True)
        st.markdown("<div class='main-title'>KPIs e Iniciativas — Gerencia de Pasajeros</div>", unsafe_allow_html=True)
        st.markdown("<div class='subtitle'>Panel ejecutivo para monitorear desempeño, gestión de iniciativas, estaciones y perfiles de carga por servicio.</div>", unsafe_allow_html=True)

with hero_right:
    periodo_sel = st.selectbox("Período de análisis", options=periodos,
                                index=default_period_index, key="periodo_top")
    st.markdown("<div class='hero-side-note'>Vista ejecutiva para seguimiento y lectura rápida.</div>",
                unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# FILTROS
# =========================================================
estados_ini  = sorted(iniciativas["estado"].dropna().astype(str).unique().tolist())
prioridades  = sorted(iniciativas["prioridad"].dropna().astype(str).unique().tolist())
responsables = sorted(iniciativas["responsable"].dropna().astype(str).unique().tolist())

servicios_sel    = servicios_lista
estados_ini_sel  = estados_ini
prioridades_sel  = prioridades
responsables_sel = responsables

toolbar_left, toolbar_right = st.columns([4.6, 1.0])
with toolbar_right:
    popover_ctx = st.popover if hasattr(st, "popover") else st.expander
    pop_kwargs  = {} if hasattr(st, "popover") else {"expanded": False}
    with popover_ctx("Filtros", **pop_kwargs):
        servicios_sel = st.multiselect(
            "Servicio", options=servicios_lista, default=servicios_lista, key="servicios_body_filter")
        estados_ini_sel = st.multiselect(
            "Estado iniciativa", options=estados_ini, default=estados_ini, key="estado_body_filter")
        prioridades_sel = st.multiselect(
            "Prioridad", options=prioridades, default=prioridades, key="prioridad_body_filter")
        responsables_sel = st.multiselect(
            "Responsable", options=responsables, default=responsables, key="responsable_body_filter")
        if st.button("Restablecer filtros", key="reset_filters_btn", use_container_width=True):
            for k, v in [("servicios_body_filter", servicios_lista),
                         ("estado_body_filter", estados_ini),
                         ("prioridad_body_filter", prioridades),
                         ("responsable_body_filter", responsables)]:
                st.session_state[k] = v
            st.rerun()
        st.caption(f"Origen de datos: {data_path}")

servicios_sel    = servicios_sel    or servicios_lista
estados_ini_sel  = estados_ini_sel  or estados_ini
prioridades_sel  = prioridades_sel  or prioridades
responsables_sel = responsables_sel or responsables

with toolbar_left:
    summary = summarize_active_filters(servicios_sel, servicios_lista, estados_ini_sel,
                                        estados_ini, prioridades_sel, prioridades,
                                        responsables_sel, responsables)
    chips   = build_filter_chip_row(servicios_sel, servicios_lista, estados_ini_sel,
                                    estados_ini, prioridades_sel, prioridades,
                                    responsables_sel, responsables)
    st.markdown(f"<div class='toolbar-panel'>"
                f"<div class='filters-summary'><strong>Filtros activos:</strong> {summary}</div>"
                f"{chips}</div>", unsafe_allow_html=True)

# =========================================================
# FILTRADO PRINCIPAL
# =========================================================
kpis_f = kpis[
    (kpis["periodo"].astype(str) == str(periodo_sel)) &
    (kpis["servicio"].isin(servicios_sel))
].copy()

iniciativas_f = iniciativas[
    iniciativas["servicio"].isin(servicios_sel) &
    iniciativas["estado"].isin(estados_ini_sel) &
    iniciativas["prioridad"].isin(prioridades_sel) &
    iniciativas["responsable"].isin(responsables_sel)
].copy()

kpis_hist = kpis[kpis["servicio"].isin(servicios_sel)].copy()

if "orden" in kpis_f.columns:
    kpis_f = kpis_f.sort_values(["orden","servicio","nombre"])
else:
    kpis_f = kpis_f.sort_values(["nombre","servicio"])

# =========================================================
# NAVEGACIÓN
# =========================================================
with st.container():
    st.markdown("<span class='sticky-nav-anchor'></span>", unsafe_allow_html=True)
    st.markdown("<div class='nav-panel'>", unsafe_allow_html=True)
    section_sel = option_selector(
        "Navegación",
        ["KPIs por Servicio","Personas","Estaciones","Perfil de Carga","OD Estaciones"],
        key="main_nav_selector", default="KPIs por Servicio", horizontal=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# SECCIONES
# =========================================================

def render_resumen_ejecutivo():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>KPIs por Servicio</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>KPIs del período por servicio y evolución histórica del indicador seleccionado.</div>",
                unsafe_allow_html=True)

    servicios_con_datos = [s for s in servicios_sel
                           if s in kpis_f["servicio"].astype(str).unique().tolist()]
    if kpis_f.empty or not servicios_con_datos:
        st.warning("No existen KPIs para los filtros seleccionados.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    resumen_srv = option_selector("Servicio visible", servicios_con_datos,
                                   key="resumen_servicio_selector",
                                   default=servicios_con_datos[0], horizontal=True)

    servicio_df = kpis_f[kpis_f["servicio"].astype(str) == str(resumen_srv)].copy()
    if "orden" in servicio_df.columns:
        servicio_df = servicio_df.sort_values(["orden","nombre","categoria"])
    else:
        servicio_df = servicio_df.sort_values(["nombre","categoria"])

    st.markdown(f"<div class='service-title'>{resumen_srv}</div>", unsafe_allow_html=True)

    if not servicio_df.empty:
        cols_por_fila = 3 if len(servicio_df) >= 3 else max(1, len(servicio_df))
        for i in range(0, len(servicio_df), cols_por_fila):
            row_df = servicio_df.iloc[i:i+cols_por_fila]
            row_cols = st.columns(cols_por_fila)
            for idx, (_, row) in enumerate(row_df.iterrows()):
                with row_cols[idx]:
                    render_kpi_card(
                        str(row["nombre"]),
                        fmt_number(row["valor"], row["unidad"], row["nombre"]),
                        f"Meta: {fmt_number(row['meta'], row['unidad'], row['nombre'])}",
                        f"Desviación: {fmt_pct(row['variacion_pct'])}",
                        row["estado"],
                    )
                    render_observation_box(row.get("observacion", None))

    st.markdown("<div class='section-title'>Evolución del KPI seleccionado</div>", unsafe_allow_html=True)
    hist_service = kpis_hist[kpis_hist["servicio"].astype(str) == str(resumen_srv)].copy()
    nombres_kpi  = sorted(hist_service["nombre"].dropna().astype(str).unique().tolist())

    resumen_kpi_sel = option_selector("KPI a visualizar", nombres_kpi,
                                       key="kpi_hist_sel_resumen",
                                       default=nombres_kpi[0] if nombres_kpi else None,
                                       horizontal=True)
    if not nombres_kpi or not resumen_kpi_sel:
        st.info("No hay datos históricos para el servicio seleccionado.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    hist_sel = hist_service[hist_service["nombre"] == resumen_kpi_sel].copy()
    hist_sel = scale_kpi_dataframe_for_display(hist_sel, resumen_kpi_sel, ("valor","meta"))
    unit_hist = (hist_sel["unidad"].dropna().astype(str).iloc[0]
                 if not hist_sel.empty and "unidad" in hist_sel.columns
                 and not hist_sel["unidad"].dropna().empty else None)

    if hist_sel.empty:
        st.info("No hay datos históricos para el KPI seleccionado.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # Gráfico con tendencia (nuevo)
    hist_plot = hist_sel.groupby("periodo", as_index=False)["valor"].sum()
    tab1, tab2, tab3 = st.tabs(["📈 Evolución", "📉 Tendencia", "⚠️ Anomalías"])
    with tab1:
        fig_svc = build_line_chart(hist_plot, f"{resumen_kpi_sel} — {resumen_srv}",
                                    height=370, unit=unit_hist, kpi_name=resumen_kpi_sel)
        fig_svc.update_traces(line_color=EFE_BLUE)
        st.plotly_chart(fig_svc, use_container_width=True)
    with tab2:
        fig_trend = build_trend_line_chart(hist_plot, resumen_kpi_sel, unit_hist, resumen_srv)
        st.plotly_chart(fig_trend, use_container_width=True)
    with tab3:
        fig_anom = detect_anomalies(hist_plot, resumen_kpi_sel, resumen_srv, unit_hist)
        st.plotly_chart(fig_anom, use_container_width=True)

    st.markdown("</div></div>", unsafe_allow_html=True)


def render_kpis():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Análisis de KPIs</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Evolución, contraste con meta y detalle del indicador seleccionado.</div>",
                unsafe_allow_html=True)

    nombres_kpi = sorted(kpis["nombre"].dropna().astype(str).unique().tolist())
    kpi_sel = option_selector("Seleccione KPI", nombres_kpi, key="kpi_analisis",
                               default=nombres_kpi[0] if nombres_kpi else None)

    hist_kpi = kpis_hist[kpis_hist["nombre"] == kpi_sel].copy()
    hist_kpi = scale_kpi_dataframe_for_display(hist_kpi, kpi_sel, ("valor","meta"))
    unit_col  = (hist_kpi["unidad"].dropna().astype(str).iloc[0]
                 if not hist_kpi.empty and "unidad" in hist_kpi.columns
                 and not hist_kpi["unidad"].dropna().empty else None)

    st.markdown("<div class='section-title'>Evolución por grupos de servicio</div>", unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        bt_hist = hist_kpi[hist_kpi["servicio"] == "Biotren"].copy()
        if bt_hist.empty:
            st.info("No hay datos de Biotren para el KPI seleccionado.")
        else:
            fig_bt = build_line_chart(bt_hist.groupby("periodo", as_index=False)["valor"].sum(),
                                       f"{kpi_sel} — Biotren", height=340,
                                       unit=unit_col, kpi_name=kpi_sel)
            fig_bt.update_traces(line_color=EFE_BLUE)
            st.plotly_chart(fig_bt, use_container_width=True)
    with col_b:
        otros_hist = hist_kpi[hist_kpi["servicio"].isin(RURAL_SERVICES)].copy()
        if otros_hist.empty:
            st.info("No hay datos de otros servicios para el KPI seleccionado.")
        else:
            fig_ot = build_line_chart(
                otros_hist.groupby(["periodo","servicio"], as_index=False)["valor"].sum(),
                f"{kpi_sel} — Otros servicios", color="servicio",
                height=340, unit=unit_col, kpi_name=kpi_sel)
            st.plotly_chart(fig_ot, use_container_width=True)

    st.markdown("<div class='section-title'>Valor vs meta por servicio</div>", unsafe_allow_html=True)
    actual = kpis_f[kpis_f["nombre"] == kpi_sel].copy()
    actual = scale_kpi_dataframe_for_display(actual, kpi_sel, ("valor","meta"))
    if not actual.empty:
        servicios_actuales = ([s for s in servicios_sel if s in actual["servicio"].astype(str).unique()]
                              or actual["servicio"].dropna().astype(str).unique().tolist())
        cols_por_fila = 2 if len(servicios_actuales) > 1 else 1
        for i in range(0, len(servicios_actuales), cols_por_fila):
            row_services = servicios_actuales[i:i+cols_por_fila]
            row_cols = st.columns(cols_por_fila)
            for j, servicio in enumerate(row_services):
                sdf = actual[actual["servicio"].astype(str) == str(servicio)].copy()
                with row_cols[j]:
                    if sdf.empty:
                        st.info(f"No hay datos para {servicio}.")
                    else:
                        unidad = sdf["unidad"].iloc[0]
                        fig_meta = go.Figure()
                        fig_meta.add_trace(go.Bar(
                            x=["Valor","Meta"],
                            y=[sdf["valor"].sum(), sdf["meta"].sum()],
                            marker_color=[EFE_BLUE, EFE_RED],
                            text=[fmt_number(sdf["valor"].sum(), unidad, kpi_sel),
                                  fmt_number(sdf["meta"].sum(),  unidad, kpi_sel)],
                            textposition="outside", showlegend=False,
                        ))
                        fig_meta.update_layout(
                            title=f"{servicio} — {periodo_sel}",
                            plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
                            margin=dict(l=20,r=20,t=50,b=20), height=340,
                            font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
                        )
                        st.plotly_chart(fig_meta, use_container_width=True)
    else:
        st.info("No hay datos para el KPI seleccionado en el período actual.")

    st.markdown("<div class='section-title'>Detalle del KPI</div>", unsafe_allow_html=True)
    detalle_cols = ["servicio","categoria","valor","meta","unidad","variacion_pct","estado"]
    if "observacion" in kpis_f.columns:
        detalle_cols.append("observacion")
    detalle_kpi = kpis_f[kpis_f["nombre"] == kpi_sel][detalle_cols].copy()
    if not detalle_kpi.empty:
        detalle_kpi["Valor"]    = detalle_kpi.apply(lambda r: fmt_number(r["valor"], r["unidad"], kpi_sel), axis=1)
        detalle_kpi["Meta"]     = detalle_kpi.apply(lambda r: fmt_number(r["meta"],  r["unidad"], kpi_sel), axis=1)
        detalle_kpi["Variación"]= detalle_kpi["variacion_pct"].apply(fmt_pct)
        show_cols  = ["servicio","categoria","Valor","Meta","Variación","estado"]
        rename_map = {"servicio":"Servicio","categoria":"Categoría","estado":"Estado"}
        if "observacion" in detalle_kpi.columns:
            show_cols.append("observacion")
            rename_map["observacion"] = "Observación"
        st.dataframe(detalle_kpi[show_cols].rename(columns=rename_map),
                     use_container_width=True, hide_index=True)
    else:
        st.info("No existe detalle para el KPI seleccionado.")
    st.markdown("</div></div>", unsafe_allow_html=True)


def render_personas():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Vista por persona</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Seguimiento de iniciativas, avance y estado por responsable.</div>",
                unsafe_allow_html=True)

    total_ini   = len(iniciativas_f)
    en_curso    = int((iniciativas_f["estado"] == "En curso").sum())
    atrasadas   = int((iniciativas_f["estado"] == "Atrasada").sum())
    finalizadas = int((iniciativas_f["estado"] == "Finalizada").sum())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total iniciativas", total_ini)
    m2.metric("En curso", en_curso)
    m3.metric("Atrasadas", atrasadas)
    m4.metric("Finalizadas", finalizadas)

    personas_opts = sorted(iniciativas_f["responsable"].dropna().astype(str).unique().tolist())
    persona_sel = option_selector("Seleccione responsable", personas_opts,
                                   key="persona_selector",
                                   default=personas_opts[0] if personas_opts else None)
    if not personas_opts or not persona_sel:
        st.warning("No hay responsables disponibles con los filtros actuales.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    per_df = iniciativas_f[iniciativas_f["responsable"] == persona_sel].copy()
    avance_prom = float(per_df["avance_pct"].mean()) if not per_df.empty else 0

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Asignadas",    len(per_df))
    p2.metric("Finalizadas",  int((per_df["estado"] == "Finalizada").sum()))
    p3.metric("Atrasadas",    int((per_df["estado"] == "Atrasada").sum()))
    p4.metric("Avance promedio", fmt_pct(avance_prom))

    left_p, right_p = st.columns([1.2, 0.8])
    with left_p:
        if per_df.empty:
            st.info("No hay iniciativas para el responsable seleccionado.")
        else:
            fig = px.bar(per_df.sort_values("avance_pct"), x="avance_pct",
                         y="nombre_iniciativa", orientation="h",
                         title=f"Avance por iniciativa — {persona_sel}", text="avance_pct")
            fig.update_traces(marker_color=EFE_BLUE)
            fig.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
                              margin=dict(l=20,r=20,t=50,b=20), height=420,
                              font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16))
            fig.update_xaxes(title="Avance %"); fig.update_yaxes(title="")
            st.plotly_chart(fig, use_container_width=True)
    with right_p:
        estado_persona = per_df["estado"].value_counts().reset_index()
        estado_persona.columns = ["estado","cantidad"]
        if not estado_persona.empty:
            fig2 = px.bar(estado_persona, x="estado", y="cantidad",
                          title="Distribución por estado", color="estado",
                          color_discrete_map={"Planificada":TEXT_MUTED,"En curso":EFE_BLUE,
                                              "Atrasada":EFE_RED,"Finalizada":SUCCESS,"Pausada":WARNING})
            fig2.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
                               margin=dict(l=20,r=20,t=50,b=20), height=420,
                               font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16),
                               showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<div class='section-title'>Detalle por responsable</div>", unsafe_allow_html=True)
    detalle_cols = ["nombre_iniciativa","servicio","estado","avance_pct",
                    "fecha_inicio","fecha_fin","prioridad","comentario"]
    if "criticidad" in per_df.columns:
        detalle_cols.insert(-1, "criticidad")
    detalle_cols = [c for c in detalle_cols if c in per_df.columns]
    rename_map = {"nombre_iniciativa":"Iniciativa","servicio":"Servicio","estado":"Estado",
                  "avance_pct":"Avance %","fecha_inicio":"Inicio","fecha_fin":"Fin",
                  "prioridad":"Prioridad","comentario":"Comentario","criticidad":"Criticidad"}
    st.dataframe(per_df[detalle_cols].rename(columns=rename_map),
                 use_container_width=True, hide_index=True)
    st.markdown("</div></div>", unsafe_allow_html=True)


def render_detalle_servicio():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Estaciones</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Afluencia por estación y lectura territorial del servicio seleccionado.</div>",
                unsafe_allow_html=True)
    st.markdown("<div class='map-note'>Vista georreferenciada de afluencia registrada vs meta por estación.</div>",
                unsafe_allow_html=True)

    if estaciones.empty or afluencia_estacion.empty:
        st.info("Para habilitar esta vista, agregue estaciones.csv y afluencia_estacion.csv al repositorio.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    estaciones_activas = estaciones[estaciones["activa"] == 1].copy()
    servicios_detalle  = sorted(
        set(estaciones_activas["servicio"].dropna().astype(str)) &
        set(afluencia_estacion["servicio"].dropna().astype(str))
    )
    servicios_detalle = [s for s in servicios_lista if s in servicios_detalle] or servicios_detalle

    if not servicios_detalle:
        st.warning("No existen servicios comunes entre estaciones.csv y afluencia_estacion.csv.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    default_srv = servicios_sel[0] if len(servicios_sel) == 1 and servicios_sel[0] in servicios_detalle else servicios_detalle[0]
    sel_col1, sel_col2 = st.columns([1.35, 1])
    with sel_col1:
        detalle_srv = option_selector("Servicio georreferenciado", servicios_detalle,
                                       key="detalle_servicio_selector",
                                       default=default_srv)

    periodos_detalle = sorted(
        afluencia_estacion[afluencia_estacion["servicio"].astype(str) == str(detalle_srv)]
        ["periodo"].dropna().astype(str).unique().tolist()
    )
    if not periodos_detalle:
        st.warning("No existen períodos disponibles para el servicio seleccionado.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    default_per = str(periodo_sel) if str(periodo_sel) in periodos_detalle else periodos_detalle[-1]
    with sel_col2:
        detalle_per = option_selector("Período de detalle", periodos_detalle,
                                       key="detalle_periodo_selector", default=default_per)

    estaciones_srv = estaciones_activas[estaciones_activas["servicio"].astype(str) == str(detalle_srv)].copy()
    if "orden_trazado" in estaciones_srv.columns:
        estaciones_srv = estaciones_srv.sort_values(["orden_trazado","estacion"])
    else:
        estaciones_srv = estaciones_srv.sort_values("estacion")

    afluencia_srv = afluencia_estacion[
        (afluencia_estacion["servicio"].astype(str) == str(detalle_srv)) &
        (afluencia_estacion["periodo"].astype(str) == str(detalle_per))
    ].copy()

    detail_df = estaciones_srv.merge(afluencia_srv, how="left", on=["id_estacion","servicio"],
                                      suffixes=("_est","_afl"))
    for col in ["entradas","meta_entradas","perdida_pax","fuga_pct"]:
        detail_df[col] = pd.to_numeric(detail_df.get(col), errors="coerce")
    detail_df["fuga_pct_display"]     = detail_df["fuga_pct"].apply(maybe_scale_percent)
    detail_df["observacion_estacion"] = detail_df.get("observacion_est",  detail_df.get("observacion_x", None))
    detail_df["observacion_afluencia"]= detail_df.get("observacion_afl", detail_df.get("observacion_y", None))

    valid_map_df = detail_df.dropna(subset=["latitud","longitud"]).copy()
    bar_df = detail_df[["estacion","entradas","meta_entradas"]].copy()

    if "orden_trazado" in detail_df.columns:
        station_order = (detail_df.sort_values(["orden_trazado","estacion"])
                         ["estacion"].dropna().astype(str).tolist())
    else:
        station_order = sorted(bar_df["estacion"].dropna().astype(str).tolist())

    bar_df["entradas"]      = pd.to_numeric(bar_df["entradas"],      errors="coerce").fillna(0)
    bar_df["meta_entradas"] = pd.to_numeric(bar_df["meta_entradas"], errors="coerce").fillna(0)

    top_left, top_right = st.columns([0.95, 1.05])
    with top_left:
        if valid_map_df.empty:
            st.warning("No existen coordenadas válidas para graficar.")
        else:
            st.plotly_chart(build_station_map(valid_map_df), use_container_width=True)
    with top_right:
        total_entradas = detail_df["entradas"].sum(min_count=1)
        total_meta     = detail_df["meta_entradas"].sum(min_count=1)
        total_perdida  = detail_df["perdida_pax"].sum(min_count=1)
        fuga_prom      = detail_df["fuga_pct_display"].mean()
        m1, m2 = st.columns(2); m3, m4 = st.columns(2)
        m1.metric("Afluencia", fmt_pax(total_entradas))
        m2.metric("Meta afluencia", fmt_pax(total_meta))
        m3.metric("Pérdida total", fmt_pax(total_perdida))
        m4.metric("Fuga promedio", fmt_fuga_pct(fuga_prom))

        if not bar_df.empty:
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(x=bar_df["estacion"], y=bar_df["entradas"],
                                     name="Afluencia", marker_color=EFE_BLUE))
            fig_bar.add_trace(go.Bar(x=bar_df["estacion"], y=bar_df["meta_entradas"],
                                     name="Meta", marker_color=EFE_RED))
            fig_bar.update_layout(
                title="Afluencia vs meta por estación",
                plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
                margin=dict(l=20,r=20,t=50,b=20), height=465,
                barmode="group", font=dict(color=TEXT_MAIN),
                title_font=dict(color=EFE_BLUE, size=16),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig_bar.update_xaxes(title="", tickangle=-90, categoryorder="array",
                                  categoryarray=station_order)
            fig_bar.update_yaxes(title="Pasajeros")
            st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("<div class='section-title'>Detalle de estaciones</div>", unsafe_allow_html=True)
    detail_table = detail_df[["estacion","comuna","region","entradas","meta_entradas",
                               "perdida_pax","fuga_pct_display",
                               "observacion_afluencia","observacion_estacion"]].copy()
    detail_table["Afluencia"]      = detail_table["entradas"].apply(fmt_pax)
    detail_table["Meta afluencia"] = detail_table["meta_entradas"].apply(fmt_pax)
    detail_table["Pérdida pax"]    = detail_table["perdida_pax"].apply(fmt_pax)
    detail_table["Fuga %"]         = detail_table["fuga_pct_display"].apply(fmt_fuga_pct)
    st.dataframe(
        detail_table[["estacion","comuna","region","Afluencia","Meta afluencia",
                       "Pérdida pax","Fuga %","observacion_afluencia","observacion_estacion"]]
        .rename(columns={"estacion":"Estación","comuna":"Comuna","region":"Región",
                         "observacion_afluencia":"Obs. afluencia","observacion_estacion":"Obs. estación"}),
        use_container_width=True, hide_index=True,
    )
    st.markdown("</div></div>", unsafe_allow_html=True)


def render_perfil_carga():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Perfil de Carga</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Lectura diaria por servicio: pasajeros a bordo, embarques y bajadas por estación.</div>",
                unsafe_allow_html=True)

    service_options = list(PROFILE_SERVICE_CONFIG.keys())
    sel_service_col, sel_date_col, info_col = st.columns([1.15, 1.05, 1.8])
    with sel_service_col:
        profile_srv = st.selectbox("Servicio de perfil", options=service_options,
                                    index=0, key="profile_service_root_selector")

    perfil_df, perfil_path, perfil_missing, perfil_files, perfil_status = load_profile_service_data(
        profile_srv, str(data_path))
    folder_name  = PROFILE_SERVICE_CONFIG.get(profile_srv, {}).get("folder_candidates", ["perfil_carga"])[0]
    service_desc = PROFILE_SERVICE_CONFIG.get(profile_srv, {}).get("description", "")

    with info_col:
        st.markdown(f"<div class='map-note'><b>Carpeta esperada:</b> {folder_name}<br>{service_desc}</div>",
                    unsafe_allow_html=True)

    if perfil_status in ("no_data",) or perfil_df.empty:
        with sel_date_col:
            st.selectbox("📅 Fecha disponible", options=[], index=None,
                         placeholder="Sin fechas disponibles", key="perfil_fecha_selector_empty")
        st.info(f"No se encontraron archivos CSV para <b>{profile_srv}</b>. "
                f"Cree la carpeta <b>{folder_name}</b> y agregue los archivos diarios. "
                f"Ruta buscada: <b>{perfil_path}</b>.", icon="ℹ️")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    if perfil_status == "unsupported_format" or perfil_missing:
        with sel_date_col:
            fechas_tmp = sorted(pd.to_datetime(perfil_df.get("fecha"), errors="coerce")
                                .dropna().dt.date.unique().tolist(), reverse=True) \
                         if "fecha" in perfil_df.columns else []
            st.selectbox("📅 Fecha disponible", options=fechas_tmp, index=0 if fechas_tmp else None,
                         placeholder="Sin fechas válidas", key="perfil_fecha_selector_unsupported",
                         format_func=lambda d: pd.to_datetime(d).strftime("%d-%m-%Y") if pd.notna(d) else "-")
        st.warning(f"Archivos detectados, pero formato no compatible. "
                   f"Columnas faltantes: <b>{', '.join(perfil_missing)}</b>.")
        if perfil_files:
            st.caption(f"Archivos detectados: {len(perfil_files)} | carpeta: {perfil_path}")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_disponibles = sorted(perfil_df["fecha"].dropna().unique().tolist())
    if not fechas_disponibles:
        st.warning("No existen fechas válidas en los archivos de perfil de carga.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_set   = set(fechas_disponibles)
    fecha_default= fechas_disponibles[-1]
    fecha_key    = f"perfil_fecha_cal_{profile_srv}"
    fecha_prev   = st.session_state.get(fecha_key)
    if isinstance(fecha_prev, date):
        fecha_default = (fecha_prev if fecha_prev in fechas_set
                         else min(fechas_disponibles, key=lambda d: abs((d-fecha_prev).days)))

    with sel_date_col:
        fecha_sel_input = st.date_input("📅 Fecha", value=fecha_default,
                                         min_value=fechas_disponibles[0],
                                         max_value=fechas_disponibles[-1],
                                         format="DD/MM/YYYY", key=fecha_key)

    fecha_sel = fecha_sel_input
    if fecha_sel not in fechas_set:
        fecha_sel = min(fechas_disponibles, key=lambda d: abs((d-fecha_sel).days))
        st.info(f"Fecha sin datos. Se usa la más cercana: "
                f"{pd.to_datetime(fecha_sel).strftime('%d-%m-%Y')}.")

    perfil_fecha = perfil_df[perfil_df["fecha"] == fecha_sel].copy()
    lineas_disp  = sorted([x for x in perfil_fecha["linea"].dropna().astype(str).unique() if x])

    row_sel_2a, row_sel_2b, row_sel_2c = st.columns([0.9, 1.15, 1.15])
    with row_sel_2a:
        linea_sel = option_selector("Línea", lineas_disp,
                                     key=f"perfil_linea_selector_{profile_srv}",
                                     default=lineas_disp[0] if lineas_disp else None)

    perfil_linea = (perfil_fecha[perfil_fecha["linea"].astype(str) == str(linea_sel)].copy()
                    if linea_sel else perfil_fecha.iloc[0:0].copy())
    direcciones_disp = sorted([x for x in perfil_linea["direccion"].dropna().astype(str).unique() if x])

    with row_sel_2b:
        dir_sel = option_selector("Dirección", direcciones_disp,
                                   key=f"perfil_direccion_selector_{profile_srv}",
                                   default=direcciones_disp[0] if direcciones_disp else None)

    perfil_dir = (perfil_linea[perfil_linea["direccion"].astype(str) == str(dir_sel)].copy()
                  if dir_sel else perfil_linea.iloc[0:0].copy())
    servicios_disp = sorted(perfil_dir["servicio_label"].dropna().astype(str).unique(),
                             key=lambda x: (len(x), x))

    with row_sel_2c:
        servicio_sel = (st.selectbox("Servicio específico", options=servicios_disp,
                                      index=0 if servicios_disp else None,
                                      placeholder="Sin servicios disponibles",
                                      key=f"perfil_servicio_selector_{profile_srv}")
                        if servicios_disp else None)

    if perfil_dir.empty or not servicio_sel:
        st.warning("No existen datos para la combinación seleccionada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    perfil_servicio = perfil_dir[perfil_dir["servicio_label"].astype(str) == str(servicio_sel)].copy()
    perfil_servicio["event_time"] = perfil_servicio["t_arr_est"].fillna(perfil_servicio["t_dep_est"])
    station_order = get_station_order_from_profile(perfil_servicio)
    if station_order:
        perfil_servicio["estacion"] = pd.Categorical(perfil_servicio["estacion"],
                                                      categories=station_order, ordered=True)
        perfil_servicio = perfil_servicio.sort_values(["estacion","event_time"])

    total_embarque = perfil_servicio["B_embarque"].sum(min_count=1)
    total_bajadas  = perfil_servicio["D_bajadas"].sum(min_count=1)
    max_abordo     = perfil_servicio["L_out_abordo"].max()
    capacidad_col  = perfil_servicio.get("capacidad_tren", pd.Series([], dtype=float))
    capacidad      = (float(capacidad_col.dropna().iloc[0])
                      if "capacidad_tren" in perfil_servicio.columns
                      and perfil_servicio["capacidad_tren"].dropna().any() else None)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Servicios del día",      perfil_dir["servicio_label"].nunique())
    m2.metric("Embarques del servicio", fmt_pax(total_embarque))
    m3.metric("Bajadas del servicio",   fmt_pax(total_bajadas))
    m4.metric("Máximo a bordo",         fmt_pax(max_abordo))

    titulo = f"{profile_srv} | {linea_sel} | {dir_sel} | Servicio {servicio_sel}"
    st.plotly_chart(build_perfil_carga_chart(perfil_servicio, titulo), use_container_width=True)

    if capacidad and pd.notna(max_abordo) and float(capacidad) != 0:
        st.caption(f"Capacidad tren: {fmt_pax(capacidad)} · "
                   f"Ocupación máxima: {fmt_pct((float(max_abordo)/float(capacidad))*100)}")
    elif perfil_files:
        st.caption(f"Archivos cargados: {len(perfil_files)} | carpeta: {perfil_path}")

    st.markdown("<div class='section-title'>Comparativo diario de pasajeros a bordo</div>",
                unsafe_allow_html=True)
    fig_comp = build_perfil_abordo_comparativo_chart(
        perfil_dir, f"{profile_srv} | {linea_sel} | {dir_sel} | Todos los servicios")
    st.plotly_chart(fig_comp, use_container_width=True)

    st.markdown("<div class='section-title'>Detalle por estación</div>", unsafe_allow_html=True)
    detalle_cols = ["estacion","t_arr_est","t_dep_est","B_embarque","D_bajadas",
                    "L_in_abordo","L_out_abordo","Capacidad_disponible","R_quedados",
                    "Q_out_cola","archivo_origen"]
    detalle_cols = [c for c in detalle_cols if c in perfil_servicio.columns]
    detalle = perfil_servicio[detalle_cols].copy()

    fmt_map = {
        "t_arr_est": ("Llegada",  lambda s: pd.to_datetime(s, errors="coerce").dt.strftime("%H:%M:%S").fillna("-")),
        "t_dep_est": ("Salida",   lambda s: pd.to_datetime(s, errors="coerce").dt.strftime("%H:%M:%S").fillna("-")),
        "B_embarque":("Suben",    lambda s: s.apply(fmt_pax)),
        "D_bajadas": ("Bajan",    lambda s: s.apply(fmt_pax)),
        "L_in_abordo":("A bordo entrada", lambda s: s.apply(fmt_pax)),
        "L_out_abordo":("A bordo salida", lambda s: s.apply(fmt_pax)),
        "Capacidad_disponible":("Cap. disponible", lambda s: s.apply(fmt_pax)),
        "R_quedados":("Quedados", lambda s: s.apply(fmt_pax)),
        "Q_out_cola":("Cola salida", lambda s: s.apply(fmt_pax)),
        "archivo_origen":("Archivo", lambda s: s),
    }
    for raw_col, (new_col, fn) in fmt_map.items():
        if raw_col in detalle.columns:
            detalle[new_col] = fn(detalle[raw_col])

    show_cols = ["estacion"] + [v[0] for k,v in fmt_map.items() if k in detalle.columns]
    show_cols = [c for c in show_cols if c in detalle.columns]
    st.dataframe(detalle[show_cols].rename(columns={"estacion":"Estación"}),
                 use_container_width=True, hide_index=True)
    st.markdown("</div></div>", unsafe_allow_html=True)


def render_od_estaciones():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>OD Estaciones — Biotren</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>Análisis centrado en la estación seleccionada: comportamiento horario, entradas, salidas y relaciones origen-destino por bloque de 1 hora. Carpeta: <b>od_bt</b>.</div>",
        unsafe_allow_html=True)

    od_df, od_path, od_missing, od_files, od_status = load_od_service_data("Biotren", str(data_path))
    folder_name = OD_SERVICE_CONFIG["Biotren"]["folder_candidates"][0]

    st.markdown(
        "<div class='map-note'><b>Enfoque:</b> lectura detallada estación por estación. Primero se define la fecha, línea y bloque horario; luego se revisa la estación específica y sus relaciones OD para ese periodo.</div>",
        unsafe_allow_html=True)

    if od_status == "no_data" or od_df.empty:
        st.info(f"No se encontraron archivos CSV en <b>{folder_name}</b>. Ruta buscada: <b>{od_path}</b>.", icon="ℹ️")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return
    if od_status == "unsupported_format" or od_missing:
        st.warning(f"Formato no compatible. Columnas faltantes: <b>{', '.join(od_missing)}</b>.")
        if od_files:
            st.caption(f"Archivos detectados: {len(od_files)} | carpeta: {od_path}")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_disponibles = sorted([x for x in od_df["fecha"].dropna().unique() if pd.notna(x)])
    if not fechas_disponibles:
        st.warning("No existen fechas válidas en la base OD cargada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_set = set(fechas_disponibles)
    fecha_default = fechas_disponibles[-1]
    fecha_key = "od_bt_fecha_cal"
    fecha_prev = st.session_state.get(fecha_key)
    if isinstance(fecha_prev, date):
        fecha_default = fecha_prev if fecha_prev in fechas_set else min(fechas_disponibles, key=lambda d: abs((d-fecha_prev).days))

    row_f1a, row_f1b = st.columns([1.0, 1.0])
    with row_f1a:
        fecha_input = st.date_input(
            "📅 Fecha",
            value=fecha_default,
            min_value=fechas_disponibles[0],
            max_value=fechas_disponibles[-1],
            format="DD/MM/YYYY",
            key=fecha_key,
        )

    fecha_sel = fecha_input
    if fecha_sel not in fechas_set:
        fecha_sel = min(fechas_disponibles, key=lambda d: abs((d-fecha_sel).days))
        st.info(f"Fecha sin datos. Se usa la más cercana: {pd.to_datetime(fecha_sel).strftime('%d-%m-%Y')}.")

    od_fecha = od_df[od_df["fecha"] == fecha_sel].copy()
    lineas_disp = sorted([x for x in od_fecha["linea"].dropna().astype(str).unique() if x])
    with row_f1b:
        linea_sel = option_selector("Línea", lineas_disp, key="od_linea_selector",
                                    default=lineas_disp[0] if lineas_disp else None)

    od_linea = od_fecha[od_fecha["linea"].astype(str) == str(linea_sel)].copy() if linea_sel else od_fecha.iloc[0:0].copy()
    if od_linea.empty:
        st.warning("No existen datos para la combinación de fecha y línea seleccionada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    granularity_sel = "Bloques de 1 hora"
    od_linea["entry_bucket"] = get_time_bucket_series(od_linea["t_entrada_viaje"], granularity_sel)
    od_linea["exit_bucket"] = get_time_bucket_series(od_linea["t_salida_viaje"], granularity_sel)
    bucket_order = get_bucket_order(
        od_linea["entry_bucket"].dropna().tolist() + od_linea["exit_bucket"].dropna().tolist(),
        granularity_sel,
    )
    if not bucket_order:
        st.warning("No existen bloques horarios válidos para la fecha y línea seleccionadas.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    bucket_display_map = {b: b.replace('-', ' a ') for b in bucket_order}
    row_f2a, row_f2b = st.columns([1.0, 1.2])
    with row_f2a:
        default_bucket = st.session_state.get("od_bucket_selector_selectbox")
        if default_bucket not in bucket_order:
            default_bucket = bucket_order[0]
        bucket_sel = st.selectbox(
            "Bloque horario de análisis",
            options=bucket_order,
            index=bucket_order.index(default_bucket) if default_bucket in bucket_order else 0,
            format_func=lambda x: bucket_display_map.get(x, x),
            key="od_bucket_selector_selectbox",
        )

    bucket_entry_summary = (
        od_linea[od_linea["entry_bucket"] == bucket_sel]
        .groupby("origen", as_index=False).size()
        .rename(columns={"origen": "estacion", "size": "entradas"})
        .sort_values(["entradas", "estacion"], ascending=[False, True])
    )
    bucket_exit_summary = (
        od_linea[od_linea["exit_bucket"] == bucket_sel]
        .groupby("destino", as_index=False).size()
        .rename(columns={"destino": "estacion", "size": "salidas"})
        .sort_values(["salidas", "estacion"], ascending=[False, True])
    )

    top_entry_station = (
        f"{bucket_entry_summary.iloc[0]['estacion']} ({fmt_pax(bucket_entry_summary.iloc[0]['entradas'])})"
        if not bucket_entry_summary.empty else "-"
    )
    top_exit_station = (
        f"{bucket_exit_summary.iloc[0]['estacion']} ({fmt_pax(bucket_exit_summary.iloc[0]['salidas'])})"
        if not bucket_exit_summary.empty else "-"
    )
    total_entries_block = int(bucket_entry_summary["entradas"].sum()) if not bucket_entry_summary.empty else 0
    total_exits_block = int(bucket_exit_summary["salidas"].sum()) if not bucket_exit_summary.empty else 0

    with row_f2b:
        st.markdown(
            f"<div class='filters-summary'><strong>Resumen del bloque {bucket_display_map.get(bucket_sel, bucket_sel)}</strong> · Línea {linea_sel}</div>",
            unsafe_allow_html=True,
        )
        rm1, rm2, rm3, rm4 = st.columns(4)
        rm1.metric("Entradas bloque", fmt_pax(total_entries_block))
        rm2.metric("Salidas bloque", fmt_pax(total_exits_block))
        rm3.metric("Mayor entrada", top_entry_station)
        rm4.metric("Mayor salida", top_exit_station)

    station_ref = prepare_od_station_reference("Biotren", od_linea, estaciones)
    station_candidates = sorted(set(od_linea["origen"].dropna().astype(str)) | set(od_linea["destino"].dropna().astype(str)))
    default_station = station_candidates[0] if station_candidates else None
    prev_station = st.session_state.get("od_station_selector")
    if prev_station in station_candidates:
        default_station = prev_station

    station_sel = (st.selectbox(
        "Estación",
        options=station_candidates,
        index=(station_candidates.index(default_station) if station_candidates and default_station in station_candidates else 0),
        key="od_station_selector",
    ) if station_candidates else None)

    if not station_sel:
        st.warning("No existen estaciones disponibles para la selección actual.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    station_entries = (
        od_linea[od_linea["origen"].astype(str) == str(station_sel)]
        .groupby("entry_bucket", as_index=False).size()
        .rename(columns={"entry_bucket": "bucket", "size": "cantidad"})
    )
    station_entries["tipo"] = "Entradas"
    station_exits = (
        od_linea[od_linea["destino"].astype(str) == str(station_sel)]
        .groupby("exit_bucket", as_index=False).size()
        .rename(columns={"exit_bucket": "bucket", "size": "cantidad"})
    )
    station_exits["tipo"] = "Salidas"
    station_flow = pd.concat([station_entries, station_exits], ignore_index=True)
    station_flow = station_flow.dropna(subset=["bucket"]).copy()

    station_bucket_order = get_bucket_order(station_flow["bucket"].dropna().tolist(), "Bloques de 1 hora")
    if not station_bucket_order:
        station_bucket_order = bucket_order

    st.markdown("<div class='section-title'>Comportamiento horario de la estación seleccionada</div>", unsafe_allow_html=True)
    st.plotly_chart(
        build_station_flow_chart(station_flow, station_bucket_order, station_sel, "Bloques de 1 hora"),
        use_container_width=True,
    )

    total_entries_day = int(station_entries["cantidad"].sum()) if not station_entries.empty else 0
    total_exits_day = int(station_exits["cantidad"].sum()) if not station_exits.empty else 0
    peak_entry_row = station_entries.sort_values(["cantidad", "bucket"], ascending=[False, True]).head(1)
    peak_exit_row = station_exits.sort_values(["cantidad", "bucket"], ascending=[False, True]).head(1)
    peak_entry_label = f"{bucket_display_map.get(peak_entry_row.iloc[0]['bucket'], peak_entry_row.iloc[0]['bucket'])} ({fmt_pax(peak_entry_row.iloc[0]['cantidad'])})" if not peak_entry_row.empty else "-"
    peak_exit_label = f"{bucket_display_map.get(peak_exit_row.iloc[0]['bucket'], peak_exit_row.iloc[0]['bucket'])} ({fmt_pax(peak_exit_row.iloc[0]['cantidad'])})" if not peak_exit_row.empty else "-"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Entradas día", fmt_pax(total_entries_day))
    m2.metric("Salidas día", fmt_pax(total_exits_day))
    m3.metric("Hora punta entradas", peak_entry_label)
    m4.metric("Hora punta salidas", peak_exit_label)

    destinos_df = (
        od_linea[(od_linea["origen"].astype(str) == str(station_sel)) & (od_linea["entry_bucket"] == bucket_sel)]
        .groupby("destino", as_index=False).size()
        .rename(columns={"size": "viajes"})
        .sort_values(["viajes", "destino"], ascending=[False, True]).head(10)
    )
    origenes_df = (
        od_linea[(od_linea["destino"].astype(str) == str(station_sel)) & (od_linea["exit_bucket"] == bucket_sel)]
        .groupby("origen", as_index=False).size()
        .rename(columns={"size": "viajes"})
        .sort_values(["viajes", "origen"], ascending=[False, True]).head(10)
    )

    selected_entries = int(destinos_df["viajes"].sum()) if not destinos_df.empty else 0
    selected_exits = int(origenes_df["viajes"].sum()) if not origenes_df.empty else 0

    st.markdown(
        f"<div class='section-title'>Relaciones OD en el bloque {bucket_display_map.get(bucket_sel, bucket_sel)}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='section-subtitle'><b>{station_sel}</b> · Salidas desde estación: {fmt_pax(selected_entries)} · Llegadas hacia estación: {fmt_pax(selected_exits)}</div>",
        unsafe_allow_html=True,
    )

    map_from_title = f"Viajes desde {station_sel} | {bucket_display_map.get(bucket_sel, bucket_sel)}"
    map_to_title = f"Viajes hacia {station_sel} | {bucket_display_map.get(bucket_sel, bucket_sel)}"

    row_map1, row_map2 = st.columns(2)
    with row_map1:
        from_fig = build_od_connection_map(
            destinos_df,
            pd.DataFrame(columns=["origen", "viajes"]),
            station_ref,
            station_sel,
            bucket_sel,
            title_text=map_from_title,
        )
        if from_fig:
            st.plotly_chart(from_fig, use_container_width=True)
        else:
            st.info("Sin coordenadas válidas para el mapa de salidas desde la estación.")
        dest_fig = build_top_od_bar_chart(destinos_df, "destino", f"Principales destinos desde {station_sel}", EFE_BLUE)
        if dest_fig:
            st.plotly_chart(dest_fig, use_container_width=True)
        else:
            st.info("No existen viajes desde la estación en el bloque seleccionado.")

    with row_map2:
        to_fig = build_od_connection_map(
            pd.DataFrame(columns=["destino", "viajes"]),
            origenes_df,
            station_ref,
            station_sel,
            bucket_sel,
            title_text=map_to_title,
        )
        if to_fig:
            st.plotly_chart(to_fig, use_container_width=True)
        else:
            st.info("Sin coordenadas válidas para el mapa de llegadas hacia la estación.")
        ori_fig = build_top_od_bar_chart(origenes_df, "origen", f"Principales orígenes hacia {station_sel}", EFE_RED)
        if ori_fig:
            st.plotly_chart(ori_fig, use_container_width=True)
        else:
            st.info("No existen viajes hacia la estación en el bloque seleccionado.")

    if od_files:
        st.caption(f"Archivos OD cargados: {len(od_files)} | carpeta: {od_path}")
    st.markdown("</div></div>", unsafe_allow_html=True)


# =========================================================
# DISPATCH
# =========================================================
if section_sel == "KPIs por Servicio":
    render_resumen_ejecutivo()
elif section_sel == "Personas":
    render_personas()
elif section_sel == "Estaciones":
    render_detalle_servicio()
elif section_sel == "Perfil de Carga":
    render_perfil_carga()
elif section_sel == "OD Estaciones":
    render_od_estaciones()

# =========================================================
# PIE DE PÁGINA
# =========================================================
st.markdown("---")
st.caption(
    "Los archivos CSV se leen automáticamente desde el repositorio de GitHub, "
    "incluyendo carpetas dedicadas para perfiles de carga y datos OD por servicio.")
