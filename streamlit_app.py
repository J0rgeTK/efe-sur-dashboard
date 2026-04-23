"""
EFE Sur | KPIs e Iniciativas - Gerencia de Pasajeros
=====================================================
Versión optimizada v3 — mejoras de rendimiento y tiempo de carga:
  ─── Globales ────────────────────────────────────────────────────────────────
  • normalize_text decorado con @lru_cache(4096): elimina recomputación repetida
  • get_time_bucket_series vectorizado con np.select (elimina .apply fila a fila)
  • _MESES y _MESES_LARGO hoisted a nivel de módulo
  • scale_kpi_dataframe_for_display vectorizado con np.where
  • show_plot optimizado: usa update_xaxes/update_yaxes en vez de iterar fig.layout
  • PLOTLY_CHART_CONFIG deduplicado (una sola definición canónica)
  ─── Pestaña "Promedio mensual" (cuello de botella principal) ─────────────────
  • build_monthly_profile_tables_by_direction envuelto en @st.cache_data
    → la función solo se recalcula cuando cambian mes, línea o servicio
  • O(N²) onboard loop en build_transactional_service_profile reemplazado por
    numpy vectorizado con cumsum: O(N·K) → O(N) donde N=filas, K=estaciones
  • Itinerary/order lookups pre-computados una vez por llamada (no por día×dir)
  • classify_profile_day_type vectorizado con pd.Series.dt.weekday
  • Agregación mensual por servicio: iterrows() + groupby loop reemplazado por
    vectorized groupby.agg con pandas transform
  ─── Torniquetes ─────────────────────────────────────────────────────────────
  • Pre-filtro de fecha antes del merge reduce el producto cartesiano
  • Rename de columnas vectorizado con normalize_series
"""

# =========================================================
# IMPORTACIONES (sin duplicados)
# =========================================================
import unicodedata
from datetime import date
from functools import lru_cache
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


# PLOTLY_CHART_CONFIG definido más abajo junto a show_plot (única definición)

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

LIGHT_COLORS = dict(COLORS)
DARK_COLORS = {
    "EFE_BLUE":  "#8CB7FF",
    "EFE_RED":   "#FF7A86",
    "EFE_WHITE": "#0F172A",
    "BG_LIGHT":  "#020617",
    "BORDER":    "#334155",
    "TEXT_MAIN": "#E5E7EB",
    "TEXT_MUTED":"#94A3B8",
    "SUCCESS":   "#34D399",
    "WARNING":   "#FBBF24",
    "DANGER":    "#FB7185",
}

def apply_runtime_palette(palette: dict):
    global COLORS, EFE_BLUE, EFE_RED, EFE_WHITE, TEXT_MAIN, TEXT_MUTED, SUCCESS, WARNING, DANGER, BORDER
    COLORS = dict(palette)
    EFE_BLUE = COLORS["EFE_BLUE"]
    EFE_RED = COLORS["EFE_RED"]
    EFE_WHITE = COLORS["EFE_WHITE"]
    TEXT_MAIN = COLORS["TEXT_MAIN"]
    TEXT_MUTED = COLORS["TEXT_MUTED"]
    SUCCESS = COLORS["SUCCESS"]
    WARNING = COLORS["WARNING"]
    DANGER = COLORS["DANGER"]
    BORDER = COLORS["BORDER"]


def build_runtime_css(theme_mode: str, colors: dict) -> str:
    if theme_mode == "Oscuro":
        return f"""
        <style>
        .stApp {{
            background:
                radial-gradient(circle at top left, rgba(140,183,255,0.10) 0%, rgba(140,183,255,0.00) 22%),
                linear-gradient(180deg, #020617 0%, #0B1220 100%) !important;
            color: {colors['TEXT_MAIN']} !important;
        }}
        .hero-minimal {{ padding: 0.05rem 0 0.35rem; margin-bottom: 0.2rem; }}
        .main-title {{ color: {colors['TEXT_MAIN']} !important; margin-top: -0.1rem !important; }}
        .subtitle, .hero-side-note {{ color: {colors['TEXT_MUTED']} !important; }}
        .section-shell, .nav-panel, .efe-card, .map-note, .toolbar-panel,
        div[data-testid="stMetric"], div[data-testid="stPlotlyChart"] {{
            background: #111827 !important;
            border-color: {colors['BORDER']} !important;
            box-shadow: 0 8px 22px rgba(0,0,0,0.28) !important;
        }}
        .section-title, .service-title, .efe-card-value, .efe-card-delta, .efe-card-meta,
        .efe-card-title, .map-note, .filters-summary, .filter-chip {{ color: {colors['TEXT_MAIN']} !important; }}
        .section-subtitle {{ color: {colors['TEXT_MUTED']} !important; }}
        .filter-chip {{ background: #0F172A !important; border-color: {colors['BORDER']} !important; }}
        .stButton > button, .stDownloadButton > button {{
            background: #111827 !important; color: {colors['TEXT_MAIN']} !important; border-color: {colors['BORDER']} !important;
        }}
        div[data-baseweb="select"] > div {{
            background: #111827 !important; border-color: {colors['BORDER']} !important; color: {colors['TEXT_MAIN']} !important;
        }}
        .stMarkdown, .stCaption, label, .stRadio, .stMultiSelect, .stSelectbox {{ color: {colors['TEXT_MAIN']} !important; }}
        </style>
        """
    return f"""
    <style>
    .hero-minimal {{ padding: 0.0rem 0 0.3rem; margin-bottom: 0.2rem; }}
    .main-title {{ margin-top: -0.12rem !important; }}
    .section-shell, .nav-panel, div[data-testid="stPlotlyChart"] {{ box-shadow: 0 10px 24px rgba(0,40,87,0.05) !important; }}
    </style>
    """

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

# =========================================================
# TIPOGRAFÍA BASE PARA GRÁFICOS
# =========================================================
PLOT_FONT_SIZE = 15
PLOT_TITLE_SIZE = 19
PLOT_ANNOTATION_SIZE = 12

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

@lru_cache(maxsize=4096)
def normalize_text(text: str) -> str:
    """Normaliza un string individual (con cache LRU para evitar recomputación)."""
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


def fmt_avg_pax(value) -> str:
    if pd.isna(value):
        return "-"
    return f"{float(value):,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_fuga_pct(value) -> str:
    if pd.isna(value):
        return "-"
    return fmt_pct(maybe_scale_percent(value))


PLOTLY_CHART_CONFIG = {
    "scrollZoom": False,
    "displayModeBar": False,
    "doubleClick": False,
    "showTips": False,
    "responsive": True,
}

def show_plot(fig: go.Figure, use_container_width: bool = True, **kwargs):
    """
    Wrapper Streamlit/Plotly optimizado:
    Reemplaza iteración sobre fig.layout por update_xaxes/update_yaxes (una sola op).
    """
    try:
        fig.update_layout(dragmode=False)
        fig.update_xaxes(fixedrange=True)
        fig.update_yaxes(fixedrange=True)
    except Exception:
        pass
    return st.plotly_chart(fig, use_container_width=use_container_width, config=PLOTLY_CHART_CONFIG, **kwargs)


def periodo_to_date(value):
    value = "" if value is None else str(value).strip()
    if not value:
        return pd.NaT
    if len(value) == 7:
        value += "-01"
    return pd.to_datetime(value, errors="coerce")


# Constantes a nivel de módulo — evitan recrear el dict en cada llamada
_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}
_MESES_LARGO = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}

def periodo_to_label(value) -> str:
    dt = periodo_to_date(value)
    if pd.isna(dt):
        return str(value)
    return f"{_MESES.get(int(dt.month), str(dt.month))}-{str(dt.year)[2:]}"


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
        # np.select vectorizado — elimina .apply(classify_operational_period) fila a fila
        h = ts.dt.hour + ts.dt.minute / 60.0
        labels_op = np.select(
            [(h >= 6) & (h < 9), (h >= 9) & (h < 17), (h >= 17) & (h < 21)],
            ["Punta Mañana", "Valle", "Punta Tarde"],
            default="Fuera de periodo",
        )
        return pd.Series(np.where(ts.isna(), None, labels_op), index=ts.index, dtype=object)
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

TURNSTILE_SERVICE_CONFIG = {
    "Biotren": {
        "folder_candidates": ["transacciones_bt", "torniquetes_bt", ".transacciones_bt"],
        "description": "Base cruda de torniquetes para cruce por tarjeta y cercanía temporal con el perfil de carga.",
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

    required_agg_cols = [
        "fecha", "linea", "direccion", "servicio", "estacion",
        "t_arr_est", "t_dep_est", "capacidad_tren", "D_bajadas",
        "B_embarque", "L_out_abordo"
    ]
    required_tx_cols = [
        "origen", "destino", "servicio_final", "linea", "direccion",
        "t_entrada_viaje", "t_salida_viaje"
    ]

    csv_files, folder_path = _resolve_folder(service_name, PROFILE_SERVICE_CONFIG, data_path)
    if not csv_files:
        return pd.DataFrame(), folder_path, required_agg_cols, [], "no_data"

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
        return pd.DataFrame(), folder_path, required_agg_cols, loaded, "read_error"

    perfil_df = pd.concat(frames, ignore_index=True)

    has_agg_schema = all(col in perfil_df.columns for col in required_agg_cols)
    has_tx_schema = all(col in perfil_df.columns for col in required_tx_cols)

    if has_agg_schema:
        perfil_df["fecha"] = pd.to_datetime(perfil_df["fecha"], errors="coerce").dt.date
        perfil_df["linea"] = perfil_df["linea"].fillna("").astype(str).str.strip()
        perfil_df["direccion"] = perfil_df["direccion"].fillna("").astype(str).str.strip()
        perfil_df["estacion"] = perfil_df["estacion"].fillna("").astype(str).str.strip()
        perfil_df["servicio_label"] = perfil_df["servicio"].apply(format_service_id)
        perfil_df["profile_schema"] = "aggregated"

        for tc in ["t_arr_est", "t_dep_est"]:
            perfil_df[tc] = pd.to_datetime(perfil_df[tc], errors="coerce")

        for col in [
            "capacidad_tren", "A_llegadas_anden", "D_bajadas", "Demanda_anden",
            "Capacidad_disponible", "B_embarque", "R_quedados", "Q_out_cola",
            "L_in_abordo", "L_out_abordo"
        ]:
            if col in perfil_df.columns:
                perfil_df[col] = pd.to_numeric(perfil_df[col], errors="coerce")

        perfil_df = perfil_df.dropna(subset=["fecha"]).copy()
        perfil_df.attrs["profile_schema"] = "aggregated"
        return perfil_df, folder_path, [], loaded, "ok"

    if has_tx_schema:
        perfil_df["origen"] = perfil_df["origen"].fillna("").astype(str).str.strip()
        perfil_df["destino"] = perfil_df["destino"].fillna("").astype(str).str.strip()
        perfil_df["linea"] = perfil_df["linea"].fillna("").astype(str).str.strip()
        perfil_df["direccion"] = perfil_df["direccion"].fillna("").astype(str).str.strip()
        perfil_df["t_entrada_viaje"] = pd.to_datetime(perfil_df["t_entrada_viaje"], errors="coerce")
        perfil_df["t_salida_viaje"] = pd.to_datetime(perfil_df["t_salida_viaje"], errors="coerce")
        perfil_df["fecha"] = perfil_df["t_entrada_viaje"].dt.date

        missing_fecha_mask = perfil_df["fecha"].isna()
        if missing_fecha_mask.any():
            perfil_df.loc[missing_fecha_mask, "fecha"] = perfil_df.loc[missing_fecha_mask, "t_salida_viaje"].dt.date

        if "dia_proceso" in perfil_df.columns:
            dia_proceso = pd.to_datetime(perfil_df["dia_proceso"], errors="coerce").dt.date
            perfil_df["fecha"] = perfil_df["fecha"].where(pd.Series(perfil_df["fecha"]).notna(), dia_proceso)

        perfil_df["servicio_label"] = perfil_df["servicio_final"].apply(format_service_id)
        perfil_df["profile_schema"] = "transactional"

        for col in ["viaje_idx", "tarjeta_id", "servicio_final", "servicio_tramo_v1", "servicio_tramo_v2"]:
            if col in perfil_df.columns:
                perfil_df[col] = pd.to_numeric(perfil_df[col], errors="coerce")

        perfil_df = perfil_df.dropna(subset=["fecha"]).copy()
        perfil_df.attrs["profile_schema"] = "transactional"
        return perfil_df, folder_path, [], loaded, "ok"

    missing = [c for c in required_agg_cols if c not in perfil_df.columns]
    if len(missing) == len(required_agg_cols):
        missing = [c for c in required_tx_cols if c not in perfil_df.columns]
    return perfil_df, folder_path, missing, loaded, "unsupported_format"




@st.cache_data
def load_od_service_data(service_name: str, data_path_str: str):
    data_path = Path(data_path_str)
    csv_files, folder_path = _resolve_folder(service_name, OD_SERVICE_CONFIG, data_path)

    required_old = ["origen", "destino", "t_entrada_viaje", "t_salida_viaje"]
    required_new = ["origen", "destino", "fecha_entrada", "fecha_salida"]
    required_display = ["origen", "destino", "fecha_entrada", "fecha_salida"]

    if not csv_files:
        return pd.DataFrame(), folder_path, required_display, [], "no_data"

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
        return pd.DataFrame(), folder_path, required_display, loaded, "read_error"

    od_df = pd.concat(frames, ignore_index=True)

    has_new_schema = all(col in od_df.columns for col in required_new)
    has_old_schema = all(col in od_df.columns for col in required_old)

    if has_new_schema:
        od_df["t_entrada_viaje"] = pd.to_datetime(od_df["fecha_entrada"], errors="coerce")
        od_df["t_salida_viaje"] = pd.to_datetime(od_df["fecha_salida"], errors="coerce")
    elif has_old_schema:
        od_df["t_entrada_viaje"] = pd.to_datetime(od_df["t_entrada_viaje"], errors="coerce")
        od_df["t_salida_viaje"] = pd.to_datetime(od_df["t_salida_viaje"], errors="coerce")
    else:
        missing = [c for c in required_display if c not in od_df.columns]
        if not missing:
            missing = [c for c in required_old if c not in od_df.columns]
        return od_df, folder_path, missing, loaded, "unsupported_format"

    for col in ["origen", "destino", "direccion", "linea", "linea_entrada", "linea_salida"]:
        if col not in od_df.columns:
            od_df[col] = ""
        od_df[col] = od_df[col].fillna("").astype(str).str.strip()

    if od_df["linea"].eq("").all():
        od_df["linea"] = np.where(
            od_df["linea_entrada"].astype(str) == od_df["linea_salida"].astype(str),
            od_df["linea_entrada"].astype(str),
            (od_df["linea_entrada"].astype(str) + "→" + od_df["linea_salida"].astype(str)).str.strip("→"),
        )

    od_df["fecha"] = od_df["t_entrada_viaje"].dt.date
    missing_fecha_mask = od_df["fecha"].isna()
    if missing_fecha_mask.any():
        od_df.loc[missing_fecha_mask, "fecha"] = od_df.loc[missing_fecha_mask, "t_salida_viaje"].dt.date

    if "dia_proceso" in od_df.columns:
        dia_proceso = pd.to_datetime(od_df["dia_proceso"], errors="coerce").dt.date
        od_df["fecha"] = od_df["fecha"].where(pd.Series(od_df["fecha"]).notna(), dia_proceso)

    if "servicio_final" in od_df.columns:
        od_df["servicio_label"] = od_df["servicio_final"].apply(format_service_id)
    elif "servicio" in od_df.columns:
        od_df["servicio_label"] = od_df["servicio"].apply(format_service_id)
    else:
        od_df["servicio_label"] = "-"

    for col in ["tarjeta_id", "viaje_idx", "terminal_entrada", "terminal_salida"]:
        if col in od_df.columns:
            od_df[col] = pd.to_numeric(od_df[col], errors="coerce")

    return od_df.dropna(subset=["fecha"]).copy(), folder_path, [], loaded, "ok"






@st.cache_data
def load_turnstile_service_data(service_name: str, data_path_str: str):
    """
    Carga la base cruda de torniquetes para cruzarla con el perfil transaccional.
    Espera al menos las columnas FECHA_TRANSACCION, NUMERO_TARJETA y MONTO_TRANSACCION.
    Soporta CSV, XLSX y XLS; la fecha se parsea desde el timestamp con separador 'T'.
    """
    data_path = Path(data_path_str)
    config = TURNSTILE_SERVICE_CONFIG.get(service_name, {})
    folder_names = config.get("folder_candidates", [])
    base = Path(__file__).resolve().parent
    search_roots = [base, data_path, base / "data", base / "datos"]

    files = []
    folder_path = ""
    for folder_name in folder_names:
        for root in search_roots:
            candidate = root / folder_name
            if candidate.exists() and candidate.is_dir():
                found = [fp for fp in candidate.iterdir() if fp.is_file() and fp.suffix.lower() in {".csv", ".xlsx", ".xls"} and not fp.name.startswith("~$")]
                if found:
                    files = sorted(found, key=lambda fp: fp.name.lower())
                    folder_path = str(candidate)
                    break
        if files:
            break

    if not files:
        fallback = (data_path / folder_names[0]) if folder_names else data_path / "transacciones_bt"
        return pd.DataFrame(), str(fallback), ["FECHA_TRANSACCION", "NUMERO_TARJETA", "MONTO_TRANSACCION"], [], "no_data"

    frames, loaded = [], []
    for f in files:
        try:
            if f.suffix.lower() == ".csv":
                temp = pd.read_csv(f, low_memory=False)
            else:
                temp = pd.read_excel(f)
            if temp.empty:
                continue
            temp["archivo_origen"] = f.name
            frames.append(temp)
            loaded.append(f.name)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(), folder_path, ["FECHA_TRANSACCION", "NUMERO_TARJETA", "MONTO_TRANSACCION"], [], "read_error"

    df = pd.concat(frames, ignore_index=True)

    _turnstile_col_map = {
        "fecha_transaccion": "FECHA_TRANSACCION",
        "numero_tarjeta":    "NUMERO_TARJETA",
        "monto_transaccion": "MONTO_TRANSACCION",
    }
    col_norms = normalize_series(pd.Series(df.columns.tolist()))
    rename_map = {orig: _turnstile_col_map[norm]
                  for orig, norm in zip(df.columns, col_norms)
                  if norm in _turnstile_col_map}
    df = df.rename(columns=rename_map)

    required = ["FECHA_TRANSACCION", "NUMERO_TARJETA", "MONTO_TRANSACCION"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return df, folder_path, missing, loaded, "unsupported_format"

    timestamp_txt = df["FECHA_TRANSACCION"].fillna("").astype(str).str.strip()
    df["fecha_transaccion_txt"] = timestamp_txt
    df["fecha_transaccion"] = pd.to_datetime(timestamp_txt.str.replace("T", " ", regex=False), errors="coerce")
    df["fecha"] = df["fecha_transaccion"].dt.date
    df["hora_transaccion"] = df["fecha_transaccion"].dt.strftime("%H:%M:%S")
    df["tarjeta_id"] = pd.to_numeric(df["NUMERO_TARJETA"], errors="coerce")
    df["monto_transaccion"] = pd.to_numeric(df["MONTO_TRANSACCION"], errors="coerce")
    df["turnstile_tx_id"] = np.arange(1, len(df) + 1)

    df = df.dropna(subset=["fecha_transaccion", "fecha", "tarjeta_id", "monto_transaccion"]).copy()
    return df, folder_path, [], loaded, "ok"


def match_turnstile_transactions_to_profile(turnstile_df: pd.DataFrame,
                                            profile_tx_df: pd.DataFrame,
                                            tolerance_minutes: int = 20):
    """
    Cruza transacciones de torniquete con viajes del perfil usando:
    - tarjeta_id exacto
    - cercanía temporal al evento más próximo del viaje:
      * t_entrada_viaje
      * t_salida_viaje

    En la práctica, para la base cruda de torniquetes Biotren, FECHA_TRANSACCION puede quedar
    más cerca de la salida que de la entrada. Por eso el match usa el evento con menor diferencia.
    """
    empty_summary = pd.DataFrame(columns=[
        "linea", "direccion", "servicio_label", "tx_cruzadas",
        "tarifa_media_aprox", "tarifa_mediana_aprox", "recaudacion_aprox",
        "desviacion_tarifa_aprox", "diff_mediana_min", "match_ref_principal"
    ])
    empty_stats = {
        "turnstile_total": 0,
        "matched_total": 0,
        "match_pct": np.nan,
        "diff_mediana_min": np.nan,
        "tolerance_minutes": tolerance_minutes,
        "pct_match_entrada": np.nan,
        "pct_match_salida": np.nan,
    }
    if turnstile_df.empty or profile_tx_df.empty:
        return pd.DataFrame(), empty_summary, empty_stats

    tx = turnstile_df.copy()
    prof = profile_tx_df.copy()

    tx["tarjeta_id"] = pd.to_numeric(tx["tarjeta_id"], errors="coerce")
    prof["tarjeta_id"] = pd.to_numeric(prof["tarjeta_id"], errors="coerce")
    tx["fecha_transaccion"] = pd.to_datetime(tx["fecha_transaccion"], errors="coerce")
    if "t_entrada_viaje" in prof.columns:
        prof["t_entrada_viaje"] = pd.to_datetime(prof["t_entrada_viaje"], errors="coerce")
    if "t_salida_viaje" in prof.columns:
        prof["t_salida_viaje"] = pd.to_datetime(prof["t_salida_viaje"], errors="coerce")

    keep_prof = [c for c in [
        "tarjeta_id", "t_entrada_viaje", "t_salida_viaje", "servicio_label",
        "linea", "direccion", "servicio_final", "viaje_idx", "origen", "destino"
    ] if c in prof.columns]
    if not {"tarjeta_id", "servicio_label"}.issubset(set(keep_prof)):
        return pd.DataFrame(), empty_summary, empty_stats
    if not any(c in keep_prof for c in ["t_entrada_viaje", "t_salida_viaje"]):
        return pd.DataFrame(), empty_summary, empty_stats

    tx = tx.dropna(subset=["tarjeta_id", "fecha_transaccion", "monto_transaccion"]).copy()
    prof = prof[keep_prof].copy()
    prof = prof.dropna(subset=["tarjeta_id", "servicio_label"], how="any").copy()
    # conservar filas que tengan al menos una referencia temporal
    valid_time_mask = False
    if "t_entrada_viaje" in prof.columns:
        valid_time_mask = valid_time_mask | prof["t_entrada_viaje"].notna()
    if "t_salida_viaje" in prof.columns:
        valid_time_mask = valid_time_mask | prof["t_salida_viaje"].notna()
    prof = prof[valid_time_mask].copy()

    empty_stats["turnstile_total"] = int(len(tx))
    if tx.empty or prof.empty:
        return pd.DataFrame(), empty_summary, empty_stats

    tx["turnstile_tx_id"] = pd.to_numeric(tx.get("turnstile_tx_id"), errors="coerce")
    if tx["turnstile_tx_id"].isna().all():
        tx["turnstile_tx_id"] = np.arange(1, len(tx) + 1)
    tx["turnstile_tx_id"] = tx["turnstile_tx_id"].astype(int)

    # Pre-filtro de fecha: reduce el producto cartesiano antes del merge
    if "fecha_transaccion" in tx.columns and tx["fecha_transaccion"].notna().any():
        tx_dates = set(tx["fecha_transaccion"].dt.date.dropna())
        if tx_dates:
            prof_date_mask = pd.Series(False, index=prof.index)
            if "t_entrada_viaje" in prof.columns:
                prof_date_mask |= pd.to_datetime(prof["t_entrada_viaje"], errors="coerce").dt.date.isin(tx_dates)
            if "t_salida_viaje" in prof.columns:
                prof_date_mask |= pd.to_datetime(prof["t_salida_viaje"], errors="coerce").dt.date.isin(tx_dates)
            prof = prof[prof_date_mask].copy()

    merged = tx.merge(prof, how="inner", on="tarjeta_id", suffixes=("", "_perfil"))
    if merged.empty:
        return pd.DataFrame(), empty_summary, empty_stats

    # Diferencia contra entrada y salida
    if "t_entrada_viaje" in merged.columns:
        merged["diff_entrada_min"] = (merged["fecha_transaccion"] - merged["t_entrada_viaje"]).abs().dt.total_seconds() / 60.0
    else:
        merged["diff_entrada_min"] = np.nan

    if "t_salida_viaje" in merged.columns:
        merged["diff_salida_min"] = (merged["fecha_transaccion"] - merged["t_salida_viaje"]).abs().dt.total_seconds() / 60.0
    else:
        merged["diff_salida_min"] = np.nan

    merged["match_diff_min"] = merged[["diff_entrada_min", "diff_salida_min"]].min(axis=1, skipna=True)
    merged["match_ref"] = np.where(
        merged["diff_salida_min"].fillna(np.inf) < merged["diff_entrada_min"].fillna(np.inf),
        "salida",
        "entrada",
    )

    # timestamp de referencia efectivamente usado
    merged["match_timestamp"] = np.where(
        merged["match_ref"] == "salida",
        merged.get("t_salida_viaje"),
        merged.get("t_entrada_viaje"),
    )
    merged["match_timestamp"] = pd.to_datetime(merged["match_timestamp"], errors="coerce")

    merged = merged[merged["match_diff_min"] <= float(tolerance_minutes)].copy()
    if merged.empty:
        return pd.DataFrame(), empty_summary, empty_stats

    matched_df = (
        merged.sort_values(["turnstile_tx_id", "match_diff_min", "match_timestamp"], kind="stable")
        .drop_duplicates(subset=["turnstile_tx_id"], keep="first")
        .reset_index(drop=True)
    )

    stats = {
        "turnstile_total": int(len(tx)),
        "matched_total": int(len(matched_df)),
        "match_pct": (float(len(matched_df)) / float(len(tx)) * 100.0) if len(tx) else np.nan,
        "diff_mediana_min": float(matched_df["match_diff_min"].median()) if not matched_df.empty else np.nan,
        "tolerance_minutes": tolerance_minutes,
        "pct_match_entrada": (float((matched_df["match_ref"] == "entrada").mean()) * 100.0) if not matched_df.empty else np.nan,
        "pct_match_salida": (float((matched_df["match_ref"] == "salida").mean()) * 100.0) if not matched_df.empty else np.nan,
    }

    summary = (
        matched_df.groupby(["linea", "direccion", "servicio_label"], as_index=False)
        .agg(
            tx_cruzadas=("monto_transaccion", "size"),
            tarifa_media_aprox=("monto_transaccion", "mean"),
            tarifa_mediana_aprox=("monto_transaccion", "median"),
            recaudacion_aprox=("monto_transaccion", "sum"),
            desviacion_tarifa_aprox=("monto_transaccion", "std"),
            diff_mediana_min=("match_diff_min", "median"),
        )
    )
    # referencia temporal predominante por servicio
    if not matched_df.empty:
        ref_summary = (
            matched_df.groupby(["linea", "direccion", "servicio_label", "match_ref"], as_index=False)
            .size().rename(columns={"size": "n"})
            .sort_values(["linea", "direccion", "servicio_label", "n", "match_ref"], ascending=[True, True, True, False, True])
            .drop_duplicates(subset=["linea", "direccion", "servicio_label"], keep="first")
            .rename(columns={"match_ref": "match_ref_principal"})
        )
        summary = summary.merge(
            ref_summary[["linea", "direccion", "servicio_label", "match_ref_principal"]],
            how="left",
            on=["linea", "direccion", "servicio_label"],
        )
    else:
        summary["match_ref_principal"] = np.nan
    return matched_df, summary, stats



@st.cache_data
def load_itinerary_reference(data_path_str: str):
    """
    Carga la base de itinerario generada desde PDF.
    Prioriza CSV en carpeta itinerarios/, pero también soporta el XLSX consolidado.
    """
    data_path = Path(data_path_str)
    base = Path(__file__).resolve().parent
    search_roots = [base / "itinerarios", data_path / "itinerarios", base, data_path, base / "data", base / "datos"]

    summary_df = pd.DataFrame()
    detail_df = pd.DataFrame()
    found_path = None
    found_files = []

    def _safe_read_csv(path: Path):
        try:
            return pd.read_csv(path, low_memory=False)
        except Exception:
            return pd.DataFrame()

    def _safe_read_xlsx(path: Path, sheet: str):
        try:
            return pd.read_excel(path, sheet_name=sheet)
        except Exception:
            return pd.DataFrame()

    for root in search_roots:
        if not root.exists():
            continue
        summary_csv = root / 'itinerario_resumen_servicios.csv'
        detail_csv = root / 'itinerario_detalle_estaciones.csv'
        xlsx_file   = root / 'itinerario_efe_sur_extraido.xlsx'

        temp_summary = pd.DataFrame()
        temp_detail = pd.DataFrame()
        temp_files = []

        if summary_csv.exists():
            temp_summary = _safe_read_csv(summary_csv)
            if not temp_summary.empty:
                temp_files.append(summary_csv.name)
        if detail_csv.exists():
            temp_detail = _safe_read_csv(detail_csv)
            if not temp_detail.empty:
                temp_files.append(detail_csv.name)
        if temp_summary.empty and xlsx_file.exists():
            temp_summary = _safe_read_xlsx(xlsx_file, 'Resumen_servicios')
            temp_detail = _safe_read_xlsx(xlsx_file, 'Detalle_estaciones')
            if not temp_summary.empty:
                temp_files.append(xlsx_file.name + '::Resumen_servicios')
            if not temp_detail.empty:
                temp_files.append(xlsx_file.name + '::Detalle_estaciones')

        if not temp_summary.empty:
            summary_df = temp_summary.copy()
            detail_df = temp_detail.copy()
            found_path = str(root)
            found_files = temp_files
            break

    if summary_df.empty:
        return pd.DataFrame(), pd.DataFrame(), '', [], 'no_data'

    # Normalización mínima
    for df in [summary_df, detail_df]:
        if df.empty:
            continue
        for col in ['sector', 'tipo_dia', 'sentido', 'estacion_origen', 'estacion_terminal', 'estacion']:
            if col in df.columns:
                df[col] = df[col].fillna('').astype(str).str.strip()
        if 'servicio' in df.columns:
            df['servicio_label'] = df['servicio'].apply(format_service_id)

    if 'hora_salida_origen' in summary_df.columns:
        summary_df['hora_salida_origen_str'] = summary_df['hora_salida_origen'].fillna('').astype(str).str.strip()
    if 'hora_llegada_term' in summary_df.columns:
        summary_df['hora_llegada_term_str'] = summary_df['hora_llegada_term'].fillna('').astype(str).str.strip()

    return summary_df, detail_df, found_path or '', found_files, 'ok'


def infer_itinerary_day_filter(fecha_sel: date) -> str:
    if fecha_sel.weekday() == 5:
        return 'sabado'
    if fecha_sel.weekday() == 6:
        return 'domingo'
    return 'lunes a viernes'


def infer_itinerary_sector(profile_service: str, linea_sel: str) -> str | None:
    if normalize_text(profile_service) != 'biotren':
        return None
    line_key = normalize_text(linea_sel).replace(' ', '')
    if line_key == 'l2':
        return 'CONCEPCIÓN-CORONEL'
    if line_key == 'l1':
        return 'LAJA-TALCAHUANO'
    return None


def infer_itinerary_sentido(linea_sel: str, direccion_sel: str) -> str | None:
    line_key = normalize_text(linea_sel).replace(' ', '')
    dir_key = _normalize_direction_key(direccion_sel)
    if line_key == 'l2':
        if dir_key == 'cw-cc':
            return 'Coronel a Concepción'
        if dir_key == 'cc-cw':
            return 'Concepción a Coronel'
    if line_key == 'l1':
        if dir_key == 'hq-th':
            return 'Laja a Talcahuano'
        if dir_key == 'th-hq':
            return 'Talcahuano a Laja'
    return None


def enrich_service_summary_with_itinerary(summary_df: pd.DataFrame,
                                         itinerary_summary: pd.DataFrame,
                                         profile_service: str,
                                         linea_sel: str,
                                         dir_sel: str,
                                         fecha_sel: date) -> pd.DataFrame:
    if summary_df.empty or itinerary_summary.empty:
        return summary_df.copy()

    enriched = summary_df.copy()
    itin = itinerary_summary.copy()
    itin['servicio_label'] = itin['servicio_label'].astype(str)
    enriched['servicio_label'] = enriched['servicio_label'].astype(str)

    day_filter = infer_itinerary_day_filter(fecha_sel)
    sector = infer_itinerary_sector(profile_service, linea_sel)
    sentido = infer_itinerary_sentido(linea_sel, dir_sel)

    if sector and 'sector' in itin.columns:
        itin = itin[normalize_series(itin['sector']) == normalize_text(sector)].copy()
    if day_filter and 'tipo_dia' in itin.columns:
        itin = itin[normalize_series(itin['tipo_dia']).str.contains(day_filter, regex=False)].copy()
    if sentido and 'sentido' in itin.columns:
        temp = itin[normalize_series(itin['sentido']) == normalize_text(sentido)].copy()
        if not temp.empty:
            itin = temp

    if itin.empty:
        return enriched

    itin = itin.sort_values(['servicio_label', 'pagina_pdf']).drop_duplicates(subset=['servicio_label'], keep='first').copy()
    join_cols = ['servicio_label']
    extra_cols = [c for c in ['estacion_origen', 'hora_salida_origen_str', 'estacion_terminal', 'hora_llegada_term_str', 'tipo_dia', 'sentido', 'sector'] if c in itin.columns]
    itin_small = itin[join_cols + extra_cols].copy()
    itin_small = itin_small.rename(columns={
        'estacion_origen': 'it_estacion_origen',
        'hora_salida_origen_str': 'it_hora_salida',
        'estacion_terminal': 'it_estacion_terminal',
        'hora_llegada_term_str': 'it_hora_llegada_term',
        'tipo_dia': 'it_tipo_dia',
        'sentido': 'it_sentido',
        'sector': 'it_sector',
    })

    enriched = enriched.merge(itin_small, how='left', on='servicio_label')
    if 'it_estacion_origen' in enriched.columns:
        enriched['estacion_origen'] = enriched['it_estacion_origen'].where(enriched['it_estacion_origen'].fillna('').astype(str).str.strip() != '', enriched['estacion_origen'])
    if 'it_hora_salida' in enriched.columns:
        base_date = pd.Timestamp(fecha_sel)
        it_ts = pd.to_datetime(base_date.strftime('%Y-%m-%d') + ' ' + enriched['it_hora_salida'].fillna('').astype(str), errors='coerce')
        enriched['hora_salida'] = it_ts.where(it_ts.notna(), enriched['hora_salida'])
    enriched['hora_salida'] = pd.to_datetime(enriched['hora_salida'], errors='coerce')
    enriched['hora_salida_fmt'] = enriched['hora_salida'].dt.strftime('%H:%M:%S').fillna('-')

    enriched = enriched.sort_values(['hora_salida', 'servicio_label'], na_position='last').reset_index(drop=True)
    return enriched


@st.cache_data

def load_service_order_reference(data_path_str: str):
    """
    Carga el orden operativo de servicios para usarlo en el selector y en el eje X.
    Prioriza una columna explícita de orden cuando existe. Si el archivo no trae esa
    columna, usa estrictamente el orden de las filas del archivo como respaldo.
    """
    data_path = Path(data_path_str)
    base = Path(__file__).resolve().parent
    search_roots = [base / "itinerarios", data_path / "itinerarios", base, data_path, base / "data", base / "datos"]

    candidates = []

    def _safe_read_csv(path: Path):
        try:
            temp = pd.read_csv(path, low_memory=False)
            temp["__sheet_seq"] = 0
            temp["__row_seq"] = np.arange(1, len(temp) + 1)
            return temp
        except Exception:
            return pd.DataFrame()

    def _safe_read_xlsx(path: Path):
        try:
            xl = pd.ExcelFile(path)
            frames = []
            sheet_map = {
                "Lun a Vie": "Lunes a Viernes",
                "Sabado y Domingo": "Sabado y Domingo",
            }
            for sheet_idx, sheet in enumerate(xl.sheet_names):
                temp = pd.read_excel(path, sheet_name=sheet)
                if temp.empty:
                    continue
                temp["tipo_dia_ref"] = sheet_map.get(sheet, str(sheet))
                temp["__sheet_seq"] = sheet_idx
                temp["__row_seq"] = np.arange(1, len(temp) + 1)
                frames.append(temp)
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    for root in search_roots:
        if not root.exists():
            continue
        for filename, reader in [("itinerario_orden.xlsx", _safe_read_xlsx), ("itinerario_orden.csv", _safe_read_csv)]:
            file_path = root / filename
            if not file_path.exists():
                continue
            temp = reader(file_path)
            if temp.empty:
                continue

            rename_map = {}
            for c in temp.columns:
                nc = normalize_text(c)
                if nc == "servicio":
                    rename_map[c] = "servicio"
                elif nc == "linea":
                    rename_map[c] = "linea"
                elif nc == "sentido":
                    rename_map[c] = "direccion"
                elif nc in {"tipo dia", "tipo_dia", "tipodia", "tipo dia ref", "tipo_dia_ref"}:
                    rename_map[c] = "tipo_dia_ref"
                elif nc == "orden":
                    rename_map[c] = "orden"
            temp = temp.rename(columns=rename_map)

            has_required = {"servicio", "linea", "direccion"}.issubset(set(temp.columns))
            if not has_required:
                continue

            if "orden" in temp.columns:
                temp["orden"] = pd.to_numeric(temp["orden"], errors="coerce")
            else:
                temp["orden"] = np.nan

            temp["__sheet_seq"] = pd.to_numeric(temp.get("__sheet_seq"), errors="coerce").fillna(0).astype(int)
            temp["__row_seq"] = pd.to_numeric(temp.get("__row_seq"), errors="coerce")
            if temp["__row_seq"].isna().all():
                temp["__row_seq"] = np.arange(1, len(temp) + 1)
            temp["__row_seq"] = temp["__row_seq"].astype(int)

            explicit_order_count = int(temp["orden"].notna().sum())
            candidates.append({
                "df": temp.copy(),
                "root": str(root),
                "file": filename,
                "explicit_order_count": explicit_order_count,
                "is_xlsx": int(filename.lower().endswith(".xlsx")),
            })

    if not candidates:
        return pd.DataFrame(), "", [], "no_data"

    candidates = sorted(
        candidates,
        key=lambda x: (x["explicit_order_count"], x["is_xlsx"]),
        reverse=True,
    )
    best = candidates[0]
    order_df = best["df"].copy()
    found_path = best["root"]
    found_files = [best["file"]]

    if "tipo_dia_ref" not in order_df.columns:
        order_df["tipo_dia_ref"] = "Lunes a Viernes"

    # Si no existe orden explícito, usar estrictamente el orden de filas del archivo
    if order_df["orden"].isna().all():
        order_df["orden"] = np.arange(1, len(order_df) + 1)
    else:
        # para filas sin orden explícito, usar el orden físico del archivo como respaldo
        missing_mask = order_df["orden"].isna()
        if missing_mask.any():
            fallback_base = int(order_df["orden"].dropna().max())
            order_df.loc[missing_mask, "orden"] = np.arange(fallback_base + 1, fallback_base + 1 + int(missing_mask.sum()))

    order_df["servicio_label"] = order_df["servicio"].apply(format_service_id)
    order_df["linea"] = order_df["linea"].fillna("").astype(str).str.strip()
    order_df["direccion"] = order_df["direccion"].fillna("").astype(str).str.strip()
    order_df["tipo_dia_ref"] = order_df["tipo_dia_ref"].fillna("").astype(str).str.strip()
    order_df["orden"] = pd.to_numeric(order_df["orden"], errors="coerce")
    order_df = order_df.dropna(subset=["orden"]).copy()
    order_df["orden"] = order_df["orden"].astype(int)

    order_df = (
        order_df.sort_values(["tipo_dia_ref", "linea", "direccion", "orden", "__sheet_seq", "__row_seq"], kind="stable")
        .drop_duplicates(subset=["tipo_dia_ref", "linea", "direccion", "servicio_label"], keep="first")
        .reset_index(drop=True)
    )
    return order_df, found_path, found_files, "ok"



def infer_service_order_day_filter(fecha_sel: date) -> str:
    return "sabado y domingo" if fecha_sel.weekday() >= 5 else "lunes a viernes"



def apply_service_order_and_labels(summary_df: pd.DataFrame,
                                   order_df: pd.DataFrame,
                                   profile_service: str,
                                   linea_sel: str,
                                   dir_sel: str,
                                   fecha_sel: date) -> pd.DataFrame:
    if summary_df.empty:
        return summary_df.copy()

    enriched = summary_df.copy()
    enriched["__input_order"] = np.arange(len(enriched))
    enriched["servicio_label"] = enriched["servicio_label"].astype(str).str.strip()
    enriched["hora_salida"] = pd.to_datetime(enriched["hora_salida"], errors="coerce")
    enriched["hora_salida_fmt"] = enriched["hora_salida"].dt.strftime("%H:%M:%S").fillna("-")
    enriched["hora_salida_corta"] = enriched["hora_salida_fmt"].astype(str).str.slice(0, 5).replace({"-": "s/h"})
    enriched["estacion_origen"] = enriched["estacion_origen"].fillna("-").astype(str).str.strip().replace({"": "-"})

    enriched["servicio_orden_idx"] = np.nan

    if not order_df.empty and normalize_text(profile_service) == "biotren":
        temp = order_df.copy()
        day_filter = infer_service_order_day_filter(fecha_sel)
        temp["tipo_dia_ref_norm"] = normalize_series(temp["tipo_dia_ref"])
        temp["linea_norm"] = normalize_series(temp["linea"])
        temp["direccion_norm"] = normalize_series(temp["direccion"])

        temp_day = temp[temp["tipo_dia_ref_norm"].str.contains(day_filter, regex=False, na=False)].copy()
        if temp_day.empty:
            temp_day = temp.copy()

        temp_day = temp_day[temp_day["linea_norm"] == normalize_text(linea_sel)].copy()
        temp_day = temp_day[temp_day["direccion_norm"] == normalize_text(dir_sel)].copy()

        if not temp_day.empty:
            temp_day["__file_seq"] = np.arange(len(temp_day))
            temp_day = (
                temp_day.sort_values(["orden", "__file_seq"], kind="stable")
                .drop_duplicates(subset=["servicio_label"], keep="first")
                .reset_index(drop=True)
            )
            # Usar el orden del archivo / columna Orden, no el número del servicio ni la hora
            temp_day["servicio_orden_idx"] = np.arange(1, len(temp_day) + 1)
            order_map = temp_day.set_index("servicio_label")["servicio_orden_idx"].to_dict()
            enriched["servicio_orden_idx"] = enriched["servicio_label"].map(order_map)

    # Respaldo SOLO para servicios ausentes del archivo de orden.
    # No usar número de servicio ni hora como criterio principal.
    missing_mask = enriched["servicio_orden_idx"].isna()
    if missing_mask.any():
        explicit_orders = pd.to_numeric(enriched["servicio_orden_idx"], errors="coerce").dropna()
        fallback_base = int(explicit_orders.max()) if not explicit_orders.empty else 0
        fallback_services = (
            enriched.loc[missing_mask, ["servicio_label", "__input_order"]]
            .drop_duplicates(subset=["servicio_label"], keep="first")
            .sort_values(["__input_order"], kind="stable")
            .reset_index(drop=True)
        )
        fallback_map = {
            row["servicio_label"]: fallback_base + idx + 1
            for idx, (_, row) in enumerate(fallback_services.iterrows())
        }
        enriched.loc[missing_mask, "servicio_orden_idx"] = enriched.loc[missing_mask, "servicio_label"].map(fallback_map)

    enriched["servicio_orden_idx"] = pd.to_numeric(enriched["servicio_orden_idx"], errors="coerce").fillna(999999).astype(int)
    enriched = enriched.sort_values(["servicio_orden_idx", "__input_order"], kind="stable").reset_index(drop=True)

    enriched["servicio_display_label"] = (
        enriched["servicio_label"].astype(str)
        + " | " + enriched["hora_salida_corta"].astype(str)
        + " | " + enriched["estacion_origen"].astype(str)
    )

    dup_rank = enriched.groupby("servicio_display_label").cumcount() + 1
    dup_total = enriched.groupby("servicio_display_label")["servicio_display_label"].transform("size")
    enriched["servicio_display_label"] = np.where(
        dup_total > 1,
        enriched["servicio_display_label"] + " (" + dup_rank.astype(str) + ")",
        enriched["servicio_display_label"],
    )
    if "__input_order" in enriched.columns:
        enriched = enriched.drop(columns="__input_order")
    return enriched



# =========================================================
# GRÁFICOS — KPIs y evolución
# =========================================================

def scale_kpi_dataframe_for_display(df: pd.DataFrame, kpi_name: str,
                                     value_columns=("valor",)) -> pd.DataFrame:
    df = df.copy()
    if is_occupancy_rate_kpi(kpi_name):
        for col in value_columns:
            if col in df.columns:
                s = pd.to_numeric(df[col], errors="coerce")
                df[col] = np.where(s.isna(), np.nan, np.where(s.abs() <= 1.5, s * 100.0, s))
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
        legend_title_text="", font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(size=16, color=EFE_BLUE), hovermode="x unified",
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=category_order, showgrid=False)
    fig.update_yaxes(title="", gridcolor="#E8EEF4", zeroline=False)

    if boxed_values and not plot_df.empty:
        annot_cols = ["periodo_label","valor","valor_label"]
        if color and color in plot_df.columns:
            annot_cols.append(color)
        _line_annots = []
        for _, row in plot_df[annot_cols].iterrows():
            xshift = 0
            if color and color in plot_df.columns:
                xshift = 10 if len(str(row[color])) % 2 == 0 else -10
            _line_annots.append(dict(
                x=row["periodo_label"], y=row["valor"], text=row["valor_label"],
                showarrow=False, yshift=18, xshift=xshift,
                font=dict(size=PLOT_ANNOTATION_SIZE, color=EFE_BLUE),
                bgcolor="rgba(255,255,255,0.92)", bordercolor=BORDER,
                borderwidth=1, borderpad=3, align="center",
                xref="x", yref="y",
            ))
        if _line_annots:
            fig.update_layout(annotations=_line_annots)
    return fig


def build_trend_line_chart(df: pd.DataFrame, kpi_name: str, unit: str | None,
                            service_name: str) -> go.Figure:
    """
    Evolución histórica con línea de tendencia y etiquetas del valor mensual.
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
    plot_df["valor_label"] = plot_df["valor"].apply(lambda v: fmt_number(v, unit or "", kpi_name))

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
        margin=dict(l=20, r=20, t=55, b=20), height=460,
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=category_order, showgrid=False)
    fig.update_yaxes(title="", gridcolor="#E8EEF4", zeroline=False)
    _bg = "rgba(255,255,255,0.96)" if COLORS.get("EFE_WHITE") == "#FFFFFF" else "rgba(15,23,42,0.92)"
    _trend_annots = [
        dict(
            x=row["periodo_label"], y=row["valor"], text=row["valor_label"],
            showarrow=False, yshift=18 if (idx % 2 == 0) else 30,
            font=dict(size=max(PLOT_ANNOTATION_SIZE, 11), color=EFE_BLUE),
            bgcolor=_bg, bordercolor=BORDER, borderwidth=1, borderpad=4,
            align="center", xref="x", yref="y",
        )
        for idx, (_, row) in enumerate(plot_df.iterrows())
    ]
    fig.update_layout(annotations=_trend_annots)
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
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
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

    bounds = compute_map_bounds(plot_df)

    fig = go.Figure()
    fig.add_trace(go.Scattermapbox(
        lat=plot_df["latitud"].astype(float),
        lon=plot_df["longitud"].astype(float),
        mode="markers+text",
        text=plot_df["label_mapa"],
        textposition="top right",
        textfont=dict(size=13, color=EFE_BLUE, family="Arial, sans-serif"),
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

PROFILE_STATION_SEQUENCES = {
    "l1": {
        "hq-th": [
            "Hualqui", "La Leonera", "Manquimavida", "Pedro Medina", "Chiguayante",
            "Concepcion", "Lzo. Arenas", "UTF Santa Maria", "Los Condores",
            "Higueras", "El Arenal", "Mercado",
        ],
        "th-hq": [
            "Mercado", "El Arenal", "Higueras", "Los Condores", "UTF Santa Maria",
            "Lzo. Arenas", "Concepcion", "Chiguayante", "Pedro Medina",
            "Manquimavida", "La Leonera", "Hualqui",
        ],
    },
    "l2": {
        "cw-cc": [
            "Coronel", "Laguna Quinenco", "Cristo Redentor", "Huinca", "Los Canelos",
            "Hito Galvarino", "Cdal. Raul Silva Henriquez", "Lomas Coloradas", "El Parque",
            "Costa Mar", "Alborada", "Diagonal Bio Bio", "Juan Pablo II", "Concepcion",
        ],
        "cc-cw": [
            "Concepcion", "Juan Pablo II", "Diagonal Bio Bio", "Alborada", "Costa Mar",
            "El Parque", "Lomas Coloradas", "Cdal. Raul Silva Henriquez", "Hito Galvarino",
            "Los Canelos", "Huinca", "Cristo Redentor", "Laguna Quinenco", "Coronel",
        ],
    },
}


def _normalize_direction_key(value: str) -> str:
    raw = "" if value is None else str(value).strip().lower()
    for token in ["→", "—", "–", "_", "/", "\\"]:
        raw = raw.replace(token, "-")
    raw = raw.replace(" ", "")
    while "--" in raw:
        raw = raw.replace("--", "-")
    return raw.strip("-")


def get_configured_station_order(linea: str, direccion: str, stations_present: list[str] | None = None) -> list:
    line_key = normalize_text(linea).replace(" ", "")
    dir_key = _normalize_direction_key(direccion)
    seq = PROFILE_STATION_SEQUENCES.get(line_key, {}).get(dir_key, [])
    if not seq:
        return []
    if not stations_present:
        return list(seq)

    norm_to_actual = {}
    for station in stations_present:
        st = "" if station is None else str(station).strip()
        if st:
            norm_to_actual.setdefault(normalize_text(st), st)

    ordered = [norm_to_actual[normalize_text(st)] for st in seq if normalize_text(st) in norm_to_actual]
    extras = [st for st in stations_present if st not in ordered]
    return ordered + extras


def get_station_order_from_profile(df: pd.DataFrame) -> list:
    if df.empty or "estacion" not in df.columns:
        return []

    temp = df.copy()
    temp["estacion"] = temp["estacion"].fillna("").astype(str).str.strip()
    temp = temp[temp["estacion"] != ""]
    if temp.empty:
        return []

    estaciones_presentes = list(dict.fromkeys(temp["estacion"].astype(str).tolist()))
    linea = temp["linea"].dropna().astype(str).str.strip().iloc[0] if "linea" in temp.columns and not temp["linea"].dropna().empty else ""
    direccion = temp["direccion"].dropna().astype(str).str.strip().iloc[0] if "direccion" in temp.columns and not temp["direccion"].dropna().empty else ""

    configured_order = get_configured_station_order(linea, direccion, estaciones_presentes)
    if configured_order:
        return configured_order

    if "event_time" in temp.columns:
        temp["event_time"] = pd.to_datetime(temp["event_time"], errors="coerce")
    else:
        arr = pd.to_datetime(temp["t_arr_est"], errors="coerce") if "t_arr_est" in temp.columns else pd.Series(index=temp.index, dtype="datetime64[ns]")
        dep = pd.to_datetime(temp["t_dep_est"], errors="coerce") if "t_dep_est" in temp.columns else pd.Series(index=temp.index, dtype="datetime64[ns]")
        temp["event_time"] = arr.fillna(dep)

    if temp["event_time"].notna().any():
        order = (
            temp.groupby("estacion", as_index=False)["event_time"]
            .min()
            .sort_values(["event_time", "estacion"])["estacion"]
            .tolist()
        )
    else:
        order = temp["estacion"].tolist()
    return list(dict.fromkeys(order))



def build_transactional_service_profile(service_tx: pd.DataFrame) -> pd.DataFrame:
    """
    Reconstruye un perfil de carga por estación a partir de transacciones OD de un servicio.
    El cálculo de pasajeros a bordo se realiza directamente desde la matriz OD,
    respetando el orden operacional definido para cada línea y sentido.
    """
    tx = service_tx.copy()
    empty_cols = [
        "estacion", "t_arr_est", "t_dep_est", "B_embarque",
        "D_bajadas", "L_in_abordo", "L_out_abordo", "servicio_label",
        "linea", "direccion", "event_time"
    ]
    if tx.empty:
        return pd.DataFrame(columns=empty_cols)

    tx["t_entrada_viaje"] = pd.to_datetime(tx["t_entrada_viaje"], errors="coerce")
    tx["t_salida_viaje"] = pd.to_datetime(tx["t_salida_viaje"], errors="coerce")
    tx["origen"] = tx["origen"].fillna("").astype(str).str.strip()
    tx["destino"] = tx["destino"].fillna("").astype(str).str.strip()

    linea = str(tx["linea"].dropna().astype(str).iloc[0]).strip() if "linea" in tx.columns and not tx["linea"].dropna().empty else ""
    direccion = str(tx["direccion"].dropna().astype(str).iloc[0]).strip() if "direccion" in tx.columns and not tx["direccion"].dropna().empty else ""
    servicio_label = str(tx["servicio_label"].dropna().astype(str).iloc[0]).strip() if "servicio_label" in tx.columns and not tx["servicio_label"].dropna().empty else "-"

    entry_events = tx.loc[tx["origen"] != "", ["origen", "t_entrada_viaje"]].copy()
    entry_events.columns = ["estacion", "event_time"]
    exit_events = tx.loc[tx["destino"] != "", ["destino", "t_salida_viaje"]].copy()
    exit_events.columns = ["estacion", "event_time"]
    station_events = pd.concat([entry_events, exit_events], ignore_index=True).dropna(subset=["event_time"])

    stations_present = list(dict.fromkeys(
        tx.loc[tx["origen"] != "", "origen"].astype(str).tolist() +
        tx.loc[tx["destino"] != "", "destino"].astype(str).tolist()
    ))

    configured_full = PROFILE_STATION_SEQUENCES.get(normalize_text(linea).replace(" ", ""), {}).get(_normalize_direction_key(direccion), [])
    if configured_full:
        norm_to_actual = {}
        for st in stations_present:
            st_clean = "" if st is None else str(st).strip()
            if st_clean:
                norm_to_actual.setdefault(normalize_text(st_clean), st_clean)
        ordered_stations = [norm_to_actual.get(normalize_text(st), st) for st in configured_full]
        extras = [st for st in stations_present if normalize_text(st) not in {normalize_text(x) for x in configured_full}]
        if station_events.empty:
            extras_ordered = extras
        else:
            extras_ordered = (
                station_events.assign(station_key=normalize_series(station_events["estacion"]))
                .groupby("station_key", as_index=False)["event_time"].median()
                .sort_values(["event_time", "station_key"])["station_key"]
                .tolist()
            )
            extras_lookup = {normalize_text(st): st for st in extras}
            extras_ordered = [extras_lookup[k] for k in extras_ordered if k in extras_lookup]
        order_list = ordered_stations + [st for st in extras_ordered if st not in ordered_stations]
    else:
        if station_events.empty:
            return pd.DataFrame(columns=empty_cols)
        order_list = (
            station_events.groupby("estacion", as_index=False)["event_time"]
            .median()
            .sort_values(["event_time", "estacion"])["estacion"]
            .tolist()
        )

    order_df = pd.DataFrame({"estacion": order_list, "station_idx": range(len(order_list))})
    order_df["station_key"] = normalize_series(order_df["estacion"])
    key_to_idx = dict(zip(order_df["station_key"], order_df["station_idx"]))

    tx["origen_key"] = normalize_series(tx["origen"])
    tx["destino_key"] = normalize_series(tx["destino"])
    tx["origen_idx"] = tx["origen_key"].map(key_to_idx)
    tx["destino_idx"] = tx["destino_key"].map(key_to_idx)

    valid_tx = tx.dropna(subset=["origen_idx", "destino_idx"]).copy()
    valid_tx["origen_idx"] = valid_tx["origen_idx"].astype(int)
    valid_tx["destino_idx"] = valid_tx["destino_idx"].astype(int)

    board = (
        valid_tx.groupby("origen_idx", as_index=False)
        .size().rename(columns={"size": "B_embarque", "origen_idx": "station_idx"})
    )
    alight = (
        valid_tx.groupby("destino_idx", as_index=False)
        .size().rename(columns={"size": "D_bajadas", "destino_idx": "station_idx"})
    )
    arr_times = (
        valid_tx.groupby("origen_idx", as_index=False)["t_entrada_viaje"]
        .median().rename(columns={"origen_idx": "station_idx", "t_entrada_viaje": "t_arr_est"})
    )
    dep_times = (
        valid_tx.groupby("destino_idx", as_index=False)["t_salida_viaje"]
        .median().rename(columns={"destino_idx": "station_idx", "t_salida_viaje": "t_dep_est"})
    )

    profile = (
        order_df.merge(board, how="left", on="station_idx")
        .merge(alight, how="left", on="station_idx")
        .merge(arr_times, how="left", on="station_idx")
        .merge(dep_times, how="left", on="station_idx")
    )
    profile["B_embarque"] = pd.to_numeric(profile["B_embarque"], errors="coerce").fillna(0)
    profile["D_bajadas"] = pd.to_numeric(profile["D_bajadas"], errors="coerce").fillna(0)

    # ── Vectorized onboard calculation: O(K) instead of O(N×K) ─────────────────
    # Build boarding/alighting sparse arrays, then cumsum to get passengers onboard
    n_stations = len(order_df)
    board_arr  = np.zeros(n_stations, dtype=np.int64)
    alight_arr = np.zeros(n_stations, dtype=np.int64)

    orig_arr = valid_tx["origen_idx"].to_numpy(dtype=np.int64)
    dest_arr = valid_tx["destino_idx"].to_numpy(dtype=np.int64)

    # Count boardings at each origin station and alightings at each destination
    for idx in orig_arr:
        if 0 <= idx < n_stations:
            board_arr[idx] += 1
    for idx in dest_arr:
        if 0 <= idx < n_stations:
            alight_arr[idx] += 1

    # L_in_abordo[i]  = passengers already on board as train arrives at station i
    #                 = cumsum(board) up to i-1 - cumsum(alight) up to i-1
    # L_out_abordo[i] = passengers on board after train departs station i
    #                 = cumsum(board) up to i   - cumsum(alight) up to i
    cum_board  = np.cumsum(board_arr)
    cum_alight = np.cumsum(alight_arr)

    # station indices in profile order
    station_indices = profile["station_idx"].to_numpy(dtype=np.int64)
    l_in_arr  = np.where(station_indices > 0,
                         cum_board[station_indices - 1] - cum_alight[station_indices - 1],
                         0)
    l_out_arr = cum_board[station_indices] - cum_alight[station_indices]

    profile["L_in_abordo"]  = l_in_arr.tolist()
    profile["L_out_abordo"] = l_out_arr.tolist()

    profile["t_arr_est"] = pd.to_datetime(profile["t_arr_est"], errors="coerce")
    profile["t_dep_est"] = pd.to_datetime(profile["t_dep_est"], errors="coerce")
    profile["event_time"] = profile["t_arr_est"].fillna(profile["t_dep_est"])

    # Para estaciones sin eventos observados, usar un tiempo sintético solo como apoyo visual
    if profile["event_time"].isna().any():
        base_time = None
        non_null_times = pd.concat([valid_tx["t_entrada_viaje"], valid_tx["t_salida_viaje"]], ignore_index=True).dropna()
        if not non_null_times.empty:
            base_time = non_null_times.min().floor("min")
        else:
            base_time = pd.Timestamp("2000-01-01 00:00:00")
        synthetic = [base_time + pd.Timedelta(minutes=int(idx)) for idx in profile["station_idx"]]
        synthetic = pd.Series(synthetic, index=profile.index)
        profile["event_time"] = profile["event_time"].fillna(synthetic)
        profile["t_arr_est"] = profile["t_arr_est"].fillna(profile["event_time"])
        profile["t_dep_est"] = profile["t_dep_est"].fillna(profile["event_time"])

    profile["servicio_label"] = servicio_label
    profile["linea"] = linea
    profile["direccion"] = direccion

    keep_cols = [
        "estacion", "t_arr_est", "t_dep_est", "event_time", "B_embarque",
        "D_bajadas", "L_in_abordo", "L_out_abordo", "servicio_label",
        "linea", "direccion"
    ]
    return profile[keep_cols].copy()


def build_transactional_profiles_for_subset(profile_tx_df: pd.DataFrame) -> pd.DataFrame:
    profiles = []
    if profile_tx_df.empty:
        return pd.DataFrame()

    for servicio_label, svc_df in profile_tx_df.groupby("servicio_label", sort=False):
        profile = build_transactional_service_profile(svc_df)
        if not profile.empty:
            profiles.append(profile)

    if not profiles:
        return pd.DataFrame()

    return pd.concat(profiles, ignore_index=True)


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

    cap = pd.to_numeric(plot_df.get("capacidad_tren", pd.Series(index=plot_df.index, dtype=float)), errors="coerce")
    if isinstance(cap, pd.Series) and cap.notna().any():
        capacidad = float(cap.dropna().iloc[0])
        fig.add_trace(go.Scatter(x=plot_df["estacion"], y=[capacidad]*len(plot_df),
                                  mode="lines", name="Capacidad",
                                  line=dict(color=TEXT_MUTED, width=2, dash="dash"),
                                  hovertemplate="Capacidad: %{y:,.0f}<extra></extra>"))

    # Batch annotations: una sola llamada a update_layout en vez de N add_annotation
    _abordo_rows = plot_df.dropna(subset=["L_out_abordo"])
    if not _abordo_rows.empty:
        _annots = [
            dict(
                x=row["estacion"], y=row["L_out_abordo"],
                text=fmt_pax(row["L_out_abordo"]),
                showarrow=False, yshift=18,
                font=dict(size=PLOT_ANNOTATION_SIZE, color=SUCCESS),
                bgcolor="rgba(255,255,255,0.96)",
                bordercolor=SUCCESS, borderwidth=1, borderpad=3,
                align="center", xref="x", yref="y",
            )
            for _, row in _abordo_rows.iterrows()
        ]
        existing_annots = list(fig.layout.annotations or [])
        fig.update_layout(annotations=existing_annots + _annots)

    fig.update_layout(
        title=titulo, plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=55,b=20), height=580, barmode="group",
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=station_order or None)
    fig.update_yaxes(title="Pasajeros", tickfont=dict(size=PLOT_FONT_SIZE))
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
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        legend_title_text="Servicio", hovermode="x unified",
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.01),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=station_order or None)
    fig.update_yaxes(title="Pasajeros a bordo", tickfont=dict(size=PLOT_FONT_SIZE))
    return fig


def build_service_level_summary(profile_subset: pd.DataFrame, profile_schema: str) -> pd.DataFrame:
    columns = [
        "servicio_label", "hora_salida", "hora_salida_fmt", "estacion_origen",
        "pasajeros_transportados", "max_abordo"
    ]
    if profile_subset.empty:
        return pd.DataFrame(columns=columns)

    summaries = []
    for servicio_label, svc_df in profile_subset.groupby("servicio_label", sort=False):
        svc_df = svc_df.copy()
        if profile_schema == "transactional":
            profile = build_transactional_service_profile(svc_df)
        else:
            profile = svc_df.copy()
            if "event_time" not in profile.columns:
                arr = pd.to_datetime(profile["t_arr_est"], errors="coerce") if "t_arr_est" in profile.columns else pd.Series(index=profile.index, dtype="datetime64[ns]")
                dep = pd.to_datetime(profile["t_dep_est"], errors="coerce") if "t_dep_est" in profile.columns else pd.Series(index=profile.index, dtype="datetime64[ns]")
                profile["event_time"] = arr.fillna(dep)
        if profile.empty:
            continue

        station_order = get_station_order_from_profile(profile)
        if station_order:
            origin_station = str(station_order[0])
        elif "estacion" in profile.columns and not profile["estacion"].dropna().empty:
            origin_station = str(profile["estacion"].dropna().astype(str).iloc[0]).strip()
        else:
            origin_station = "-"

        departure_ts = pd.NaT
        if profile_schema == "transactional":
            if origin_station != "-" and "origen" in svc_df.columns:
                origin_mask = normalize_series(svc_df["origen"]) == normalize_text(origin_station)
                departure_candidates = pd.to_datetime(svc_df.loc[origin_mask, "t_entrada_viaje"], errors="coerce").dropna()
                if not departure_candidates.empty:
                    departure_ts = departure_candidates.min()
            if pd.isna(departure_ts) and "event_time" in profile.columns:
                fallback = pd.to_datetime(profile["event_time"], errors="coerce").dropna()
                if not fallback.empty:
                    departure_ts = fallback.min()
        else:
            ordered_profile = profile.copy()
            if station_order and "estacion" in ordered_profile.columns:
                ordered_profile["estacion"] = pd.Categorical(ordered_profile["estacion"], categories=station_order, ordered=True)
                sort_cols = ["estacion"]
                if "event_time" in ordered_profile.columns:
                    sort_cols.append("event_time")
                ordered_profile = ordered_profile.sort_values(sort_cols)
            if not ordered_profile.empty:
                first_row = ordered_profile.iloc[0]
                for col in ["t_dep_est", "t_arr_est", "event_time"]:
                    if col in ordered_profile.columns:
                        ts = pd.to_datetime(first_row[col], errors="coerce")
                        if pd.notna(ts):
                            departure_ts = ts
                            break

        pasajeros_transportados = float(pd.to_numeric(profile.get("D_bajadas"), errors="coerce").fillna(0).sum()) if "D_bajadas" in profile.columns else 0.0
        max_abordo = float(pd.to_numeric(profile.get("L_out_abordo"), errors="coerce").dropna().max()) if "L_out_abordo" in profile.columns and pd.to_numeric(profile.get("L_out_abordo"), errors="coerce").notna().any() else np.nan

        summaries.append({
            "servicio_label": str(servicio_label),
            "hora_salida": departure_ts,
            "estacion_origen": origin_station,
            "pasajeros_transportados": pasajeros_transportados,
            "max_abordo": max_abordo,
        })

    summary_df = pd.DataFrame(summaries)
    if summary_df.empty:
        return pd.DataFrame(columns=columns)

    summary_df["hora_salida"] = pd.to_datetime(summary_df["hora_salida"], errors="coerce")
    summary_df = summary_df.sort_values(["hora_salida", "servicio_label"], na_position="last").reset_index(drop=True)
    summary_df["hora_salida_fmt"] = summary_df["hora_salida"].dt.strftime("%H:%M:%S").fillna("-")
    return summary_df


def build_service_transport_chart(summary_df: pd.DataFrame, title: str) -> go.Figure:
    plot_df = summary_df.copy()
    if plot_df.empty:
        fig = go.Figure()
        fig.update_layout(title=title, plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, height=430)
        return fig

    plot_df["servicio_label"] = plot_df["servicio_label"].astype(str).str.strip()
    plot_df["hora_salida_fmt"] = plot_df["hora_salida_fmt"].fillna("-").astype(str)
    plot_df["estacion_origen"] = plot_df["estacion_origen"].fillna("-").astype(str)
    label_col = "servicio_display_label" if "servicio_display_label" in plot_df.columns else None

    if not label_col:
        plot_df["hora_salida_corta"] = plot_df["hora_salida_fmt"].astype(str).str.slice(0, 5)
        dup_rank = plot_df.groupby(["servicio_label", "hora_salida_corta"]).cumcount() + 1
        dup_total = plot_df.groupby(["servicio_label", "hora_salida_corta"])["servicio_label"].transform("size")
        plot_df["servicio_display_label"] = (
            plot_df["servicio_label"].astype(str) + " | "
            + plot_df["hora_salida_corta"].replace({"-": "s/h"}) + " | "
            + plot_df["estacion_origen"].astype(str)
        )
        plot_df["servicio_display_label"] = np.where(
            dup_total > 1,
            plot_df["servicio_display_label"] + " (" + dup_rank.astype(str) + ")",
            plot_df["servicio_display_label"],
        )
        label_col = "servicio_display_label"

    if "servicio_orden_idx" in plot_df.columns:
        plot_df = plot_df.sort_values(["servicio_orden_idx", "servicio_label"], kind="stable", na_position="last").reset_index(drop=True)
    else:
        plot_df = plot_df.sort_values(["servicio_label"], kind="stable", na_position="last").reset_index(drop=True)

    service_order = plot_df[label_col].tolist()
    # Vectorized formatting: fmt_pax/fmt_number sobre Series completas
    def _vec_fmt_pax(series: pd.Series) -> pd.Series:
        s = pd.to_numeric(series, errors="coerce")
        return s.apply(lambda v: f"{float(v):,.0f}".replace(",", ".") if pd.notna(v) else "-")
    def _vec_fmt_clp(series: pd.Series) -> pd.Series:
        s = pd.to_numeric(series, errors="coerce")
        return s.apply(lambda v: f"$ {v:,.0f}".replace(",", ".") if pd.notna(v) else "-")
    plot_df["pasajeros_label"]   = _vec_fmt_pax(plot_df["pasajeros_transportados"])
    plot_df["max_abordo_label"]  = _vec_fmt_pax(plot_df["max_abordo"])
    plot_df["tarifa_media_label"]= _vec_fmt_clp(plot_df.get("tarifa_media_aprox", pd.Series(dtype=float)))
    plot_df["recaudacion_label"] = _vec_fmt_clp(plot_df.get("recaudacion_aprox", pd.Series(dtype=float)))
    plot_df["tx_cruzadas_label"] = _vec_fmt_pax(plot_df.get("tx_cruzadas", pd.Series(dtype=float)))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=plot_df[label_col],
        y=plot_df["pasajeros_transportados"],
        marker_color=EFE_BLUE,
        text=plot_df["pasajeros_label"],
        textposition="outside",
        customdata=plot_df[["servicio_label", "hora_salida_fmt", "estacion_origen", "max_abordo_label", "tarifa_media_label", "recaudacion_label", "tx_cruzadas_label"]].values,
        hovertemplate=(
            "<b>Servicio %{customdata[0]}</b><br>"
            "Hora salida: %{customdata[1]}<br>"
            "Origen: %{customdata[2]}<br>"
            "Pasajeros transportados: %{y:,.0f}<br>"
            "Máx. a bordo: %{customdata[3]}<br>"
            "Tarifa media aprox.: %{customdata[4]}<br>"
            "Recaudación aprox.: %{customdata[5]}<br>"
            "Tx cruzadas: %{customdata[6]}<extra></extra>"
        ),
        name="Pasajeros transportados",
    ))
    fig.update_layout(
        title=title,
        plot_bgcolor=EFE_WHITE,
        paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20),
        height=520,
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        showlegend=False,
    )
    fig.update_xaxes(
        title="Servicio | Hora de salida | Estación origen",
        tickangle=-90,
        tickfont=dict(size=PLOT_FONT_SIZE),
        categoryorder="array",
        categoryarray=service_order,
    )
    fig.update_yaxes(title="Pasajeros transportados", tickfont=dict(size=PLOT_FONT_SIZE))
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

    # Optimizado: px.line con color="estacion" en lugar de un trace por estación
    if hour_order:
        hourly["hora"] = pd.Categorical(hourly["hora"], categories=hour_order, ordered=True)
    if station_order:
        hourly["estacion"] = pd.Categorical(hourly["estacion"].astype(str),
                                             categories=[str(s) for s in station_order], ordered=True)
    hourly = hourly.sort_values(["estacion", "hora"])

    fig = px.line(hourly, x="hora", y="total", color="estacion", markers=True,
                  category_orders={"hora": hour_order or [], "estacion": [str(s) for s in (station_order or [])]},
                  title="Movimientos por hora y estación")
    fig.update_traces(line=dict(width=2), marker=dict(size=6),
                      hovertemplate="<b>%{fullData.name}</b><br>%{x}<br>Movimientos: %{y:,.0f}<extra></extra>")
    fig.update_layout(
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20,r=20,t=55,b=20), height=440,
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        legend_title_text="Estación",
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
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
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
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
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
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
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
        font=dict(color=TEXT_MAIN, size=11), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
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
        barmode="group", font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
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
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
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
            textfont=dict(size=13, color=EFE_BLUE, family="Arial, sans-serif"),
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
            textfont=dict(size=13, color=EFE_BLUE, family="Arial, sans-serif"),
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
        paper_bgcolor=EFE_WHITE, font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
    )
    return fig


def build_od_bubble_map(flow_df: pd.DataFrame, category_col: str,
                        station_ref: pd.DataFrame, selected_station: str,
                        title_text: str, bubble_color: str) -> go.Figure | None:
    """
    Mapa de burbujas para mostrar todos los puntos de origen/destino asociados
    a la estación seleccionada, evitando la sobrecarga visual de líneas OD.
    """
    if station_ref is None or station_ref.empty:
        return None
    if flow_df is None:
        flow_df = pd.DataFrame(columns=[category_col, "viajes"])

    ref = station_ref.copy()
    ref["station_key"] = ref["station_key"].astype(str)
    selected_key = normalize_text(selected_station)
    selected_df = ref[ref["station_key"] == selected_key].copy()
    if selected_df.empty:
        return None
    selected_row = selected_df.iloc[0]

    plot_df = flow_df.copy()
    if category_col not in plot_df.columns:
        plot_df[category_col] = []
    if "viajes" not in plot_df.columns:
        plot_df["viajes"] = []

    plot_df["station_key"] = normalize_series(plot_df[category_col]) if not plot_df.empty else pd.Series(dtype=str)
    plot_df = plot_df.merge(
        ref[["station_key", "estacion", "latitud", "longitud"]],
        how="left", on="station_key", suffixes=("", "_ref")
    )
    plot_df = plot_df.dropna(subset=["latitud", "longitud"]).copy()

    if not plot_df.empty and float(plot_df["viajes"].max()) > float(plot_df["viajes"].min()):
        plot_df["marker_size"] = 12 + ((plot_df["viajes"] - plot_df["viajes"].min()) /
                                        (plot_df["viajes"].max() - plot_df["viajes"].min())) * 20
    else:
        plot_df["marker_size"] = 16 if not plot_df.empty else pd.Series(dtype=float)

    all_points = pd.concat([
        pd.DataFrame([{
            "estacion": selected_station,
            "latitud": float(selected_row["latitud"]),
            "longitud": float(selected_row["longitud"]),
        }]),
        plot_df[["estacion", "latitud", "longitud"]] if not plot_df.empty else pd.DataFrame(columns=["estacion", "latitud", "longitud"]),
    ], ignore_index=True).drop_duplicates(subset=["estacion"])

    lat_min = float(all_points["latitud"].min()); lat_max = float(all_points["latitud"].max())
    lon_min = float(all_points["longitud"].min()); lon_max = float(all_points["longitud"].max())
    lat_pad = max((lat_max - lat_min) * 0.18, 0.015)
    lon_pad = max((lon_max - lon_min) * 0.65, 0.04)

    fig = go.Figure()

    if not plot_df.empty:
        fig.add_trace(go.Scattermapbox(
            lat=plot_df["latitud"].astype(float),
            lon=plot_df["longitud"].astype(float),
            mode="markers+text",
            text=plot_df["estacion"].astype(str),
            textposition="top right",
            textfont=dict(size=13, color=EFE_BLUE),
            marker=dict(size=plot_df["marker_size"], color=bubble_color, opacity=0.72, sizemode="diameter"),
            customdata=plot_df[["estacion", "viajes"]].values,
            hovertemplate="<b>%{customdata[0]}</b><br>Viajes: %{customdata[1]:,.0f}<extra></extra>",
            showlegend=False,
        ))

    fig.add_trace(go.Scattermapbox(
        lat=[float(selected_row["latitud"])],
        lon=[float(selected_row["longitud"])],
        mode="markers+text",
        text=[str(selected_station)],
        textposition="top right",
        textfont=dict(size=13, color=EFE_BLUE),
        marker=dict(size=18, color=WARNING, opacity=0.95, sizemode="diameter"),
        hovertemplate=f"<b>{selected_station}</b><extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        title=title_text,
        mapbox=dict(
            style="white-bg",
            layers=[dict(
                sourcetype="raster",
                source=["https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"],
                below="traces",
            )],
            bounds=dict(
                west=lon_min - lon_pad,
                east=lon_max + lon_pad,
                south=lat_min - lat_pad,
                north=lat_max + lat_pad,
            ),
        ),
        margin=dict(l=0, r=0, t=45, b=0),
        height=460,
        paper_bgcolor=EFE_WHITE,
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
    )
    return fig


def build_od_station_bar_chart(flow_df: pd.DataFrame, category_col: str,
                               station_ref: pd.DataFrame, title: str,
                               bar_color: str) -> go.Figure | None:
    """
    Distribución de viajes por estación ordenada de mayor a menor, tipo Pareto.
    """
    if flow_df is None or flow_df.empty:
        return None

    plot_df = flow_df.copy()
    plot_df[category_col] = plot_df[category_col].fillna("").astype(str).str.strip()
    plot_df = plot_df[plot_df[category_col] != ""].copy()
    if plot_df.empty:
        return None

    plot_df = plot_df.sort_values(["viajes", category_col], ascending=[False, True]).reset_index(drop=True)
    station_order = plot_df[category_col].astype(str).tolist()

    total_viajes = float(plot_df["viajes"].sum()) if not plot_df.empty else 0.0
    plot_df["participacion"] = np.where(total_viajes > 0, plot_df["viajes"] / total_viajes * 100, 0.0)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=plot_df[category_col],
        y=plot_df["viajes"],
        marker_color=bar_color,
        hovertemplate="<b>%{x}</b><br>Viajes: %{y:,.0f}<br>Participación: %{customdata:.1f}%<extra></extra>",
        customdata=plot_df["participacion"],
        name="Viajes",
    ))
    fig.update_layout(
        title=title,
        plot_bgcolor=EFE_WHITE,
        paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=50, b=20),
        height=340,
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        showlegend=False,
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array", categoryarray=station_order)
    fig.update_yaxes(title="Viajes")
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
# Vectorized: evita .apply() fila a fila
iniciativas["vencida"] = (
    pd.to_datetime(iniciativas["fecha_fin"], errors="coerce") < pd.Timestamp(today)
) & iniciativas["fecha_fin"].notna()
_estado_norm = iniciativas["estado"].fillna("").astype(str).str.strip()
iniciativas["critica"] = (
    (_estado_norm == "Atrasada") |
    (iniciativas["vencida"] & (_estado_norm != "Finalizada"))
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
st.session_state.setdefault("dashboard_theme_mode", "☀️ Claro")

header_left, header_right = st.columns([5.2, 1.2])
with header_right:
    theme_mode = option_selector(
        "Tema",
        ["☀️ Claro", "🌙 Oscuro"],
        key="dashboard_theme_mode_selector",
        default=st.session_state.get("dashboard_theme_mode", "☀️ Claro"),
        horizontal=True,
    ) or st.session_state.get("dashboard_theme_mode", "☀️ Claro")
    st.session_state["dashboard_theme_mode"] = theme_mode

apply_runtime_palette(DARK_COLORS if "Oscuro" in st.session_state["dashboard_theme_mode"] else LIGHT_COLORS)
st.markdown(build_runtime_css("Oscuro" if "Oscuro" in st.session_state["dashboard_theme_mode"] else "Claro", COLORS), unsafe_allow_html=True)

with header_left:
    st.markdown("<div class='hero-minimal'>", unsafe_allow_html=True)
    logo_col, title_col = st.columns([0.72, 5.0])
    with logo_col:
        for logo_path in [Path(__file__).resolve().parent / "assets" / "logoefe-azul.png",
                          Path(__file__).resolve().parent / "logoefe-azul.png"]:
            if logo_path.exists():
                st.image(str(logo_path), use_container_width=True)
                break
    with title_col:
        st.markdown("<div class='main-title'>KPIs e Iniciativas — Gerencia de Pasajeros</div>", unsafe_allow_html=True)
        st.markdown("<div class='subtitle'>Panel ejecutivo para monitorear desempeño, perfiles de carga y análisis por estación.</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# FILTROS
# =========================================================
estados_ini  = sorted(iniciativas["estado"].dropna().astype(str).unique().tolist())
prioridades  = sorted(iniciativas["prioridad"].dropna().astype(str).unique().tolist())
responsables = sorted(iniciativas["responsable"].dropna().astype(str).unique().tolist())

st.session_state.setdefault("estado_body_filter", estados_ini)
st.session_state.setdefault("prioridad_body_filter", prioridades)
st.session_state.setdefault("responsable_body_filter", responsables)

servicios_sel = servicios_lista
estados_ini_sel = st.session_state.get("estado_body_filter", estados_ini) or estados_ini
prioridades_sel = st.session_state.get("prioridad_body_filter", prioridades) or prioridades
responsables_sel = st.session_state.get("responsable_body_filter", responsables) or responsables

# =========================================================
# FILTRADO PRINCIPAL
# =========================================================
kpis_f = kpis.copy()

iniciativas_f = iniciativas[
    iniciativas["servicio"].isin(servicios_sel) &
    iniciativas["estado"].isin(estados_ini_sel) &
    iniciativas["prioridad"].isin(prioridades_sel) &
    iniciativas["responsable"].isin(responsables_sel)
].copy()

kpis_hist = kpis.copy()

if "orden" in kpis_f.columns:
    kpis_f = kpis_f.sort_values(["orden","servicio","nombre"])
else:
    kpis_f = kpis_f.sort_values(["nombre","servicio"])

# =========================================================
# NAVEGACIÓN
# =========================================================
SERVICE_NAV_OPTIONS = ["Biotren", "Tren Araucanía", "Laja Talcahuano", "Llanquihue Puerto Montt", "Personas"]
BIOTREN_DETAIL_PAGES = ["KPIs", "Perfil de Carga", "Análisis por Estación"]
STANDARD_SERVICE_PAGES = ["KPIs"]

with st.container():
    st.markdown("<span class='sticky-nav-anchor'></span>", unsafe_allow_html=True)
    st.markdown("<div class='nav-panel'>", unsafe_allow_html=True)
    root_sel = option_selector(
        "Servicio / vista",
        SERVICE_NAV_OPTIONS,
        key="main_root_selector", default="Biotren", horizontal=True,
    )
    if root_sel == "Personas":
        section_sel = "Personas"
    else:
        service_subpages = BIOTREN_DETAIL_PAGES if root_sel == "Biotren" else STANDARD_SERVICE_PAGES
        section_label = option_selector(
            "Navegación",
            service_subpages,
            key="main_service_page_selector",
            default=service_subpages[0], horizontal=True,
        )
        section_map = {
            "KPIs": "KPIs por Servicio",
            "Perfil de Carga": "Perfil de Carga",
            "Análisis por Estación": "OD Estaciones",
        }
        section_sel = section_map.get(section_label, "KPIs por Servicio")
    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# SECCIONES
# =========================================================

def render_resumen_ejecutivo(target_service: str | None = None):
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    top_title_col, top_period_col = st.columns([4.5, 1.2])
    with top_title_col:
        st.markdown("<div class='section-title'>KPIs por Servicio</div>", unsafe_allow_html=True)
        st.markdown("<div class='section-subtitle'>KPIs del período por servicio y evolución histórica del indicador seleccionado.</div>",
                    unsafe_allow_html=True)
    with top_period_col:
        period_key = f"periodo_kpi_selector_{target_service or 'general'}"
        periodo_sel_local = st.selectbox("Período de análisis", options=periodos,
                                         index=default_period_index, key=period_key)

    kpis_periodo = kpis[kpis["periodo"].astype(str) == str(periodo_sel_local)].copy()
    servicios_con_datos = sorted(kpis_periodo["servicio"].dropna().astype(str).unique().tolist())
    if target_service:
        servicios_con_datos = [s for s in servicios_con_datos if s == str(target_service)]
    if kpis_periodo.empty or not servicios_con_datos:
        st.warning("No existen KPIs para los filtros seleccionados.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    resumen_srv = str(target_service) if target_service else option_selector(
        "Servicio visible", servicios_con_datos,
        key="resumen_servicio_selector",
        default=servicios_con_datos[0], horizontal=True)

    servicio_df = kpis_periodo[kpis_periodo["servicio"].astype(str) == str(resumen_srv)].copy()
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

    hist_plot = hist_sel.groupby("periodo", as_index=False)["valor"].sum()
    fig_trend = build_trend_line_chart(hist_plot, resumen_kpi_sel, unit_hist, resumen_srv)
    fig_trend.update_layout(height=470)
    show_plot(fig_trend, use_container_width=True)

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
            show_plot(fig_bt, use_container_width=True)
    with col_b:
        otros_hist = hist_kpi[hist_kpi["servicio"].isin(RURAL_SERVICES)].copy()
        if otros_hist.empty:
            st.info("No hay datos de otros servicios para el KPI seleccionado.")
        else:
            fig_ot = build_line_chart(
                otros_hist.groupby(["periodo","servicio"], as_index=False)["valor"].sum(),
                f"{kpi_sel} — Otros servicios", color="servicio",
                height=340, unit=unit_col, kpi_name=kpi_sel)
            show_plot(fig_ot, use_container_width=True)

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
                            title=f"{servicio}",
                            plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
                            margin=dict(l=20,r=20,t=50,b=20), height=340,
                            font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
                        )
                        show_plot(fig_meta, use_container_width=True)
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
    title_col, filter_col = st.columns([4.6, 1.2])
    with title_col:
        st.markdown("<div class='section-title'>Vista por persona</div>", unsafe_allow_html=True)
        st.markdown("<div class='section-subtitle'>Seguimiento de iniciativas, avance y estado por responsable.</div>",
                    unsafe_allow_html=True)
    with filter_col:
        popover_ctx = st.popover if hasattr(st, "popover") else st.expander
        pop_kwargs  = {} if hasattr(st, "popover") else {"expanded": False}
        with popover_ctx("Filtros", **pop_kwargs):
            st.multiselect("Estado iniciativa", options=estados_ini, default=estados_ini_sel, key="estado_body_filter")
            st.multiselect("Prioridad", options=prioridades, default=prioridades_sel, key="prioridad_body_filter")
            st.multiselect("Responsable", options=responsables, default=responsables_sel, key="responsable_body_filter")
            if st.button("Restablecer", key="reset_personas_filters", use_container_width=True):
                st.session_state["estado_body_filter"] = estados_ini
                st.session_state["prioridad_body_filter"] = prioridades
                st.session_state["responsable_body_filter"] = responsables
                st.rerun()

    iniciativas_local = iniciativas[
        iniciativas["servicio"].isin(servicios_lista) &
        iniciativas["estado"].isin(st.session_state.get("estado_body_filter", estados_ini) or estados_ini) &
        iniciativas["prioridad"].isin(st.session_state.get("prioridad_body_filter", prioridades) or prioridades) &
        iniciativas["responsable"].isin(st.session_state.get("responsable_body_filter", responsables) or responsables)
    ].copy()

    total_ini   = len(iniciativas_local)
    en_curso    = int((iniciativas_local["estado"] == "En curso").sum())
    atrasadas   = int((iniciativas_local["estado"] == "Atrasada").sum())
    finalizadas = int((iniciativas_local["estado"] == "Finalizada").sum())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total iniciativas", total_ini)
    m2.metric("En curso", en_curso)
    m3.metric("Atrasadas", atrasadas)
    m4.metric("Finalizadas", finalizadas)

    personas_opts = sorted(iniciativas_local["responsable"].dropna().astype(str).unique().tolist())
    persona_sel = option_selector("Seleccione responsable", personas_opts,
                                   key="persona_selector",
                                   default=personas_opts[0] if personas_opts else None)
    if not personas_opts or not persona_sel:
        st.warning("No hay responsables disponibles con los filtros actuales.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    per_df = iniciativas_local[iniciativas_local["responsable"] == persona_sel].copy()
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
                              font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE))
            fig.update_xaxes(title="Avance %"); fig.update_yaxes(title="")
            show_plot(fig, use_container_width=True)
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
                               font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE), title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
                               showlegend=False)
            show_plot(fig2, use_container_width=True)

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

    default_per = periodos_detalle[-1]
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
            show_plot(build_station_map(valid_map_df), use_container_width=True)
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
                barmode="group", font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
                title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig_bar.update_xaxes(title="", tickangle=-90, categoryorder="array",
                                  categoryarray=station_order)
            fig_bar.update_yaxes(title="Pasajeros")
            show_plot(fig_bar, use_container_width=True)

    st.markdown("</div></div>", unsafe_allow_html=True)



def classify_profile_day_type(fecha_value) -> str | None:
    """Versión escalar. Para clasificar una Serie completa, usar classify_day_type_series()."""
    if pd.isna(fecha_value):
        return None
    wd = int(pd.Timestamp(fecha_value).weekday())
    return "Laboral" if wd < 5 else ("Sábado" if wd == 5 else "Domingo")


def classify_day_type_series(fecha_series: pd.Series) -> pd.Series:
    """Versión vectorizada de classify_profile_day_type para columnas completas."""
    ts = pd.to_datetime(fecha_series, errors="coerce")
    wd = ts.dt.weekday
    return pd.Series(
        np.select([wd < 5, wd == 5], ["Laboral", "Sábado"], default="Domingo"),
        index=fecha_series.index,
        dtype=object,
    ).where(ts.notna(), None)


def month_period_to_label(period_value) -> str:
    if period_value is None or pd.isna(period_value):
        return "-"
    ts = pd.Timestamp(str(period_value))
    return f"{_MESES_LARGO.get(int(ts.month), str(ts.month))} {int(ts.year)}"


@st.cache_data(show_spinner="Calculando promedios mensuales…")
def build_monthly_profile_tables_by_direction(perfil_df: pd.DataFrame,
                                              profile_schema: str,
                                              profile_srv: str,
                                              month_period: str,
                                              linea_sel: str,
                                              itinerary_summary_df: pd.DataFrame,
                                              service_order_df: pd.DataFrame,
                                              turnstile_df: pd.DataFrame,
                                              turnstile_status: str) -> tuple[dict, list]:
    if perfil_df.empty or not month_period or not linea_sel:
        return {}, []

    fecha_series = pd.to_datetime(perfil_df["fecha"], errors="coerce")
    month_mask = fecha_series.dt.to_period("M").astype(str) == str(month_period)
    perfil_mes = perfil_df.loc[month_mask].copy()
    if perfil_mes.empty:
        return {}, []

    perfil_mes = perfil_mes[perfil_mes["linea"].astype(str).str.strip() == str(linea_sel)].copy()
    if perfil_mes.empty:
        return {}, []

    directions = [x for x in list(dict.fromkeys(perfil_mes["direccion"].dropna().astype(str).str.strip().tolist())) if x]
    if not directions:
        return {}, []

    daily_rows = []
    fechas_mes = sorted([x for x in perfil_mes["fecha"].dropna().unique().tolist() if pd.notna(x)])
    for fecha_day in fechas_mes:
        perfil_day_all = perfil_mes[perfil_mes["fecha"] == fecha_day].copy()
        if perfil_day_all.empty:
            continue

        fare_day_all = pd.DataFrame()
        if normalize_text(profile_srv) == "biotren" and profile_schema == "transactional" and turnstile_status == "ok" and not turnstile_df.empty:
            turnstile_day = turnstile_df[turnstile_df["fecha"] == fecha_day].copy()
            if not turnstile_day.empty:
                _, fare_day_all, _ = match_turnstile_transactions_to_profile(turnstile_day, perfil_day_all, tolerance_minutes=20)

        for dir_sel in directions:
            perfil_day_dir = perfil_day_all[perfil_day_all["direccion"].astype(str).str.strip() == str(dir_sel)].copy()
            if perfil_day_dir.empty:
                continue

            daily_summary = build_service_level_summary(perfil_day_dir, profile_schema)
            if daily_summary.empty:
                continue

            daily_summary = enrich_service_summary_with_itinerary(
                daily_summary, itinerary_summary_df, profile_srv, linea_sel, dir_sel, fecha_day
            )
            daily_summary = apply_service_order_and_labels(
                daily_summary, service_order_df, profile_srv, linea_sel, dir_sel, fecha_day
            )

            for col in ["tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox", "recaudacion_aprox", "desviacion_tarifa_aprox", "diff_mediana_min", "match_ref_principal"]:
                if col not in daily_summary.columns:
                    daily_summary[col] = np.nan

            if not fare_day_all.empty:
                fare_dir = fare_day_all[
                    (fare_day_all["linea"].astype(str).str.strip() == str(linea_sel)) &
                    (fare_day_all["direccion"].astype(str).str.strip() == str(dir_sel))
                ].copy()
                if not fare_dir.empty:
                    daily_summary = daily_summary.drop(columns=[c for c in ["tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox", "recaudacion_aprox", "desviacion_tarifa_aprox", "diff_mediana_min", "match_ref_principal"] if c in daily_summary.columns], errors="ignore")
                    daily_summary = daily_summary.merge(
                        fare_dir[["servicio_label", "tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox", "recaudacion_aprox", "desviacion_tarifa_aprox", "diff_mediana_min", "match_ref_principal"]],
                        how="left", on="servicio_label"
                    )

            daily_summary["tarifa_media_aprox"] = pd.to_numeric(daily_summary.get("tarifa_media_aprox"), errors="coerce")
            daily_summary["pasajeros_transportados"] = pd.to_numeric(daily_summary.get("pasajeros_transportados"), errors="coerce")
            daily_summary["tx_cruzadas"] = pd.to_numeric(daily_summary.get("tx_cruzadas"), errors="coerce")
            daily_summary["fecha"] = fecha_day
            daily_summary["tipo_dia"] = classify_profile_day_type(fecha_day)  # scalar ok (single fecha)
            daily_summary["direccion_ref"] = dir_sel
            daily_rows.append(daily_summary)

    if not daily_rows:
        return {}, directions

    monthly_daily = pd.concat(daily_rows, ignore_index=True)
    result = {}
    for tipo_dia in ["Laboral", "Sábado", "Domingo"]:
        result[tipo_dia] = {}
        temp_tipo = monthly_daily[monthly_daily["tipo_dia"] == tipo_dia].copy()
        for dir_sel in directions:
            temp = temp_tipo[temp_tipo["direccion_ref"].astype(str).str.strip() == str(dir_sel)].copy()
            if temp.empty:
                result[tipo_dia][dir_sel] = pd.DataFrame()
                continue

            # ── Vectorized aggregation: elimina el loop for servicio_label ──────────
            temp = temp.sort_values(["servicio_orden_idx", "fecha", "servicio_label"], na_position="last")
            temp["_tx"]     = pd.to_numeric(temp.get("tx_cruzadas"),           errors="coerce").fillna(0)
            temp["_tarifa"] = pd.to_numeric(temp.get("tarifa_media_aprox"),    errors="coerce")
            temp["_pax"]    = pd.to_numeric(temp.get("pasajeros_transportados"),errors="coerce")

            # Weighted mean tariff: sum(tarifa * tx) / sum(tx); fallback to simple mean
            temp["_tarifa_x_tx"] = temp["_tarifa"].fillna(0) * temp["_tx"]

            grp = temp.groupby("servicio_label", sort=False)

            agg_df = grp.agg(
                tx_sum               = ("_tx",                  "sum"),
                tarifa_x_tx_sum      = ("_tarifa_x_tx",         "sum"),
                tarifa_mean          = ("_tarifa",              "mean"),
                pax_mean             = ("_pax",                 "mean"),
                servicio_display_label = ("servicio_display_label", "first"),
            ).reset_index()

            # tarifa_mes: weighted if tx_sum > 0 and at least one non-NaN tarifa_mean
            has_weight = (agg_df["tx_sum"] > 0) & agg_df["tarifa_mean"].notna()
            agg_df["tarifa_media_mes"] = np.where(
                has_weight,
                agg_df["tarifa_x_tx_sum"] / agg_df["tx_sum"],
                agg_df["tarifa_mean"],
            )
            agg_df["pasajeros_promedio_mes"] = agg_df["pax_mean"]

            # servicio_orden_idx: take minimum (first) value per service
            orden_df = grp["servicio_orden_idx"].min().reset_index() if "servicio_orden_idx" in temp.columns else pd.DataFrame()
            if not orden_df.empty:
                orden_df["servicio_orden_idx"] = pd.to_numeric(orden_df["servicio_orden_idx"], errors="coerce")
                agg_df = agg_df.merge(orden_df, on="servicio_label", how="left")
            else:
                agg_df["servicio_orden_idx"] = np.nan

            agg_df["servicio_display_label"] = agg_df["servicio_display_label"].fillna(agg_df["servicio_label"]).astype(str)
            result_df = agg_df[["servicio_label", "servicio_display_label", "servicio_orden_idx", "pasajeros_promedio_mes", "tarifa_media_mes"]].copy()
            result_df["servicio_orden_idx"] = pd.to_numeric(result_df["servicio_orden_idx"], errors="coerce")
            result_df = result_df.sort_values(["servicio_orden_idx", "servicio_label"], kind="stable", na_position="last").reset_index(drop=True)
            result[tipo_dia][dir_sel] = result_df

    return result, directions

def render_perfil_carga(default_service: str | None = None):
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Perfil de Carga</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Reconstrucción del perfil de carga por servicio a partir de transacciones OD: embarques, bajadas y pasajeros a bordo por estación.</div>",
                unsafe_allow_html=True)

    service_options = list(PROFILE_SERVICE_CONFIG.keys())
    if default_service and default_service in service_options:
        profile_srv = default_service
    else:
        profile_srv = st.selectbox("Servicio de perfil", options=service_options, index=0, key="profile_service_root_selector")

    perfil_df, perfil_path, perfil_missing, perfil_files, perfil_status = load_profile_service_data(
        profile_srv, str(data_path))
    if isinstance(perfil_df, pd.DataFrame):
        profile_schema = perfil_df.attrs.get("profile_schema")
        if not profile_schema and "profile_schema" in perfil_df.columns and not perfil_df["profile_schema"].dropna().empty:
            profile_schema = str(perfil_df["profile_schema"].dropna().astype(str).iloc[0]).strip().lower()
        profile_schema = profile_schema or "aggregated"
    else:
        profile_schema = "aggregated"
    folder_name = PROFILE_SERVICE_CONFIG.get(profile_srv, {}).get("folder_candidates", ["perfil_carga"])[0]

    if perfil_status in ("no_data",) or perfil_df.empty:
        st.info(f"No se encontraron archivos CSV para <b>{profile_srv}</b>. Cree la carpeta <b>{folder_name}</b> y agregue los archivos diarios. Ruta buscada: <b>{perfil_path}</b>.", icon="ℹ️")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    if perfil_status == "unsupported_format" or perfil_missing:
        st.warning(f"Archivos detectados, pero formato no compatible. Columnas faltantes: <b>{', '.join(perfil_missing)}</b>.")
        if perfil_files:
            st.caption(f"Archivos detectados: {len(perfil_files)} | carpeta: {perfil_path}")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_disponibles = sorted([x for x in perfil_df["fecha"].dropna().unique().tolist() if pd.notna(x)])
    if not fechas_disponibles:
        st.warning("No existen fechas válidas en los archivos de perfil de carga.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    itinerary_summary_df, itinerary_detail_df, itinerary_path, itinerary_files, itinerary_status = load_itinerary_reference(str(data_path))
    service_order_df, service_order_path, service_order_files, service_order_status = load_service_order_reference(str(data_path))
    turnstile_df, turnstile_path, turnstile_missing, turnstile_files, turnstile_status = load_turnstile_service_data(profile_srv, str(data_path))

    tab_diario, tab_mensual = st.tabs(["Análisis diario", "Promedio mensual"])

    with tab_diario:
        fechas_set = set(fechas_disponibles)
        fecha_default = fechas_disponibles[-1]
        fecha_key = f"perfil_fecha_cal_{profile_srv}"
        fecha_prev = st.session_state.get(fecha_key)
        if isinstance(fecha_prev, date):
            fecha_default = fecha_prev if fecha_prev in fechas_set else min(fechas_disponibles, key=lambda d: abs((d-fecha_prev).days))

        fecha_sel_input = st.date_input(
            "📅 Fecha",
            value=fecha_default,
            min_value=fechas_disponibles[0],
            max_value=fechas_disponibles[-1],
            format="DD/MM/YYYY",
            key=fecha_key,
        )

        fecha_sel = fecha_sel_input
        if fecha_sel not in fechas_set:
            fecha_sel = min(fechas_disponibles, key=lambda d: abs((d-fecha_sel).days))
            st.info(f"Fecha sin datos. Se usa la más cercana: {pd.to_datetime(fecha_sel).strftime('%d-%m-%Y')}.")

        perfil_fecha = perfil_df[perfil_df["fecha"] == fecha_sel].copy()
        lineas_disp = sorted([x for x in perfil_fecha["linea"].dropna().astype(str).unique() if x])

        row_sel_2a, row_sel_2b, row_sel_2c = st.columns([0.9, 1.15, 1.15])
        with row_sel_2a:
            linea_sel = option_selector("Línea", lineas_disp,
                                        key=f"perfil_linea_selector_{profile_srv}",
                                        default=lineas_disp[0] if lineas_disp else None)

        perfil_linea = perfil_fecha[perfil_fecha["linea"].astype(str) == str(linea_sel)].copy() if linea_sel else perfil_fecha.iloc[0:0].copy()
        direcciones_disp = sorted([x for x in perfil_linea["direccion"].dropna().astype(str).unique() if x])

        with row_sel_2b:
            dir_sel = option_selector("Dirección", direcciones_disp,
                                      key=f"perfil_direccion_selector_{profile_srv}",
                                      default=direcciones_disp[0] if direcciones_disp else None)

        perfil_dir = perfil_linea[perfil_linea["direccion"].astype(str) == str(dir_sel)].copy() if dir_sel else perfil_linea.iloc[0:0].copy()

        if perfil_dir.empty:
            st.warning("No existen datos para la combinación seleccionada.")
        else:
            if profile_schema not in {"transactional", "aggregated"}:
                schema_local = "transactional" if {"origen", "destino", "t_entrada_viaje", "t_salida_viaje"}.issubset(set(perfil_dir.columns)) else "aggregated"
            else:
                schema_local = profile_schema

            turnstile_day = pd.DataFrame()
            service_fare_summary = pd.DataFrame()
            turnstile_stats = {"turnstile_total": 0, "matched_total": 0, "match_pct": np.nan, "diff_mediana_min": np.nan, "tolerance_minutes": 20}
            if normalize_text(profile_srv) == "biotren" and schema_local == "transactional" and turnstile_status == "ok" and not turnstile_df.empty:
                turnstile_day = turnstile_df[turnstile_df["fecha"] == fecha_sel].copy()
                if not turnstile_day.empty:
                    _, service_fare_summary, turnstile_stats = match_turnstile_transactions_to_profile(turnstile_day, perfil_fecha, tolerance_minutes=20)

            service_summary = build_service_level_summary(perfil_dir, schema_local)
            service_summary = enrich_service_summary_with_itinerary(
                service_summary, itinerary_summary_df, profile_srv, linea_sel, dir_sel, fecha_sel
            )
            service_summary = apply_service_order_and_labels(
                service_summary, service_order_df, profile_srv, linea_sel, dir_sel, fecha_sel
            )
            if not service_summary.empty:
                for col in ["tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox", "recaudacion_aprox", "desviacion_tarifa_aprox", "diff_mediana_min", "match_ref_principal"]:
                    if col not in service_summary.columns:
                        service_summary[col] = np.nan
                if not service_fare_summary.empty:
                    fare_sel = service_fare_summary[
                        (service_fare_summary["linea"].astype(str).str.strip() == str(linea_sel)) &
                        (service_fare_summary["direccion"].astype(str).str.strip() == str(dir_sel))
                    ].copy()
                    if not fare_sel.empty:
                        service_summary = service_summary.drop(columns=[c for c in ["tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox", "recaudacion_aprox", "desviacion_tarifa_aprox", "diff_mediana_min"] if c in service_summary.columns], errors="ignore")
                        service_summary = service_summary.merge(
                            fare_sel[["servicio_label", "tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox", "recaudacion_aprox", "desviacion_tarifa_aprox", "diff_mediana_min", "match_ref_principal"]],
                            how="left", on="servicio_label"
                        )
                        for col in ["tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox", "recaudacion_aprox", "desviacion_tarifa_aprox", "diff_mediana_min", "match_ref_principal"]:
                            if col not in service_summary.columns:
                                service_summary[col] = np.nan
                        service_summary["tarifa_media_aprox"] = pd.to_numeric(service_summary.get("tarifa_media_aprox"), errors="coerce")
                        service_summary["pasajeros_transportados"] = pd.to_numeric(service_summary.get("pasajeros_transportados"), errors="coerce")
                        service_summary["recaudacion_aprox"] = np.where(
                            service_summary["tarifa_media_aprox"].notna() & service_summary["pasajeros_transportados"].notna(),
                            service_summary["tarifa_media_aprox"] * service_summary["pasajeros_transportados"],
                            np.nan,
                        )

            if not service_summary.empty:
                option_df = service_summary[["servicio_label", "servicio_display_label", "servicio_orden_idx"]].drop_duplicates(subset=["servicio_label"], keep="first").copy()
                option_df = option_df.sort_values(["servicio_orden_idx", "servicio_label"])
                option_labels = option_df["servicio_display_label"].astype(str).tolist()
                label_to_service = dict(zip(option_df["servicio_display_label"].astype(str), option_df["servicio_label"].astype(str)))
                prev_service = st.session_state.get(f"perfil_servicio_selector_{profile_srv}")
                default_label = option_labels[0] if option_labels else None
                if prev_service in set(option_df["servicio_label"].astype(str)):
                    default_label = option_df.loc[option_df["servicio_label"].astype(str) == str(prev_service), "servicio_display_label"].iloc[0]

                with row_sel_2c:
                    servicio_label_sel = st.selectbox(
                        "Servicio específico",
                        options=option_labels,
                        index=(option_labels.index(default_label) if option_labels and default_label in option_labels else 0),
                        placeholder="Sin servicios disponibles",
                        key=f"perfil_servicio_selector_label_{profile_srv}",
                    ) if option_labels else None
                servicio_sel = label_to_service.get(servicio_label_sel) if servicio_label_sel else None
                if servicio_sel:
                    st.session_state[f"perfil_servicio_selector_{profile_srv}"] = servicio_sel
            else:
                servicios_disp = sorted(perfil_dir["servicio_label"].dropna().astype(str).unique(), key=lambda x: (len(x), x))
                with row_sel_2c:
                    servicio_sel = st.selectbox(
                        "Servicio específico",
                        options=servicios_disp,
                        index=0 if servicios_disp else None,
                        placeholder="Sin servicios disponibles",
                        key=f"perfil_servicio_selector_{profile_srv}",
                    ) if servicios_disp else None

            if not servicio_sel:
                st.warning("No existen servicios disponibles para la selección actual.")
            else:
                if schema_local == "transactional":
                    perfil_servicio_tx = perfil_dir[perfil_dir["servicio_label"].astype(str) == str(servicio_sel)].copy()
                    perfil_servicio = build_transactional_service_profile(perfil_servicio_tx)
                else:
                    perfil_servicio = perfil_dir[perfil_dir["servicio_label"].astype(str) == str(servicio_sel)].copy()
                    perfil_servicio["event_time"] = perfil_servicio["t_arr_est"].fillna(perfil_servicio["t_dep_est"])

                if perfil_servicio.empty:
                    st.warning("No fue posible reconstruir el perfil de carga para el servicio seleccionado.")
                else:
                    station_order = get_station_order_from_profile(perfil_servicio)
                    if station_order:
                        perfil_servicio["estacion"] = pd.Categorical(perfil_servicio["estacion"], categories=station_order, ordered=True)
                        sort_cols = ["estacion"]
                        if "event_time" in perfil_servicio.columns:
                            sort_cols.append("event_time")
                        perfil_servicio = perfil_servicio.sort_values(sort_cols)

                    total_bajadas = perfil_servicio["D_bajadas"].sum(min_count=1)
                    max_abordo = perfil_servicio["L_out_abordo"].max()
                    capacidad_col = perfil_servicio.get("capacidad_tren", pd.Series([], dtype=float))
                    capacidad = (float(capacidad_col.dropna().iloc[0]) if "capacidad_tren" in perfil_servicio.columns and perfil_servicio["capacidad_tren"].dropna().any() else None)

                    servicios_realizados = int(len(service_summary)) if not service_summary.empty else int(perfil_dir["servicio_label"].nunique())
                    pasajeros_transportados = total_bajadas
                    tramo_max_abordo = "-"
                    l_out_series = pd.to_numeric(perfil_servicio.get("L_out_abordo"), errors="coerce")
                    if l_out_series.notna().any():
                        ordered_stations = [str(s) for s in station_order] if station_order else perfil_servicio["estacion"].astype(str).tolist()
                        max_idx = l_out_series.idxmax()
                        est_max = str(perfil_servicio.loc[max_idx, "estacion"])
                        if est_max in ordered_stations:
                            pos = ordered_stations.index(est_max)
                            if pos < len(ordered_stations) - 1:
                                tramo_max_abordo = f"{ordered_stations[pos]} - {ordered_stations[pos + 1]}"
                            elif pos > 0:
                                tramo_max_abordo = f"{ordered_stations[pos - 1]} - {ordered_stations[pos]}"
                            else:
                                tramo_max_abordo = est_max

                    selected_service_row = service_summary[service_summary["servicio_label"].astype(str) == str(servicio_sel)].head(1) if not service_summary.empty else pd.DataFrame()
                    tarifa_media_sel = pd.to_numeric(selected_service_row["tarifa_media_aprox"], errors="coerce").iloc[0] if not selected_service_row.empty and "tarifa_media_aprox" in selected_service_row.columns else np.nan
                    recaudacion_sel = pd.to_numeric(selected_service_row["recaudacion_aprox"], errors="coerce").iloc[0] if not selected_service_row.empty and "recaudacion_aprox" in selected_service_row.columns else np.nan

                    capacidad_referencia_linea = 605.0
                    ocupacion_general_pct = np.nan
                    ocupacion_servicio_pct = np.nan
                    if not service_summary.empty and servicios_realizados > 0:
                        pasajeros_linea_total = pd.to_numeric(service_summary.get("pasajeros_transportados"), errors="coerce").fillna(0).sum()
                        denominador_ocupacion = float(servicios_realizados) * capacidad_referencia_linea
                        if denominador_ocupacion > 0:
                            ocupacion_general_pct = (float(pasajeros_linea_total) / denominador_ocupacion) * 100.0
                    if pd.notna(pasajeros_transportados) and float(capacidad_referencia_linea) > 0:
                        ocupacion_servicio_pct = (float(pasajeros_transportados) / float(capacidad_referencia_linea)) * 100.0

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric(f"Servicios realizados ({linea_sel} | {dir_sel})", servicios_realizados)
                        st.metric(f"Tasa de ocupación línea ({linea_sel} | {dir_sel})", fmt_pct(ocupacion_general_pct) if pd.notna(ocupacion_general_pct) else "-")
                    with col2:
                        st.metric("Pasajeros transportados", fmt_pax(pasajeros_transportados))
                        st.metric(f"Tasa de ocupación servicio {servicio_sel}", fmt_pct(ocupacion_servicio_pct) if pd.notna(ocupacion_servicio_pct) else "-")
                    with col3:
                        st.metric("Máximo a bordo", fmt_pax(max_abordo))
                        st.metric("Tramo con máximo a bordo", tramo_max_abordo)
                    with col4:
                        st.metric("Tarifa media aprox. servicio", fmt_number(tarifa_media_sel, "CLP") if pd.notna(tarifa_media_sel) else "-")
                        st.metric("Recaudación aprox. servicio", fmt_number(recaudacion_sel, "CLP") if pd.notna(recaudacion_sel) else "-")

                    st.caption(
                        f"La recaudación aproximada se calcula como tarifa media aproximada × pasajeros transportados del servicio seleccionado. "
                        f"La tasa de ocupación de línea se calcula como pasajeros transportados totales de la línea / (servicios realizados × {int(capacidad_referencia_linea)} pasajeros). "
                        f"La tasa de ocupación del servicio seleccionado se calcula como pasajeros transportados del servicio / {int(capacidad_referencia_linea)} pasajeros."
                    )

                    titulo = f"{profile_srv} | {linea_sel} | {dir_sel} | Servicio {servicio_sel}"
                    show_plot(build_perfil_carga_chart(perfil_servicio, titulo), use_container_width=True)

                    cap_msg = None
                    if capacidad and pd.notna(max_abordo) and float(capacidad) != 0:
                        cap_msg = f"Capacidad tren: {fmt_pax(capacidad)} · Ocupación máxima: {fmt_pct((float(max_abordo)/float(capacidad))*100)}"
                    ref_parts = []
                    if perfil_files:
                        ref_parts.append(f"Perfil: {len(perfil_files)} archivo(s) en {perfil_path}")
                    if itinerary_status == 'ok' and itinerary_files:
                        ref_parts.append(f"Itinerario: {len(itinerary_files)} archivo(s) en {itinerary_path}")
                    elif itinerary_status == 'no_data':
                        ref_parts.append("Itinerario no encontrado; se usa hora/origen inferidos desde las transacciones")
                    if service_order_status == 'ok' and service_order_files:
                        ref_parts.append(f"Orden servicios: {len(service_order_files)} archivo(s) en {service_order_path}")
                    if normalize_text(profile_srv) == 'biotren':
                        if turnstile_status == 'ok' and turnstile_files:
                            turnstile_msg = f"Torniquetes: {len(turnstile_files)} archivo(s) en {turnstile_path}"
                            if turnstile_stats.get('turnstile_total', 0) > 0:
                                turnstile_msg += f" · match día: {fmt_pct(turnstile_stats.get('match_pct')) if pd.notna(turnstile_stats.get('match_pct')) else '-'}"
                            ref_parts.append(turnstile_msg)
                    caption_parts = [x for x in [cap_msg] + ref_parts if x]
                    if caption_parts:
                        st.caption(" · ".join(caption_parts))

                    st.markdown("<div class='section-title'>Pasajeros transportados por servicio</div>", unsafe_allow_html=True)
                    if service_summary.empty:
                        st.info("No existen servicios disponibles para resumir en el día seleccionado.")
                    else:
                        fig_transport = build_service_transport_chart(
                            service_summary,
                            f"{profile_srv} | {linea_sel} | {dir_sel} | Pasajeros transportados por servicio",
                        )
                        show_plot(fig_transport, use_container_width=True)

                    st.markdown("<div class='section-title'>Detalle por servicio</div>", unsafe_allow_html=True)
                    if service_summary.empty:
                        st.info("No existen detalles de servicios para el día seleccionado.")
                    else:
                        detalle_servicios = service_summary.copy()
                        detalle_servicios = detalle_servicios.sort_values(["servicio_orden_idx", "servicio_label"], kind="stable", na_position="last").copy() if "servicio_orden_idx" in detalle_servicios.columns else detalle_servicios.sort_values(["servicio_label"], kind="stable", na_position="last").copy()
                        detalle_servicios["Hora salida"] = detalle_servicios["hora_salida_fmt"]
                        detalle_servicios["Servicio"] = detalle_servicios["servicio_label"]
                        detalle_servicios["Estación origen"] = detalle_servicios["estacion_origen"]
                        detalle_servicios["Pasajeros transportados"] = detalle_servicios["pasajeros_transportados"].apply(fmt_pax)
                        detalle_servicios["Máximo a bordo"] = detalle_servicios["max_abordo"].apply(fmt_pax)
                        if "tx_cruzadas" in detalle_servicios.columns:
                            detalle_servicios["Tx cruzadas"] = pd.to_numeric(detalle_servicios["tx_cruzadas"], errors="coerce").apply(lambda v: fmt_pax(v) if pd.notna(v) else "-")
                        if "tarifa_media_aprox" in detalle_servicios.columns:
                            detalle_servicios["Tarifa media aprox."] = pd.to_numeric(detalle_servicios["tarifa_media_aprox"], errors="coerce").apply(lambda v: fmt_number(v, "CLP") if pd.notna(v) else "-")
                        if "recaudacion_aprox" in detalle_servicios.columns:
                            detalle_servicios["Recaudación aprox."] = pd.to_numeric(detalle_servicios["recaudacion_aprox"], errors="coerce").apply(lambda v: fmt_number(v, "CLP") if pd.notna(v) else "-")
                        visible_cols = ["Servicio", "Hora salida", "Estación origen", "Pasajeros transportados", "Máximo a bordo", "Tx cruzadas", "Tarifa media aprox.", "Recaudación aprox."]
                        visible_cols = [c for c in visible_cols if c in detalle_servicios.columns]
                        st.dataframe(detalle_servicios[visible_cols], use_container_width=True, hide_index=True)

    with tab_mensual:
        st.markdown("<div class='section-title'>Promedio mensual por tipo de día</div>", unsafe_allow_html=True)
        st.markdown("<div class='section-subtitle'>Vista separada del análisis diario. Solo utiliza filtros de mes y línea; la información se presenta en tablas paralelas por dirección.</div>", unsafe_allow_html=True)

        month_series = pd.to_datetime(perfil_df["fecha"], errors="coerce").dt.to_period("M").astype(str)
        month_options = [m for m in sorted(pd.Series(month_series).dropna().unique().tolist()) if m and m != 'NaT']
        month_default = month_options[-1] if month_options else None
        line_col_m, month_col_m = st.columns([1.0, 1.0])
        with month_col_m:
            month_sel = st.selectbox(
                "Mes",
                options=month_options,
                index=(month_options.index(month_default) if month_options and month_default in month_options else 0),
                format_func=month_period_to_label,
                key=f"perfil_month_selector_{profile_srv}",
            ) if month_options else None

        perfil_month = perfil_df[pd.to_datetime(perfil_df["fecha"], errors="coerce").dt.to_period("M").astype(str) == str(month_sel)].copy() if month_sel else perfil_df.iloc[0:0].copy()
        lineas_mes = sorted([x for x in perfil_month["linea"].dropna().astype(str).unique() if x])
        with line_col_m:
            linea_mes_sel = option_selector(
                "Línea",
                lineas_mes,
                key=f"perfil_linea_mes_selector_{profile_srv}",
                default=lineas_mes[0] if lineas_mes else None,
            )

        if not month_sel or not linea_mes_sel:
            st.info("No existen datos mensuales disponibles para los filtros seleccionados.")
        else:
            tablas_mensuales, directions = build_monthly_profile_tables_by_direction(
                perfil_df, profile_schema, profile_srv, month_sel, linea_mes_sel,
                itinerary_summary_df, service_order_df, turnstile_df, turnstile_status,
            )
            if not tablas_mensuales:
                st.info("No existen datos mensuales para la línea y mes seleccionados.")
            else:
                st.caption(f"Mes analizado: {month_period_to_label(month_sel)} · Línea: {linea_mes_sel}")
                for tipo_dia in ["Laboral", "Sábado", "Domingo"]:
                    st.markdown(f"<div class='section-title' style='font-size:0.95rem'>{tipo_dia}</div>", unsafe_allow_html=True)
                    dir_list = directions[:2] if directions else []
                    if not dir_list:
                        st.info(f"No existen datos para {tipo_dia.lower()}.")
                        continue
                    cols = st.columns(2)
                    showed_any = False
                    for idx, dir_val in enumerate(dir_list):
                        with cols[idx]:
                            st.markdown(f"<div class='map-note'><b>Dirección:</b> {dir_val}</div>", unsafe_allow_html=True)
                            tabla_dir = tablas_mensuales.get(tipo_dia, {}).get(dir_val, pd.DataFrame())
                            if tabla_dir is None or tabla_dir.empty:
                                st.info("Sin datos para esta dirección.")
                            else:
                                showed_any = True
                                tabla_show = tabla_dir.copy()
                                tabla_show["Servicio"] = tabla_show.get("servicio_display_label", tabla_show["servicio_label"])
                                tabla_show["Pasajeros Promedio Mes"] = pd.to_numeric(tabla_show["pasajeros_promedio_mes"], errors="coerce").apply(fmt_avg_pax)
                                tabla_show["Tarifa Media Mes"] = pd.to_numeric(tabla_show["tarifa_media_mes"], errors="coerce").apply(lambda v: fmt_number(v, "CLP") if pd.notna(v) else "-")
                                st.dataframe(
                                    tabla_show[["Servicio", "Pasajeros Promedio Mes", "Tarifa Media Mes"]],
                                    use_container_width=True,
                                    hide_index=True,
                                )
                    if not showed_any:
                        st.info(f"No existen datos para {tipo_dia.lower()} con los filtros seleccionados.")

    st.markdown("</div></div>", unsafe_allow_html=True)

def render_od_estaciones():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>OD Estaciones — Biotren</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>Análisis centrado en una estación: comportamiento horario, perfil de entradas/salidas y distribución espacial de viajes dentro del periodo seleccionado. Carpeta: <b>od_bt</b>.</div>",
        unsafe_allow_html=True)

    od_df, od_path, od_missing, od_files, od_status = load_od_service_data("Biotren", str(data_path))
    folder_name = OD_SERVICE_CONFIG["Biotren"]["folder_candidates"][0]

    st.markdown(
        "<div class='map-note'><b>Enfoque:</b> la pestaña prioriza la lectura de la estación seleccionada. "
        "Se mantienen bloques horarios múltiples, pero la interpretación se apoya en el perfil horario de la estación, "
        "la distribución de destinos/orígenes por estación y mapas de burbujas completos sin líneas OD.</div>",
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
        fecha_default = fecha_prev if fecha_prev in fechas_set else min(fechas_disponibles, key=lambda d: abs((d - fecha_prev).days))

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
        fecha_sel = min(fechas_disponibles, key=lambda d: abs((d - fecha_sel).days))
        st.info(f"Fecha sin datos. Se usa la más cercana: {pd.to_datetime(fecha_sel).strftime('%d-%m-%Y')}.")

    od_fecha = od_df[od_df["fecha"] == fecha_sel].copy()
    if od_fecha.empty:
        st.warning("No existen datos para la fecha seleccionada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    granularity_sel = "Bloques de 1 hora"
    od_fecha["entry_bucket"] = get_time_bucket_series(od_fecha["t_entrada_viaje"], granularity_sel)
    od_fecha["exit_bucket"] = get_time_bucket_series(od_fecha["t_salida_viaje"], granularity_sel)
    bucket_order = get_bucket_order(
        od_fecha["entry_bucket"].dropna().tolist() + od_fecha["exit_bucket"].dropna().tolist(),
        granularity_sel,
    )
    if not bucket_order:
        st.warning("No existen bloques horarios válidos para la fecha seleccionada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    bucket_display_map = {b: b.replace("-", " a ") for b in bucket_order}
    default_blocks = st.session_state.get("od_bloques_selector_multi")
    if not isinstance(default_blocks, list) or not default_blocks:
        default_blocks = [bucket_order[0]]
    default_blocks = [b for b in default_blocks if b in bucket_order] or [bucket_order[0]]

    st.markdown("<div class='section-title'>Periodo horario de análisis</div>", unsafe_allow_html=True)
    bloques_sel = st.multiselect(
        "Bloques horarios de análisis",
        options=bucket_order,
        default=default_blocks,
        format_func=lambda x: bucket_display_map.get(x, x),
        key="od_bloques_selector_multi",
    )
    if not bloques_sel:
        st.warning("Seleccione al menos un bloque horario para continuar.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    bloques_sel = [b for b in bucket_order if b in bloques_sel]
    bloques_label = ", ".join(bucket_display_map.get(b, b) for b in bloques_sel)

    bucket_entry_summary = (
        od_fecha[od_fecha["entry_bucket"].isin(bloques_sel)]
        .groupby("origen", as_index=False).size()
        .rename(columns={"origen": "estacion", "size": "entradas"})
        .sort_values(["entradas", "estacion"], ascending=[False, True])
    )
    bucket_exit_summary = (
        od_fecha[od_fecha["exit_bucket"].isin(bloques_sel)]
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

    st.markdown(
        f"<div class='filters-summary'><strong>Bloques seleccionados:</strong> {bloques_label}</div>",
        unsafe_allow_html=True,
    )
    rm1, rm2, rm3, rm4 = st.columns(4)
    rm1.metric("Entradas período", fmt_pax(total_entries_block))
    rm2.metric("Salidas período", fmt_pax(total_exits_block))
    rm3.metric("Mayor entrada", top_entry_station)
    rm4.metric("Mayor salida", top_exit_station)

    station_ref = prepare_od_station_reference("Biotren", od_fecha, estaciones)
    station_candidates = sorted(set(od_fecha["origen"].dropna().astype(str)) | set(od_fecha["destino"].dropna().astype(str)))
    default_station = station_candidates[0] if station_candidates else None
    prev_station = st.session_state.get("od_station_selector")
    if prev_station in station_candidates:
        default_station = prev_station

    station_sel = (
        st.selectbox(
            "Estación",
            options=station_candidates,
            index=(station_candidates.index(default_station) if station_candidates and default_station in station_candidates else 0),
            key="od_station_selector",
        )
        if station_candidates else None
    )

    if not station_sel:
        st.warning("No existen estaciones disponibles para la selección actual.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    station_entries = (
        od_fecha[od_fecha["origen"].astype(str) == str(station_sel)]
        .groupby("entry_bucket", as_index=False).size()
        .rename(columns={"entry_bucket": "bucket", "size": "cantidad"})
    )
    station_entries["tipo"] = "Entradas"
    station_exits = (
        od_fecha[od_fecha["destino"].astype(str) == str(station_sel)]
        .groupby("exit_bucket", as_index=False).size()
        .rename(columns={"exit_bucket": "bucket", "size": "cantidad"})
    )
    station_exits["tipo"] = "Salidas"
    station_flow = pd.concat([station_entries, station_exits], ignore_index=True)
    station_flow = station_flow.dropna(subset=["bucket"]).copy()

    station_bucket_order = get_bucket_order(station_flow["bucket"].dropna().tolist(), "Bloques de 1 hora") or bucket_order

    st.markdown("<div class='section-title'>Perfil horario de la estación seleccionada</div>", unsafe_allow_html=True)
    show_plot(
        build_station_flow_chart(station_flow, station_bucket_order, station_sel, "Bloques de 1 hora"),
        use_container_width=True,
    )

    total_entries_day = int(station_entries["cantidad"].sum()) if not station_entries.empty else 0
    total_exits_day = int(station_exits["cantidad"].sum()) if not station_exits.empty else 0
    peak_entry_row = station_entries.sort_values(["cantidad", "bucket"], ascending=[False, True]).head(1)
    peak_exit_row = station_exits.sort_values(["cantidad", "bucket"], ascending=[False, True]).head(1)
    peak_entry_label = (
        f"{bucket_display_map.get(peak_entry_row.iloc[0]['bucket'], peak_entry_row.iloc[0]['bucket'])} ({fmt_pax(peak_entry_row.iloc[0]['cantidad'])})"
        if not peak_entry_row.empty else "-"
    )
    peak_exit_label = (
        f"{bucket_display_map.get(peak_exit_row.iloc[0]['bucket'], peak_exit_row.iloc[0]['bucket'])} ({fmt_pax(peak_exit_row.iloc[0]['cantidad'])})"
        if not peak_exit_row.empty else "-"
    )

    sm1, sm2, sm3, sm4 = st.columns(4)
    sm1.metric("Entradas día", fmt_pax(total_entries_day))
    sm2.metric("Salidas día", fmt_pax(total_exits_day))
    sm3.metric("Hora punta entradas", peak_entry_label)
    sm4.metric("Hora punta salidas", peak_exit_label)

    destinos_df = (
        od_fecha[(od_fecha["origen"].astype(str) == str(station_sel)) & (od_fecha["entry_bucket"].isin(bloques_sel))]
        .groupby("destino", as_index=False).size()
        .rename(columns={"size": "viajes"})
        .sort_values(["viajes", "destino"], ascending=[False, True])
    )
    origenes_df = (
        od_fecha[(od_fecha["destino"].astype(str) == str(station_sel)) & (od_fecha["exit_bucket"].isin(bloques_sel))]
        .groupby("origen", as_index=False).size()
        .rename(columns={"size": "viajes"})
        .sort_values(["viajes", "origen"], ascending=[False, True])
    )

    if not destinos_df.empty:
        destinos_df = destinos_df[destinos_df["destino"].astype(str) != str(station_sel)].copy()
    if not origenes_df.empty:
        origenes_df = origenes_df[origenes_df["origen"].astype(str) != str(station_sel)].copy()

    salidas_estacion = int(destinos_df["viajes"].sum()) if not destinos_df.empty else 0
    llegadas_estacion = int(origenes_df["viajes"].sum()) if not origenes_df.empty else 0
    principal_destino = (
        f"{destinos_df.iloc[0]['destino']} ({fmt_pax(destinos_df.iloc[0]['viajes'])})" if not destinos_df.empty else "-"
    )
    principal_origen = (
        f"{origenes_df.iloc[0]['origen']} ({fmt_pax(origenes_df.iloc[0]['viajes'])})" if not origenes_df.empty else "-"
    )

    st.markdown("<div class='section-title'>Perfil de viajes de la estación en el periodo seleccionado</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='section-subtitle'><b>{station_sel}</b> · Periodo: {bloques_label} · "
        f"Salidas desde estación: {fmt_pax(salidas_estacion)} · Llegadas hacia estación: {fmt_pax(llegadas_estacion)}</div>",
        unsafe_allow_html=True,
    )
    dm1, dm2 = st.columns(2)
    dm1.metric("Principal destino", principal_destino)
    dm2.metric("Principal origen", principal_origen)

    row_bar1, row_bar2 = st.columns(2)
    with row_bar1:
        dest_bar = build_od_station_bar_chart(
            destinos_df, "destino", station_ref,
            f"Destinos desde {station_sel} | {bloques_label}", EFE_BLUE
        )
        if dest_bar:
            show_plot(dest_bar, use_container_width=True)
        else:
            st.info("No existen viajes desde la estación en el periodo seleccionado.")
    with row_bar2:
        ori_bar = build_od_station_bar_chart(
            origenes_df, "origen", station_ref,
            f"Orígenes hacia {station_sel} | {bloques_label}", EFE_RED
        )
        if ori_bar:
            show_plot(ori_bar, use_container_width=True)
        else:
            st.info("No existen viajes hacia la estación en el periodo seleccionado.")

    row_map1, row_map2 = st.columns(2)
    with row_map1:
        from_fig = build_od_bubble_map(
            destinos_df, "destino", station_ref, station_sel,
            f"Mapa de destinos desde {station_sel} | {bloques_label}", EFE_BLUE,
        )
        if from_fig:
            show_plot(from_fig, use_container_width=True)
        else:
            st.info("Sin coordenadas válidas para el mapa de destinos.")
    with row_map2:
        to_fig = build_od_bubble_map(
            origenes_df, "origen", station_ref, station_sel,
            f"Mapa de orígenes hacia {station_sel} | {bloques_label}", EFE_RED,
        )
        if to_fig:
            show_plot(to_fig, use_container_width=True)
        else:
            st.info("Sin coordenadas válidas para el mapa de orígenes.")

    if od_files:
        st.caption(f"Archivos OD cargados: {len(od_files)} | carpeta: {od_path}")
    st.markdown("</div></div>", unsafe_allow_html=True)


# =========================================================
# DISPATCH
# =========================================================
selected_service_context = root_sel if root_sel != "Personas" else None

if section_sel == "KPIs por Servicio":
    render_resumen_ejecutivo(target_service=selected_service_context)
elif section_sel == "Personas":
    render_personas()
elif section_sel == "Estaciones":
    render_detalle_servicio()
elif section_sel == "Perfil de Carga":
    render_perfil_carga(default_service=selected_service_context)
elif section_sel == "OD Estaciones":
    render_od_estaciones()

# =========================================================
# PIE DE PÁGINA
# =========================================================
st.markdown("---")
st.caption(
    "Los archivos CSV se leen automáticamente desde el repositorio de GitHub, "
    "incluyendo carpetas dedicadas para perfiles de carga y datos OD por servicio.")
