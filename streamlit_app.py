"""
EFE Sur | KPIs e Iniciativas - Gerencia de Pasajeros
=====================================================
Versión reescrita (v4) — arquitectura limpia y robusta.

Principios de diseño:
  • Cero atajos de optimización que crashen: sin np.where con divisiones de
    riesgo, sin Categorical en annotations de Plotly, sin masks bool-Python,
    sin acceso a iloc[0] sin chequeo.
  • Helpers minúsculos, atómicos, testeables. Cada uno hace UNA cosa.
  • Toda función pública valida sus entradas y retorna estructuras vacías
    bien tipadas en lugar de explotar.
  • Capa de carga totalmente separada de la de presentación.
  • Caches conservadores con TTL razonable.
  • Botón "⋮" en cabecera para limpiar caches sin reiniciar el servidor.

Mantiene EXACTAMENTE el mismo diseño visual y funcional del dashboard
original (mismos colores, mismas pestañas, mismas tarjetas, mismas tablas,
misma sección de tipo de pasajero).
"""

# ================================================================
# 1. IMPORTS
# ================================================================
from __future__ import annotations

import gc
import logging
import time
import unicodedata
import warnings
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --- Suprimir warnings ruidosos que saturan el log y degradan rendimiento --
# Streamlit 1.36+ deprecó `use_container_width`. Cada widget que use el flag
# emite un warning en cada re-run; con docenas de widgets esto satura el
# logger y consume CPU. Hasta migrar todas las llamadas, los silenciamos.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="streamlit")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="plotly")
warnings.filterwarnings("ignore", message=".*use_container_width.*")
warnings.filterwarnings("ignore", message=".*scattermapbox.*")
warnings.filterwarnings("ignore", message=".*mapbox.*")

# Bajar el nivel del logger de Streamlit a ERROR para que los warnings
# repetidos no llenen los logs de Streamlit Cloud (≥ 1k entradas observadas
# en sesiones cortas, lo que satura la cola de mensajes y puede provocar
# que el servidor mate el proceso por presión de I/O).
for _logger_name in (
    "streamlit", "streamlit.runtime", "streamlit.runtime.scriptrunner",
    "plotly", "plotly.graph_objects",
):
    try:
        logging.getLogger(_logger_name).setLevel(logging.ERROR)
    except Exception:
        pass


# --- Excepciones internas de Streamlit que NO son crashes -----------------
# Cuando el usuario cambia un widget mientras Streamlit ejecuta el script,
# Streamlit aborta el script en curso lanzando una RerunException o
# StopException. Capturarlas como "crash" causa errores falsos. Las
# importamos defensivamente porque la ruta del módulo cambia entre versiones.
_RERUN_EXCEPTIONS: tuple = ()
for _path in (
    "streamlit.runtime.scriptrunner.exceptions",
    "streamlit.runtime.scriptrunner.script_runner",
    "streamlit.script_runner",
):
    try:
        _mod = __import__(_path, fromlist=["RerunException", "StopException"])
        _excs = []
        for _name in ("RerunException", "StopException"):
            _e = getattr(_mod, _name, None)
            if isinstance(_e, type) and issubclass(_e, BaseException):
                _excs.append(_e)
        if _excs:
            _RERUN_EXCEPTIONS = tuple(_excs)
            break
    except Exception:
        continue


def is_streamlit_internal_exception(exc: BaseException) -> bool:
    """¿Es una excepción interna de Streamlit (rerun/stop) que NO es un crash?"""
    if _RERUN_EXCEPTIONS and isinstance(exc, _RERUN_EXCEPTIONS):
        return True
    name = type(exc).__name__
    return name in {"RerunException", "StopException", "RerunData"}


def maybe_fragment(fn):
    """
    Decorador que aplica @st.fragment cuando está disponible (Streamlit ≥ 1.32).
    En versiones más antiguas devuelve la función sin cambios.

    st.fragment aísla un bloque del dashboard: cuando el usuario cambia un
    filtro DENTRO del fragment, sólo se re-ejecuta ese fragment, no el
    script completo. Esto evita que cambios rápidos disparen recargas
    pesadas en cascada.
    """
    if hasattr(st, "fragment"):
        try:
            return st.fragment(fn)
        except Exception:
            return fn
    return fn


def release_memory(*objs) -> None:
    """Libera referencias y fuerza garbage collection para evitar OOM."""
    for obj in objs:
        try:
            del obj
        except Exception:
            pass
    try:
        gc.collect()
    except Exception:
        pass


# ================================================================
# 2. CONFIGURACIÓN DE PÁGINA
# ================================================================
st.set_page_config(
    page_title="EFE Sur | KPIs e Iniciativas - Gerencia de Pasajeros",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ================================================================
# 3. PALETA DE COLORES
# ================================================================
LIGHT_COLORS = {
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

# Globales que se actualizan según el tema
COLORS = dict(LIGHT_COLORS)
EFE_BLUE  = COLORS["EFE_BLUE"]
EFE_RED   = COLORS["EFE_RED"]
EFE_WHITE = COLORS["EFE_WHITE"]
TEXT_MAIN = COLORS["TEXT_MAIN"]
TEXT_MUTED= COLORS["TEXT_MUTED"]
SUCCESS   = COLORS["SUCCESS"]
WARNING   = COLORS["WARNING"]
DANGER    = COLORS["DANGER"]
BORDER    = COLORS["BORDER"]


def apply_runtime_palette(palette: dict) -> None:
    """Reemplaza la paleta global usada por los gráficos plotly."""
    global COLORS, EFE_BLUE, EFE_RED, EFE_WHITE, TEXT_MAIN, TEXT_MUTED
    global SUCCESS, WARNING, DANGER, BORDER
    COLORS = dict(palette)
    EFE_BLUE  = COLORS["EFE_BLUE"]
    EFE_RED   = COLORS["EFE_RED"]
    EFE_WHITE = COLORS["EFE_WHITE"]
    TEXT_MAIN = COLORS["TEXT_MAIN"]
    TEXT_MUTED= COLORS["TEXT_MUTED"]
    SUCCESS   = COLORS["SUCCESS"]
    WARNING   = COLORS["WARNING"]
    DANGER    = COLORS["DANGER"]
    BORDER    = COLORS["BORDER"]


# ================================================================
# 4. CONSTANTES VISUALES Y TEMÁTICAS
# ================================================================
PLOT_FONT_SIZE = 15
PLOT_TITLE_SIZE = 19
PLOT_ANNOTATION_SIZE = 12

RURAL_SERVICES = ["Laja Talcahuano", "Tren Araucanía", "Llanquihue Puerto Montt"]

PASSENGER_TYPE_ORDER = ["Monedero", "Estudiante", "Adulto Mayor", "Discapacitado", "Otros"]
PASSENGER_TYPE_COLORS = {
    "Monedero":      "#002857",
    "Estudiante":    "#FF0016",
    "Adulto Mayor":  "#D97706",
    "Discapacitado": "#0F766E",
    "Otros":         "#6B7280",
}


# ================================================================
# 5. CSS — TEMPLATE BASE Y RUNTIME
# ================================================================
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
.main-title {{
    font-size: 2.35rem; font-weight: 850; color: {EFE_BLUE};
    margin-top: 0.05rem; margin-bottom: 0.18rem; line-height: 1.08;
}}
.subtitle {{ font-size: 0.94rem; color: {TEXT_MUTED}; margin-top: 0.25rem; }}
.hero-minimal {{ padding: 0.0rem 0 0.3rem; margin-bottom: 0.2rem; }}
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
}}
.content-panel {{ background: transparent; }}
div[data-baseweb="select"] > div {{
    border-radius: 16px !important; border-color: #D7E0EA !important;
    background: rgba(255,255,255,0.98) !important; min-height: 48px !important;
    box-shadow: none !important;
}}
div[data-testid="stMetric"] {{
    background: linear-gradient(180deg,#FFFFFF 0%,#FCFDFE 100%);
    border: 1px solid #DFE7EF; padding: 0.7rem 0.85rem;
    border-radius: 18px; box-shadow: 0 10px 24px rgba(0,40,87,0.05);
    transition: transform 0.16s ease, box-shadow 0.16s ease;
}}
div[data-testid="stMetric"]:hover {{
    transform: translateY(-2px); box-shadow: 0 14px 30px rgba(0,40,87,0.08);
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
.pax-type-card {{
    background: linear-gradient(180deg,#FFFFFF 0%,#FCFDFE 100%);
    border: 1px solid #DFE7EF; border-left: 5px solid {EFE_BLUE};
    border-radius: 18px; padding: 0.78rem 0.95rem 0.72rem;
    box-shadow: 0 10px 24px rgba(0,40,87,0.05);
    transition: transform 0.16s ease, box-shadow 0.16s ease;
    min-height: 118px; display: flex; flex-direction: column; justify-content: center;
}}
.pax-type-card:hover {{ transform: translateY(-2px); box-shadow: 0 14px 30px rgba(0,40,87,0.08); }}
.pax-type-card.is-empty {{ opacity: 0.55; }}
.pax-type-card.--monedero      {{ border-left-color: #002857; }}
.pax-type-card.--estudiante    {{ border-left-color: #FF0016; }}
.pax-type-card.--adulto-mayor  {{ border-left-color: #D97706; }}
.pax-type-card.--discapacitado {{ border-left-color: #0F766E; }}
.pax-type-card.--otros         {{ border-left-color: #6B7280; }}
.pax-type-card .pax-card-title {{
    font-size: 0.86rem; color: {TEXT_MUTED}; margin-bottom: 0.28rem;
    font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
}}
.pax-type-card .pax-card-value {{
    font-size: 1.55rem; font-weight: 850; color: {EFE_BLUE}; line-height: 1.05;
    margin-bottom: 0.18rem;
}}
.pax-type-card .pax-card-pct {{ font-size: 0.92rem; color: {TEXT_MAIN}; font-weight: 700; }}
.pax-type-card .pax-card-fare {{ font-size: 0.82rem; color: {TEXT_MUTED}; margin-top: 0.22rem; }}
.integrity-badge {{
    display: inline-flex; align-items: center; gap: 0.35rem;
    background: #ECFDF5; color: {SUCCESS}; border: 1px solid #A7F3D0;
    padding: 0.22rem 0.55rem; border-radius: 999px;
    font-size: 0.78rem; font-weight: 700; margin-top: 0.35rem;
}}
.integrity-badge.warn {{ background: #FFF7ED; color: {WARNING}; border-color: #FED7AA; }}
.efe-card-spark {{ margin-top: 0.45rem; }}
.efe-card-streak {{
    margin-top: 0.3rem; font-size: 0.78rem; font-weight: 700;
    color: {TEXT_MUTED};
}}
.efe-card-yoy {{
    margin-top: 0.25rem; font-size: 0.82rem; font-weight: 700;
    color: {EFE_BLUE};
    background: rgba(0,40,87,0.06);
    padding: 0.2rem 0.5rem; border-radius: 999px;
    display: inline-block;
}}
.efe-cumulative-card {{
    background: linear-gradient(135deg, {EFE_BLUE} 0%, #1A4A8C 100%);
    color: #FFFFFF;
    border-radius: 18px;
    padding: 1.0rem 1.15rem;
    margin: 0.5rem 0 0.85rem;
    box-shadow: 0 12px 28px rgba(0,40,87,0.20);
}}
.efe-cumulative-card .efe-cumulative-label {{
    font-size: 0.78rem; font-weight: 700; opacity: 0.82;
    text-transform: uppercase; letter-spacing: 0.04em;
    margin-bottom: 0.35rem;
}}
.efe-cumulative-card .efe-cumulative-value {{
    font-size: 2.2rem; font-weight: 850; line-height: 1.05;
    margin-bottom: 0.3rem;
}}
.efe-cumulative-card .efe-cumulative-comparison {{
    display: inline-block;
    background: rgba(255,255,255,0.92);
    padding: 0.25rem 0.7rem; border-radius: 999px;
    font-size: 0.86rem; font-weight: 800;
    margin-bottom: 0.35rem;
}}
.efe-cumulative-card .efe-cumulative-sub {{
    font-size: 0.82rem; opacity: 0.85;
}}
.efe-cumulative-card .efe-cumulative-sub strong {{ color: #FFFFFF; }}
.efe-narrative {{
    background: linear-gradient(135deg, rgba(0,40,87,0.06) 0%, rgba(0,40,87,0.02) 100%);
    border: 1px solid #C7D9EC; border-left: 4px solid {EFE_BLUE};
    border-radius: 16px; padding: 0.88rem 1.05rem 0.85rem;
    margin: 0.35rem 0 0.85rem; box-shadow: 0 8px 18px rgba(0,40,87,0.04);
}}
.efe-narrative-title {{
    font-size: 0.78rem; color: {EFE_BLUE}; font-weight: 800;
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem;
}}
.efe-narrative-body {{
    font-size: 0.93rem; line-height: 1.55; color: {TEXT_MAIN};
}}
.efe-narrative-body strong {{ color: {EFE_BLUE}; }}
.efe-summary-row {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 0.65rem; margin: 0.3rem 0 0.7rem;
}}
.efe-summary-card {{
    background: linear-gradient(180deg, #FFFFFF 0%, #FCFDFE 100%);
    border: 1px solid #DFE7EF; border-radius: 16px;
    padding: 0.7rem 0.85rem; box-shadow: 0 8px 18px rgba(0,40,87,0.04);
    transition: transform 0.16s ease;
}}
.efe-summary-card:hover {{ transform: translateY(-2px); }}
.efe-summary-card .efe-summary-label {{
    font-size: 0.74rem; color: {TEXT_MUTED}; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.04em;
}}
.efe-summary-card .efe-summary-value {{
    font-size: 1.45rem; color: {EFE_BLUE}; font-weight: 850;
    margin-top: 0.18rem; line-height: 1.1;
}}
.efe-summary-card .efe-summary-sub {{
    font-size: 0.78rem; color: {TEXT_MUTED}; margin-top: 0.18rem;
}}
.efe-update-tag {{
    display: inline-flex; align-items: center; gap: 0.32rem;
    background: rgba(0,40,87,0.04); color: {TEXT_MUTED};
    padding: 0.22rem 0.55rem; border-radius: 999px;
    font-size: 0.74rem; font-weight: 700;
}}
</style>
"""


def build_dark_overrides_css(colors: dict) -> str:
    """Sobreescritura para tema oscuro."""
    return f"""
    <style>
    .stApp {{
        background:
            radial-gradient(circle at top left, rgba(140,183,255,0.10) 0%, rgba(140,183,255,0.00) 22%),
            linear-gradient(180deg, #020617 0%, #0B1220 100%) !important;
        color: {colors['TEXT_MAIN']} !important;
    }}
    .main-title {{ color: {colors['TEXT_MAIN']} !important; }}
    .subtitle {{ color: {colors['TEXT_MUTED']} !important; }}
    .section-shell, .nav-panel, .efe-card, .map-note,
    div[data-testid="stMetric"], div[data-testid="stPlotlyChart"],
    .pax-type-card {{
        background: #111827 !important;
        border-color: {colors['BORDER']} !important;
        box-shadow: 0 8px 22px rgba(0,0,0,0.28) !important;
    }}
    .section-title, .service-title, .efe-card-value, .efe-card-delta,
    .efe-card-meta, .efe-card-title, .filters-summary, .filter-chip,
    .pax-card-value, .pax-card-pct {{ color: {colors['TEXT_MAIN']} !important; }}
    .section-subtitle, .pax-card-title, .pax-card-fare {{ color: {colors['TEXT_MUTED']} !important; }}
    .filter-chip {{ background: #0F172A !important; border-color: {colors['BORDER']} !important; }}
    .stButton > button, .stDownloadButton > button {{
        background: #111827 !important; color: {colors['TEXT_MAIN']} !important;
        border-color: {colors['BORDER']} !important;
    }}
    div[data-baseweb="select"] > div {{
        background: #111827 !important; border-color: {colors['BORDER']} !important;
        color: {colors['TEXT_MAIN']} !important;
    }}
    .stMarkdown, .stCaption, label {{ color: {colors['TEXT_MAIN']} !important; }}
    </style>
    """


def render_global_css() -> None:
    """Inyecta CSS global. Llamada UNA vez al arranque."""
    st.markdown(_CSS_TEMPLATE.format(**COLORS), unsafe_allow_html=True)

# ================================================================
# 6. HELPERS DE TEXTO Y FORMATO
# ================================================================

@lru_cache(maxsize=4096)
def normalize_text(text) -> str:
    """Normaliza un string individual a ASCII minúsculas sin espacios laterales."""
    if text is None:
        return ""
    text = str(text)
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
        .lower()
    )


def normalize_series(series: pd.Series) -> pd.Series:
    """Versión vectorizada de normalize_text para columnas completas."""
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
    """Convierte número de servicio a string limpio (sin .0 cuando es entero)."""
    if pd.isna(value):
        return "-"
    try:
        vf = float(value)
        return str(int(vf)) if vf.is_integer() else f"{vf:g}"
    except (ValueError, TypeError):
        return str(value).strip()


def is_occupancy_rate_kpi(kpi_name: str) -> bool:
    """¿Es un KPI de tasa de ocupación? (necesita escalado a porcentaje)."""
    name = normalize_text(kpi_name or "")
    return "tasa" in name and "ocupacion" in name


def maybe_scale_percent(value):
    """Escala a porcentaje si viene como fracción (≤ 1.5)."""
    if pd.isna(value):
        return value
    try:
        v = float(value)
    except (ValueError, TypeError):
        return value
    return v * 100 if abs(v) <= 1.5 else v


def fmt_number(value, unit: str = "", kpi_name: str | None = None) -> str:
    """Formatea valores numéricos según unidad (CLP, %, pax, número genérico)."""
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
    try:
        return f"{float(value):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "-"


def fmt_avg_pax(value) -> str:
    if pd.isna(value):
        return "-"
    try:
        return f"{float(value):,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "-"


def fmt_fuga_pct(value) -> str:
    if pd.isna(value):
        return "-"
    return fmt_pct(maybe_scale_percent(value))


# ================================================================
# 7. HELPERS DE PERÍODO
# ================================================================
_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}
_MESES_LARGO = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}


def periodo_to_date(value):
    """Convierte 'YYYY-MM' o 'YYYY-MM-DD' a Timestamp."""
    if value is None:
        return pd.NaT
    s = str(value).strip()
    if not s:
        return pd.NaT
    if len(s) == 7:
        s += "-01"
    return pd.to_datetime(s, errors="coerce")


def periodo_to_label(value) -> str:
    dt = periodo_to_date(value)
    if pd.isna(dt):
        return str(value)
    return f"{_MESES.get(int(dt.month), str(dt.month))}-{str(dt.year)[2:]}"


def month_period_to_label(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    try:
        ts = pd.Timestamp(str(value))
    except (ValueError, TypeError):
        return str(value)
    return f"{_MESES_LARGO.get(int(ts.month), str(ts.month))} {int(ts.year)}"


def safe_to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def classify_profile_day_type(fecha_value) -> str | None:
    """Clasifica una fecha como Laboral/Sábado/Domingo."""
    if pd.isna(fecha_value):
        return None
    try:
        wd = int(pd.Timestamp(fecha_value).weekday())
    except (ValueError, TypeError):
        return None
    if wd < 5:
        return "Laboral"
    if wd == 5:
        return "Sábado"
    return "Domingo"


# ================================================================
# 8. CLASIFICACIÓN DE ESTADOS Y COLORES
# ================================================================
def classify_status(value, meta, higher_is_better: bool = True) -> str:
    """Status semafórico con manejo seguro de meta=0."""
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


# ================================================================
# 9. UI HELPERS
# ================================================================
PLOTLY_CHART_CONFIG = {
    "scrollZoom": False,
    "displayModeBar": False,
    "doubleClick": False,
    "showTips": False,
    "responsive": True,
}


def show_plot(fig: go.Figure, width: str = "stretch", **kwargs):
    """Wrapper de plotly_chart con configuración estándar y safe-fallback.

    En Streamlit ≥ 1.36 se usa `width='stretch'` o `width='content'`.
    `use_container_width` quedó deprecado y emite warning en cada llamada.
    """
    try:
        fig.update_layout(dragmode=False)
        fig.update_xaxes(fixedrange=True)
        fig.update_yaxes(fixedrange=True)
    except Exception:
        pass
    # Compatibilidad: si llaman con use_container_width, mapear a width
    if "use_container_width" in kwargs:
        ucw = kwargs.pop("use_container_width")
        width = "stretch" if ucw else "content"
    try:
        return st.plotly_chart(
            fig, width=width, config=PLOTLY_CHART_CONFIG, **kwargs,
        )
    except TypeError:
        # Fallback para Streamlit < 1.36 (no debería ocurrir en producción)
        return st.plotly_chart(
            fig, use_container_width=(width == "stretch"),
            config=PLOTLY_CHART_CONFIG, **kwargs,
        )


def option_selector(label: str, options: list, key: str,
                    default=None, horizontal: bool = True):
    """Pills primero, fallback a radio. Siempre devuelve un valor válido."""
    if not options:
        return None
    if default is None or default not in options:
        default = options[0]
    try:
        selected = st.pills(
            label, options=options, selection_mode="single",
            default=default, key=key,
        )
        return selected if selected is not None else default
    except Exception:
        idx = options.index(default)
        return st.radio(label, options=options, index=idx,
                        key=f"{key}_radio", horizontal=horizontal)


def render_kpi_card(title, value, meta, delta_text, status):
    """Tarjeta KPI con borde lateral según status."""
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
        st.markdown(
            "<div class='efe-observation-empty'><strong>Observación:</strong> Sin observaciones</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div class='efe-observation'><strong>Observación:</strong> {txt}</div>",
            unsafe_allow_html=True,
        )


# ================================================================
# 9b. SPARKLINE INLINE PARA TARJETAS KPI
# ================================================================
def build_sparkline_svg(values: list, width: int = 110, height: int = 28,
                        color: str | None = None) -> str:
    """
    Genera un SVG inline minimalista que representa una serie de valores.
    Pensado para incrustarse en una tarjeta de KPI sin dependencias externas.
    Devuelve string vacío si la serie es muy corta o no graficable.
    """
    if not values:
        return ""
    clean = [v for v in values if v is not None and not (isinstance(v, float) and pd.isna(v))]
    if len(clean) < 2:
        return ""
    color = color or EFE_BLUE
    vmin = float(min(clean))
    vmax = float(max(clean))
    rng = vmax - vmin if vmax > vmin else 1.0

    pad_x, pad_y = 2, 4
    n = len(clean)
    step_x = (width - 2 * pad_x) / max(n - 1, 1)
    points = []
    for i, v in enumerate(clean):
        x = pad_x + i * step_x
        y = height - pad_y - ((float(v) - vmin) / rng) * (height - 2 * pad_y)
        points.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(points)
    last_x, last_y = points[-1].split(",")
    return (
        f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' "
        f"style='display:block; overflow:visible;'>"
        f"<polyline fill='none' stroke='{color}' stroke-width='1.6' "
        f"stroke-linecap='round' stroke-linejoin='round' points='{poly}' />"
        f"<circle cx='{last_x}' cy='{last_y}' r='2.4' fill='{color}' />"
        f"</svg>"
    )


def is_afluencia_kpi(kpi_name: str) -> bool:
    """¿Es un KPI de afluencia/pasajeros (acumula bien por año)?"""
    name = normalize_text(kpi_name or "")
    return any(kw in name for kw in ["afluencia", "pasajeros", "transportados"])


def render_yearly_cumulative_card(history_df: pd.DataFrame,
                                   current_period: str,
                                   kpi_name: str,
                                   unit: str = "") -> None:
    """
    Recuadro fijo acumulativo: muestra los pasajeros acumulados en el año
    hasta el período seleccionado, comparados con el mismo rango del año
    anterior.
    """
    if history_df is None or history_df.empty:
        return
    if "periodo" not in history_df.columns or "valor" not in history_df.columns:
        return

    try:
        current_dt = periodo_to_date(current_period)
        if pd.isna(current_dt):
            return

        df = history_df.copy()
        df["periodo_dt"] = df["periodo"].apply(periodo_to_date)
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
        df = df.dropna(subset=["periodo_dt", "valor"])
        if df.empty:
            return

        current_year = int(current_dt.year)
        # Acumulado del año actual: enero hasta el mes actual (inclusive)
        mask_curr = (
            (df["periodo_dt"].dt.year == current_year)
            & (df["periodo_dt"] <= current_dt)
        )
        acumulado_actual = float(df.loc[mask_curr, "valor"].sum())

        # Acumulado del año anterior: enero hasta el mismo mes
        prev_year = current_year - 1
        prev_until = current_dt - pd.DateOffset(years=1)
        mask_prev = (
            (df["periodo_dt"].dt.year == prev_year)
            & (df["periodo_dt"] <= prev_until)
        )
        acumulado_anterior = float(df.loc[mask_prev, "valor"].sum())

        # Determinar si tenemos comparación válida
        has_comparison = acumulado_anterior > 0

        if has_comparison:
            diff_pct = (acumulado_actual - acumulado_anterior) / acumulado_anterior * 100.0
            arrow = "↑" if diff_pct >= 0 else "↓"
            sign = "+" if diff_pct >= 0 else ""
            comparison_label = f"{arrow} {sign}{diff_pct:.1f}% vs {prev_year}"
            comparison_color = SUCCESS if diff_pct >= 0 else DANGER
            sub_html = (
                f"Año anterior (mismo período): "
                f"<strong>{fmt_number(acumulado_anterior, unit, kpi_name)}</strong>"
            )
        else:
            comparison_label = f"Sin datos de {prev_year}"
            comparison_color = TEXT_MUTED
            sub_html = "Sin comparativa con año anterior"

        current_label = periodo_to_label(current_period)
        cumul_html = (
            f"<div class='efe-cumulative-card'>"
            f"<div class='efe-cumulative-label'>"
            f"📈 Acumulado año {current_year} (ene–{current_label.split('-')[0]})"
            f"</div>"
            f"<div class='efe-cumulative-value'>"
            f"{fmt_number(acumulado_actual, unit, kpi_name)}"
            f"</div>"
            f"<div class='efe-cumulative-comparison' "
            f"style='color:{comparison_color};'>"
            f"{comparison_label}"
            f"</div>"
            f"<div class='efe-cumulative-sub'>{sub_html}</div>"
            f"</div>"
        )
        st.markdown(cumul_html, unsafe_allow_html=True)
    except BaseException:
        return


def render_kpi_card_with_sparkline(title, value, meta, delta_text, status,
                                    history_values: list | None = None,
                                    streak_text: str | None = None,
                                    yoy_text: str | None = None):
    """Tarjeta KPI con sparkline pequeño, racha y comparación año anterior."""
    color = status_color(status)
    spark_svg = build_sparkline_svg(history_values, color=color) if history_values else ""
    streak_html = (
        f"<div class='efe-card-streak'>{streak_text}</div>"
        if streak_text else ""
    )
    yoy_html = (
        f"<div class='efe-card-yoy'>{yoy_text}</div>"
        if yoy_text else ""
    )
    spark_html = (
        f"<div class='efe-card-spark'>{spark_svg}</div>" if spark_svg else ""
    )
    st.markdown(f"""
    <div class="efe-card" style="border-left:6px solid {color};">
        <div class="efe-card-title">{title}</div>
        <div class="efe-card-value">{value}</div>
        <div class="efe-card-meta">{meta}</div>
        <div class="efe-card-delta" style="color:{color};">{delta_text}</div>
        {yoy_html}
        {spark_html}
        {streak_html}
    </div>""", unsafe_allow_html=True)


# ================================================================
# 9c-2. COMPARACIÓN AÑO ANTERIOR (YoY)
# ================================================================
def compute_yoy_comparison(history_df: pd.DataFrame, current_period: str,
                           kpi_name: str) -> str | None:
    """
    Calcula la variación vs mismo mes del año anterior.
    history_df: histórico del KPI con columnas 'periodo' y 'valor'.
    current_period: período actual en formato 'YYYY-MM'.
    Retorna string formato '↑ +5,2% vs abr-25' o None si no hay dato anterior.
    """
    if history_df is None or history_df.empty:
        return None
    if "periodo" not in history_df.columns or "valor" not in history_df.columns:
        return None

    try:
        current_dt = periodo_to_date(current_period)
        if pd.isna(current_dt):
            return None
        prev_year_dt = current_dt - pd.DateOffset(years=1)
        prev_period = prev_year_dt.strftime("%Y-%m")

        df = history_df.copy()
        df["periodo_str"] = df["periodo"].astype(str).str[:7]
        current_row = df[df["periodo_str"] == str(current_period)[:7]]
        prev_row = df[df["periodo_str"] == prev_period]
        if current_row.empty or prev_row.empty:
            return None

        current_val = pd.to_numeric(current_row["valor"], errors="coerce").iloc[0]
        prev_val = pd.to_numeric(prev_row["valor"], errors="coerce").iloc[0]
        if pd.isna(current_val) or pd.isna(prev_val) or prev_val == 0:
            return None

        diff_pct = (current_val - prev_val) / abs(prev_val) * 100.0
        # Flecha siempre indica la dirección del cambio numérico
        arrow = "↑" if diff_pct >= 0 else "↓"
        prev_label = periodo_to_label(prev_period)
        sign = "+" if diff_pct >= 0 else ""
        return f"{arrow} {sign}{diff_pct:.1f}% vs {prev_label}"
    except BaseException:
        return None


# ================================================================
# 9c. INDICADOR DE RACHA Y CUMPLIMIENTO HISTÓRICO
# ================================================================
def compute_kpi_streak(history_df: pd.DataFrame, kpi_name: str) -> str | None:
    """
    Calcula la 'racha' del KPI: cuántos períodos consecutivos cumple meta,
    o desde cuándo no la cumple. Devuelve string corto para mostrar en tarjeta.
    """
    if history_df is None or history_df.empty:
        return None
    if not {"valor", "meta", "periodo"}.issubset(history_df.columns):
        return None

    df = history_df.copy()
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["meta"]  = pd.to_numeric(df["meta"],  errors="coerce")
    df["periodo_date"] = df["periodo"].apply(periodo_to_date)
    df = df.dropna(subset=["periodo_date", "valor", "meta"])
    if df.empty:
        return None
    df = df.sort_values("periodo_date")

    # Determinar dirección "cumple" (asumimos higher_is_better salvo casos
    # donde la unidad sugiera lo contrario, p.ej. fuga, retraso, %evasión).
    name_norm = normalize_text(kpi_name or "")
    higher_is_better = not any(
        kw in name_norm for kw in ["fuga", "evasion", "retraso", "espera", "incidente"]
    )
    cumple = (df["valor"] >= df["meta"]) if higher_is_better else (df["valor"] <= df["meta"])

    # Iterar desde el último período hacia atrás
    cumple_list = cumple.tolist()
    if not cumple_list:
        return None

    last_status = cumple_list[-1]
    streak = 0
    for v in reversed(cumple_list):
        if v == last_status:
            streak += 1
        else:
            break

    if last_status:
        if streak >= 2:
            return f"✓ {streak} períodos cumpliendo"
        return None
    else:
        # Buscar último período cumpliendo
        last_ok_idx = None
        for i in range(len(cumple_list) - 1, -1, -1):
            if cumple_list[i]:
                last_ok_idx = i
                break
        if last_ok_idx is None:
            return f"⚠ Sin cumplir hace {streak} períodos"
        last_ok_period = df["periodo"].iloc[last_ok_idx]
        return f"⚠ Sin cumplir desde {periodo_to_label(last_ok_period)}"


# ================================================================
# 9d. NARRATIVA AUTOMÁTICA "QUÉ PASÓ ESTE PERÍODO"
# ================================================================
def generate_narrative_kpis(kpis_periodo: pd.DataFrame,
                             servicio: str | None = None) -> str:
    """
    Genera 2-3 frases en lenguaje natural describiendo el estado de los KPIs.
    Sin IA, solo reglas sobre los datos.
    """
    if kpis_periodo is None or kpis_periodo.empty:
        return ""
    df = kpis_periodo.copy()
    if servicio:
        df = df[df["servicio"].astype(str) == str(servicio)]
    if df.empty:
        return ""

    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["meta"]  = pd.to_numeric(df["meta"],  errors="coerce")

    total = len(df)
    cumplen = int((df["estado"].astype(str).str.strip().str.lower() == "ok").sum())
    alerta  = int((df["estado"].astype(str).str.strip().str.lower() == "alerta").sum())
    critico = int((df["estado"].astype(str).str.strip().str.lower() == "critico").sum())

    parts = []
    if total > 0:
        pct = cumplen * 100 / total
        if pct >= 80:
            parts.append(f"De {total} indicadores, <strong>{cumplen} cumplen meta</strong> ({pct:.0f}%): desempeño general sólido.")
        elif pct >= 50:
            parts.append(f"De {total} indicadores, {cumplen} cumplen meta ({pct:.0f}%); persisten áreas con desviaciones relevantes.")
        else:
            parts.append(f"<strong>Solo {cumplen} de {total} indicadores cumplen meta</strong> ({pct:.0f}%): el período presenta desafíos generalizados.")

    if critico > 0:
        criticos_df = df[df["estado"].astype(str).str.strip().str.lower() == "critico"]
        criticos_names = criticos_df["nombre"].astype(str).tolist()[:3]
        if criticos_names:
            parts.append(f"Críticos: <strong>{', '.join(criticos_names)}</strong>{' y otros' if critico > 3 else ''}.")
    elif alerta > 0:
        alerta_df = df[df["estado"].astype(str).str.strip().str.lower() == "alerta"]
        alerta_names = alerta_df["nombre"].astype(str).tolist()[:2]
        if alerta_names:
            parts.append(f"En alerta: {', '.join(alerta_names)}{' y otros' if alerta > 2 else ''}.")

    # Mejor variación positiva si existe
    df_var = df.dropna(subset=["variacion_pct"]).copy()
    if not df_var.empty:
        df_var["variacion_pct"] = pd.to_numeric(df_var["variacion_pct"], errors="coerce")
        df_var = df_var.dropna(subset=["variacion_pct"])
        if not df_var.empty:
            top_pos = df_var.sort_values("variacion_pct", ascending=False).head(1)
            top_neg = df_var.sort_values("variacion_pct").head(1)
            if not top_pos.empty and float(top_pos["variacion_pct"].iloc[0]) > 0.5:
                parts.append(
                    f"Mayor avance: {top_pos['nombre'].iloc[0]} "
                    f"({top_pos['variacion_pct'].iloc[0]:+.1f}%)."
                )
            if not top_neg.empty and float(top_neg["variacion_pct"].iloc[0]) < -0.5:
                parts.append(
                    f"Mayor caída: {top_neg['nombre'].iloc[0]} "
                    f"({top_neg['variacion_pct'].iloc[0]:+.1f}%)."
                )

    return " ".join(parts)


def render_narrative_box(narrative_html: str, title: str = "📋 Lectura del período") -> None:
    """Caja destacada con la narrativa generada automáticamente."""
    if not narrative_html:
        return
    st.markdown(
        f"<div class='efe-narrative'>"
        f"<div class='efe-narrative-title'>{title}</div>"
        f"<div class='efe-narrative-body'>{narrative_html}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ================================================================
# 9e. EXPORTACIÓN A PDF/IMAGEN DE LA SECCIÓN
# ================================================================
def render_export_button(section_id: str, label: str = "📥 Exportar sección") -> None:
    """
    Botón que invoca window.print con un selector CSS específico.
    Genera un PDF a través del print del navegador (sin dependencias).
    """
    btn_html = f"""
    <div style='text-align:right; margin: 0.2rem 0 0.5rem;'>
        <button onclick="
            const sec = window.parent.document.querySelector('[data-section=\\'{section_id}\\']');
            if (sec) {{
                const w = window.open('', '_blank');
                w.document.write('<html><head><title>EFE Sur — Exportar</title>');
                w.document.write('<link rel=stylesheet href=\\'data:text/css;,body{{font-family:Arial}}\\'>');
                w.document.write('</head><body>' + sec.innerHTML + '</body></html>');
                w.document.close();
                setTimeout(function(){{ w.print(); }}, 500);
            }} else {{
                alert('Sección no encontrada');
            }}
        " style='background:white; border:1px solid #D7E0EA; color:#002857; font-weight:700;
                 padding:0.4rem 0.85rem; border-radius:999px; cursor:pointer; font-size:0.85rem;'>
            {label}
        </button>
    </div>
    """
    st.markdown(btn_html, unsafe_allow_html=True)


def validate_columns(df: pd.DataFrame, required_cols: list, label: str) -> list:
    """Lista de columnas faltantes, sin levantar excepción."""
    if df is None:
        return list(required_cols)
    return [c for c in required_cols if c not in df.columns]

# ================================================================
# 10. CONFIGURACIÓN DE SERVICIOS Y CARPETAS
# ================================================================
PROFILE_SERVICE_CONFIG = {
    "Biotren": {
        "folder_candidates": ["perfil_bt", ".perfil-bt", ".perfil_bt"],
        "description": "Formato base implementado para Biotren.",
    },
    "Tren Araucanía": {
        "folder_candidates": ["perfil_ta", "perfil_tren_araucania"],
        "description": "Preparado para futura incorporación.",
    },
    "Laja Talcahuano": {
        "folder_candidates": ["perfil_lt", "perfil_laja_talcahuano"],
        "description": "Preparado para futura incorporación.",
    },
    "Llanquihue Puerto Montt": {
        "folder_candidates": ["perfil_lpm", "perfil_llanquihue_puerto_montt"],
        "description": "Preparado para futura incorporación.",
    },
}

OD_SERVICE_CONFIG = {
    "Biotren": {
        "folder_candidates": ["od_bt", ".od_bt"],
        "description": "Base transaccional OD por estación.",
    },
}

TURNSTILE_SERVICE_CONFIG = {
    "Biotren": {
        "folder_candidates": ["transacciones_bt", "torniquetes_bt", ".transacciones_bt"],
        "description": "Base cruda de torniquetes para cruce con perfil.",
    },
}


def _resolve_folder(service_name: str, config_dict: dict, data_path: Path) -> tuple[list, str]:
    """Devuelve (lista_archivos_csv, ruta_carpeta) buscando candidatos."""
    base = Path(__file__).resolve().parent
    config = config_dict.get(service_name, {})
    folder_names = config.get("folder_candidates", [])
    folder_default = folder_names[0] if folder_names else "data"

    for folder_name in folder_names:
        for root in [base, data_path]:
            candidate = root / folder_name
            if candidate.exists() and candidate.is_dir():
                files = sorted(candidate.glob("*.csv"))
                if files:
                    return list(files), str(candidate)

    return [], str(data_path / folder_default)


def get_repo_data_path() -> Path:
    """Encuentra la carpeta con kpis.csv, iniciativas.csv, personas.csv."""
    base = Path(__file__).resolve().parent
    for folder in [base / "data", base / "datos", base]:
        required = ["kpis.csv", "iniciativas.csv", "personas.csv"]
        if all((folder / f).exists() for f in required):
            return folder
    st.error(
        "No se encontraron kpis.csv, iniciativas.csv y personas.csv. "
        "Ubíquelos en la raíz o en una carpeta 'data'."
    )
    st.stop()


# ================================================================
# 11. CARGA DE DATOS PRINCIPAL
# ================================================================

@st.cache_data(ttl=900, show_spinner=False)
def load_data():
    """Carga KPIs, iniciativas, personas, servicios, estaciones, afluencia."""
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

    # Validar columnas obligatorias
    required_kpis = ["id_kpi", "nombre", "categoria", "servicio", "valor",
                     "meta", "unidad", "periodo", "variacion_pct", "estado"]
    missing = validate_columns(kpis, required_kpis, "kpis.csv")
    if missing:
        st.error(f"kpis.csv: columnas faltantes → {', '.join(missing)}")
        st.stop()

    required_ini = ["id_iniciativa", "nombre", "responsable_id", "servicio",
                    "estado", "avance_pct", "fecha_inicio", "fecha_fin", "prioridad"]
    missing = validate_columns(iniciativas, required_ini, "iniciativas.csv")
    if missing:
        st.error(f"iniciativas.csv: columnas faltantes → {', '.join(missing)}")
        st.stop()

    required_per = ["id_persona", "nombre", "cargo", "area", "activo"]
    missing = validate_columns(personas, required_per, "personas.csv")
    if missing:
        st.error(f"personas.csv: columnas faltantes → {', '.join(missing)}")
        st.stop()

    # Tipos numéricos
    for col in ["valor", "meta", "variacion_pct"]:
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
        for col in ["latitud", "longitud", "orden_trazado"]:
            if col in estaciones.columns:
                estaciones[col] = pd.to_numeric(estaciones[col], errors="coerce")
        if "activa" in estaciones.columns:
            estaciones["activa"] = pd.to_numeric(estaciones["activa"], errors="coerce").fillna(0).astype(int)

    if not afluencia_estacion.empty:
        for col in ["entradas", "meta_entradas", "perdida_pax", "fuga_pct"]:
            if col in afluencia_estacion.columns:
                afluencia_estacion[col] = pd.to_numeric(afluencia_estacion[col], errors="coerce")

    return kpis, iniciativas, personas, servicios, estaciones, afluencia_estacion, data_path


# ================================================================
# 12. CARGA DE PERFIL DE CARGA
# ================================================================
PROFILE_AGG_REQUIRED = ["fecha", "linea", "direccion", "servicio", "estacion",
                        "t_arr_est", "t_dep_est", "capacidad_tren", "D_bajadas",
                        "B_embarque", "L_out_abordo"]
PROFILE_TX_REQUIRED = ["origen", "destino", "servicio_final", "linea", "direccion",
                       "t_entrada_viaje", "t_salida_viaje"]


@st.cache_data(ttl=900, show_spinner=False)
def load_profile_service_data(service_name: str, data_path_str: str):
    """Carga el perfil de carga para un servicio. Detecta schema agg vs tx."""
    data_path = Path(data_path_str)
    csv_files, folder_path = _resolve_folder(service_name, PROFILE_SERVICE_CONFIG, data_path)
    if not csv_files:
        return pd.DataFrame(), folder_path, list(PROFILE_AGG_REQUIRED), [], "no_data"

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
        return pd.DataFrame(), folder_path, list(PROFILE_AGG_REQUIRED), loaded, "read_error"

    df = pd.concat(frames, ignore_index=True)
    has_agg = all(c in df.columns for c in PROFILE_AGG_REQUIRED)
    has_tx  = all(c in df.columns for c in PROFILE_TX_REQUIRED)

    if has_agg:
        df = _normalize_aggregated_profile(df)
        return df, folder_path, [], loaded, "ok"
    if has_tx:
        df = _normalize_transactional_profile(df)
        return df, folder_path, [], loaded, "ok"

    missing = [c for c in PROFILE_AGG_REQUIRED if c not in df.columns]
    if len(missing) == len(PROFILE_AGG_REQUIRED):
        missing = [c for c in PROFILE_TX_REQUIRED if c not in df.columns]
    return df, folder_path, missing, loaded, "unsupported_format"


def _normalize_aggregated_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza un perfil con schema agregado (estación-nivel)."""
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    for col in ["linea", "direccion", "estacion"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["servicio_label"] = df["servicio"].apply(format_service_id)
    df["profile_schema"] = "aggregated"

    for tc in ["t_arr_est", "t_dep_est"]:
        df[tc] = pd.to_datetime(df[tc], errors="coerce")

    numeric_cols = [
        "capacidad_tren", "A_llegadas_anden", "D_bajadas", "Demanda_anden",
        "Capacidad_disponible", "B_embarque", "R_quedados", "Q_out_cola",
        "L_in_abordo", "L_out_abordo",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["fecha"]).copy()
    df.attrs["profile_schema"] = "aggregated"
    return df


def _normalize_transactional_profile(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza un perfil con schema transaccional (origen-destino).

    Soporta el formato enriquecido con tarifa y tipo de pasajero por viaje:
    columnas opcionales `MONTO_TRANSACCION` y `tipo_pasajero_norm`.
    Cuando vienen presentes, el dashboard evita el cruce con torniquetes
    y obtiene tarifa/tipo directamente del perfil.
    """
    df = df.copy()
    for col in ["origen", "destino", "linea", "direccion"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["t_entrada_viaje"] = pd.to_datetime(df["t_entrada_viaje"], errors="coerce")
    df["t_salida_viaje"] = pd.to_datetime(df["t_salida_viaje"], errors="coerce")
    df["fecha"] = df["t_entrada_viaje"].dt.date

    missing_mask = df["fecha"].isna()
    if missing_mask.any():
        df.loc[missing_mask, "fecha"] = df.loc[missing_mask, "t_salida_viaje"].dt.date

    if "dia_proceso" in df.columns:
        dia_proceso = pd.to_datetime(df["dia_proceso"], errors="coerce").dt.date
        df["fecha"] = df["fecha"].where(pd.Series(df["fecha"]).notna(), dia_proceso)

    df["servicio_label"] = df["servicio_final"].apply(format_service_id)
    df["profile_schema"] = "transactional"

    for col in ["viaje_idx", "tarjeta_id", "servicio_final",
                "servicio_tramo_v1", "servicio_tramo_v2"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Formato enriquecido (tarifa y tipo de pasajero ya pegados) -----
    # Si el archivo del perfil incluye `MONTO_TRANSACCION` y/o
    # `tipo_pasajero_norm` por viaje, los normalizamos. Esto reemplaza
    # el cruce con torniquetes en runtime.
    monto_col = next(
        (c for c in df.columns if c.lower() in {"monto_transaccion", "monto"}),
        None,
    )
    if monto_col is not None:
        df["monto_transaccion"] = pd.to_numeric(df[monto_col], errors="coerce")

    tipo_col = next(
        (c for c in df.columns
         if c.lower() in {"tipo_pasajero_norm", "tipo_pasajero"}),
        None,
    )
    if tipo_col is not None:
        tipo = df[tipo_col].astype(str).str.strip()
        tipo = tipo.replace({"": np.nan, "nan": np.nan, "None": np.nan})
        df["tipo_pasajero"] = tipo

    df = df.dropna(subset=["fecha"]).copy()
    df.attrs["profile_schema"] = "transactional"
    # Marca explícita: ¿el perfil ya trae tarifa/tipo o necesitamos cruce?
    df.attrs["enriched"] = bool(
        ("monto_transaccion" in df.columns) or ("tipo_pasajero" in df.columns)
    )
    return df


# ================================================================
# 13. CARGA DE OD
# ================================================================
@st.cache_data(ttl=900, show_spinner=False)
def load_od_service_data(service_name: str, data_path_str: str):
    """Carga la base OD por estación con manejo de schemas viejos y nuevos."""
    data_path = Path(data_path_str)
    csv_files, folder_path = _resolve_folder(service_name, OD_SERVICE_CONFIG, data_path)
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

    has_new = all(c in od_df.columns for c in required_display)
    has_old = all(c in od_df.columns for c in ["origen", "destino", "t_entrada_viaje", "t_salida_viaje"])

    if has_new:
        od_df["t_entrada_viaje"] = pd.to_datetime(od_df["fecha_entrada"], errors="coerce")
        od_df["t_salida_viaje"]  = pd.to_datetime(od_df["fecha_salida"],  errors="coerce")
    elif has_old:
        od_df["t_entrada_viaje"] = pd.to_datetime(od_df["t_entrada_viaje"], errors="coerce")
        od_df["t_salida_viaje"]  = pd.to_datetime(od_df["t_salida_viaje"],  errors="coerce")
    else:
        return od_df, folder_path, required_display, loaded, "unsupported_format"

    for col in ["origen", "destino", "direccion", "linea", "linea_entrada", "linea_salida"]:
        if col not in od_df.columns:
            od_df[col] = ""
        od_df[col] = od_df[col].fillna("").astype(str).str.strip()

    if od_df["linea"].eq("").all():
        same = od_df["linea_entrada"].astype(str) == od_df["linea_salida"].astype(str)
        od_df["linea"] = np.where(
            same,
            od_df["linea_entrada"].astype(str),
            (od_df["linea_entrada"].astype(str) + "→" + od_df["linea_salida"].astype(str)).str.strip("→"),
        )

    od_df["fecha"] = od_df["t_entrada_viaje"].dt.date
    missing_mask = od_df["fecha"].isna()
    if missing_mask.any():
        od_df.loc[missing_mask, "fecha"] = od_df.loc[missing_mask, "t_salida_viaje"].dt.date
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


# ================================================================
# 14. CARGA DE TORNIQUETES
# ================================================================
TURNSTILE_REQUIRED = ["FECHA_TRANSACCION", "NUMERO_TARJETA", "MONTO_TRANSACCION"]
_TURNSTILE_COL_MAP = {
    "fecha_transaccion":  "FECHA_TRANSACCION",
    "numero_tarjeta":     "NUMERO_TARJETA",
    "monto_transaccion":  "MONTO_TRANSACCION",
    "tipo_pasajero_norm": "TIPO_PASAJERO_NORM",
    "tipo_pasajero":      "TIPO_PASAJERO_NORM",
}


@st.cache_data(ttl=900, show_spinner=False)
def load_turnstile_service_data(service_name: str, data_path_str: str):
    """Carga la base cruda de torniquetes (CSV o XLSX). Soporta tipo_pasajero opcional."""
    data_path = Path(data_path_str)
    config = TURNSTILE_SERVICE_CONFIG.get(service_name, {})
    folder_names = config.get("folder_candidates", [])
    base = Path(__file__).resolve().parent
    search_roots = [base, data_path, base / "data", base / "datos"]

    files: list[Path] = []
    folder_path = ""
    for folder_name in folder_names:
        for root in search_roots:
            candidate = root / folder_name
            if candidate.exists() and candidate.is_dir():
                found = [
                    fp for fp in candidate.iterdir()
                    if fp.is_file() and fp.suffix.lower() in {".csv", ".xlsx", ".xls"}
                    and not fp.name.startswith("~$")
                ]
                if found:
                    files = sorted(found, key=lambda fp: fp.name.lower())
                    folder_path = str(candidate)
                    break
        if files:
            break

    if not files:
        fallback = (data_path / folder_names[0]) if folder_names else data_path / "transacciones_bt"
        return pd.DataFrame(), str(fallback), list(TURNSTILE_REQUIRED), [], "no_data"

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
        return pd.DataFrame(), folder_path, list(TURNSTILE_REQUIRED), [], "read_error"

    df = pd.concat(frames, ignore_index=True)
    col_norms = normalize_series(pd.Series(df.columns.tolist()))
    rename_map = {
        orig: _TURNSTILE_COL_MAP[norm]
        for orig, norm in zip(df.columns, col_norms)
        if norm in _TURNSTILE_COL_MAP
    }
    df = df.rename(columns=rename_map)

    missing = [c for c in TURNSTILE_REQUIRED if c not in df.columns]
    if missing:
        return df, folder_path, missing, loaded, "unsupported_format"

    timestamp_txt = df["FECHA_TRANSACCION"].fillna("").astype(str).str.strip()
    df["fecha_transaccion_txt"] = timestamp_txt
    df["fecha_transaccion"] = pd.to_datetime(
        timestamp_txt.str.replace("T", " ", regex=False), errors="coerce"
    )
    df["fecha"] = df["fecha_transaccion"].dt.date
    df["hora_transaccion"] = df["fecha_transaccion"].dt.strftime("%H:%M:%S")
    df["tarjeta_id"] = pd.to_numeric(df["NUMERO_TARJETA"], errors="coerce")
    df["monto_transaccion"] = pd.to_numeric(df["MONTO_TRANSACCION"], errors="coerce")
    df["turnstile_tx_id"] = np.arange(1, len(df) + 1)

    if "TIPO_PASAJERO_NORM" in df.columns:
        tipo = df["TIPO_PASAJERO_NORM"].astype(str).str.strip()
        tipo = tipo.replace({"": np.nan, "nan": np.nan, "None": np.nan})
        df["tipo_pasajero"] = tipo

    df = df.dropna(subset=["fecha_transaccion", "fecha", "tarjeta_id", "monto_transaccion"]).copy()
    return df, folder_path, [], loaded, "ok"


# ================================================================
# 14b. SLICES PRE-FILTRADOS POR PERÍODO (REDUCEN MEMORIA Y CRASHES)
# ================================================================
# Cuando el usuario cambia rápido de fecha/mes, en lugar de cargar el
# dataset entero y filtrar en cada re-run, cacheamos rebanadas pequeñas
# por período. Esto reduce la memoria activa por re-run y mejora
# drásticamente la robustez ante cambios rápidos de filtros.

@st.cache_data(ttl=900, show_spinner=False, max_entries=24)
def get_profile_for_day(service_name: str, data_path_str: str,
                        fecha_iso: str) -> tuple[pd.DataFrame, str]:
    """Retorna sólo las filas del perfil para un día específico."""
    perfil_df, _p, _m, _f, status = load_profile_service_data(service_name, data_path_str)
    if status != "ok" or perfil_df.empty or not fecha_iso:
        schema_default = "aggregated"
        if not perfil_df.empty:
            schema_default = perfil_df.attrs.get("profile_schema", "aggregated")
        return pd.DataFrame(), schema_default

    schema = perfil_df.attrs.get("profile_schema", "aggregated")
    target = pd.to_datetime(fecha_iso, errors="coerce")
    if pd.isna(target):
        return pd.DataFrame(), schema
    sliced = perfil_df.loc[perfil_df["fecha"] == target.date()].copy()
    sliced.attrs["profile_schema"] = schema
    return sliced, schema


@st.cache_data(ttl=900, show_spinner=False, max_entries=12)
def get_profile_for_month(service_name: str, data_path_str: str,
                          month_period: str) -> tuple[pd.DataFrame, str]:
    """Retorna sólo las filas del perfil correspondientes a un mes (YYYY-MM)."""
    perfil_df, _p, _m, _f, status = load_profile_service_data(service_name, data_path_str)
    if status != "ok" or perfil_df.empty or not month_period:
        schema_default = "aggregated"
        if not perfil_df.empty:
            schema_default = perfil_df.attrs.get("profile_schema", "aggregated")
        return pd.DataFrame(), schema_default

    schema = perfil_df.attrs.get("profile_schema", "aggregated")
    fecha_periods = pd.to_datetime(perfil_df["fecha"], errors="coerce").dt.to_period("M").astype(str)
    sliced = perfil_df.loc[fecha_periods == str(month_period)].copy()
    sliced.attrs["profile_schema"] = schema
    return sliced, schema


@st.cache_data(ttl=900, show_spinner=False, max_entries=24)
def get_turnstile_for_day(service_name: str, data_path_str: str,
                          fecha_iso: str) -> pd.DataFrame:
    """Retorna sólo las transacciones de torniquete para un día específico."""
    turnstile_df, _p, _m, _f, status = load_turnstile_service_data(service_name, data_path_str)
    if status != "ok" or turnstile_df.empty or not fecha_iso:
        return pd.DataFrame()
    target = pd.to_datetime(fecha_iso, errors="coerce")
    if pd.isna(target):
        return pd.DataFrame()
    return turnstile_df.loc[turnstile_df["fecha"] == target.date()].copy()


@st.cache_data(ttl=900, show_spinner=False, max_entries=12)
def get_available_dates(service_name: str, data_path_str: str) -> list:
    """Lista ordenada de fechas únicas disponibles para el servicio."""
    perfil_df, _p, _m, _f, status = load_profile_service_data(service_name, data_path_str)
    if status != "ok" or perfil_df.empty:
        return []
    fechas = perfil_df["fecha"].dropna().unique().tolist()
    return sorted([f for f in fechas if pd.notna(f)])


@st.cache_data(ttl=900, show_spinner=False, max_entries=12)
def get_available_months(service_name: str, data_path_str: str) -> list:
    """Lista ordenada de meses únicos (YYYY-MM) disponibles."""
    perfil_df, _p, _m, _f, status = load_profile_service_data(service_name, data_path_str)
    if status != "ok" or perfil_df.empty:
        return []
    series = pd.to_datetime(perfil_df["fecha"], errors="coerce").dt.to_period("M").astype(str)
    return [m for m in sorted(pd.Series(series).dropna().unique().tolist())
            if m and m != "NaT"]


# ================================================================
# 15. CARGA DE ITINERARIO Y ORDEN DE SERVICIOS
# ================================================================
@st.cache_data(ttl=1800, show_spinner=False)
def load_itinerary_reference(data_path_str: str):
    """Carga el resumen de itinerario desde CSV o XLSX."""
    data_path = Path(data_path_str)
    base = Path(__file__).resolve().parent
    search_roots = [
        base / "itinerarios", data_path / "itinerarios",
        base, data_path, base / "data", base / "datos",
    ]

    summary_df = pd.DataFrame()
    detail_df = pd.DataFrame()
    found_path = None
    found_files: list[str] = []

    def _safe_csv(p: Path) -> pd.DataFrame:
        try:
            return pd.read_csv(p, low_memory=False)
        except Exception:
            return pd.DataFrame()

    def _safe_xlsx(p: Path, sheet: str) -> pd.DataFrame:
        try:
            return pd.read_excel(p, sheet_name=sheet)
        except Exception:
            return pd.DataFrame()

    for root in search_roots:
        if not root.exists():
            continue
        s_csv = root / "itinerario_resumen_servicios.csv"
        d_csv = root / "itinerario_detalle_estaciones.csv"
        x = root / "itinerario_efe_sur_extraido.xlsx"

        ts, td, tf = pd.DataFrame(), pd.DataFrame(), []
        if s_csv.exists():
            ts = _safe_csv(s_csv)
            if not ts.empty:
                tf.append(s_csv.name)
        if d_csv.exists():
            td = _safe_csv(d_csv)
            if not td.empty:
                tf.append(d_csv.name)
        if ts.empty and x.exists():
            ts = _safe_xlsx(x, "Resumen_servicios")
            td = _safe_xlsx(x, "Detalle_estaciones")
            if not ts.empty:
                tf.append(x.name + "::Resumen_servicios")
            if not td.empty:
                tf.append(x.name + "::Detalle_estaciones")

        if not ts.empty:
            summary_df = ts.copy()
            detail_df = td.copy()
            found_path = str(root)
            found_files = tf
            break

    if summary_df.empty:
        return pd.DataFrame(), pd.DataFrame(), "", [], "no_data"

    for df in [summary_df, detail_df]:
        if df.empty:
            continue
        for col in ["sector", "tipo_dia", "sentido",
                    "estacion_origen", "estacion_terminal", "estacion"]:
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str).str.strip()
        if "servicio" in df.columns:
            df["servicio_label"] = df["servicio"].apply(format_service_id)

    if "hora_salida_origen" in summary_df.columns:
        summary_df["hora_salida_origen_str"] = summary_df["hora_salida_origen"].fillna("").astype(str).str.strip()
    if "hora_llegada_term" in summary_df.columns:
        summary_df["hora_llegada_term_str"] = summary_df["hora_llegada_term"].fillna("").astype(str).str.strip()

    return summary_df, detail_df, found_path or "", found_files, "ok"


@st.cache_data(ttl=1800, show_spinner=False)
def load_service_order_reference(data_path_str: str):
    """Carga el orden operativo de servicios desde XLSX o CSV."""
    data_path = Path(data_path_str)
    base = Path(__file__).resolve().parent
    search_roots = [
        base / "itinerarios", data_path / "itinerarios",
        base, data_path, base / "data", base / "datos",
    ]

    candidates = []

    def _safe_csv(p: Path) -> pd.DataFrame:
        try:
            t = pd.read_csv(p, low_memory=False)
            t["__sheet_seq"] = 0
            t["__row_seq"] = np.arange(1, len(t) + 1)
            return t
        except Exception:
            return pd.DataFrame()

    def _safe_xlsx(p: Path) -> pd.DataFrame:
        try:
            xl = pd.ExcelFile(p)
            frames = []
            sheet_map = {"Lun a Vie": "Lunes a Viernes", "Sabado y Domingo": "Sabado y Domingo"}
            for i, sheet in enumerate(xl.sheet_names):
                t = pd.read_excel(p, sheet_name=sheet)
                if t.empty:
                    continue
                t["tipo_dia_ref"] = sheet_map.get(sheet, str(sheet))
                t["__sheet_seq"] = i
                t["__row_seq"] = np.arange(1, len(t) + 1)
                frames.append(t)
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    for root in search_roots:
        if not root.exists():
            continue
        for fname, reader in [("itinerario_orden.xlsx", _safe_xlsx),
                              ("itinerario_orden.csv", _safe_csv)]:
            fp = root / fname
            if not fp.exists():
                continue
            t = reader(fp)
            if t.empty:
                continue

            rename = {}
            for c in t.columns:
                nc = normalize_text(c)
                if nc == "servicio":
                    rename[c] = "servicio"
                elif nc == "linea":
                    rename[c] = "linea"
                elif nc == "sentido":
                    rename[c] = "direccion"
                elif nc in {"tipo dia", "tipo_dia", "tipodia", "tipo dia ref", "tipo_dia_ref"}:
                    rename[c] = "tipo_dia_ref"
                elif nc == "orden":
                    rename[c] = "orden"
            t = t.rename(columns=rename)

            if not {"servicio", "linea", "direccion"}.issubset(t.columns):
                continue
            if "orden" in t.columns:
                t["orden"] = pd.to_numeric(t["orden"], errors="coerce")
            else:
                t["orden"] = np.nan

            t["__sheet_seq"] = pd.to_numeric(t.get("__sheet_seq"), errors="coerce").fillna(0).astype(int)
            t["__row_seq"]   = pd.to_numeric(t.get("__row_seq"),   errors="coerce")
            if t["__row_seq"].isna().all():
                t["__row_seq"] = np.arange(1, len(t) + 1)
            t["__row_seq"] = t["__row_seq"].astype(int)

            candidates.append({
                "df": t.copy(),
                "root": str(root),
                "file": fname,
                "explicit_order_count": int(t["orden"].notna().sum()),
                "is_xlsx": int(fname.lower().endswith(".xlsx")),
            })

    if not candidates:
        return pd.DataFrame(), "", [], "no_data"

    candidates.sort(key=lambda x: (x["explicit_order_count"], x["is_xlsx"]), reverse=True)
    best = candidates[0]
    order_df = best["df"].copy()

    if "tipo_dia_ref" not in order_df.columns:
        order_df["tipo_dia_ref"] = "Lunes a Viernes"

    if order_df["orden"].isna().all():
        order_df["orden"] = np.arange(1, len(order_df) + 1)
    else:
        missing = order_df["orden"].isna()
        if missing.any():
            base_n = int(order_df["orden"].dropna().max())
            order_df.loc[missing, "orden"] = np.arange(base_n + 1, base_n + 1 + int(missing.sum()))

    order_df["servicio_label"] = order_df["servicio"].apply(format_service_id)
    order_df["linea"]          = order_df["linea"].fillna("").astype(str).str.strip()
    order_df["direccion"]      = order_df["direccion"].fillna("").astype(str).str.strip()
    order_df["tipo_dia_ref"]   = order_df["tipo_dia_ref"].fillna("").astype(str).str.strip()
    order_df["orden"]          = pd.to_numeric(order_df["orden"], errors="coerce")
    order_df = order_df.dropna(subset=["orden"]).copy()
    order_df["orden"] = order_df["orden"].astype(int)

    order_df = (
        order_df.sort_values(
            ["tipo_dia_ref", "linea", "direccion", "orden", "__sheet_seq", "__row_seq"],
            kind="stable",
        )
        .drop_duplicates(subset=["tipo_dia_ref", "linea", "direccion", "servicio_label"], keep="first")
        .reset_index(drop=True)
    )
    return order_df, best["root"], [best["file"]], "ok"

# ================================================================
# 16. SECUENCIAS DE ESTACIONES OPERATIVAS
# ================================================================
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


def _normalize_direction_key(value) -> str:
    """Normaliza un código de dirección como 'CW→CC' a 'cw-cc'."""
    raw = "" if value is None else str(value).strip().lower()
    for token in ["→", "—", "–", "_", "/", "\\"]:
        raw = raw.replace(token, "-")
    raw = raw.replace(" ", "")
    while "--" in raw:
        raw = raw.replace("--", "-")
    return raw.strip("-")


def get_configured_station_order(linea: str, direccion: str,
                                 stations_present: list[str] | None = None) -> list:
    """Retorna la secuencia de estaciones canónica para una línea+dirección."""
    line_key = normalize_text(linea).replace(" ", "")
    dir_key = _normalize_direction_key(direccion)
    seq = PROFILE_STATION_SEQUENCES.get(line_key, {}).get(dir_key, [])
    if not seq:
        return []
    if not stations_present:
        return list(seq)

    norm_to_actual: dict[str, str] = {}
    for s in stations_present:
        if s is None:
            continue
        clean = str(s).strip()
        if clean:
            norm_to_actual.setdefault(normalize_text(clean), clean)

    ordered = [norm_to_actual[normalize_text(s)] for s in seq if normalize_text(s) in norm_to_actual]
    extras  = [s for s in stations_present if s not in ordered]
    return ordered + extras


def get_station_order_from_profile(df: pd.DataFrame) -> list:
    """Retorna estaciones en orden esperado para graficar."""
    if df is None or df.empty or "estacion" not in df.columns:
        return []

    temp = df.copy()
    temp["estacion"] = temp["estacion"].fillna("").astype(str).str.strip()
    temp = temp[temp["estacion"] != ""]
    if temp.empty:
        return []

    estaciones = list(dict.fromkeys(temp["estacion"].astype(str).tolist()))
    linea = ""
    if "linea" in temp.columns and not temp["linea"].dropna().empty:
        linea = temp["linea"].dropna().astype(str).str.strip().iloc[0]
    direccion = ""
    if "direccion" in temp.columns and not temp["direccion"].dropna().empty:
        direccion = temp["direccion"].dropna().astype(str).str.strip().iloc[0]

    configured = get_configured_station_order(linea, direccion, estaciones)
    if configured:
        return configured

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


# ================================================================
# 17. CONSTRUCCIÓN DEL PERFIL POR SERVICIO (TRANSACTIONAL)
# ================================================================
PROFILE_EMPTY_COLS = [
    "estacion", "t_arr_est", "t_dep_est", "B_embarque",
    "D_bajadas", "L_in_abordo", "L_out_abordo", "servicio_label",
    "linea", "direccion", "event_time",
]


def build_transactional_service_profile(service_tx: pd.DataFrame) -> pd.DataFrame:
    """
    Reconstruye un perfil de carga por estación a partir de transacciones OD
    de UN servicio. Devuelve siempre un DataFrame con todas las columnas
    esperadas (vacío si no hay datos).

    Implementación:
      1. Determinar el orden canónico de estaciones (secuencia oficial L1/L2,
         o por mediana de timestamp si la línea no es conocida).
      2. Asignar índice ordinal (`station_idx`) a cada estación.
      3. Mapear origen/destino de cada tx a su índice.
      4. Contar embarques (board) y bajadas (alight) por estación.
      5. Calcular pasajeros a bordo con cumsum simple sobre arrays numpy.
    """
    if service_tx is None or service_tx.empty:
        return pd.DataFrame(columns=PROFILE_EMPTY_COLS)

    tx = service_tx.copy()

    # Asegurar tipos
    tx["t_entrada_viaje"] = pd.to_datetime(tx["t_entrada_viaje"], errors="coerce")
    tx["t_salida_viaje"]  = pd.to_datetime(tx["t_salida_viaje"],  errors="coerce")
    tx["origen"]  = tx["origen"].fillna("").astype(str).str.strip()
    tx["destino"] = tx["destino"].fillna("").astype(str).str.strip()

    # Metadatos del servicio
    def _first_str(col: str) -> str:
        if col in tx.columns and not tx[col].dropna().empty:
            return str(tx[col].dropna().astype(str).iloc[0]).strip()
        return ""

    linea          = _first_str("linea")
    direccion      = _first_str("direccion")
    servicio_label = _first_str("servicio_label") or "-"

    # --- Determinar el orden de estaciones ----------------------------
    stations_present = list(dict.fromkeys(
        tx.loc[tx["origen"]  != "", "origen"].astype(str).tolist() +
        tx.loc[tx["destino"] != "", "destino"].astype(str).tolist()
    ))

    # Eventos para fallback de orden temporal
    entry_events = tx.loc[tx["origen"]  != "", ["origen",  "t_entrada_viaje"]].rename(
        columns={"origen":  "estacion", "t_entrada_viaje": "event_time"}
    )
    exit_events  = tx.loc[tx["destino"] != "", ["destino", "t_salida_viaje"]].rename(
        columns={"destino": "estacion", "t_salida_viaje":  "event_time"}
    )
    station_events = pd.concat([entry_events, exit_events], ignore_index=True).dropna(subset=["event_time"])

    line_key = normalize_text(linea).replace(" ", "")
    dir_key  = _normalize_direction_key(direccion)
    configured_full = PROFILE_STATION_SEQUENCES.get(line_key, {}).get(dir_key, [])

    if configured_full:
        # Orden canónico + extras al final
        norm_to_actual: dict[str, str] = {}
        for s in stations_present:
            clean = str(s).strip() if s is not None else ""
            if clean:
                norm_to_actual.setdefault(normalize_text(clean), clean)
        ordered_stations = [norm_to_actual.get(normalize_text(s), s) for s in configured_full]

        configured_norms = {normalize_text(x) for x in configured_full}
        extras_set = [s for s in stations_present if normalize_text(s) not in configured_norms]
        if station_events.empty:
            extras_ordered = list(extras_set)
        else:
            tmp = station_events.copy()
            tmp["station_key"] = normalize_series(tmp["estacion"])
            extras_keys = (
                tmp.groupby("station_key", as_index=False)["event_time"].median()
                .sort_values(["event_time", "station_key"])["station_key"].tolist()
            )
            extras_lookup = {normalize_text(s): s for s in extras_set}
            extras_ordered = [extras_lookup[k] for k in extras_keys if k in extras_lookup]
        order_list = ordered_stations + [s for s in extras_ordered if s not in ordered_stations]
    else:
        # Sin línea conocida: orden por mediana de tiempo
        if station_events.empty:
            return pd.DataFrame(columns=PROFILE_EMPTY_COLS)
        order_list = (
            station_events.groupby("estacion", as_index=False)["event_time"]
            .median().sort_values(["event_time", "estacion"])["estacion"].tolist()
        )

    if not order_list:
        return pd.DataFrame(columns=PROFILE_EMPTY_COLS)

    # --- Asignar índices ----------------------------------------------
    order_df = pd.DataFrame({
        "estacion":    order_list,
        "station_idx": range(len(order_list)),
    })
    order_df["station_key"] = normalize_series(order_df["estacion"])
    key_to_idx = dict(zip(order_df["station_key"], order_df["station_idx"]))

    tx["origen_key"]  = normalize_series(tx["origen"])
    tx["destino_key"] = normalize_series(tx["destino"])
    tx["origen_idx"]  = tx["origen_key"].map(key_to_idx)
    tx["destino_idx"] = tx["destino_key"].map(key_to_idx)

    valid_tx = tx.dropna(subset=["origen_idx", "destino_idx"]).copy()
    if not valid_tx.empty:
        valid_tx["origen_idx"]  = valid_tx["origen_idx"].astype(int)
        valid_tx["destino_idx"] = valid_tx["destino_idx"].astype(int)

    # --- Agregaciones por estación ------------------------------------
    if valid_tx.empty:
        # Sin transacciones válidas: perfil con ceros
        profile = order_df[["estacion", "station_idx"]].copy()
        profile["B_embarque"]   = 0
        profile["D_bajadas"]    = 0
        profile["t_arr_est"]    = pd.NaT
        profile["t_dep_est"]    = pd.NaT
        profile["L_in_abordo"]  = 0
        profile["L_out_abordo"] = 0
    else:
        board = (
            valid_tx.groupby("origen_idx", as_index=False).size()
            .rename(columns={"origen_idx": "station_idx", "size": "B_embarque"})
        )
        alight = (
            valid_tx.groupby("destino_idx", as_index=False).size()
            .rename(columns={"destino_idx": "station_idx", "size": "D_bajadas"})
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
            order_df.merge(board,     how="left", on="station_idx")
                    .merge(alight,    how="left", on="station_idx")
                    .merge(arr_times, how="left", on="station_idx")
                    .merge(dep_times, how="left", on="station_idx")
        )
        profile["B_embarque"] = pd.to_numeric(profile["B_embarque"], errors="coerce").fillna(0).astype(int)
        profile["D_bajadas"]  = pd.to_numeric(profile["D_bajadas"],  errors="coerce").fillna(0).astype(int)

        # Pasajeros a bordo: cumsum simple
        # En cada estación i:
        #   L_in[i]  = cumsum(board[0..i-1]) - cumsum(alight[0..i-1])
        #   L_out[i] = cumsum(board[0..i])   - cumsum(alight[0..i])
        profile = profile.sort_values("station_idx").reset_index(drop=True)
        board_arr  = profile["B_embarque"].to_numpy(dtype=np.int64)
        alight_arr = profile["D_bajadas"].to_numpy(dtype=np.int64)
        cum_board  = np.cumsum(board_arr)
        cum_alight = np.cumsum(alight_arr)
        # L_out[i] = cum_board[i] - cum_alight[i]
        l_out = (cum_board - cum_alight).astype(int)
        # L_in[i] = L_out[i-1] (con L_in[0] = 0)
        l_in = np.zeros_like(l_out)
        if len(l_out) > 1:
            l_in[1:] = l_out[:-1]
        profile["L_in_abordo"]  = l_in.tolist()
        profile["L_out_abordo"] = l_out.tolist()

    profile["t_arr_est"]   = pd.to_datetime(profile["t_arr_est"], errors="coerce")
    profile["t_dep_est"]   = pd.to_datetime(profile["t_dep_est"], errors="coerce")
    profile["event_time"]  = profile["t_arr_est"].fillna(profile["t_dep_est"])

    # Para estaciones sin eventos: timestamp sintético sólo para mantener orden
    if profile["event_time"].isna().any():
        non_null = pd.concat(
            [valid_tx["t_entrada_viaje"], valid_tx["t_salida_viaje"]] if not valid_tx.empty else [pd.Series(dtype="datetime64[ns]")],
            ignore_index=True,
        ).dropna() if not valid_tx.empty else pd.Series(dtype="datetime64[ns]")
        base_time = non_null.min().floor("min") if not non_null.empty else pd.Timestamp("2000-01-01")
        synth = pd.Series(
            [base_time + pd.Timedelta(minutes=int(i)) for i in profile["station_idx"]],
            index=profile.index,
        )
        profile["event_time"] = profile["event_time"].fillna(synth)
        profile["t_arr_est"]  = profile["t_arr_est"].fillna(profile["event_time"])
        profile["t_dep_est"]  = profile["t_dep_est"].fillna(profile["event_time"])

    profile["servicio_label"] = servicio_label
    profile["linea"]          = linea
    profile["direccion"]      = direccion

    keep_cols = [
        "estacion", "t_arr_est", "t_dep_est", "event_time",
        "B_embarque", "D_bajadas", "L_in_abordo", "L_out_abordo",
        "servicio_label", "linea", "direccion",
    ]
    return profile[keep_cols].copy()


# ================================================================
# 18. CRUCE TORNIQUETES ↔ PERFIL
# ================================================================
def match_turnstile_transactions_to_profile(turnstile_df: pd.DataFrame,
                                            profile_tx_df: pd.DataFrame,
                                            tolerance_minutes: int = 20):
    """
    Cruza transacciones de torniquete con viajes del perfil. Retorna:
      (matched_df, summary_df, stats_dict)
    Garantiza retorno seguro ante DataFrames vacíos o inconsistencias.
    """
    empty_summary = pd.DataFrame(columns=[
        "linea", "direccion", "servicio_label", "tx_cruzadas",
        "tarifa_media_aprox", "tarifa_mediana_aprox", "recaudacion_aprox",
        "desviacion_tarifa_aprox", "diff_mediana_min", "match_ref_principal",
    ])
    empty_stats = {
        "turnstile_total": 0, "matched_total": 0,
        "match_pct": np.nan, "diff_mediana_min": np.nan,
        "tolerance_minutes": tolerance_minutes,
        "pct_match_entrada": np.nan, "pct_match_salida": np.nan,
    }
    if turnstile_df is None or turnstile_df.empty or profile_tx_df is None or profile_tx_df.empty:
        return pd.DataFrame(), empty_summary, empty_stats

    tx = turnstile_df.copy()
    prof = profile_tx_df.copy()

    # --- Tipo de pasajero (opcional) ----------------------------------
    if "tipo_pasajero" in tx.columns:
        s = tx["tipo_pasajero"].astype(str).str.strip()
        s = s.replace({"": np.nan, "nan": np.nan, "None": np.nan})
        tx["tipo_pasajero"] = s.fillna("Otros")

    # --- Tipos seguros ------------------------------------------------
    tx["tarjeta_id"]        = pd.to_numeric(tx["tarjeta_id"], errors="coerce")
    tx["fecha_transaccion"] = pd.to_datetime(tx["fecha_transaccion"], errors="coerce")

    if "tarjeta_id" in prof.columns:
        prof["tarjeta_id"] = pd.to_numeric(prof["tarjeta_id"], errors="coerce")
    for col in ["t_entrada_viaje", "t_salida_viaje"]:
        if col in prof.columns:
            prof[col] = pd.to_datetime(prof[col], errors="coerce")

    keep_prof_cols = [
        c for c in [
            "tarjeta_id", "t_entrada_viaje", "t_salida_viaje", "servicio_label",
            "linea", "direccion", "servicio_final", "viaje_idx", "origen", "destino",
        ] if c in prof.columns
    ]
    if not {"tarjeta_id", "servicio_label"}.issubset(set(keep_prof_cols)):
        return pd.DataFrame(), empty_summary, empty_stats
    if not any(c in keep_prof_cols for c in ["t_entrada_viaje", "t_salida_viaje"]):
        return pd.DataFrame(), empty_summary, empty_stats

    tx = tx.dropna(subset=["tarjeta_id", "fecha_transaccion", "monto_transaccion"]).copy()
    prof = prof[keep_prof_cols].dropna(subset=["tarjeta_id", "servicio_label"]).copy()

    # Filtrar perfil a filas con al menos un timestamp
    has_entrada = prof["t_entrada_viaje"].notna() if "t_entrada_viaje" in prof.columns else pd.Series(False, index=prof.index)
    has_salida  = prof["t_salida_viaje"].notna()  if "t_salida_viaje"  in prof.columns else pd.Series(False, index=prof.index)
    prof = prof[has_entrada | has_salida].copy()

    empty_stats["turnstile_total"] = int(len(tx))
    if tx.empty or prof.empty:
        return pd.DataFrame(), empty_summary, empty_stats

    # --- ID por transacción ------------------------------------------
    tx["turnstile_tx_id"] = pd.to_numeric(tx.get("turnstile_tx_id"), errors="coerce")
    if tx["turnstile_tx_id"].isna().all():
        tx["turnstile_tx_id"] = np.arange(1, len(tx) + 1)
    tx["turnstile_tx_id"] = tx["turnstile_tx_id"].astype(int)

    # --- Merge por tarjeta_id ----------------------------------------
    # Pre-filtramos prof a tarjetas que existen en tx para no crear un
    # producto cartesiano gigante. Esto reduce la memoria del merge en
    # 5–20× cuando hay muchos viajes registrados en el perfil pero pocas
    # transacciones de torniquete en el día.
    tx_card_ids = set(tx["tarjeta_id"].dropna().unique().tolist())
    if tx_card_ids:
        prof = prof[prof["tarjeta_id"].isin(tx_card_ids)].copy()
    if prof.empty:
        return pd.DataFrame(), empty_summary, empty_stats

    merged = tx.merge(prof, how="inner", on="tarjeta_id", suffixes=("", "_perfil"))
    if merged.empty:
        return pd.DataFrame(), empty_summary, empty_stats

    # Cota dura de seguridad: si el merge excede ~2M filas (puede ocurrir
    # con muchas tarjetas con muchos viajes), tomamos una muestra para
    # evitar OOM. La estadística agregada sigue siendo representativa.
    MAX_MERGE_ROWS = 2_000_000
    if len(merged) > MAX_MERGE_ROWS:
        merged = merged.sample(n=MAX_MERGE_ROWS, random_state=42).copy()

    # --- Diferencia temporal contra entrada y salida ------------------
    if "t_entrada_viaje" in merged.columns:
        merged["diff_entrada_min"] = (
            (merged["fecha_transaccion"] - merged["t_entrada_viaje"]).abs().dt.total_seconds() / 60.0
        )
    else:
        merged["diff_entrada_min"] = np.nan

    if "t_salida_viaje" in merged.columns:
        merged["diff_salida_min"] = (
            (merged["fecha_transaccion"] - merged["t_salida_viaje"]).abs().dt.total_seconds() / 60.0
        )
    else:
        merged["diff_salida_min"] = np.nan

    merged["match_diff_min"] = merged[["diff_entrada_min", "diff_salida_min"]].min(axis=1, skipna=True)

    # match_ref: 'salida' si esa diferencia es menor, 'entrada' en caso contrario
    diff_e = merged["diff_entrada_min"].fillna(np.inf)
    diff_s = merged["diff_salida_min"].fillna(np.inf)
    merged["match_ref"] = np.where(diff_s < diff_e, "salida", "entrada")

    # match_timestamp: el timestamp efectivamente usado
    ts_entrada = merged["t_entrada_viaje"] if "t_entrada_viaje" in merged.columns else pd.Series(pd.NaT, index=merged.index)
    ts_salida  = merged["t_salida_viaje"]  if "t_salida_viaje"  in merged.columns else pd.Series(pd.NaT, index=merged.index)
    merged["match_timestamp"] = np.where(merged["match_ref"] == "salida", ts_salida, ts_entrada)
    merged["match_timestamp"] = pd.to_datetime(merged["match_timestamp"], errors="coerce")

    # Filtrar por tolerancia
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
        "matched_total":   int(len(matched_df)),
        "match_pct": (float(len(matched_df)) / float(len(tx)) * 100.0) if len(tx) else np.nan,
        "diff_mediana_min": float(matched_df["match_diff_min"].median()) if not matched_df.empty else np.nan,
        "tolerance_minutes": tolerance_minutes,
        "pct_match_entrada": float((matched_df["match_ref"] == "entrada").mean() * 100.0) if not matched_df.empty else np.nan,
        "pct_match_salida":  float((matched_df["match_ref"] == "salida").mean() * 100.0)  if not matched_df.empty else np.nan,
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

    if not matched_df.empty:
        ref_summary = (
            matched_df.groupby(["linea", "direccion", "servicio_label", "match_ref"], as_index=False)
            .size().rename(columns={"size": "n"})
            .sort_values(
                ["linea", "direccion", "servicio_label", "n", "match_ref"],
                ascending=[True, True, True, False, True],
            )
            .drop_duplicates(subset=["linea", "direccion", "servicio_label"], keep="first")
            .rename(columns={"match_ref": "match_ref_principal"})
        )
        summary = summary.merge(
            ref_summary[["linea", "direccion", "servicio_label", "match_ref_principal"]],
            how="left", on=["linea", "direccion", "servicio_label"],
        )
    else:
        summary["match_ref_principal"] = np.nan

    return matched_df, summary, stats


# ================================================================
# 19. RESUMEN A NIVEL SERVICIO Y DISTRIBUCIÓN POR TIPO DE PASAJERO
# ================================================================
SERVICE_SUMMARY_COLS = [
    "servicio_label", "hora_salida", "hora_salida_fmt",
    "estacion_origen", "pasajeros_transportados", "max_abordo",
]


def build_service_level_summary(profile_subset: pd.DataFrame, profile_schema: str) -> pd.DataFrame:
    """Resumen por servicio (hora salida, origen, pax, máximo a bordo)."""
    if profile_subset is None or profile_subset.empty:
        return pd.DataFrame(columns=SERVICE_SUMMARY_COLS)

    rows = []
    for srv_label, svc_df in profile_subset.groupby("servicio_label", sort=False):
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

        # Hora de salida: primera entrada del origen
        departure_ts = pd.NaT
        if profile_schema == "transactional":
            if origin_station != "-" and "origen" in svc_df.columns:
                origin_mask = normalize_series(svc_df["origen"]) == normalize_text(origin_station)
                cands = pd.to_datetime(svc_df.loc[origin_mask, "t_entrada_viaje"], errors="coerce").dropna()
                if not cands.empty:
                    departure_ts = cands.min()
            if pd.isna(departure_ts) and "event_time" in profile.columns:
                fallback = pd.to_datetime(profile["event_time"], errors="coerce").dropna()
                if not fallback.empty:
                    departure_ts = fallback.min()
        else:
            ordered = profile.copy()
            if station_order:
                ordered["estacion"] = pd.Categorical(ordered["estacion"], categories=station_order, ordered=True)
                sort_cols = ["estacion"]
                if "event_time" in ordered.columns:
                    sort_cols.append("event_time")
                ordered = ordered.sort_values(sort_cols)
            if not ordered.empty:
                first = ordered.iloc[0]
                for col in ["t_dep_est", "t_arr_est", "event_time"]:
                    if col in ordered.columns:
                        ts = pd.to_datetime(first[col], errors="coerce")
                        if pd.notna(ts):
                            departure_ts = ts
                            break

        pax = float(pd.to_numeric(profile.get("D_bajadas"), errors="coerce").fillna(0).sum()) if "D_bajadas" in profile.columns else 0.0
        max_a = np.nan
        if "L_out_abordo" in profile.columns:
            l_series = pd.to_numeric(profile["L_out_abordo"], errors="coerce").dropna()
            if not l_series.empty:
                max_a = float(l_series.max())

        rows.append({
            "servicio_label": str(srv_label),
            "hora_salida": departure_ts,
            "estacion_origen": origin_station,
            "pasajeros_transportados": pax,
            "max_abordo": max_a,
        })

    if not rows:
        return pd.DataFrame(columns=SERVICE_SUMMARY_COLS)

    summary_df = pd.DataFrame(rows)
    summary_df["hora_salida"] = pd.to_datetime(summary_df["hora_salida"], errors="coerce")
    summary_df = summary_df.sort_values(
        ["hora_salida", "servicio_label"], na_position="last"
    ).reset_index(drop=True)
    summary_df["hora_salida_fmt"] = summary_df["hora_salida"].dt.strftime("%H:%M:%S").fillna("-")
    return summary_df


def _scale_counts_largest_remainder(counts: pd.Series, target_total: int) -> pd.Series:
    """
    Escala 'counts' a un total entero exacto usando el método de mayor residuo.
    Garantiza que la suma de retornos = target_total cuando target_total > 0.
    """
    counts = pd.to_numeric(counts, errors="coerce").fillna(0).astype(float)
    if counts.empty:
        return counts.astype(int)
    total = float(counts.sum())
    target = int(round(float(target_total))) if pd.notna(target_total) else 0
    if total <= 0 or target <= 0:
        return pd.Series(0, index=counts.index, dtype=int)

    raw = counts / total * target
    floors = np.floor(raw).astype(int)
    remainder = int(target - int(floors.sum()))
    if remainder > 0:
        residuals = raw - floors
        order = sorted(
            counts.index.tolist(),
            key=lambda i: (-float(residuals.loc[i]), -float(counts.loc[i])),
        )
        for i in order[:remainder]:
            floors.loc[i] += 1
    elif remainder < 0:
        residuals = raw - floors
        order = sorted(
            counts.index.tolist(),
            key=lambda i: (float(residuals.loc[i]), float(counts.loc[i])),
        )
        for i in order[:abs(remainder)]:
            if floors.loc[i] > 0:
                floors.loc[i] -= 1
    return floors.astype(int)


PASSENGER_DIST_COLS = ["tipo_pasajero", "tx_cruzadas", "porcentaje", "pasajeros_estimados", "tarifa_media"]


def build_passenger_type_distribution(matched_df: pd.DataFrame,
                                      servicio_sel: str,
                                      pasajeros_transportados: float,
                                      linea_sel: str | None = None,
                                      direccion_sel: str | None = None) -> pd.DataFrame:
    """
    Distribución por tipo de pasajero del servicio seleccionado, escalada para
    que la suma cierre en `pasajeros_transportados`. Siempre devuelve los 5
    tipos canónicos (con 0/NaN cuando no hay datos).

    Acepta tanto el resultado del cruce torniquetes×perfil (legacy) como el
    perfil enriquecido directo (recomendado, sin merge).
    """
    if (matched_df is None or matched_df.empty
            or "tipo_pasajero" not in matched_df.columns):
        return pd.DataFrame(columns=PASSENGER_DIST_COLS)

    df = matched_df

    mask = df["servicio_label"].astype(str) == str(servicio_sel)
    if linea_sel is not None and "linea" in df.columns:
        mask &= df["linea"].astype(str).str.strip() == str(linea_sel).strip()
    if direccion_sel is not None and "direccion" in df.columns:
        mask &= df["direccion"].astype(str).str.strip() == str(direccion_sel).strip()
    sel = df[mask].copy()
    if sel.empty:
        return pd.DataFrame(columns=PASSENGER_DIST_COLS)

    sel["tipo_pasajero"] = sel["tipo_pasajero"].fillna("Otros").astype(str).str.strip()
    # Tratar strings vacíos o "nan" literales como Otros
    sel.loc[sel["tipo_pasajero"].isin(["", "nan", "None", "NaN", "NaT"]), "tipo_pasajero"] = "Otros"
    sel.loc[~sel["tipo_pasajero"].isin(PASSENGER_TYPE_ORDER), "tipo_pasajero"] = "Otros"

    if "monto_transaccion" in sel.columns:
        sel["_monto"] = pd.to_numeric(sel["monto_transaccion"], errors="coerce")
    else:
        sel["_monto"] = np.nan

    stats = (
        sel.groupby("tipo_pasajero", as_index=False)
           .agg(tx_cruzadas=("_monto", "size"),
                tarifa_media=("_monto", "mean"))
    )
    if stats.empty:
        return pd.DataFrame(columns=PASSENGER_DIST_COLS)

    total_tx = float(stats["tx_cruzadas"].sum())
    stats["porcentaje"] = (stats["tx_cruzadas"].astype(float) / total_tx * 100.0) if total_tx > 0 else 0.0

    target = 0 if pd.isna(pasajeros_transportados) else int(round(float(pasajeros_transportados)))
    scaled = _scale_counts_largest_remainder(
        stats.set_index("tipo_pasajero")["tx_cruzadas"], target,
    )
    stats["pasajeros_estimados"] = stats["tipo_pasajero"].map(scaled).fillna(0).astype(int)

    base = pd.DataFrame({"tipo_pasajero": PASSENGER_TYPE_ORDER})
    out = base.merge(stats, on="tipo_pasajero", how="left")
    out["tx_cruzadas"] = out["tx_cruzadas"].fillna(0).astype(int)
    out["porcentaje"] = out["porcentaje"].fillna(0.0)
    out["pasajeros_estimados"] = out["pasajeros_estimados"].fillna(0).astype(int)
    return out[PASSENGER_DIST_COLS]


# ================================================================
# 19b. RESUMEN DE TARIFA POR SERVICIO (DESDE PERFIL ENRIQUECIDO)
# ================================================================
def build_service_fare_summary_from_profile(perfil_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula tarifa media, tarifa mediana, recaudación, tx cruzadas y desviación
    DIRECTAMENTE desde el perfil enriquecido (con monto_transaccion ya pegado
    por viaje). Reemplaza match_turnstile_transactions_to_profile cuando el
    perfil ya viene cruzado offline.

    Retorna un DataFrame con las mismas columnas que producía el cruce
    torniquetes×perfil, para mantener compatibilidad con el resto del código.
    """
    empty_cols = [
        "linea", "direccion", "servicio_label", "tx_cruzadas",
        "tarifa_media_aprox", "tarifa_mediana_aprox", "recaudacion_aprox",
        "desviacion_tarifa_aprox", "diff_mediana_min", "match_ref_principal",
    ]
    if (perfil_df is None or perfil_df.empty
            or "monto_transaccion" not in perfil_df.columns):
        return pd.DataFrame(columns=empty_cols)

    df = perfil_df.copy()
    df["monto_transaccion"] = pd.to_numeric(df["monto_transaccion"], errors="coerce")
    df = df.dropna(subset=["monto_transaccion"])
    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    for col in ["linea", "direccion", "servicio_label"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()

    summary = (
        df.groupby(["linea", "direccion", "servicio_label"], as_index=False)
        .agg(
            tx_cruzadas             = ("monto_transaccion", "size"),
            tarifa_media_aprox      = ("monto_transaccion", "mean"),
            tarifa_mediana_aprox    = ("monto_transaccion", "median"),
            recaudacion_aprox       = ("monto_transaccion", "sum"),
            desviacion_tarifa_aprox = ("monto_transaccion", "std"),
        )
    )
    # Columnas que existían en el cruce y conservamos vacías para
    # compatibilidad de schema con el resto del dashboard.
    summary["diff_mediana_min"]    = np.nan
    summary["match_ref_principal"] = "perfil_enriquecido"
    return summary[empty_cols]

# ================================================================
# 20. ENRIQUECIMIENTO CON ITINERARIO
# ================================================================

def infer_itinerary_day_filter(fecha_sel: date) -> str:
    if fecha_sel.weekday() == 5:
        return "sabado"
    if fecha_sel.weekday() == 6:
        return "domingo"
    return "lunes a viernes"


def infer_itinerary_sector(profile_service: str, linea_sel: str) -> str | None:
    if normalize_text(profile_service) != "biotren":
        return None
    line_key = normalize_text(linea_sel).replace(" ", "")
    if line_key == "l2":
        return "CONCEPCIÓN-CORONEL"
    if line_key == "l1":
        return "LAJA-TALCAHUANO"
    return None


def infer_itinerary_sentido(linea_sel: str, direccion_sel: str) -> str | None:
    line_key = normalize_text(linea_sel).replace(" ", "")
    dir_key  = _normalize_direction_key(direccion_sel)
    if line_key == "l2":
        if dir_key == "cw-cc":
            return "Coronel a Concepción"
        if dir_key == "cc-cw":
            return "Concepción a Coronel"
    if line_key == "l1":
        if dir_key == "hq-th":
            return "Laja a Talcahuano"
        if dir_key == "th-hq":
            return "Talcahuano a Laja"
    return None


def enrich_service_summary_with_itinerary(summary_df: pd.DataFrame,
                                          itinerary_summary: pd.DataFrame,
                                          profile_service: str,
                                          linea_sel: str,
                                          dir_sel: str,
                                          fecha_sel: date) -> pd.DataFrame:
    """Completa hora de salida y estación origen usando el itinerario oficial."""
    if summary_df is None or summary_df.empty:
        return summary_df.copy() if summary_df is not None else pd.DataFrame()
    if itinerary_summary is None or itinerary_summary.empty:
        return summary_df.copy()

    enriched = summary_df.copy()
    itin = itinerary_summary.copy()
    itin["servicio_label"]     = itin["servicio_label"].astype(str)
    enriched["servicio_label"] = enriched["servicio_label"].astype(str)

    day_filter = infer_itinerary_day_filter(fecha_sel)
    sector     = infer_itinerary_sector(profile_service, linea_sel)
    sentido    = infer_itinerary_sentido(linea_sel, dir_sel)

    if sector and "sector" in itin.columns:
        itin = itin[normalize_series(itin["sector"]) == normalize_text(sector)].copy()
    if day_filter and "tipo_dia" in itin.columns:
        itin = itin[normalize_series(itin["tipo_dia"]).str.contains(day_filter, regex=False)].copy()
    if sentido and "sentido" in itin.columns:
        temp = itin[normalize_series(itin["sentido"]) == normalize_text(sentido)].copy()
        if not temp.empty:
            itin = temp

    if itin.empty:
        return enriched

    sort_cols = ["servicio_label"]
    if "pagina_pdf" in itin.columns:
        sort_cols.append("pagina_pdf")
    itin = itin.sort_values(sort_cols).drop_duplicates(
        subset=["servicio_label"], keep="first",
    ).copy()

    extra_cols = [c for c in [
        "estacion_origen", "hora_salida_origen_str", "estacion_terminal",
        "hora_llegada_term_str", "tipo_dia", "sentido", "sector",
    ] if c in itin.columns]
    itin_small = itin[["servicio_label"] + extra_cols].rename(columns={
        "estacion_origen":          "it_estacion_origen",
        "hora_salida_origen_str":   "it_hora_salida",
        "estacion_terminal":        "it_estacion_terminal",
        "hora_llegada_term_str":    "it_hora_llegada_term",
        "tipo_dia":                 "it_tipo_dia",
        "sentido":                  "it_sentido",
        "sector":                   "it_sector",
    })

    enriched = enriched.merge(itin_small, how="left", on="servicio_label")

    if "it_estacion_origen" in enriched.columns:
        non_empty = enriched["it_estacion_origen"].fillna("").astype(str).str.strip() != ""
        enriched["estacion_origen"] = enriched["it_estacion_origen"].where(
            non_empty, enriched["estacion_origen"],
        )
    if "it_hora_salida" in enriched.columns:
        base_date = pd.Timestamp(fecha_sel)
        it_ts = pd.to_datetime(
            base_date.strftime("%Y-%m-%d") + " " + enriched["it_hora_salida"].fillna("").astype(str),
            errors="coerce",
        )
        enriched["hora_salida"] = it_ts.where(it_ts.notna(), enriched["hora_salida"])

    enriched["hora_salida"]     = pd.to_datetime(enriched["hora_salida"], errors="coerce")
    enriched["hora_salida_fmt"] = enriched["hora_salida"].dt.strftime("%H:%M:%S").fillna("-")
    enriched = enriched.sort_values(
        ["hora_salida", "servicio_label"], na_position="last",
    ).reset_index(drop=True)
    return enriched


# ================================================================
# 21. ORDEN OPERATIVO DE SERVICIOS Y LABELS
# ================================================================

def infer_service_order_day_filter(fecha_sel: date) -> str:
    return "sabado y domingo" if fecha_sel.weekday() >= 5 else "lunes a viernes"


def apply_service_order_and_labels(summary_df: pd.DataFrame,
                                   order_df: pd.DataFrame,
                                   profile_service: str,
                                   linea_sel: str,
                                   dir_sel: str,
                                   fecha_sel: date) -> pd.DataFrame:
    """Asigna servicio_orden_idx y construye servicio_display_label."""
    if summary_df is None or summary_df.empty:
        return summary_df.copy() if summary_df is not None else pd.DataFrame()

    enriched = summary_df.copy()
    enriched["__input_order"] = np.arange(len(enriched))
    enriched["servicio_label"] = enriched["servicio_label"].astype(str).str.strip()
    enriched["hora_salida"]    = pd.to_datetime(enriched["hora_salida"], errors="coerce")
    enriched["hora_salida_fmt"] = enriched["hora_salida"].dt.strftime("%H:%M:%S").fillna("-")
    enriched["hora_salida_corta"] = enriched["hora_salida_fmt"].astype(str).str.slice(0, 5).replace({"-": "s/h"})
    enriched["estacion_origen"] = enriched["estacion_origen"].fillna("-").astype(str).str.strip().replace({"": "-"})
    enriched["servicio_orden_idx"] = np.nan

    if (order_df is not None and not order_df.empty
            and normalize_text(profile_service) == "biotren"):
        temp = order_df.copy()
        day_filter = infer_service_order_day_filter(fecha_sel)
        temp["tipo_dia_ref_norm"] = normalize_series(temp["tipo_dia_ref"])
        temp["linea_norm"]        = normalize_series(temp["linea"])
        temp["direccion_norm"]    = normalize_series(temp["direccion"])

        temp_day = temp[temp["tipo_dia_ref_norm"].str.contains(day_filter, regex=False, na=False)].copy()
        if temp_day.empty:
            temp_day = temp.copy()

        temp_day = temp_day[temp_day["linea_norm"]     == normalize_text(linea_sel)].copy()
        temp_day = temp_day[temp_day["direccion_norm"] == normalize_text(dir_sel)].copy()

        if not temp_day.empty:
            temp_day["__file_seq"] = np.arange(len(temp_day))
            temp_day = (
                temp_day.sort_values(["orden", "__file_seq"], kind="stable")
                        .drop_duplicates(subset=["servicio_label"], keep="first")
                        .reset_index(drop=True)
            )
            temp_day["servicio_orden_idx"] = np.arange(1, len(temp_day) + 1)
            order_map = temp_day.set_index("servicio_label")["servicio_orden_idx"].to_dict()
            enriched["servicio_orden_idx"] = enriched["servicio_label"].map(order_map)

    # Fallback para servicios no listados en el archivo de orden
    missing = enriched["servicio_orden_idx"].isna()
    if missing.any():
        explicit = pd.to_numeric(enriched["servicio_orden_idx"], errors="coerce").dropna()
        base_n = int(explicit.max()) if not explicit.empty else 0
        fallback_services = (
            enriched.loc[missing, ["servicio_label", "__input_order"]]
                    .drop_duplicates(subset=["servicio_label"], keep="first")
                    .sort_values(["__input_order"], kind="stable")
                    .reset_index(drop=True)
        )
        fallback_map = {
            row["servicio_label"]: base_n + idx + 1
            for idx, (_, row) in enumerate(fallback_services.iterrows())
        }
        enriched.loc[missing, "servicio_orden_idx"] = enriched.loc[missing, "servicio_label"].map(fallback_map)

    enriched["servicio_orden_idx"] = pd.to_numeric(
        enriched["servicio_orden_idx"], errors="coerce",
    ).fillna(999999).astype(int)
    enriched = enriched.sort_values(
        ["servicio_orden_idx", "__input_order"], kind="stable",
    ).reset_index(drop=True)

    enriched["servicio_display_label"] = (
        enriched["servicio_label"].astype(str)
        + " | " + enriched["hora_salida_corta"].astype(str)
        + " | " + enriched["estacion_origen"].astype(str)
    )

    # Desambiguar duplicados
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


# ================================================================
# 22. INDICADORES MENSUALES (EXECUTIVOS)
# ================================================================
CAPACIDAD_REFERENCIA_LINEA = 605.0


def _compute_metric_block(group_df: pd.DataFrame) -> dict:
    """Calcula tarifa media ponderada, ocupación y totales para un grupo."""
    if group_df is None or group_df.empty:
        return {
            "tarifa_media_mensual": np.nan,
            "tasa_ocupacion_mensual": np.nan,
            "servicios_realizados": 0,
            "pasajeros_transportados": 0.0,
            "tx_cruzadas": 0.0,
        }
    tx_sum = float(group_df["_tx"].sum())
    tarifa_simple = group_df["_tarifa"].mean(skipna=True)
    if tx_sum > 0 and pd.notna(tarifa_simple):
        tarifa = float(group_df["_tarifa_x_tx"].sum()) / tx_sum
    else:
        tarifa = float(tarifa_simple) if pd.notna(tarifa_simple) else np.nan
    servicios = int(len(group_df))
    pax = float(group_df["_pax"].sum())
    denom = servicios * float(CAPACIDAD_REFERENCIA_LINEA)
    ocup = (pax / denom * 100.0) if denom > 0 else np.nan
    return {
        "tarifa_media_mensual": tarifa,
        "tasa_ocupacion_mensual": ocup,
        "servicios_realizados": servicios,
        "pasajeros_transportados": pax,
        "tx_cruzadas": tx_sum,
    }


def compute_monthly_executive_metrics(monthly_daily: pd.DataFrame) -> dict:
    """Computa métricas ejecutivas mensuales. Estructura: linea / por_sentido / por_tipo_dia."""
    if monthly_daily is None or monthly_daily.empty:
        return {"linea": {}, "por_sentido": {}, "por_tipo_dia": {}}

    base = monthly_daily.copy()
    base["_tx"]     = pd.to_numeric(base.get("tx_cruzadas"), errors="coerce").fillna(0)
    base["_tarifa"] = pd.to_numeric(base.get("tarifa_media_aprox"), errors="coerce")
    base["_pax"]    = pd.to_numeric(base.get("pasajeros_transportados"), errors="coerce").fillna(0)
    base["_tarifa_x_tx"] = base["_tarifa"].fillna(0) * base["_tx"]

    metrics = {
        "linea": _compute_metric_block(base),
        "por_sentido": {},
        "por_tipo_dia": {},
    }

    for dir_val, g in base.groupby("direccion_ref", sort=False):
        metrics["por_sentido"][str(dir_val)] = _compute_metric_block(g)

    for tipo_dia, g_tipo in base.groupby("tipo_dia", sort=False):
        metrics["por_tipo_dia"][str(tipo_dia)] = {
            "linea": _compute_metric_block(g_tipo),
            "por_sentido": {},
        }
        for dir_val, g_dir in g_tipo.groupby("direccion_ref", sort=False):
            metrics["por_tipo_dia"][str(tipo_dia)]["por_sentido"][str(dir_val)] = _compute_metric_block(g_dir)

    return metrics


@st.cache_data(ttl=600, show_spinner="Calculando promedios mensuales…", max_entries=3)
def build_monthly_profile_tables_cached(profile_srv: str,
                                          data_path_str: str,
                                          month_period: str,
                                          linea_sel: str,
                                          turnstile_status: str) -> tuple[dict, list, dict, pd.DataFrame]:
    """
    Versión cacheada de build_monthly_profile_tables. Recibe SOLO claves
    primitivas (strings) en lugar de DataFrames, evitando que Streamlit tenga
    que hashear DataFrames de 50k+ filas en cada cambio de filtro.

    Internamente carga el slice mensual y los datos auxiliares por su cuenta
    (a través de los caches existentes get_profile_for_month, etc.).
    """
    # Cargar slice mensual desde cache
    try:
        perfil_month, profile_schema = get_profile_for_month(
            profile_srv, data_path_str, month_period,
        )
    except BaseException:
        return {}, [], {"linea": {}, "por_sentido": {}, "por_tipo_dia": {}}, pd.DataFrame()

    if perfil_month is None or perfil_month.empty:
        return {}, [], {"linea": {}, "por_sentido": {}, "por_tipo_dia": {}}, pd.DataFrame()

    # Cargar referencias auxiliares (todas cacheadas)
    try:
        itinerary_summary_df, _, _, _, _ = load_itinerary_reference(data_path_str)
    except BaseException:
        itinerary_summary_df = pd.DataFrame()
    try:
        service_order_df, _, _, _ = load_service_order_reference(data_path_str)
    except BaseException:
        service_order_df = pd.DataFrame()
    try:
        turnstile_df, _, _, _, ts_status = load_turnstile_service_data(profile_srv, data_path_str)
        if not turnstile_status:
            turnstile_status = ts_status
    except BaseException:
        turnstile_df = pd.DataFrame()

    return build_monthly_profile_tables(
        perfil_month, profile_schema, profile_srv, month_period, linea_sel,
        itinerary_summary_df, service_order_df, turnstile_df, turnstile_status,
    )


def _fast_service_summary_enriched(perfil_day_dir: pd.DataFrame) -> pd.DataFrame:
    """
    Fast-path para perfiles enriquecidos: calcula pasajeros transportados,
    máximo a bordo aproximado y hora de salida directamente con groupby,
    SIN reconstruir el perfil servicio por servicio. Reduce la complejidad
    del bucle mensual de O(días×dirs×servicios) reconstrucciones a
    O(días×dirs) groupbys.
    """
    if perfil_day_dir is None or perfil_day_dir.empty:
        return pd.DataFrame(columns=SERVICE_SUMMARY_COLS)

    df = perfil_day_dir.copy()
    df["servicio_label"] = df.get("servicio_label", df.get("servicio_final", pd.Series(dtype=str))).astype(str)
    if "t_entrada_viaje" in df.columns:
        df["t_entrada_viaje"] = pd.to_datetime(df["t_entrada_viaje"], errors="coerce")

    # Agregación por servicio:
    # - pasajeros_transportados = nº de viajes (cada fila es un viaje)
    # - hora_salida = mínima entrada
    # - estación origen = origen más frecuente
    # - max_abordo = aproximamos por el conteo total
    grp = df.groupby("servicio_label", sort=False)
    summary = grp.agg(
        pasajeros_transportados=("origen", "size"),
        hora_salida=("t_entrada_viaje", "min"),
    ).reset_index()

    # Estación origen: la más frecuente como origen
    origen_top = (
        df.groupby(["servicio_label", "origen"], sort=False)
        .size().reset_index(name="n")
        .sort_values(["servicio_label", "n"], ascending=[True, False])
        .drop_duplicates(subset=["servicio_label"], keep="first")
        [["servicio_label", "origen"]]
        .rename(columns={"origen": "estacion_origen"})
    )
    summary = summary.merge(origen_top, on="servicio_label", how="left")
    summary["estacion_origen"] = summary["estacion_origen"].fillna("-").astype(str)

    # Máximo a bordo: aproximación = pasajeros transportados (cota superior;
    # el cálculo exacto requiere reconstrucción de cumsum). En la pestaña
    # mensual esta aproximación es suficiente porque sólo se usa para
    # contexto, no para análisis fino del perfil.
    summary["max_abordo"] = summary["pasajeros_transportados"]

    summary["hora_salida"] = pd.to_datetime(summary["hora_salida"], errors="coerce")
    summary["hora_salida_fmt"] = summary["hora_salida"].dt.strftime("%H:%M:%S").fillna("-")
    summary = summary.sort_values(["hora_salida", "servicio_label"], na_position="last").reset_index(drop=True)
    return summary[SERVICE_SUMMARY_COLS]


def build_monthly_profile_tables(perfil_df: pd.DataFrame,
                                 profile_schema: str,
                                 profile_srv: str,
                                 month_period: str,
                                 linea_sel: str,
                                 itinerary_summary_df: pd.DataFrame,
                                 service_order_df: pd.DataFrame,
                                 turnstile_df: pd.DataFrame,
                                 turnstile_status: str) -> tuple[dict, list, dict, pd.DataFrame]:
    """
    Construye tablas mensuales por tipo_dia x dirección con métricas ejecutivas.
    Retorna: (tablas_dict, directions_list, monthly_metrics_dict, monthly_daily_df)
    El monthly_daily se devuelve para alimentar gráficos adicionales (heatmaps, tendencias).
    """
    if perfil_df is None or perfil_df.empty or not month_period or not linea_sel:
        return {}, [], {"linea": {}, "por_sentido": {}, "por_tipo_dia": {}}, pd.DataFrame()

    fecha_series = pd.to_datetime(perfil_df["fecha"], errors="coerce")
    month_mask = fecha_series.dt.to_period("M").astype(str) == str(month_period)
    perfil_mes = perfil_df.loc[month_mask].copy()
    if perfil_mes.empty:
        return {}, [], {"linea": {}, "por_sentido": {}, "por_tipo_dia": {}}, pd.DataFrame()

    perfil_mes = perfil_mes[perfil_mes["linea"].astype(str).str.strip() == str(linea_sel)].copy()
    if perfil_mes.empty:
        return {}, [], {"linea": {}, "por_sentido": {}, "por_tipo_dia": {}}, pd.DataFrame()

    directions = [
        x for x in list(dict.fromkeys(
            perfil_mes["direccion"].dropna().astype(str).str.strip().tolist()
        )) if x
    ]
    if not directions:
        return {}, [], {"linea": {}, "por_sentido": {}, "por_tipo_dia": {}}, pd.DataFrame()

    fechas_mes = sorted([x for x in perfil_mes["fecha"].dropna().unique().tolist() if pd.notna(x)])
    daily_rows = []

    # Guardrail: si el mes tiene demasiados días con datos masivos, advertir
    # y limitar para evitar OOM. Un mes típico de Biotren tiene ≤31 días.
    if len(fechas_mes) > 35:
        fechas_mes = fechas_mes[-35:]  # Toma los más recientes

    for day_idx, fecha_day in enumerate(fechas_mes):
        perfil_day_all = perfil_mes[perfil_mes["fecha"] == fecha_day].copy()
        if perfil_day_all.empty:
            continue

        # --- CAMINO PREFERENTE: perfil enriquecido (sin merge) ----------
        fare_day_all = pd.DataFrame()
        perfil_is_enriched = (
            "monto_transaccion" in perfil_day_all.columns
            or "tipo_pasajero" in perfil_day_all.columns
        )

        if (normalize_text(profile_srv) == "biotren"
                and profile_schema == "transactional"
                and perfil_is_enriched):
            fare_day_all = build_service_fare_summary_from_profile(perfil_day_all)

        # --- Camino legacy: cruce con torniquetes ---------------------
        elif (normalize_text(profile_srv) == "biotren"
              and profile_schema == "transactional"
              and turnstile_status == "ok"
              and turnstile_df is not None and not turnstile_df.empty):
            turnstile_day = turnstile_df[turnstile_df["fecha"] == fecha_day].copy()
            if not turnstile_day.empty:
                _, fare_day_all, _ = match_turnstile_transactions_to_profile(
                    turnstile_day, perfil_day_all, tolerance_minutes=20,
                )

        for dir_sel in directions:
            perfil_day_dir = perfil_day_all[
                perfil_day_all["direccion"].astype(str).str.strip() == str(dir_sel)
            ].copy()
            if perfil_day_dir.empty:
                continue

            # FAST-PATH para perfil enriquecido: groupby directo en lugar de
            # reconstruir el perfil servicio×servicio. Reduce ~30× el costo
            # del cálculo mensual.
            if perfil_is_enriched and profile_schema == "transactional":
                daily = _fast_service_summary_enriched(perfil_day_dir)
            else:
                daily = build_service_level_summary(perfil_day_dir, profile_schema)

            if daily.empty:
                continue
            daily = enrich_service_summary_with_itinerary(
                daily, itinerary_summary_df, profile_srv, linea_sel, dir_sel, fecha_day,
            )
            daily = apply_service_order_and_labels(
                daily, service_order_df, profile_srv, linea_sel, dir_sel, fecha_day,
            )

            for col in ["tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox",
                        "recaudacion_aprox", "desviacion_tarifa_aprox",
                        "diff_mediana_min", "match_ref_principal"]:
                if col not in daily.columns:
                    daily[col] = np.nan

            if not fare_day_all.empty:
                fare_dir = fare_day_all[
                    (fare_day_all["linea"].astype(str).str.strip()      == str(linea_sel)) &
                    (fare_day_all["direccion"].astype(str).str.strip()  == str(dir_sel))
                ].copy()
                if not fare_dir.empty:
                    drop_cols = [c for c in [
                        "tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox",
                        "recaudacion_aprox", "desviacion_tarifa_aprox",
                        "diff_mediana_min", "match_ref_principal",
                    ] if c in daily.columns]
                    daily = daily.drop(columns=drop_cols, errors="ignore").merge(
                        fare_dir[["servicio_label", "tx_cruzadas", "tarifa_media_aprox",
                                  "tarifa_mediana_aprox", "recaudacion_aprox",
                                  "desviacion_tarifa_aprox", "diff_mediana_min",
                                  "match_ref_principal"]],
                        how="left", on="servicio_label",
                    )

            daily["tarifa_media_aprox"]      = pd.to_numeric(daily.get("tarifa_media_aprox"), errors="coerce")
            daily["pasajeros_transportados"] = pd.to_numeric(daily.get("pasajeros_transportados"), errors="coerce")
            daily["tx_cruzadas"]             = pd.to_numeric(daily.get("tx_cruzadas"), errors="coerce")
            daily["fecha"]         = fecha_day
            daily["tipo_dia"]      = classify_profile_day_type(fecha_day)
            daily["direccion_ref"] = dir_sel
            # Conservar SOLO las columnas necesarias (evitar arrastrar
            # estructuras grandes de daily a través del concat final)
            keep_cols = [
                "servicio_label", "servicio_display_label", "servicio_orden_idx",
                "hora_salida", "hora_salida_fmt", "estacion_origen",
                "pasajeros_transportados", "max_abordo",
                "tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox",
                "recaudacion_aprox", "desviacion_tarifa_aprox", "diff_mediana_min",
                "match_ref_principal", "fecha", "tipo_dia", "direccion_ref",
            ]
            keep_cols = [c for c in keep_cols if c in daily.columns]
            daily_rows.append(daily[keep_cols].copy())

        # Liberar memoria intermedia cada 7 días procesados (≈ 1 vez por semana)
        if (day_idx + 1) % 7 == 0:
            try:
                del perfil_day_all, fare_day_all
            except (NameError, UnboundLocalError):
                pass
            gc.collect()

    if not daily_rows:
        return {}, directions, {"linea": {}, "por_sentido": {}, "por_tipo_dia": {}}, pd.DataFrame()

    monthly_daily = pd.concat(daily_rows, ignore_index=True)
    monthly_metrics = compute_monthly_executive_metrics(monthly_daily)

    result = {}
    for tipo_dia in ["Laboral", "Sábado", "Domingo"]:
        result[tipo_dia] = {}
        temp_tipo = monthly_daily[monthly_daily["tipo_dia"] == tipo_dia].copy()
        for dir_sel in directions:
            temp = temp_tipo[temp_tipo["direccion_ref"].astype(str).str.strip() == str(dir_sel)].copy()
            if temp.empty:
                result[tipo_dia][dir_sel] = pd.DataFrame()
                continue

            # Agregación por servicio: tarifa media ponderada por tx, pax promedio por día
            temp = temp.sort_values(
                ["servicio_orden_idx", "fecha", "servicio_label"], na_position="last",
            )
            if "servicio_display_label" not in temp.columns:
                temp["servicio_display_label"] = temp["servicio_label"].astype(str)

            temp["_tx"]          = pd.to_numeric(temp.get("tx_cruzadas"),           errors="coerce").fillna(0)
            temp["_tarifa"]      = pd.to_numeric(temp.get("tarifa_media_aprox"),    errors="coerce")
            temp["_pax"]         = pd.to_numeric(temp.get("pasajeros_transportados"), errors="coerce")
            temp["_tarifa_x_tx"] = temp["_tarifa"].fillna(0) * temp["_tx"]

            grp = temp.groupby("servicio_label", sort=False)
            agg_df = grp.agg(
                tx_sum                 = ("_tx",                  "sum"),
                tarifa_x_tx_sum        = ("_tarifa_x_tx",         "sum"),
                tarifa_mean            = ("_tarifa",              "mean"),
                pax_mean               = ("_pax",                 "mean"),
                servicio_display_label = ("servicio_display_label", "first"),
            ).reset_index()

            # Tarifa ponderada con manejo seguro de división por cero
            tx_sum = agg_df["tx_sum"].astype(float).to_numpy()
            t_x_tx = agg_df["tarifa_x_tx_sum"].astype(float).to_numpy()
            tarifa_simple = agg_df["tarifa_mean"].astype(float).to_numpy()
            weighted = np.full(len(agg_df), np.nan, dtype=float)
            mask_pos = tx_sum > 0
            weighted[mask_pos] = t_x_tx[mask_pos] / tx_sum[mask_pos]
            has_weight = mask_pos & ~np.isnan(tarifa_simple)
            agg_df["tarifa_media_mes"] = np.where(has_weight, weighted, tarifa_simple)
            agg_df["pasajeros_promedio_mes"] = agg_df["pax_mean"]

            # Orden ya viene del grupby; aseguramos servicio_orden_idx mínimo por servicio
            if "servicio_orden_idx" in temp.columns:
                orden_df = grp["servicio_orden_idx"].min().reset_index()
                orden_df["servicio_orden_idx"] = pd.to_numeric(
                    orden_df["servicio_orden_idx"], errors="coerce",
                )
                agg_df = agg_df.merge(orden_df, on="servicio_label", how="left")
            else:
                agg_df["servicio_orden_idx"] = np.nan

            agg_df["servicio_display_label"] = agg_df["servicio_display_label"].fillna(
                agg_df["servicio_label"],
            ).astype(str)
            result_df = agg_df[[
                "servicio_label", "servicio_display_label", "servicio_orden_idx",
                "pasajeros_promedio_mes", "tarifa_media_mes",
            ]].copy()
            result_df["servicio_orden_idx"] = pd.to_numeric(
                result_df["servicio_orden_idx"], errors="coerce",
            )
            result_df = result_df.sort_values(
                ["servicio_orden_idx", "servicio_label"], kind="stable", na_position="last",
            ).reset_index(drop=True)
            result[tipo_dia][dir_sel] = result_df

    return result, directions, monthly_metrics, monthly_daily

# ================================================================
# 23. GRÁFICOS — KPIs Y EVOLUCIÓN
# ================================================================

def scale_kpi_dataframe_for_display(df: pd.DataFrame, kpi_name: str,
                                    value_columns: tuple = ("valor",)) -> pd.DataFrame:
    """Escala valores fraccionales (≤ 1.5) a porcentaje para KPIs de ocupación."""
    df = df.copy()
    if is_occupancy_rate_kpi(kpi_name):
        for col in value_columns:
            if col in df.columns:
                s = pd.to_numeric(df[col], errors="coerce")
                df[col] = np.where(
                    s.isna(), np.nan,
                    np.where(s.abs() <= 1.5, s * 100.0, s),
                )
    return df


def build_line_chart(df: pd.DataFrame, title: str, color=None, line_dash=None,
                     height: int = 340, unit: str | None = None,
                     kpi_name: str | None = None,
                     boxed_values: bool = True) -> go.Figure:
    """Línea simple con etiquetas de valor sobre cada punto."""
    plot_df = df.copy()
    plot_df["periodo_date"]  = plot_df["periodo"].apply(periodo_to_date)
    plot_df = plot_df.sort_values(["periodo_date", "periodo"])
    plot_df["periodo_label"] = plot_df["periodo"].apply(periodo_to_label)
    category_order = list(dict.fromkeys(plot_df["periodo_label"].dropna().tolist()))
    plot_df["valor_label"] = plot_df["valor"].apply(lambda v: fmt_number(v, unit or "", kpi_name))

    fig = px.line(
        plot_df, x="periodo_label", y="valor", color=color,
        line_dash=line_dash, markers=True, title=title,
    )
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
        annots = []
        for _, row in plot_df.iterrows():
            xshift = 0
            if color and color in plot_df.columns:
                xshift = 10 if len(str(row[color])) % 2 == 0 else -10
            annots.append(dict(
                x=str(row["periodo_label"]), y=row["valor"],
                text=row["valor_label"], showarrow=False, yshift=18, xshift=xshift,
                font=dict(size=PLOT_ANNOTATION_SIZE, color=EFE_BLUE),
                bgcolor="rgba(255,255,255,0.92)", bordercolor=BORDER,
                borderwidth=1, borderpad=3, align="center",
                xref="x", yref="y",
            ))
        if annots:
            fig.update_layout(annotations=annots)
    return fig


def build_trend_line_chart(df: pd.DataFrame, kpi_name: str, unit: str | None,
                           service_name: str) -> go.Figure:
    """Evolución con línea de tendencia y etiquetas."""
    plot_df = df.copy()
    plot_df["periodo_date"]  = plot_df["periodo"].apply(periodo_to_date)
    plot_df = plot_df.dropna(subset=["periodo_date", "valor"]).sort_values("periodo_date")
    plot_df["periodo_label"] = plot_df["periodo"].apply(periodo_to_label)
    if len(plot_df) < 2:
        return build_line_chart(plot_df, f"{kpi_name} — {service_name}", height=370,
                                unit=unit, kpi_name=kpi_name)

    x_num  = np.arange(len(plot_df))
    y_vals = plot_df["valor"].to_numpy(dtype=float)
    coeffs = np.polyfit(x_num, y_vals, 1)
    trend  = np.polyval(coeffs, x_num)
    plot_df["tendencia"]    = trend
    plot_df["valor_label"]  = plot_df["valor"].apply(lambda v: fmt_number(v, unit or "", kpi_name))

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

    annots = []
    for idx, (_, row) in enumerate(plot_df.iterrows()):
        annots.append(dict(
            x=str(row["periodo_label"]), y=row["valor"], text=row["valor_label"],
            showarrow=False, yshift=18 if (idx % 2 == 0) else 30,
            font=dict(size=max(PLOT_ANNOTATION_SIZE, 11), color=EFE_BLUE),
            bgcolor="rgba(255,255,255,0.96)", bordercolor=BORDER,
            borderwidth=1, borderpad=4, align="center",
            xref="x", yref="y",
        ))

    fig.update_layout(
        title=f"{kpi_name} — {service_name} · Tendencia: {direction}",
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20), height=460,
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        annotations=annots,
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=category_order, showgrid=False)
    fig.update_yaxes(title="", gridcolor="#E8EEF4", zeroline=False)
    return fig


# ================================================================
# 24. GRÁFICO PERFIL DE CARGA POR SERVICIO
# ================================================================
def build_perfil_carga_chart(service_df: pd.DataFrame, titulo: str) -> go.Figure:
    """
    Gráfico de barras (suben/bajan) + línea (a bordo).
    CRÍTICO: las annotations.x se pasan SIEMPRE como str para evitar crash
    cuando 'estacion' es Categorical (Plotly no acepta Categorical en
    annotations).
    """
    fig = go.Figure()
    if service_df is None or service_df.empty:
        fig.update_layout(title=titulo, plot_bgcolor=EFE_WHITE,
                          paper_bgcolor=EFE_WHITE, height=580)
        return fig

    plot_df = service_df.copy()
    # Asegurar columna estacion como string puro (sin Categorical)
    plot_df["estacion"] = plot_df["estacion"].astype(str)

    station_order = get_station_order_from_profile(plot_df)
    station_order = [str(s) for s in station_order if s is not None]
    if station_order:
        # Reordenar manualmente; nada de pd.Categorical
        cat_to_pos = {s: i for i, s in enumerate(station_order)}
        plot_df["_pos"] = plot_df["estacion"].map(cat_to_pos).fillna(len(station_order))
        plot_df = plot_df.sort_values("_pos").drop(columns="_pos")

    fig.add_trace(go.Bar(
        x=plot_df["estacion"].tolist(), y=plot_df["B_embarque"].tolist(),
        name="Suben", marker_color=EFE_BLUE,
        hovertemplate="<b>%{x}</b><br>Suben: %{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=plot_df["estacion"].tolist(), y=plot_df["D_bajadas"].tolist(),
        name="Bajan", marker_color=EFE_RED,
        hovertemplate="<b>%{x}</b><br>Bajan: %{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=plot_df["estacion"].tolist(), y=plot_df["L_out_abordo"].tolist(),
        mode="lines+markers", name="A bordo",
        line=dict(color=SUCCESS, width=3), marker=dict(size=8),
        hovertemplate="<b>%{x}</b><br>A bordo: %{y:,.0f}<extra></extra>",
    ))

    # Línea de capacidad
    cap_series = pd.to_numeric(
        plot_df.get("capacidad_tren", pd.Series(dtype=float)), errors="coerce",
    )
    if isinstance(cap_series, pd.Series) and cap_series.notna().any():
        capacidad = float(cap_series.dropna().iloc[0])
        fig.add_trace(go.Scatter(
            x=plot_df["estacion"].tolist(),
            y=[capacidad] * len(plot_df),
            mode="lines", name="Capacidad",
            line=dict(color=TEXT_MUTED, width=2, dash="dash"),
            hovertemplate="Capacidad: %{y:,.0f}<extra></extra>",
        ))

    # Annotations: TODOS los valores x se serializan a str
    abordo_rows = plot_df.dropna(subset=["L_out_abordo"])
    annots = []
    for _, row in abordo_rows.iterrows():
        est = row["estacion"]
        try:
            est_str = str(est) if est is not None else ""
        except Exception:
            est_str = ""
        if not est_str:
            continue
        annots.append(dict(
            x=est_str, y=row["L_out_abordo"],
            text=fmt_pax(row["L_out_abordo"]),
            showarrow=False, yshift=18,
            font=dict(size=PLOT_ANNOTATION_SIZE, color=SUCCESS),
            bgcolor="rgba(255,255,255,0.96)",
            bordercolor=SUCCESS, borderwidth=1, borderpad=3,
            align="center", xref="x", yref="y",
        ))

    fig.update_layout(
        title=titulo,
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20),
        height=580, barmode="group",
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        annotations=annots,
    )
    fig.update_xaxes(
        title="", tickangle=-90,
        categoryorder="array",
        categoryarray=station_order if station_order else None,
    )
    fig.update_yaxes(title="Pasajeros", tickfont=dict(size=PLOT_FONT_SIZE))
    return fig


# ================================================================
# 24b. SATURACIÓN POR TRAMO Y COMPARATIVO VS PROMEDIO
# ================================================================
def compute_saturation_metrics(profile_df: pd.DataFrame,
                                capacidad_referencia: float = 605.0) -> dict:
    """
    Calcula métricas de saturación por tramo:
      - Tramos sobre capacidad
      - Total de tramos
      - Pico de ocupación (%)
      - Tramo de pico
      - Ocupación media
    """
    empty = {
        "tramos_sobre": 0, "total_tramos": 0, "pct_recorrido_saturado": 0.0,
        "pico_ocupacion_pct": np.nan, "tramo_pico": "-",
        "ocupacion_media_pct": np.nan,
    }
    if profile_df is None or profile_df.empty:
        return empty
    if "L_out_abordo" not in profile_df.columns:
        return empty

    cap = float(capacidad_referencia) if capacidad_referencia and capacidad_referencia > 0 else 605.0
    if "capacidad_tren" in profile_df.columns:
        cap_s = pd.to_numeric(profile_df["capacidad_tren"], errors="coerce").dropna()
        if not cap_s.empty:
            cap = float(cap_s.iloc[0])

    abordo = pd.to_numeric(profile_df["L_out_abordo"], errors="coerce").fillna(0).astype(float)
    if abordo.empty:
        return empty

    ocupacion_pct = abordo / cap * 100.0
    total = int((ocupacion_pct > 0).sum())
    if total == 0:
        return empty
    sobre = int((ocupacion_pct > 100).sum())

    pico_idx = abordo.idxmax()
    pico = float(ocupacion_pct.loc[pico_idx])
    media = float(ocupacion_pct[ocupacion_pct > 0].mean())

    estaciones = profile_df["estacion"].astype(str).tolist()
    pos_pico = profile_df.index.get_loc(pico_idx)
    tramo_pico = "-"
    if 0 <= pos_pico < len(estaciones):
        if pos_pico < len(estaciones) - 1:
            tramo_pico = f"{estaciones[pos_pico]} → {estaciones[pos_pico + 1]}"
        elif pos_pico > 0:
            tramo_pico = f"{estaciones[pos_pico - 1]} → {estaciones[pos_pico]}"

    return {
        "tramos_sobre":              sobre,
        "total_tramos":              total,
        "pct_recorrido_saturado":    (sobre / total * 100.0) if total > 0 else 0.0,
        "pico_ocupacion_pct":        pico,
        "tramo_pico":                tramo_pico,
        "ocupacion_media_pct":       media,
    }


def render_saturation_panel(saturation_metrics: dict) -> None:
    """Panel compacto con métricas de saturación del servicio."""
    m = saturation_metrics or {}
    tramos_sobre = int(m.get("tramos_sobre", 0))
    total = int(m.get("total_tramos", 0))
    pct = float(m.get("pct_recorrido_saturado", 0.0))
    pico = m.get("pico_ocupacion_pct")
    tramo_pico = m.get("tramo_pico", "-")
    ocup_media = m.get("ocupacion_media_pct")

    if total == 0:
        return

    # Color según severidad
    if pct >= 30:
        bar_color = DANGER
        verdict = "Crítico"
    elif pct >= 10:
        bar_color = WARNING
        verdict = "Atención"
    elif pct > 0:
        bar_color = WARNING
        verdict = "Puntual"
    else:
        bar_color = SUCCESS
        verdict = "Sin saturación"

    pico_str = f"{pico:.0f}%" if pd.notna(pico) else "-"
    media_str = f"{ocup_media:.0f}%" if pd.notna(ocup_media) else "-"

    html = (
        f"<div class='efe-summary-row'>"
        f"<div class='efe-summary-card' style='border-left: 4px solid {bar_color};'>"
        f"<div class='efe-summary-label'>Tramos sobre capacidad</div>"
        f"<div class='efe-summary-value'>{tramos_sobre} / {total}</div>"
        f"<div class='efe-summary-sub'>{pct:.0f}% del recorrido — {verdict}</div>"
        f"</div>"
        f"<div class='efe-summary-card'>"
        f"<div class='efe-summary-label'>Pico de ocupación</div>"
        f"<div class='efe-summary-value'>{pico_str}</div>"
        f"<div class='efe-summary-sub'>{tramo_pico}</div>"
        f"</div>"
        f"<div class='efe-summary-card'>"
        f"<div class='efe-summary-label'>Ocupación media</div>"
        f"<div class='efe-summary-value'>{media_str}</div>"
        f"<div class='efe-summary-sub'>Promedio sobre tramos con flujo</div>"
        f"</div>"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ================================================================
# 24c. COMPARATIVO HOY vs PROMEDIO DEL TIPO DE DÍA
# ================================================================
def build_perfil_comparativo_chart(service_df_today: pd.DataFrame,
                                    avg_by_station: pd.DataFrame | None,
                                    titulo: str,
                                    tipo_dia_label: str = "tipo de día") -> go.Figure:
    """
    Gráfico de perfil con comparativo del promedio del tipo de día.
    Muestra la línea 'A bordo (hoy)' contra 'A bordo (promedio)'.
    """
    fig = build_perfil_carga_chart(service_df_today, titulo)
    if avg_by_station is None or avg_by_station.empty:
        return fig

    avg = avg_by_station.copy()
    if "estacion" not in avg.columns or "L_out_abordo_avg" not in avg.columns:
        return fig

    plot_df = service_df_today.copy()
    plot_df["estacion"] = plot_df["estacion"].astype(str)
    avg["estacion"] = avg["estacion"].astype(str)

    # Alinear por estación; estaciones ausentes en hoy se omiten
    merged = plot_df[["estacion"]].merge(
        avg[["estacion", "L_out_abordo_avg"]], on="estacion", how="left",
    )
    fig.add_trace(go.Scatter(
        x=merged["estacion"].tolist(),
        y=merged["L_out_abordo_avg"].tolist(),
        mode="lines+markers",
        name=f"A bordo (prom. {tipo_dia_label})",
        line=dict(color=EFE_BLUE, width=2, dash="dot"),
        marker=dict(size=6, symbol="circle-open"),
        hovertemplate="<b>%{x}</b><br>Promedio: %{y:,.0f}<extra></extra>",
        opacity=0.85,
    ))
    return fig


def compute_avg_profile_by_day_type(perfil_df: pd.DataFrame,
                                     linea: str, direccion: str,
                                     fecha_ref: date,
                                     month_period: str | None = None) -> pd.DataFrame:
    """
    Calcula el perfil PROMEDIO por estación para todos los días del mismo
    tipo (Laboral/Sábado/Domingo) que la fecha de referencia.
    Devuelve DataFrame con columnas: estacion, L_out_abordo_avg, B_embarque_avg, D_bajadas_avg.
    """
    if perfil_df is None or perfil_df.empty:
        return pd.DataFrame()

    tipo_ref = classify_profile_day_type(fecha_ref)
    if not tipo_ref:
        return pd.DataFrame()

    df = perfil_df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    if month_period:
        df["_periodo"] = pd.to_datetime(df["fecha"], errors="coerce").dt.to_period("M").astype(str)
        df = df[df["_periodo"] == str(month_period)]
    df = df[df["linea"].astype(str) == str(linea)]
    df = df[df["direccion"].astype(str) == str(direccion)]
    if df.empty:
        return pd.DataFrame()

    df["_tipo"] = df["fecha"].apply(classify_profile_day_type)
    df = df[df["_tipo"] == tipo_ref]
    df = df[df["fecha"] != fecha_ref]  # Excluir el día de referencia
    if df.empty:
        return pd.DataFrame()

    schema_local = perfil_df.attrs.get("profile_schema", "aggregated")

    rows_per_day = []
    for fecha_day, day_df in df.groupby("fecha"):
        if schema_local == "transactional":
            for srv_label, svc_df in day_df.groupby("servicio_label", sort=False):
                profile = build_transactional_service_profile(svc_df)
                if profile.empty:
                    continue
                profile["fecha"] = fecha_day
                rows_per_day.append(profile[["estacion", "B_embarque", "D_bajadas",
                                              "L_in_abordo", "L_out_abordo", "fecha"]])
        else:
            cols = [c for c in ["estacion", "B_embarque", "D_bajadas",
                                "L_in_abordo", "L_out_abordo"] if c in day_df.columns]
            if not cols:
                continue
            tmp = day_df[cols].copy()
            tmp["fecha"] = fecha_day
            rows_per_day.append(tmp)

    if not rows_per_day:
        return pd.DataFrame()

    all_days = pd.concat(rows_per_day, ignore_index=True)
    avg = (
        all_days.groupby("estacion", as_index=False)
        .agg(
            L_out_abordo_avg=("L_out_abordo", "mean"),
            B_embarque_avg=("B_embarque", "mean"),
            D_bajadas_avg=("D_bajadas", "mean"),
        )
    )
    return avg



# ================================================================
# 24f. TENDENCIA DIARIA DE PASAJEROS DEL MES
# ================================================================
def build_monthly_daily_trend_chart(monthly_daily: pd.DataFrame,
                                     title: str = "Pasajeros por día del mes") -> go.Figure | None:
    """
    Línea con pax totales por día, marcando con color distinto los fines de
    semana. Permite detectar picos atípicos a lo largo del mes.
    """
    if monthly_daily is None or monthly_daily.empty:
        return None
    if "fecha" not in monthly_daily.columns or "pasajeros_transportados" not in monthly_daily.columns:
        return None

    df = monthly_daily.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    df = df.dropna(subset=["fecha"])
    if df.empty:
        return None

    daily = df.groupby("fecha", as_index=False)["pasajeros_transportados"].sum()
    daily = daily.sort_values("fecha")
    daily["weekday"] = daily["fecha"].apply(lambda d: pd.Timestamp(d).weekday())
    daily["tipo_dia"] = daily["weekday"].apply(
        lambda wd: "Domingo" if wd == 6 else ("Sábado" if wd == 5 else "Laboral")
    )
    daily["fecha_label"] = daily["fecha"].apply(
        lambda d: pd.Timestamp(d).strftime("%d-%m")
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["fecha_label"].tolist(),
        y=daily["pasajeros_transportados"].tolist(),
        mode="lines+markers",
        name="Pasajeros del día",
        line=dict(color=EFE_BLUE, width=2),
        marker=dict(
            size=10,
            color=daily["tipo_dia"].map({
                "Laboral": EFE_BLUE, "Sábado": WARNING, "Domingo": EFE_RED,
            }).tolist(),
            line=dict(color="white", width=1),
        ),
        customdata=daily[["tipo_dia"]].values,
        hovertemplate="<b>%{x}</b><br>%{customdata[0]}<br>Pax: %{y:,.0f}<extra></extra>",
    ))

    # Línea de promedio
    avg = float(daily["pasajeros_transportados"].mean())
    fig.add_hline(
        y=avg, line_dash="dash", line_color=TEXT_MUTED,
        annotation_text=f"Promedio: {avg:,.0f}",
        annotation_position="top right",
    )

    fig.update_layout(
        title=title,
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=50, b=20), height=340,
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        showlegend=False, hovermode="x unified",
    )
    fig.update_xaxes(title="", tickangle=-90)
    fig.update_yaxes(title="Pasajeros transportados")
    return fig


def build_service_transport_chart(summary_df: pd.DataFrame, title: str) -> go.Figure:
    """Barras de pasajeros transportados por servicio."""
    fig = go.Figure()
    if summary_df is None or summary_df.empty:
        fig.update_layout(title=title, plot_bgcolor=EFE_WHITE,
                          paper_bgcolor=EFE_WHITE, height=430)
        return fig

    plot_df = summary_df.copy()
    plot_df["servicio_label"]   = plot_df["servicio_label"].astype(str).str.strip()
    plot_df["hora_salida_fmt"]  = plot_df["hora_salida_fmt"].fillna("-").astype(str)
    plot_df["estacion_origen"]  = plot_df["estacion_origen"].fillna("-").astype(str)

    if "servicio_display_label" not in plot_df.columns:
        plot_df["hora_salida_corta"] = plot_df["hora_salida_fmt"].str.slice(0, 5)
        plot_df["servicio_display_label"] = (
            plot_df["servicio_label"] + " | "
            + plot_df["hora_salida_corta"].replace({"-": "s/h"}) + " | "
            + plot_df["estacion_origen"]
        )

    if "servicio_orden_idx" in plot_df.columns:
        plot_df = plot_df.sort_values(
            ["servicio_orden_idx", "servicio_label"],
            kind="stable", na_position="last",
        ).reset_index(drop=True)

    plot_df["servicio_display_label"] = plot_df["servicio_display_label"].astype(str)
    service_order = plot_df["servicio_display_label"].tolist()

    def _fmt_pax_series(s):
        s = pd.to_numeric(s, errors="coerce")
        return s.apply(lambda v: f"{float(v):,.0f}".replace(",", ".") if pd.notna(v) else "-")

    def _fmt_clp_series(s):
        s = pd.to_numeric(s, errors="coerce")
        return s.apply(lambda v: f"$ {v:,.0f}".replace(",", ".") if pd.notna(v) else "-")

    plot_df["pasajeros_label"]    = _fmt_pax_series(plot_df["pasajeros_transportados"])
    plot_df["max_abordo_label"]   = _fmt_pax_series(plot_df["max_abordo"])
    plot_df["tarifa_media_label"] = _fmt_clp_series(plot_df.get("tarifa_media_aprox", pd.Series(dtype=float)))
    plot_df["recaudacion_label"]  = _fmt_clp_series(plot_df.get("recaudacion_aprox",  pd.Series(dtype=float)))
    plot_df["tx_cruzadas_label"]  = _fmt_pax_series(plot_df.get("tx_cruzadas",        pd.Series(dtype=float)))

    fig.add_trace(go.Bar(
        x=plot_df["servicio_display_label"].tolist(),
        y=plot_df["pasajeros_transportados"].tolist(),
        marker_color=EFE_BLUE,
        text=plot_df["pasajeros_label"].tolist(),
        textposition="outside",
        customdata=plot_df[[
            "servicio_label", "hora_salida_fmt", "estacion_origen",
            "max_abordo_label", "tarifa_media_label",
            "recaudacion_label", "tx_cruzadas_label",
        ]].values,
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
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20), height=520,
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        showlegend=False,
    )
    fig.update_xaxes(
        title="Servicio | Hora de salida | Estación origen",
        tickangle=-90, tickfont=dict(size=PLOT_FONT_SIZE),
        categoryorder="array", categoryarray=service_order,
    )
    fig.update_yaxes(title="Pasajeros transportados", tickfont=dict(size=PLOT_FONT_SIZE))
    return fig


# ================================================================
# 25. MAPA DE ESTACIONES Y BUBBLE MAPS
# ================================================================
def compute_map_bounds(df_map: pd.DataFrame) -> dict:
    lat_min = float(df_map["latitud"].min())
    lat_max = float(df_map["latitud"].max())
    lon_min = float(df_map["longitud"].min())
    lon_max = float(df_map["longitud"].max())
    lat_pad = max((lat_max - lat_min) * 0.18, 0.015)
    lon_pad = max((lon_max - lon_min) * 0.65, 0.04)
    return dict(west=lon_min - lon_pad, east=lon_max + lon_pad,
                south=lat_min - lat_pad, north=lat_max + lat_pad)


def prepare_od_station_reference(service_name: str, od_subset: pd.DataFrame,
                                 stations_df: pd.DataFrame) -> pd.DataFrame:
    """Subconjunto de estaciones del servicio con coordenadas válidas."""
    if stations_df is None or stations_df.empty or "estacion" not in stations_df.columns:
        return pd.DataFrame()

    ref = stations_df.copy()
    if "activa" in ref.columns:
        ref = ref[ref["activa"] == 1].copy()
    if "servicio" in ref.columns:
        ref = ref[ref["servicio"].astype(str) == str(service_name)].copy()

    ref["station_key"] = normalize_series(ref["estacion"])
    ref["latitud"]  = pd.to_numeric(ref["latitud"],  errors="coerce")
    ref["longitud"] = pd.to_numeric(ref["longitud"], errors="coerce")
    ref = ref.dropna(subset=["latitud", "longitud"]).copy()

    if od_subset is not None and not od_subset.empty:
        od_keys = set(
            normalize_series(od_subset["origen"].dropna().astype(str)).tolist() +
            normalize_series(od_subset["destino"].dropna().astype(str)).tolist()
        )
        ref = ref[ref["station_key"].isin(od_keys)].copy()

    return ref.drop_duplicates(subset=["station_key"]).copy()


def build_station_map(valid_map_df: pd.DataFrame) -> go.Figure:
    """Mapa de afluencia por estación."""
    fig = go.Figure()
    if valid_map_df is None or valid_map_df.empty:
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=520)
        return fig

    plot_df = valid_map_df.copy()
    plot_df["latitud"]  = pd.to_numeric(plot_df["latitud"],  errors="coerce")
    plot_df["longitud"] = pd.to_numeric(plot_df["longitud"], errors="coerce")
    plot_df = plot_df.dropna(subset=["latitud", "longitud"]).copy()
    if plot_df.empty:
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=520)
        return fig

    plot_df["label_mapa"]    = plot_df["estacion"].fillna("").astype(str).str.strip()
    plot_df["entradas"]      = pd.to_numeric(plot_df.get("entradas"),      errors="coerce").fillna(0)
    plot_df["meta_entradas"] = pd.to_numeric(plot_df.get("meta_entradas"), errors="coerce")

    afluencia = plot_df["entradas"]
    if len(afluencia) > 1 and float(afluencia.max()) > float(afluencia.min()):
        plot_df["marker_size"] = 10 + (
            (afluencia - afluencia.min()) /
            (afluencia.max() - afluencia.min())
        ) * 18
    else:
        plot_df["marker_size"] = 14

    bounds = compute_map_bounds(plot_df)

    fig.add_trace(go.Scattermap(
        lat=plot_df["latitud"].astype(float).tolist(),
        lon=plot_df["longitud"].astype(float).tolist(),
        mode="markers+text",
        text=plot_df["label_mapa"].tolist(),
        textposition="top right",
        textfont=dict(size=13, color=EFE_BLUE, family="Arial, sans-serif"),
        marker=dict(size=plot_df["marker_size"].tolist(), color=EFE_BLUE,
                    opacity=0.88, sizemode="diameter"),
        customdata=plot_df[["estacion", "entradas", "meta_entradas"]].fillna("").values,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Afluencia: %{customdata[1]:,.0f}<br>"
            "Meta: %{customdata[2]:,.0f}<extra></extra>"
        ),
        showlegend=False,
    ))
    fig.update_layout(
        map=dict(
            style="white-bg",
            layers=[dict(
                sourcetype="raster",
                source=["https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"],
                below="traces",
            )],
            bounds=bounds,
        ),
        margin=dict(l=0, r=0, t=0, b=0), height=520, showlegend=False,
    )
    return fig


# ================================================================
# 26. GRÁFICOS OD POR ESTACIÓN (BARRAS, BURBUJAS, FLUJO)
# ================================================================
def build_station_flow_chart(flow_df: pd.DataFrame, bucket_order: list,
                             station_name: str, granularity: str) -> go.Figure:
    """Entradas/salidas por bloque horario para una estación."""
    fig = go.Figure()
    if flow_df is None or flow_df.empty:
        fig.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, height=430)
        return fig

    plot_df = flow_df.copy()
    plot_df["bucket"] = plot_df["bucket"].astype(str)
    bucket_order = [str(b) for b in (bucket_order or [])]
    if bucket_order:
        cat_pos = {b: i for i, b in enumerate(bucket_order)}
        plot_df["_pos"] = plot_df["bucket"].map(cat_pos).fillna(len(bucket_order))
        plot_df = plot_df.sort_values("_pos").drop(columns="_pos")

    for tipo, color in [("Entradas", EFE_BLUE), ("Salidas", EFE_RED)]:
        temp = plot_df[plot_df["tipo"] == tipo]
        fig.add_trace(go.Bar(
            x=temp["bucket"].tolist(), y=temp["cantidad"].tolist(), name=tipo,
            marker_color=color,
            hovertemplate=f"<b>%{{x}}</b><br>{tipo}: %{{y:,.0f}}<extra></extra>",
        ))

    total_temp = plot_df.groupby("bucket", as_index=False)["cantidad"].sum()
    if bucket_order:
        cat_pos = {b: i for i, b in enumerate(bucket_order)}
        total_temp["_pos"] = total_temp["bucket"].map(cat_pos).fillna(len(bucket_order))
        total_temp = total_temp.sort_values("_pos").drop(columns="_pos")

    fig.add_trace(go.Scatter(
        x=total_temp["bucket"].tolist(), y=total_temp["cantidad"].tolist(),
        mode="lines+markers", name="Total",
        line=dict(color=SUCCESS, width=3), marker=dict(size=8),
        hovertemplate="<b>%{x}</b><br>Total: %{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title=f"{station_name} | {granularity}",
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20), height=430, barmode="group",
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                     categoryarray=bucket_order if bucket_order else None)
    fig.update_yaxes(title="Transacciones")
    return fig


def build_od_station_bar_chart(flow_df: pd.DataFrame, category_col: str,
                               station_ref: pd.DataFrame, title: str,
                               bar_color: str) -> go.Figure | None:
    """Barras Pareto por estación destino/origen."""
    if flow_df is None or flow_df.empty:
        return None

    plot_df = flow_df.copy()
    plot_df[category_col] = plot_df[category_col].fillna("").astype(str).str.strip()
    plot_df = plot_df[plot_df[category_col] != ""].copy()
    if plot_df.empty:
        return None

    plot_df = plot_df.sort_values(["viajes", category_col], ascending=[False, True]).reset_index(drop=True)
    station_order = plot_df[category_col].astype(str).tolist()
    total = float(plot_df["viajes"].sum()) if not plot_df.empty else 0.0
    plot_df["participacion"] = np.where(total > 0, plot_df["viajes"] / total * 100, 0.0)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=plot_df[category_col].tolist(),
        y=plot_df["viajes"].tolist(),
        marker_color=bar_color,
        hovertemplate="<b>%{x}</b><br>Viajes: %{y:,.0f}<br>Participación: %{customdata:.1f}%<extra></extra>",
        customdata=plot_df["participacion"].tolist(),
        name="Viajes",
    ))
    fig.update_layout(
        title=title,
        plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=50, b=20), height=340,
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
        showlegend=False,
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array", categoryarray=station_order)
    fig.update_yaxes(title="Viajes")
    return fig


def build_od_bubble_map(flow_df: pd.DataFrame, category_col: str,
                        station_ref: pd.DataFrame, selected_station: str,
                        title_text: str, bubble_color: str) -> go.Figure | None:
    """Mapa de burbujas con destinos/orígenes desde la estación seleccionada."""
    if station_ref is None or station_ref.empty:
        return None
    if flow_df is None:
        flow_df = pd.DataFrame(columns=[category_col, "viajes"])

    ref = station_ref.copy()
    ref["station_key"] = ref["station_key"].astype(str)
    selected_key = normalize_text(selected_station)
    selected = ref[ref["station_key"] == selected_key]
    if selected.empty:
        return None
    sel_row = selected.iloc[0]

    plot_df = flow_df.copy()
    if category_col not in plot_df.columns:
        plot_df[category_col] = []
    if "viajes" not in plot_df.columns:
        plot_df["viajes"] = []

    plot_df["station_key"] = (
        normalize_series(plot_df[category_col]) if not plot_df.empty else pd.Series(dtype=str)
    )
    plot_df = plot_df.merge(
        ref[["station_key", "estacion", "latitud", "longitud"]],
        how="left", on="station_key", suffixes=("", "_ref"),
    )
    plot_df = plot_df.dropna(subset=["latitud", "longitud"]).copy()

    # OPTIMIZACIÓN MEMORIA: limitar el bubble map a las 15 estaciones más
    # relevantes. Plotly 6 con muchos marcadores en `Scattermap` consume
    # gran cantidad de memoria por trace, lo cual contribuye al OOM en
    # Streamlit Cloud al navegar entre páginas.
    if len(plot_df) > 15:
        plot_df = plot_df.nlargest(15, "viajes").copy()

    if not plot_df.empty and float(plot_df["viajes"].max()) > float(plot_df["viajes"].min()):
        plot_df["marker_size"] = 12 + (
            (plot_df["viajes"] - plot_df["viajes"].min()) /
            (plot_df["viajes"].max() - plot_df["viajes"].min())
        ) * 20
    else:
        plot_df["marker_size"] = 16 if not plot_df.empty else pd.Series(dtype=float)

    points = pd.concat([
        pd.DataFrame([{
            "estacion": selected_station,
            "latitud":  float(sel_row["latitud"]),
            "longitud": float(sel_row["longitud"]),
        }]),
        plot_df[["estacion", "latitud", "longitud"]] if not plot_df.empty
        else pd.DataFrame(columns=["estacion", "latitud", "longitud"]),
    ], ignore_index=True).drop_duplicates(subset=["estacion"])

    lat_min = float(points["latitud"].min());  lat_max = float(points["latitud"].max())
    lon_min = float(points["longitud"].min()); lon_max = float(points["longitud"].max())
    lat_pad = max((lat_max - lat_min) * 0.18, 0.015)
    lon_pad = max((lon_max - lon_min) * 0.65, 0.04)

    fig = go.Figure()
    if not plot_df.empty:
        fig.add_trace(go.Scattermap(
            lat=plot_df["latitud"].astype(float).tolist(),
            lon=plot_df["longitud"].astype(float).tolist(),
            mode="markers+text",
            text=plot_df["estacion"].astype(str).tolist(),
            textposition="top right",
            textfont=dict(size=13, color=EFE_BLUE),
            marker=dict(size=plot_df["marker_size"].tolist(), color=bubble_color,
                        opacity=0.72, sizemode="diameter"),
            customdata=plot_df[["estacion", "viajes"]].values,
            hovertemplate="<b>%{customdata[0]}</b><br>Viajes: %{customdata[1]:,.0f}<extra></extra>",
            showlegend=False,
        ))

    fig.add_trace(go.Scattermap(
        lat=[float(sel_row["latitud"])],
        lon=[float(sel_row["longitud"])],
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
        map=dict(
            style="white-bg",
            layers=[dict(
                sourcetype="raster",
                source=["https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"],
                below="traces",
            )],
            bounds=dict(
                west=lon_min - lon_pad, east=lon_max + lon_pad,
                south=lat_min - lat_pad, north=lat_max + lat_pad,
            ),
        ),
        margin=dict(l=0, r=0, t=45, b=0), height=460,
        paper_bgcolor=EFE_WHITE,
        font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
        title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
    )
    return fig


# ================================================================
# 27. HELPERS DE TIEMPO/BUCKETS PARA OD
# ================================================================
def get_time_bucket_series(timestamp_series: pd.Series, granularity: str) -> pd.Series:
    """Asigna a cada timestamp un bucket horario según granularidad."""
    ts = pd.to_datetime(timestamp_series, errors="coerce")
    if granularity == "Periodos operacionales":
        h = ts.dt.hour + ts.dt.minute / 60.0
        labels = np.select(
            [(h >= 6) & (h < 9), (h >= 9) & (h < 17), (h >= 17) & (h < 21)],
            ["Punta Mañana", "Valle", "Punta Tarde"],
            default="Fuera de periodo",
        )
        return pd.Series(np.where(ts.isna(), None, labels), index=ts.index, dtype=object)
    hours = 1 if granularity == "Bloques de 1 hora" else 2
    start = ts.dt.floor(f"{hours}h")
    end   = start + pd.Timedelta(hours=hours)
    label = start.dt.strftime("%H:%M") + "-" + end.dt.strftime("%H:%M")
    return label.where(start.notna(), None)


def get_bucket_order(values: list, granularity: str) -> list:
    """Retorna lista ordenada de buckets vistos."""
    vals = [v for v in values if pd.notna(v)]
    if granularity == "Periodos operacionales":
        ordered = ["Punta Mañana", "Valle", "Punta Tarde", "Fuera de periodo"]
        return [v for v in ordered if v in set(vals)]

    def key_fn(label):
        try:
            hh, mm = str(label).split("-")[0].split(":")
            return int(hh), int(mm)
        except (ValueError, IndexError):
            return (99, 99)

    return sorted(list(dict.fromkeys(vals)), key=key_fn)

# ================================================================
# 28. RENDERER — KPIs por Servicio (vista por servicio + evolución)
# ================================================================
def render_resumen_ejecutivo(kpis: pd.DataFrame, kpis_hist: pd.DataFrame,
                             servicios_lista: list, periodos: list,
                             default_period_index: int,
                             target_service: str | None = None):
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    top_title_col, top_period_col = st.columns([4.5, 1.2])
    with top_title_col:
        st.markdown("<div class='section-title'>KPIs por Servicio</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='section-subtitle'>KPIs del período por servicio "
            "y evolución histórica del indicador seleccionado.</div>",
            unsafe_allow_html=True,
        )
    with top_period_col:
        period_key = f"periodo_kpi_selector_{target_service or 'general'}"
        periodo_sel = st.selectbox(
            "Período de análisis", options=periodos,
            index=default_period_index, key=period_key,
        )

    kpis_periodo = kpis[kpis["periodo"].astype(str) == str(periodo_sel)].copy()
    servicios_con_datos = sorted(kpis_periodo["servicio"].dropna().astype(str).unique().tolist())
    if target_service:
        servicios_con_datos = [s for s in servicios_con_datos if s == str(target_service)]
    if kpis_periodo.empty or not servicios_con_datos:
        st.warning("No existen KPIs para los filtros seleccionados.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    resumen_srv = str(target_service) if target_service else option_selector(
        "Servicio visible", servicios_con_datos, key="resumen_servicio_selector",
        default=servicios_con_datos[0], horizontal=True,
    )

    servicio_df = kpis_periodo[kpis_periodo["servicio"].astype(str) == str(resumen_srv)].copy()
    if "orden" in servicio_df.columns:
        servicio_df = servicio_df.sort_values(["orden", "nombre", "categoria"])
    else:
        servicio_df = servicio_df.sort_values(["nombre", "categoria"])

    st.markdown(f"<div class='service-title'>{resumen_srv}</div>", unsafe_allow_html=True)

    # Narrativa automática del período para este servicio
    narrative = generate_narrative_kpis(kpis_periodo, servicio=resumen_srv)
    render_narrative_box(narrative, title="📋 Lectura del período")

    if not servicio_df.empty:
        cols_per_row = 3 if len(servicio_df) >= 3 else max(1, len(servicio_df))
        for i in range(0, len(servicio_df), cols_per_row):
            row_df = servicio_df.iloc[i:i + cols_per_row]
            cols = st.columns(cols_per_row)
            for idx, (_, row) in enumerate(row_df.iterrows()):
                with cols[idx]:
                    # Sparkline: histórico del KPI para este servicio
                    hist = kpis_hist[
                        (kpis_hist["servicio"].astype(str) == str(resumen_srv))
                        & (kpis_hist["nombre"].astype(str) == str(row["nombre"]))
                    ].copy()
                    spark_values = []
                    streak_text = None
                    yoy_text = None
                    hist_scaled_for_cumul = pd.DataFrame()
                    if not hist.empty:
                        hist_scaled = scale_kpi_dataframe_for_display(
                            hist, str(row["nombre"]), ("valor", "meta"),
                        )
                        hist_scaled_for_cumul = hist_scaled.copy()
                        hist_scaled["periodo_date"] = hist_scaled["periodo"].apply(periodo_to_date)
                        hist_scaled = hist_scaled.dropna(subset=["periodo_date", "valor"])
                        hist_scaled = hist_scaled.sort_values("periodo_date").tail(12)
                        spark_values = pd.to_numeric(hist_scaled["valor"], errors="coerce").dropna().tolist()
                        streak_text = compute_kpi_streak(hist_scaled, str(row["nombre"]))
                        # Comparación con mes del año anterior
                        yoy_text = compute_yoy_comparison(
                            hist_scaled_for_cumul,
                            str(row.get("periodo", "")),
                            str(row["nombre"]),
                        )

                    render_kpi_card_with_sparkline(
                        str(row["nombre"]),
                        fmt_number(row["valor"], row["unidad"], row["nombre"]),
                        f"Meta: {fmt_number(row['meta'], row['unidad'], row['nombre'])}",
                        f"Desviación: {fmt_pct(row['variacion_pct'])}",
                        row["estado"],
                        history_values=spark_values,
                        streak_text=streak_text,
                        yoy_text=yoy_text,
                    )
                    render_observation_box(row.get("observacion", None))

                    # Recuadro acumulativo anual: SOLO para KPIs de afluencia
                    if (is_afluencia_kpi(str(row["nombre"]))
                            and not hist_scaled_for_cumul.empty):
                        render_yearly_cumulative_card(
                            hist_scaled_for_cumul,
                            str(row.get("periodo", "")),
                            str(row["nombre"]),
                            unit=str(row.get("unidad", "")),
                        )

    st.markdown("<div class='section-title'>Evolución del KPI seleccionado</div>", unsafe_allow_html=True)
    hist_service = kpis_hist[kpis_hist["servicio"].astype(str) == str(resumen_srv)].copy()
    nombres_kpi = sorted(hist_service["nombre"].dropna().astype(str).unique().tolist())

    resumen_kpi_sel = option_selector(
        "KPI a visualizar", nombres_kpi, key="kpi_hist_sel_resumen",
        default=nombres_kpi[0] if nombres_kpi else None,
        horizontal=True,
    )
    if not nombres_kpi or not resumen_kpi_sel:
        st.info("No hay datos históricos para el servicio seleccionado.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    hist_sel = hist_service[hist_service["nombre"] == resumen_kpi_sel].copy()
    hist_sel = scale_kpi_dataframe_for_display(hist_sel, resumen_kpi_sel, ("valor", "meta"))
    unit_hist = None
    if not hist_sel.empty and "unidad" in hist_sel.columns and not hist_sel["unidad"].dropna().empty:
        unit_hist = hist_sel["unidad"].dropna().astype(str).iloc[0]

    if hist_sel.empty:
        st.info("No hay datos históricos para el KPI seleccionado.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    hist_plot = hist_sel.groupby("periodo", as_index=False)["valor"].sum()
    fig = build_trend_line_chart(hist_plot, resumen_kpi_sel, unit_hist, resumen_srv)
    fig.update_layout(height=470)
    show_plot(fig, width="stretch")
    st.markdown("</div></div>", unsafe_allow_html=True)


# ================================================================
# 29. RENDERER — Personas
# ================================================================
def render_personas(iniciativas: pd.DataFrame, servicios_lista: list,
                    estados_ini: list, prioridades: list, responsables: list):
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    title_col, filter_col = st.columns([4.6, 1.2])
    with title_col:
        st.markdown("<div class='section-title'>Vista por persona</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='section-subtitle'>Seguimiento de iniciativas, "
            "avance y estado por responsable.</div>",
            unsafe_allow_html=True,
        )
    with filter_col:
        popover_ctx = st.popover if hasattr(st, "popover") else st.expander
        kw = {} if hasattr(st, "popover") else {"expanded": False}
        with popover_ctx("Filtros", **kw):
            st.multiselect("Estado iniciativa", options=estados_ini,
                           default=st.session_state.get("estado_body_filter", estados_ini),
                           key="estado_body_filter")
            st.multiselect("Prioridad", options=prioridades,
                           default=st.session_state.get("prioridad_body_filter", prioridades),
                           key="prioridad_body_filter")
            st.multiselect("Responsable", options=responsables,
                           default=st.session_state.get("responsable_body_filter", responsables),
                           key="responsable_body_filter")
            if st.button("Restablecer", key="reset_personas_filters", width="stretch"):
                st.session_state["estado_body_filter"]      = estados_ini
                st.session_state["prioridad_body_filter"]   = prioridades
                st.session_state["responsable_body_filter"] = responsables
                st.rerun()

    iniciativas_local = iniciativas[
        iniciativas["servicio"].isin(servicios_lista) &
        iniciativas["estado"].isin(st.session_state.get("estado_body_filter", estados_ini) or estados_ini) &
        iniciativas["prioridad"].isin(st.session_state.get("prioridad_body_filter", prioridades) or prioridades) &
        iniciativas["responsable"].isin(st.session_state.get("responsable_body_filter", responsables) or responsables)
    ].copy()

    total = len(iniciativas_local)
    en_curso    = int((iniciativas_local["estado"] == "En curso").sum())
    atrasadas   = int((iniciativas_local["estado"] == "Atrasada").sum())
    finalizadas = int((iniciativas_local["estado"] == "Finalizada").sum())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total iniciativas", total)
    m2.metric("En curso", en_curso)
    m3.metric("Atrasadas", atrasadas)
    m4.metric("Finalizadas", finalizadas)

    personas_opts = sorted(iniciativas_local["responsable"].dropna().astype(str).unique().tolist())
    persona_sel = option_selector(
        "Seleccione responsable", personas_opts, key="persona_selector",
        default=personas_opts[0] if personas_opts else None,
    )
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
            fig = px.bar(
                per_df.sort_values("avance_pct"),
                x="avance_pct", y="nombre_iniciativa",
                orientation="h",
                title=f"Avance por iniciativa — {persona_sel}",
                text="avance_pct",
            )
            fig.update_traces(marker_color=EFE_BLUE)
            fig.update_layout(
                plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
                margin=dict(l=20, r=20, t=50, b=20), height=420,
                font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
                title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
            )
            fig.update_xaxes(title="Avance %"); fig.update_yaxes(title="")
            show_plot(fig, width="stretch")
    with right_p:
        estado_persona = per_df["estado"].value_counts().reset_index()
        estado_persona.columns = ["estado", "cantidad"]
        if not estado_persona.empty:
            fig2 = px.bar(
                estado_persona, x="estado", y="cantidad",
                title="Distribución por estado", color="estado",
                color_discrete_map={
                    "Planificada": TEXT_MUTED, "En curso": EFE_BLUE,
                    "Atrasada": EFE_RED, "Finalizada": SUCCESS,
                    "Pausada": WARNING,
                },
            )
            fig2.update_layout(
                plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
                margin=dict(l=20, r=20, t=50, b=20), height=420,
                font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
                title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
                showlegend=False,
            )
            show_plot(fig2, width="stretch")

    st.markdown("<div class='section-title'>Detalle por responsable</div>", unsafe_allow_html=True)
    detalle_cols = ["nombre_iniciativa", "servicio", "estado", "avance_pct",
                    "fecha_inicio", "fecha_fin", "prioridad", "comentario"]
    detalle_cols = [c for c in detalle_cols if c in per_df.columns]
    rename_map = {
        "nombre_iniciativa": "Iniciativa", "servicio": "Servicio",
        "estado": "Estado", "avance_pct": "Avance %",
        "fecha_inicio": "Inicio", "fecha_fin": "Fin",
        "prioridad": "Prioridad", "comentario": "Comentario",
    }
    st.dataframe(per_df[detalle_cols].rename(columns=rename_map),
                 width="stretch", hide_index=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

# ================================================================
# 30. RENDERER — Perfil de Carga
# ================================================================

def _safe_first(df: pd.DataFrame, col: str, fallback=None):
    """Obtiene el primer valor no nulo de una columna, con fallback seguro."""
    if df is None or df.empty or col not in df.columns:
        return fallback
    s = df[col].dropna()
    if s.empty:
        return fallback
    return s.iloc[0]


def render_perfil_carga(data_path: Path, default_service: str | None = None):
    """
    Página de Perfil de Carga, totalmente reescrita con flujo defensivo.

    Cada bloque que pueda fallar va envuelto en un try/except que captura
    el error, lo muestra al usuario y permite seguir interactuando con el
    resto del dashboard sin tirar el proceso de Streamlit.
    """
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Perfil de Carga</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>Reconstrucción del perfil de carga "
        "por servicio a partir de transacciones OD: embarques, bajadas y "
        "pasajeros a bordo por estación.</div>",
        unsafe_allow_html=True,
    )

    # ---------- 1. Selección de servicio raíz ----------
    service_options = list(PROFILE_SERVICE_CONFIG.keys())
    profile_srv = (
        default_service if default_service in service_options
        else st.selectbox(
            "Servicio de perfil", options=service_options, index=0,
            key="profile_service_root_selector",
        )
    )

    # ---------- 2. Cargar datos ----------
    try:
        perfil_df, perfil_path, perfil_missing, perfil_files, perfil_status = (
            load_profile_service_data(profile_srv, str(data_path))
        )
    except Exception as exc:
        st.error(f"Error cargando perfil de carga: {type(exc).__name__}: {exc}")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # Detectar schema
    if isinstance(perfil_df, pd.DataFrame):
        profile_schema = perfil_df.attrs.get("profile_schema", "")
        if not profile_schema and "profile_schema" in perfil_df.columns and not perfil_df["profile_schema"].dropna().empty:
            profile_schema = str(perfil_df["profile_schema"].dropna().astype(str).iloc[0]).strip().lower()
        profile_schema = profile_schema or "aggregated"
    else:
        profile_schema = "aggregated"

    # Guardar el data_path en session_state para que las subfunciones decoradas
    # con @maybe_fragment puedan acceder a los slices cacheados sin recibirlo
    # como argumento (los fragments aíslan el re-run pero requieren claves
    # estables; pasar data_path por session_state mantiene el cache hit).
    st.session_state["_profile_data_path"] = str(data_path)
    st.session_state["_profile_service_root"] = str(profile_srv)

    folder_name = PROFILE_SERVICE_CONFIG.get(profile_srv, {}).get("folder_candidates", ["perfil_carga"])[0]

    if perfil_status == "no_data" or perfil_df.empty:
        st.info(
            f"No se encontraron archivos CSV para **{profile_srv}**. "
            f"Cree la carpeta **{folder_name}** y agregue los archivos diarios. "
            f"Ruta buscada: **{perfil_path}**.",
            icon="ℹ️",
        )
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    if perfil_status == "unsupported_format" or perfil_missing:
        st.warning(
            f"Archivos detectados, pero formato no compatible. "
            f"Columnas faltantes: **{', '.join(perfil_missing)}**."
        )
        if perfil_files:
            st.caption(f"Archivos detectados: {len(perfil_files)} | carpeta: {perfil_path}")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_disponibles = sorted([f for f in perfil_df["fecha"].dropna().unique().tolist() if pd.notna(f)])
    if not fechas_disponibles:
        st.warning("No existen fechas válidas en los archivos de perfil de carga.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # ---------- 3. Cargar referencias auxiliares ----------
    try:
        itinerary_summary_df, _, itinerary_path, itinerary_files, itinerary_status = (
            load_itinerary_reference(str(data_path))
        )
    except Exception:
        itinerary_summary_df = pd.DataFrame()
        itinerary_path, itinerary_files, itinerary_status = "", [], "no_data"

    try:
        service_order_df, service_order_path, service_order_files, service_order_status = (
            load_service_order_reference(str(data_path))
        )
    except Exception:
        service_order_df = pd.DataFrame()
        service_order_path, service_order_files, service_order_status = "", [], "no_data"

    # Detectar si el perfil ya viene enriquecido (con tarifa y tipo de pasajero
    # por viaje). Si es así, NO cargamos torniquetes — ahorra RAM significativa
    # en Streamlit Cloud (donde el límite de 1 GB es crítico).
    perfil_is_enriched = bool(
        perfil_df is not None and not perfil_df.empty and (
            "monto_transaccion" in perfil_df.columns
            or "tipo_pasajero" in perfil_df.columns
        )
    )

    if perfil_is_enriched:
        turnstile_df = pd.DataFrame()
        turnstile_path, turnstile_missing, turnstile_files, turnstile_status = (
            "", [], [], "skipped_enriched_profile",
        )
    else:
        try:
            turnstile_df, turnstile_path, turnstile_missing, turnstile_files, turnstile_status = (
                load_turnstile_service_data(profile_srv, str(data_path))
            )
        except Exception:
            turnstile_df = pd.DataFrame()
            turnstile_path, turnstile_missing, turnstile_files, turnstile_status = "", [], [], "read_error"

    # ---------- 4. Pestañas ----------
    if st.session_state.get("safe_mode", False):
        st.info(
            "🛡️ **Modo seguro activo.** El cruce con torniquetes y los promedios "
            "mensuales están pausados para acelerar la navegación. "
            "Desactívelo desde el menú ⋮ cuando quiera ver los cálculos completos.",
            icon="ℹ️",
        )
    tab_diario, tab_mensual = st.tabs(["Análisis diario", "Promedio mensual"])

    with tab_diario:
        try:
            _render_perfil_diario(
                perfil_df, profile_schema, profile_srv, fechas_disponibles,
                itinerary_summary_df, service_order_df,
                turnstile_df, turnstile_status,
                perfil_files, perfil_path,
                itinerary_files, itinerary_path, itinerary_status,
                service_order_files, service_order_path, service_order_status,
                turnstile_files, turnstile_path,
            )
        except BaseException as exc:
            if is_streamlit_internal_exception(exc):
                raise
            st.error(
                f"Ocurrió un error en el análisis diario "
                f"({type(exc).__name__}: {exc}). "
                f"Pruebe limpiar el caché desde el menú ⋮ y recargar."
            )

    with tab_mensual:
        try:
            _render_perfil_mensual(
                perfil_df, profile_schema, profile_srv,
                itinerary_summary_df, service_order_df,
                turnstile_df, turnstile_status,
            )
        except BaseException as exc:
            if is_streamlit_internal_exception(exc):
                raise
            st.error(
                f"Ocurrió un error en el promedio mensual "
                f"({type(exc).__name__}: {exc}). "
                f"Pruebe limpiar el caché desde el menú ⋮."
            )

    st.markdown("</div></div>", unsafe_allow_html=True)


@maybe_fragment
def _render_perfil_diario(perfil_df, profile_schema, profile_srv, fechas_disponibles,
                          itinerary_summary_df, service_order_df,
                          turnstile_df, turnstile_status,
                          perfil_files, perfil_path,
                          itinerary_files, itinerary_path, itinerary_status,
                          service_order_files, service_order_path, service_order_status,
                          turnstile_files, turnstile_path):
    """Subpágina del análisis diario de perfil de carga."""
    fechas_set = set(fechas_disponibles)

    fecha_key = f"perfil_fecha_cal_{profile_srv}"
    fecha_default = fechas_disponibles[-1]
    prev = st.session_state.get(fecha_key)
    if isinstance(prev, date):
        fecha_default = prev if prev in fechas_set else min(
            fechas_disponibles, key=lambda d: abs((d - prev).days)
        )

    fecha_input = st.date_input(
        "📅 Fecha", value=fecha_default,
        min_value=fechas_disponibles[0], max_value=fechas_disponibles[-1],
        format="DD/MM/YYYY", key=fecha_key,
    )
    fecha_sel = fecha_input
    if fecha_sel not in fechas_set:
        fecha_sel = min(fechas_disponibles, key=lambda d: abs((d - fecha_sel).days))
        st.info(
            f"Fecha sin datos. Se usa la más cercana: "
            f"{pd.to_datetime(fecha_sel).strftime('%d-%m-%Y')}."
        )

    perfil_fecha = perfil_df[perfil_df["fecha"] == fecha_sel].copy()
    # Usar slice cacheado por día cuando el data_path está disponible.
    # Esto evita mantener el DataFrame completo en memoria durante el
    # filtrado y mejora drásticamente el cache hit cuando el usuario
    # cambia entre fechas/servicios rápidamente.
    _data_path = st.session_state.get("_profile_data_path", "")
    if _data_path:
        try:
            sliced_day, _ = get_profile_for_day(profile_srv, _data_path, str(fecha_sel))
            if not sliced_day.empty:
                perfil_fecha = sliced_day
        except BaseException:
            pass  # Fallback al filtrado en memoria
    lineas_disp = sorted([x for x in perfil_fecha["linea"].dropna().astype(str).unique() if x])

    row1, row2, row3 = st.columns([0.9, 1.15, 1.15])
    with row1:
        linea_sel = option_selector(
            "Línea", lineas_disp,
            key=f"perfil_linea_selector_{profile_srv}",
            default=lineas_disp[0] if lineas_disp else None,
        )

    perfil_linea = (
        perfil_fecha[perfil_fecha["linea"].astype(str) == str(linea_sel)].copy()
        if linea_sel else perfil_fecha.iloc[0:0].copy()
    )
    direcciones_disp = sorted(
        [x for x in perfil_linea["direccion"].dropna().astype(str).unique() if x]
    )

    with row2:
        dir_sel = option_selector(
            "Dirección", direcciones_disp,
            key=f"perfil_direccion_selector_{profile_srv}",
            default=direcciones_disp[0] if direcciones_disp else None,
        )

    perfil_dir = (
        perfil_linea[perfil_linea["direccion"].astype(str) == str(dir_sel)].copy()
        if dir_sel else perfil_linea.iloc[0:0].copy()
    )

    if perfil_dir.empty:
        st.warning("No existen datos para la combinación seleccionada.")
        return

    # Schema local
    schema_local = profile_schema
    if schema_local not in {"transactional", "aggregated"}:
        tx_cols = {"origen", "destino", "t_entrada_viaje", "t_salida_viaje"}
        schema_local = "transactional" if tx_cols.issubset(set(perfil_dir.columns)) else "aggregated"

    # ---------- Cruce torniquetes (con cache de sesión) ----------
    matched_tx_day = pd.DataFrame()
    service_fare_summary = pd.DataFrame()
    turnstile_stats = {
        "turnstile_total": 0, "matched_total": 0, "match_pct": np.nan,
        "diff_mediana_min": np.nan, "tolerance_minutes": 20,
    }
    if (normalize_text(profile_srv) == "biotren"
            and schema_local == "transactional"
            and not st.session_state.get("safe_mode", False)):

        # --- CAMINO PREFERENTE: perfil enriquecido (sin merge en runtime) ---
        # Cuando los archivos del perfil traen `monto_transaccion` y
        # `tipo_pasajero` por viaje (formato OD_Final_*_con_monto_tipo.csv),
        # calculamos tarifa y distribución directamente con groupby.
        # Esto elimina por completo la operación cara que causaba crashes.
        perfil_is_enriched = (
            "monto_transaccion" in perfil_fecha.columns
            or "tipo_pasajero" in perfil_fecha.columns
        )
        if perfil_is_enriched:
            # matched_tx_day = el propio perfil del día (ya tiene tarifa y tipo)
            matched_tx_day = perfil_fecha.copy()
            service_fare_summary = build_service_fare_summary_from_profile(perfil_fecha)
            turnstile_stats = {
                "turnstile_total": int(len(perfil_fecha)),
                "matched_total":   int(len(perfil_fecha)),
                "match_pct": 100.0,
                "diff_mediana_min": 0.0,
                "tolerance_minutes": 0,
                "pct_match_entrada": np.nan,
                "pct_match_salida": np.nan,
                "source": "perfil_enriquecido",
            }

        # --- Camino legacy: cruce con torniquetes en runtime ---------------
        elif (turnstile_status == "ok"
              and turnstile_df is not None and not turnstile_df.empty):
            turnstile_day = pd.DataFrame()
            _data_path = st.session_state.get("_profile_data_path", "")
            if _data_path:
                try:
                    turnstile_day = get_turnstile_for_day(profile_srv, _data_path, str(fecha_sel))
                except BaseException:
                    turnstile_day = pd.DataFrame()
            if turnstile_day.empty:
                turnstile_day = turnstile_df[turnstile_df["fecha"] == fecha_sel].copy()
            if not turnstile_day.empty:
                cache = st.session_state.setdefault("_turnstile_match_cache", {})
                key = (str(profile_srv), str(fecha_sel),
                       int(len(turnstile_day)), int(len(perfil_fecha)))
                cached = cache.get(key)
                if cached is None:
                    with st.spinner("Cruzando torniquetes con perfil del día…"):
                        matched_tx_day, service_fare_summary, turnstile_stats = (
                            match_turnstile_transactions_to_profile(
                                turnstile_day, perfil_fecha, tolerance_minutes=20,
                            )
                        )
                    if len(cache) > 12:
                        cache.pop(next(iter(cache)))
                    cache[key] = (matched_tx_day, service_fare_summary, turnstile_stats)
                else:
                    matched_tx_day, service_fare_summary, turnstile_stats = cached

    # ---------- Resumen por servicio ----------
    service_summary = build_service_level_summary(perfil_dir, schema_local)
    service_summary = enrich_service_summary_with_itinerary(
        service_summary, itinerary_summary_df, profile_srv, linea_sel, dir_sel, fecha_sel,
    )
    service_summary = apply_service_order_and_labels(
        service_summary, service_order_df, profile_srv, linea_sel, dir_sel, fecha_sel,
    )

    if not service_summary.empty:
        for col in ["tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox",
                    "recaudacion_aprox", "desviacion_tarifa_aprox",
                    "diff_mediana_min", "match_ref_principal"]:
            if col not in service_summary.columns:
                service_summary[col] = np.nan

        if not service_fare_summary.empty:
            fare_sel = service_fare_summary[
                (service_fare_summary["linea"].astype(str).str.strip()      == str(linea_sel)) &
                (service_fare_summary["direccion"].astype(str).str.strip() == str(dir_sel))
            ].copy()
            if not fare_sel.empty:
                drop_cols = [c for c in [
                    "tx_cruzadas", "tarifa_media_aprox", "tarifa_mediana_aprox",
                    "recaudacion_aprox", "desviacion_tarifa_aprox", "diff_mediana_min",
                ] if c in service_summary.columns]
                service_summary = service_summary.drop(columns=drop_cols, errors="ignore").merge(
                    fare_sel[[
                        "servicio_label", "tx_cruzadas", "tarifa_media_aprox",
                        "tarifa_mediana_aprox", "recaudacion_aprox",
                        "desviacion_tarifa_aprox", "diff_mediana_min",
                        "match_ref_principal",
                    ]], how="left", on="servicio_label",
                )
                service_summary["tarifa_media_aprox"] = pd.to_numeric(
                    service_summary["tarifa_media_aprox"], errors="coerce",
                )
                service_summary["pasajeros_transportados"] = pd.to_numeric(
                    service_summary["pasajeros_transportados"], errors="coerce",
                )
                # Recaudación = tarifa × pax (sin np.where con division)
                tarifa = service_summary["tarifa_media_aprox"]
                pax    = service_summary["pasajeros_transportados"]
                rec = tarifa * pax
                rec = rec.where(tarifa.notna() & pax.notna(), np.nan)
                service_summary["recaudacion_aprox"] = rec

    # ---------- Selector de servicio específico ----------
    if not service_summary.empty:
        option_df = service_summary[[
            "servicio_label", "servicio_display_label", "servicio_orden_idx",
        ]].drop_duplicates(subset=["servicio_label"], keep="first").copy()
        option_df = option_df.sort_values(["servicio_orden_idx", "servicio_label"])
        option_labels = option_df["servicio_display_label"].astype(str).tolist()
        label_to_service = dict(zip(
            option_df["servicio_display_label"].astype(str),
            option_df["servicio_label"].astype(str),
        ))
        prev_service = st.session_state.get(f"perfil_servicio_selector_{profile_srv}")
        default_label = option_labels[0] if option_labels else None
        if prev_service in set(option_df["servicio_label"].astype(str)):
            mask = option_df["servicio_label"].astype(str) == str(prev_service)
            default_label = option_df.loc[mask, "servicio_display_label"].iloc[0]

        with row3:
            if option_labels:
                idx_default = option_labels.index(default_label) if default_label in option_labels else 0
                servicio_label_sel = st.selectbox(
                    "Servicio específico", options=option_labels,
                    index=idx_default,
                    key=f"perfil_servicio_selector_label_{profile_srv}",
                )
            else:
                servicio_label_sel = None
        servicio_sel = label_to_service.get(servicio_label_sel) if servicio_label_sel else None
        if servicio_sel:
            st.session_state[f"perfil_servicio_selector_{profile_srv}"] = servicio_sel
    else:
        servicios_disp = sorted(
            perfil_dir["servicio_label"].dropna().astype(str).unique(),
            key=lambda x: (len(x), x),
        )
        with row3:
            if servicios_disp:
                servicio_sel = st.selectbox(
                    "Servicio específico", options=servicios_disp,
                    index=0, key=f"perfil_servicio_selector_{profile_srv}",
                )
            else:
                servicio_sel = None

    if not servicio_sel:
        st.warning("No existen servicios disponibles para la selección actual.")
        return

    # ---------- Construir perfil del servicio seleccionado ----------
    if schema_local == "transactional":
        perfil_servicio_tx = perfil_dir[perfil_dir["servicio_label"].astype(str) == str(servicio_sel)].copy()
        perfil_servicio = build_transactional_service_profile(perfil_servicio_tx)
    else:
        perfil_servicio = perfil_dir[perfil_dir["servicio_label"].astype(str) == str(servicio_sel)].copy()
        if not perfil_servicio.empty:
            perfil_servicio["event_time"] = perfil_servicio["t_arr_est"].fillna(perfil_servicio["t_dep_est"])

    if perfil_servicio.empty:
        st.warning("No fue posible reconstruir el perfil de carga para el servicio seleccionado.")
        return

    # Ordenar por estación según secuencia operativa (sin Categorical en plot_df)
    station_order = get_station_order_from_profile(perfil_servicio)
    if station_order:
        cat_pos = {s: i for i, s in enumerate(station_order)}
        perfil_servicio["_pos"] = perfil_servicio["estacion"].astype(str).map(cat_pos).fillna(len(station_order))
        sort_cols = ["_pos"]
        if "event_time" in perfil_servicio.columns:
            sort_cols.append("event_time")
        perfil_servicio = perfil_servicio.sort_values(sort_cols).drop(columns="_pos")

    # ---------- Métricas ejecutivas ----------
    total_bajadas = pd.to_numeric(perfil_servicio["D_bajadas"], errors="coerce").sum(min_count=1)
    l_out_series = pd.to_numeric(perfil_servicio.get("L_out_abordo"), errors="coerce")
    max_abordo = float(l_out_series.dropna().max()) if l_out_series.notna().any() else np.nan

    capacidad = None
    if "capacidad_tren" in perfil_servicio.columns:
        cap_s = pd.to_numeric(perfil_servicio["capacidad_tren"], errors="coerce").dropna()
        if not cap_s.empty:
            capacidad = float(cap_s.iloc[0])

    servicios_realizados = (
        int(len(service_summary)) if not service_summary.empty
        else int(perfil_dir["servicio_label"].nunique())
    )
    pasajeros_transportados = total_bajadas

    # Tramo de máximo a bordo
    tramo_max = "-"
    if l_out_series.notna().any():
        ordered_st = ([str(s) for s in station_order]
                      if station_order
                      else perfil_servicio["estacion"].astype(str).tolist())
        max_idx = l_out_series.idxmax()
        est_max = str(perfil_servicio.loc[max_idx, "estacion"])
        if est_max in ordered_st:
            pos = ordered_st.index(est_max)
            if pos < len(ordered_st) - 1:
                tramo_max = f"{ordered_st[pos]} - {ordered_st[pos + 1]}"
            elif pos > 0:
                tramo_max = f"{ordered_st[pos - 1]} - {ordered_st[pos]}"
            else:
                tramo_max = est_max

    # Tarifa y recaudación del servicio seleccionado
    tarifa_media_sel = np.nan
    recaudacion_sel = np.nan
    if not service_summary.empty:
        sel_row = service_summary[service_summary["servicio_label"].astype(str) == str(servicio_sel)].head(1)
        if not sel_row.empty:
            if "tarifa_media_aprox" in sel_row.columns:
                v = pd.to_numeric(sel_row["tarifa_media_aprox"], errors="coerce").iloc[0]
                tarifa_media_sel = v
            if "recaudacion_aprox" in sel_row.columns:
                v = pd.to_numeric(sel_row["recaudacion_aprox"], errors="coerce").iloc[0]
                recaudacion_sel = v

    # Ocupación
    capacidad_referencia = CAPACIDAD_REFERENCIA_LINEA
    ocupacion_general = np.nan
    ocupacion_servicio = np.nan
    if not service_summary.empty and servicios_realizados > 0:
        pax_total = pd.to_numeric(
            service_summary.get("pasajeros_transportados"), errors="coerce",
        ).fillna(0).sum()
        denom = float(servicios_realizados) * capacidad_referencia
        if denom > 0:
            ocupacion_general = float(pax_total) / denom * 100.0
    if pd.notna(pasajeros_transportados) and capacidad_referencia > 0:
        ocupacion_servicio = float(pasajeros_transportados) / float(capacidad_referencia) * 100.0

    # ---------- Render KPIs principales ----------
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(f"Servicios realizados ({linea_sel} | {dir_sel})", servicios_realizados)
        st.metric(
            f"Tasa de ocupación línea ({linea_sel} | {dir_sel})",
            fmt_pct(ocupacion_general) if pd.notna(ocupacion_general) else "-",
        )
    with col2:
        st.metric("Pasajeros transportados", fmt_pax(pasajeros_transportados))
        st.metric(
            f"Tasa de ocupación servicio {servicio_sel}",
            fmt_pct(ocupacion_servicio) if pd.notna(ocupacion_servicio) else "-",
        )
    with col3:
        st.metric("Máximo a bordo", fmt_pax(max_abordo))
        st.metric("Tramo con máximo a bordo", tramo_max)
    with col4:
        st.metric(
            "Tarifa media aprox. servicio",
            fmt_number(tarifa_media_sel, "CLP") if pd.notna(tarifa_media_sel) else "-",
        )
        st.metric(
            "Recaudación aprox. servicio",
            fmt_number(recaudacion_sel, "CLP") if pd.notna(recaudacion_sel) else "-",
        )

    st.caption(
        "Recaudación aprox. = tarifa media aprox. × pasajeros transportados. "
        f"Tasa de ocupación de línea = pax totales / (servicios × {int(capacidad_referencia)}). "
        f"Tasa de ocupación servicio = pax / {int(capacidad_referencia)}."
    )

    # ---------- Gráfico principal con comparativo opcional ----------
    titulo = f"{profile_srv} | {linea_sel} | {dir_sel} | Servicio {servicio_sel}"

    # Toggle: comparar con promedio del tipo de día
    comp_col_l, comp_col_r = st.columns([1, 4])
    with comp_col_l:
        show_comparison = st.toggle(
            "Comparar vs promedio del tipo de día",
            value=False,
            key=f"perfil_comp_toggle_{profile_srv}_{linea_sel}_{dir_sel}",
            help="Superpone una línea con el promedio del mismo tipo "
                 "de día (laboral/sábado/domingo) en el mes.",
        )

    avg_profile = pd.DataFrame()
    if show_comparison:
        try:
            month_period_now = pd.Timestamp(fecha_sel).to_period("M").strftime("%Y-%m")
            with st.spinner("Calculando promedio del tipo de día…"):
                avg_profile = compute_avg_profile_by_day_type(
                    perfil_df, linea_sel, dir_sel, fecha_sel, month_period_now,
                )
        except BaseException:
            avg_profile = pd.DataFrame()

    if show_comparison and not avg_profile.empty:
        tipo_label = (classify_profile_day_type(fecha_sel) or "tipo").lower()
        fig_main = build_perfil_comparativo_chart(perfil_servicio, avg_profile, titulo, tipo_label)
    else:
        fig_main = build_perfil_carga_chart(perfil_servicio, titulo)
    show_plot(fig_main, width="stretch")

    # ---------- Panel de saturación del servicio ----------
    saturation = compute_saturation_metrics(perfil_servicio, capacidad_referencia)
    render_saturation_panel(saturation)

    # Caption de capacidad y referencias
    cap_msg = None
    if capacidad and pd.notna(max_abordo) and float(capacidad) != 0:
        cap_msg = (
            f"Capacidad tren: {fmt_pax(capacidad)} · "
            f"Ocupación máxima: {fmt_pct(float(max_abordo) / float(capacidad) * 100)}"
        )
    ref_parts = []
    if perfil_files:
        ref_parts.append(f"Perfil: {len(perfil_files)} archivo(s) en {perfil_path}")
    if itinerary_status == "ok" and itinerary_files:
        ref_parts.append(f"Itinerario: {len(itinerary_files)} archivo(s) en {itinerary_path}")
    elif itinerary_status == "no_data":
        ref_parts.append("Itinerario no encontrado; se usa hora/origen inferidos")
    if service_order_status == "ok" and service_order_files:
        ref_parts.append(f"Orden servicios: {len(service_order_files)} archivo(s) en {service_order_path}")
    if normalize_text(profile_srv) == "biotren":
        # Detectar si los datos vinieron del perfil enriquecido o del cruce legacy
        source = (turnstile_stats.get("source") if isinstance(turnstile_stats, dict) else None)
        if source == "perfil_enriquecido":
            ref_parts.append(
                "Tarifa y tipo de pasajero leídos directamente del perfil "
                "(formato enriquecido — sin cruce en runtime)"
            )
        elif turnstile_status == "ok" and turnstile_files:
            tm = f"Torniquetes: {len(turnstile_files)} archivo(s) en {turnstile_path}"
            if turnstile_stats.get("turnstile_total", 0) > 0 and pd.notna(turnstile_stats.get("match_pct")):
                tm += f" · match día: {fmt_pct(turnstile_stats.get('match_pct'))}"
            ref_parts.append(tm)
    caption_parts = [x for x in [cap_msg] + ref_parts if x]
    if caption_parts:
        st.caption(" · ".join(caption_parts))

    # ---------- Distribución por tipo de pasajero ----------
    _render_passenger_type_distribution(
        matched_tx_day, servicio_sel, pasajeros_transportados, linea_sel, dir_sel,
    )

    # ---------- Pasajeros transportados por servicio ----------
    st.markdown(
        "<div class='section-title'>Pasajeros transportados por servicio</div>",
        unsafe_allow_html=True,
    )
    if service_summary.empty:
        st.info("No existen servicios disponibles para resumir en el día seleccionado.")
    else:
        fig = build_service_transport_chart(
            service_summary,
            f"{profile_srv} | {linea_sel} | {dir_sel} | Pasajeros transportados por servicio",
        )
        show_plot(fig, width="stretch")

    # ---------- Detalle por servicio ----------
    st.markdown("<div class='section-title'>Detalle por servicio</div>", unsafe_allow_html=True)
    if service_summary.empty:
        st.info("No existen detalles de servicios para el día seleccionado.")
    else:
        _render_service_detail_table(service_summary)


def _render_passenger_type_distribution(matched_tx_day, servicio_sel,
                                        pasajeros_transportados,
                                        linea_sel, dir_sel):
    """Render de los 5 recuadros por tipo de pasajero."""
    if matched_tx_day is None or matched_tx_day.empty:
        return
    if "tipo_pasajero" not in matched_tx_day.columns:
        return
    if pd.isna(pasajeros_transportados) or float(pasajeros_transportados) <= 0:
        return

    pax_type_df = build_passenger_type_distribution(
        matched_tx_day, servicio_sel=servicio_sel,
        pasajeros_transportados=pasajeros_transportados,
        linea_sel=linea_sel, direccion_sel=dir_sel,
    )
    if pax_type_df.empty or int(pax_type_df["tx_cruzadas"].sum()) == 0:
        return

    st.markdown(
        f"<div class='section-title'>Distribución por tipo de pasajero | "
        f"Servicio {servicio_sel}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='section-subtitle'>"
        "La composición se obtiene de las transacciones de torniquete cruzadas "
        "con el perfil del servicio (mismo mecanismo que la tarifa media) y se "
        "proyecta proporcionalmente al total de pasajeros transportados, de modo "
        "que la suma por tipo coincida con ese total."
        "</div>",
        unsafe_allow_html=True,
    )

    type_slug = {
        "Monedero":      "--monedero",
        "Estudiante":    "--estudiante",
        "Adulto Mayor":  "--adulto-mayor",
        "Discapacitado": "--discapacitado",
        "Otros":         "--otros",
    }
    rows_by_type = {row["tipo_pasajero"]: row for _, row in pax_type_df.iterrows()}
    cols = st.columns(len(PASSENGER_TYPE_ORDER))
    for col_box, tipo in zip(cols, PASSENGER_TYPE_ORDER):
        row = rows_by_type.get(tipo)
        if row is not None:
            pax_v   = int(row["pasajeros_estimados"])
            pct_v   = float(row["porcentaje"])
            tarifa  = row["tarifa_media"]
        else:
            pax_v, pct_v, tarifa = 0, 0.0, np.nan

        tarifa_label = fmt_number(tarifa, "CLP") if pd.notna(tarifa) else "-"
        empty_cls = " is-empty" if (pax_v == 0 and not pd.notna(tarifa)) else ""
        color_cls = type_slug.get(tipo, "")

        card_html = (
            f"<div class='pax-type-card {color_cls}{empty_cls}'>"
            f"  <div class='pax-card-title'>{tipo}</div>"
            f"  <div class='pax-card-value'>{fmt_pax(pax_v)}</div>"
            f"  <div class='pax-card-pct'>{fmt_pct(pct_v)} del servicio</div>"
            f"  <div class='pax-card-fare'>Tarifa media: {tarifa_label}</div>"
            f"</div>"
        )
        with col_box:
            st.markdown(card_html, unsafe_allow_html=True)

    suma = int(pax_type_df["pasajeros_estimados"].sum())
    target = int(round(float(pasajeros_transportados)))
    if suma == target:
        st.markdown(
            f"<span class='integrity-badge'>✓ Suma por tipo ({fmt_pax(suma)}) = "
            f"Pasajeros transportados ({fmt_pax(target)})</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<span class='integrity-badge warn'>Suma por tipo: {fmt_pax(suma)} · "
            f"Pasajeros transportados: {fmt_pax(target)} "
            f"(dif. redondeo: {fmt_pax(target - suma)})</span>",
            unsafe_allow_html=True,
        )


def _render_service_detail_table(service_summary: pd.DataFrame):
    """Tabla de detalle por servicio con strings formateados (compatible con todas las versiones de Streamlit)."""
    detalle = service_summary.copy()
    if "servicio_orden_idx" in detalle.columns:
        detalle = detalle.sort_values(
            ["servicio_orden_idx", "servicio_label"],
            kind="stable", na_position="last",
        ).copy()
    else:
        detalle = detalle.sort_values(
            ["servicio_label"], kind="stable", na_position="last",
        ).copy()

    out = pd.DataFrame()
    out["Servicio"]                = detalle["servicio_label"].astype(str)
    out["Hora salida"]             = detalle["hora_salida_fmt"].astype(str)
    out["Estación origen"]         = detalle["estacion_origen"].astype(str)
    out["Pasajeros transportados"] = pd.to_numeric(
        detalle["pasajeros_transportados"], errors="coerce",
    ).apply(fmt_pax)
    out["Máximo a bordo"]          = pd.to_numeric(
        detalle["max_abordo"], errors="coerce",
    ).apply(fmt_pax)
    if "tx_cruzadas" in detalle.columns:
        out["Tx cruzadas"] = pd.to_numeric(detalle["tx_cruzadas"], errors="coerce").apply(
            lambda v: fmt_pax(v) if pd.notna(v) else "-"
        )
    if "tarifa_media_aprox" in detalle.columns:
        out["Tarifa media aprox."] = pd.to_numeric(detalle["tarifa_media_aprox"], errors="coerce").apply(
            lambda v: fmt_number(v, "CLP") if pd.notna(v) else "-"
        )
    if "recaudacion_aprox" in detalle.columns:
        out["Recaudación aprox."] = pd.to_numeric(detalle["recaudacion_aprox"], errors="coerce").apply(
            lambda v: fmt_number(v, "CLP") if pd.notna(v) else "-"
        )

    st.dataframe(out, width="stretch", hide_index=True)


@maybe_fragment
def _render_perfil_mensual(perfil_df, profile_schema, profile_srv,
                           itinerary_summary_df, service_order_df,
                           turnstile_df, turnstile_status):
    """
    Subpágina del promedio mensual. Rediseño con:
      • Tarjetas resumen al inicio
      • Heatmap servicio × día (reemplaza las 6 tablas anteriores)
      • Tendencia diaria
      • Modo Resumen / Detalle (tablas se ven solo en Detalle)
    """
    st.markdown(
        "<div class='section-title'>Análisis mensual de servicios</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='section-subtitle'>Vista ejecutiva mensual: tarjetas "
        "resumen, mapa de servicio × día y tendencia diaria. Active el modo "
        "'Detalle' para ver las tablas completas por tipo de día.</div>",
        unsafe_allow_html=True,
    )

    fecha_to_period = pd.to_datetime(perfil_df["fecha"], errors="coerce").dt.to_period("M").astype(str)
    month_options = [m for m in sorted(pd.Series(fecha_to_period).dropna().unique().tolist()) if m and m != "NaT"]
    month_default = month_options[-1] if month_options else None

    # Filtros principales
    col_l, col_m, col_v = st.columns([1.0, 1.0, 0.9])
    with col_m:
        if month_options:
            idx = month_options.index(month_default) if month_default in month_options else 0
            month_sel = st.selectbox(
                "Mes", options=month_options, index=idx,
                format_func=month_period_to_label,
                key=f"perfil_month_selector_{profile_srv}",
            )
        else:
            month_sel = None

    perfil_month = (
        perfil_df[fecha_to_period == str(month_sel)].copy()
        if month_sel else perfil_df.iloc[0:0].copy()
    )
    _data_path = st.session_state.get("_profile_data_path", "")
    if month_sel and _data_path:
        try:
            sliced_month, _ = get_profile_for_month(profile_srv, _data_path, str(month_sel))
            if not sliced_month.empty:
                perfil_month = sliced_month
        except BaseException:
            pass
    lineas_mes = sorted([x for x in perfil_month["linea"].dropna().astype(str).unique() if x])
    with col_l:
        linea_mes_sel = option_selector(
            "Línea", lineas_mes,
            key=f"perfil_linea_mes_selector_{profile_srv}",
            default=lineas_mes[0] if lineas_mes else None,
        )

    # Toggle de vista
    with col_v:
        view_mode = option_selector(
            "Vista", ["Resumen", "Detalle"],
            key=f"perfil_mensual_view_mode_{profile_srv}",
            default="Resumen",
            horizontal=True,
        )

    if not month_sel or not linea_mes_sel:
        st.info("No existen datos mensuales disponibles para los filtros seleccionados.")
        return

    # Detectar cambio de mes y liberar memoria agresivamente para evitar
    # que Streamlit Cloud mate el proceso por OOM (límite 1 GB).
    last_month_key = f"_last_month_processed_{profile_srv}"
    last_month = st.session_state.get(last_month_key)
    if last_month and last_month != month_sel:
        # Cambió el mes: liberar caches de sesión obsoletos
        keys_to_drop = [
            k for k in list(st.session_state.keys())
            if k.startswith("_turnstile_match_cache")
        ]
        for k in keys_to_drop:
            try:
                del st.session_state[k]
            except KeyError:
                pass

        # Si el cambio es a un mes muy distante (no consecutivo), limpiar
        # caches de slice mensual para liberar la rebanada anterior.
        try:
            last_dt = pd.to_datetime(str(last_month) + "-01")
            cur_dt  = pd.to_datetime(str(month_sel) + "-01")
            months_diff = abs((cur_dt.year - last_dt.year) * 12 + (cur_dt.month - last_dt.month))
            if months_diff >= 1:
                # Invalidar slice mensual y la versión cacheada del cómputo
                try:
                    get_profile_for_month.clear()
                except Exception:
                    pass
                try:
                    build_monthly_profile_tables_cached.clear()
                except Exception:
                    pass
        except Exception:
            pass

        gc.collect()
    st.session_state[last_month_key] = month_sel

    if st.session_state.get("safe_mode", False):
        run_monthly = st.button(
            "▶️ Ejecutar cálculo mensual ahora",
            key=f"btn_run_monthly_{profile_srv}_{month_sel}_{linea_mes_sel}",
            type="primary", width="content",
        )
        if not run_monthly:
            st.info(
                "Modo seguro activo. Pulse '▶️ Ejecutar cálculo mensual ahora' "
                "cuando quiera ver los promedios."
            )
            return

    # Liberar memoria de re-runs anteriores antes del cálculo pesado
    gc.collect()

    # Usar la versión cacheada que recibe SOLO claves primitivas. Esto evita
    # que Streamlit hashee DataFrames de 50k+ filas en cada cambio de filtro
    # (la causa del cierre del dashboard al cambiar de mes).
    _data_path = st.session_state.get("_profile_data_path", "")

    try:
        with st.spinner("Calculando promedios mensuales por servicio…"):
            if _data_path:
                # Camino preferente: carga interna por claves simples
                tablas, directions, monthly_metrics, monthly_daily = build_monthly_profile_tables_cached(
                    profile_srv=profile_srv,
                    data_path_str=_data_path,
                    month_period=month_sel,
                    linea_sel=linea_mes_sel,
                    turnstile_status=turnstile_status,
                )
            else:
                # Camino fallback: pasaje directo de DataFrames (más lento)
                tablas, directions, monthly_metrics, monthly_daily = build_monthly_profile_tables(
                    perfil_month, profile_schema, profile_srv, month_sel, linea_mes_sel,
                    itinerary_summary_df, service_order_df,
                    turnstile_df, turnstile_status,
                )
    except MemoryError:
        # Si aun así se queda sin memoria, sugerir limpieza
        st.error(
            "⚠️ Memoria insuficiente para calcular el mes completo. "
            "Pruebe abrir el menú ⋮ → 'Limpiar caché y recargar', y "
            "luego active el modo seguro 🛡️ antes de cambiar de mes."
        )
        gc.collect()
        return
    except BaseException as exc:
        if is_streamlit_internal_exception(exc):
            raise
        st.error(
            f"Error calculando el promedio mensual: {type(exc).__name__}: {exc}. "
            f"Pruebe limpiar el caché desde el menú ⋮."
        )
        return

    # Liberar memoria intermedia
    gc.collect()

    if not tablas:
        st.info("No existen datos mensuales para la línea y mes seleccionados.")
        return

    # ============================================================
    # NARRATIVA AUTOMÁTICA
    # ============================================================
    narrative = _generate_monthly_narrative(monthly_daily, monthly_metrics,
                                            month_sel, linea_mes_sel)
    render_narrative_box(narrative, title="📋 Lectura del mes")

    # ============================================================
    # TARJETAS RESUMEN EJECUTIVO
    # ============================================================
    line_metrics = monthly_metrics.get("linea", {}) if isinstance(monthly_metrics, dict) else {}
    pax_total_mes = float(line_metrics.get("pasajeros_transportados", 0) or 0)
    tarifa_mes = line_metrics.get("tarifa_media_mensual")
    tasa_ocup = line_metrics.get("tasa_ocupacion_mensual")
    servicios_realizados = int(line_metrics.get("servicios_realizados", 0) or 0)

    # Pax promedio por tipo de día
    tipo_dia_metrics = monthly_metrics.get("por_tipo_dia", {}) if isinstance(monthly_metrics, dict) else {}
    pax_lab = float(
        (tipo_dia_metrics.get("Laboral", {}).get("linea", {}) or {}).get("pasajeros_transportados", 0) or 0
    )
    pax_sab = float(
        (tipo_dia_metrics.get("Sábado", {}).get("linea", {}) or {}).get("pasajeros_transportados", 0) or 0
    )
    pax_dom = float(
        (tipo_dia_metrics.get("Domingo", {}).get("linea", {}) or {}).get("pasajeros_transportados", 0) or 0
    )
    # Contar días por tipo
    if monthly_daily is not None and not monthly_daily.empty:
        n_lab = monthly_daily.loc[monthly_daily["tipo_dia"] == "Laboral", "fecha"].nunique()
        n_sab = monthly_daily.loc[monthly_daily["tipo_dia"] == "Sábado", "fecha"].nunique()
        n_dom = monthly_daily.loc[monthly_daily["tipo_dia"] == "Domingo", "fecha"].nunique()
    else:
        n_lab = n_sab = n_dom = 0

    pax_lab_avg = pax_lab / n_lab if n_lab else 0
    pax_sab_avg = pax_sab / n_sab if n_sab else 0
    pax_dom_avg = pax_dom / n_dom if n_dom else 0

    recaud_total_mes = pax_total_mes * (tarifa_mes if pd.notna(tarifa_mes) else 0)

    cards_html = (
        f"<div class='efe-summary-row'>"
        f"<div class='efe-summary-card' style='border-left:4px solid {EFE_BLUE};'>"
        f"<div class='efe-summary-label'>Pax totales del mes</div>"
        f"<div class='efe-summary-value'>{fmt_pax(pax_total_mes)}</div>"
        f"<div class='efe-summary-sub'>{servicios_realizados} servicios realizados</div>"
        f"</div>"
        f"<div class='efe-summary-card'>"
        f"<div class='efe-summary-label'>Pax laboral promedio</div>"
        f"<div class='efe-summary-value'>{fmt_pax(pax_lab_avg)}</div>"
        f"<div class='efe-summary-sub'>{n_lab} días laborables</div>"
        f"</div>"
        f"<div class='efe-summary-card'>"
        f"<div class='efe-summary-label'>Pax sábado promedio</div>"
        f"<div class='efe-summary-value'>{fmt_pax(pax_sab_avg)}</div>"
        f"<div class='efe-summary-sub'>{n_sab} sábados</div>"
        f"</div>"
        f"<div class='efe-summary-card'>"
        f"<div class='efe-summary-label'>Pax domingo promedio</div>"
        f"<div class='efe-summary-value'>{fmt_pax(pax_dom_avg)}</div>"
        f"<div class='efe-summary-sub'>{n_dom} domingos</div>"
        f"</div>"
        f"<div class='efe-summary-card' style='border-left:4px solid {SUCCESS};'>"
        f"<div class='efe-summary-label'>Tarifa media mensual</div>"
        f"<div class='efe-summary-value'>{fmt_number(tarifa_mes, 'CLP') if pd.notna(tarifa_mes) else '-'}</div>"
        f"<div class='efe-summary-sub'>Ponderada por demanda</div>"
        f"</div>"
        f"<div class='efe-summary-card'>"
        f"<div class='efe-summary-label'>Tasa de ocupación</div>"
        f"<div class='efe-summary-value'>{fmt_pct(tasa_ocup) if pd.notna(tasa_ocup) else '-'}</div>"
        f"<div class='efe-summary-sub'>Capacidad referencia: {int(CAPACIDAD_REFERENCIA_LINEA)}</div>"
        f"</div>"
        f"<div class='efe-summary-card' style='border-left:4px solid {WARNING};'>"
        f"<div class='efe-summary-label'>Recaudación estimada</div>"
        f"<div class='efe-summary-value'>{fmt_number(recaud_total_mes, 'CLP')}</div>"
        f"<div class='efe-summary-sub'>Pax × tarifa media</div>"
        f"</div>"
        f"</div>"
    )
    st.markdown(cards_html, unsafe_allow_html=True)

    st.caption(f"Mes analizado: {month_period_to_label(month_sel)} · Línea: {linea_mes_sel}")

    # ============================================================
    # TENDENCIA DIARIA + HEATMAP (siempre visibles)
    # ============================================================
    if monthly_daily is not None and not monthly_daily.empty:
        st.markdown(
            "<div class='section-title' style='font-size:0.95rem'>"
            "Tendencia diaria de pasajeros</div>",
            unsafe_allow_html=True,
        )
        try:
            trend_fig = build_monthly_daily_trend_chart(
                monthly_daily, title=f"Pasajeros por día — {month_period_to_label(month_sel)}",
            )
            if trend_fig is not None:
                show_plot(trend_fig, width="stretch")
            else:
                st.caption("Tendencia diaria no disponible.")
        except BaseException as exc:
            if is_streamlit_internal_exception(exc):
                raise
            st.caption(f"Tendencia diaria no disponible: {type(exc).__name__}")

    # ============================================================
    # MODO DETALLE: Tablas por tipo de día
    # ============================================================
    if view_mode == "Detalle":
        st.markdown(
            "<div class='section-title' style='font-size:0.95rem'>"
            "Detalle por tipo de día</div>",
            unsafe_allow_html=True,
        )
        for tipo_dia in ["Laboral", "Sábado", "Domingo"]:
            st.markdown(
                f"<div class='section-title' style='font-size:0.92rem'>{tipo_dia}</div>",
                unsafe_allow_html=True,
            )
            tipo_metrics = monthly_metrics.get("por_tipo_dia", {}).get(tipo_dia, {})
            tipo_line = tipo_metrics.get("linea", {}) if isinstance(tipo_metrics, dict) else {}
            tm1, tm2 = st.columns(2)
            with tm1:
                v = tipo_line.get("tarifa_media_mensual")
                st.metric(f"Tarifa media | {tipo_dia}",
                          fmt_number(v, "CLP") if pd.notna(v) else "-")
            with tm2:
                v = tipo_line.get("tasa_ocupacion_mensual")
                st.metric(f"Ocupación | {tipo_dia}",
                          fmt_pct(v) if pd.notna(v) else "-")

            dir_list = directions[:2] if directions else []
            if not dir_list:
                st.info(f"No existen datos para {tipo_dia.lower()}.")
                continue

            cols = st.columns(2)
            showed_any = False
            for i, dir_val in enumerate(dir_list):
                with cols[i]:
                    st.markdown(
                        f"<div class='map-note'><b>Dirección:</b> {dir_val}</div>",
                        unsafe_allow_html=True,
                    )
                    tabla_dir = tablas.get(tipo_dia, {}).get(dir_val, pd.DataFrame())
                    if tabla_dir is None or tabla_dir.empty:
                        st.info("Sin datos para esta dirección.")
                    else:
                        showed_any = True
                        show_df = pd.DataFrame()
                        show_df["Servicio"] = tabla_dir.get(
                            "servicio_display_label", tabla_dir["servicio_label"],
                        ).astype(str)
                        show_df["Pasajeros Promedio Mes"] = pd.to_numeric(
                            tabla_dir["pasajeros_promedio_mes"], errors="coerce",
                        ).apply(fmt_avg_pax)
                        show_df["Tarifa Media Mes"] = pd.to_numeric(
                            tabla_dir["tarifa_media_mes"], errors="coerce",
                        ).apply(lambda v: fmt_number(v, "CLP") if pd.notna(v) else "-")
                        st.dataframe(show_df, width="stretch", hide_index=True)

            if not showed_any:
                st.info(f"No existen datos para {tipo_dia.lower()} con los filtros seleccionados.")
    else:
        st.caption(
            "💡 Active la vista **Detalle** (selector arriba a la derecha) "
            "para ver las tablas completas por tipo de día."
        )


def _generate_monthly_narrative(monthly_daily: pd.DataFrame,
                                 monthly_metrics: dict,
                                 month_period: str,
                                 linea: str) -> str:
    """Genera narrativa automática para el promedio mensual."""
    if monthly_daily is None or monthly_daily.empty:
        return ""
    line_metrics = monthly_metrics.get("linea", {}) if isinstance(monthly_metrics, dict) else {}
    pax_total = float(line_metrics.get("pasajeros_transportados", 0) or 0)
    tarifa = line_metrics.get("tarifa_media_mensual")
    ocup = line_metrics.get("tasa_ocupacion_mensual")

    parts = []
    parts.append(
        f"En <strong>{month_period_to_label(month_period)}</strong>, "
        f"la línea <strong>{linea}</strong> transportó "
        f"<strong>{fmt_pax(pax_total)} pasajeros</strong> "
        f"con una tarifa media ponderada de "
        f"<strong>{fmt_number(tarifa, 'CLP') if pd.notna(tarifa) else '-'}</strong>."
    )
    if pd.notna(ocup):
        if ocup >= 60:
            parts.append(f"La ocupación mensual alcanzó <strong>{ocup:.1f}%</strong>: nivel alto que sugiere demanda sostenida sobre la oferta actual.")
        elif ocup >= 35:
            parts.append(f"La ocupación mensual fue <strong>{ocup:.1f}%</strong>, dentro de rangos operativos saludables.")
        else:
            parts.append(f"La ocupación mensual fue <strong>{ocup:.1f}%</strong>, por debajo del nivel típico; convendría revisar oferta vs demanda.")

    # Día con más pax / con menos pax
    daily_totals = monthly_daily.groupby("fecha", as_index=False)["pasajeros_transportados"].sum()
    if not daily_totals.empty:
        top_day = daily_totals.sort_values("pasajeros_transportados", ascending=False).iloc[0]
        low_day = daily_totals.sort_values("pasajeros_transportados").iloc[0]
        try:
            top_d = pd.Timestamp(top_day["fecha"]).strftime("%d-%m")
            low_d = pd.Timestamp(low_day["fecha"]).strftime("%d-%m")
            parts.append(
                f"El día con mayor afluencia fue <strong>{top_d}</strong> "
                f"({fmt_pax(top_day['pasajeros_transportados'])}); "
                f"el más bajo fue {low_d} ({fmt_pax(low_day['pasajeros_transportados'])})."
            )
        except Exception:
            pass

    return " ".join(parts)

# ================================================================
# 31. RENDERER — Estaciones (mapa + barras afluencia vs meta)
# ================================================================
def render_detalle_servicio(servicios_lista: list,
                            estaciones: pd.DataFrame,
                            afluencia_estacion: pd.DataFrame):
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Estaciones</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>Afluencia por estación y lectura "
        "territorial del servicio seleccionado.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='map-note'>Vista georreferenciada de afluencia "
        "registrada vs meta por estación.</div>",
        unsafe_allow_html=True,
    )

    if estaciones is None or estaciones.empty or afluencia_estacion is None or afluencia_estacion.empty:
        st.info(
            "Para habilitar esta vista, agregue estaciones.csv y "
            "afluencia_estacion.csv al repositorio."
        )
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    estaciones_activas = (
        estaciones[estaciones["activa"] == 1].copy()
        if "activa" in estaciones.columns else estaciones.copy()
    )
    servicios_detalle = sorted(
        set(estaciones_activas["servicio"].dropna().astype(str))
        & set(afluencia_estacion["servicio"].dropna().astype(str))
    )
    servicios_detalle = [s for s in servicios_lista if s in servicios_detalle] or servicios_detalle

    if not servicios_detalle:
        st.warning("No existen servicios comunes entre estaciones.csv y afluencia_estacion.csv.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    sel1, sel2 = st.columns([1.35, 1])
    with sel1:
        detalle_srv = option_selector(
            "Servicio georreferenciado", servicios_detalle,
            key="detalle_servicio_selector",
            default=servicios_detalle[0],
        )

    periodos_detalle = sorted(
        afluencia_estacion[afluencia_estacion["servicio"].astype(str) == str(detalle_srv)]
        ["periodo"].dropna().astype(str).unique().tolist()
    )
    if not periodos_detalle:
        st.warning("No existen períodos disponibles para el servicio seleccionado.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    with sel2:
        detalle_per = option_selector(
            "Período de detalle", periodos_detalle,
            key="detalle_periodo_selector", default=periodos_detalle[-1],
        )

    estaciones_srv = estaciones_activas[estaciones_activas["servicio"].astype(str) == str(detalle_srv)].copy()
    if "orden_trazado" in estaciones_srv.columns:
        estaciones_srv = estaciones_srv.sort_values(["orden_trazado", "estacion"])
    else:
        estaciones_srv = estaciones_srv.sort_values("estacion")

    afluencia_srv = afluencia_estacion[
        (afluencia_estacion["servicio"].astype(str) == str(detalle_srv)) &
        (afluencia_estacion["periodo"].astype(str)  == str(detalle_per))
    ].copy()

    detail_df = estaciones_srv.merge(
        afluencia_srv, how="left", on=["id_estacion", "servicio"],
        suffixes=("_est", "_afl"),
    )
    for col in ["entradas", "meta_entradas", "perdida_pax", "fuga_pct"]:
        detail_df[col] = pd.to_numeric(detail_df.get(col), errors="coerce")
    detail_df["fuga_pct_display"] = detail_df["fuga_pct"].apply(maybe_scale_percent)

    valid_map = detail_df.dropna(subset=["latitud", "longitud"]).copy()
    bar_df = detail_df[["estacion", "entradas", "meta_entradas"]].copy()
    if "orden_trazado" in detail_df.columns:
        station_order = (
            detail_df.sort_values(["orden_trazado", "estacion"])
                     ["estacion"].dropna().astype(str).tolist()
        )
    else:
        station_order = sorted(bar_df["estacion"].dropna().astype(str).tolist())

    bar_df["entradas"]      = pd.to_numeric(bar_df["entradas"],      errors="coerce").fillna(0)
    bar_df["meta_entradas"] = pd.to_numeric(bar_df["meta_entradas"], errors="coerce").fillna(0)

    top_l, top_r = st.columns([0.95, 1.05])
    with top_l:
        if valid_map.empty:
            st.warning("No existen coordenadas válidas para graficar.")
        else:
            show_plot(build_station_map(valid_map), width="stretch")
    with top_r:
        total_entradas = detail_df["entradas"].sum(min_count=1)
        total_meta     = detail_df["meta_entradas"].sum(min_count=1)
        total_perdida  = detail_df["perdida_pax"].sum(min_count=1)
        fuga_prom      = detail_df["fuga_pct_display"].mean()
        m1, m2 = st.columns(2)
        m3, m4 = st.columns(2)
        m1.metric("Afluencia",       fmt_pax(total_entradas))
        m2.metric("Meta afluencia",  fmt_pax(total_meta))
        m3.metric("Pérdida total",   fmt_pax(total_perdida))
        m4.metric("Fuga promedio",   fmt_fuga_pct(fuga_prom))

        if not bar_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=bar_df["estacion"].tolist(), y=bar_df["entradas"].tolist(),
                name="Afluencia", marker_color=EFE_BLUE,
            ))
            fig.add_trace(go.Bar(
                x=bar_df["estacion"].tolist(), y=bar_df["meta_entradas"].tolist(),
                name="Meta", marker_color=EFE_RED,
            ))
            fig.update_layout(
                title="Afluencia vs meta por estación",
                plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE,
                margin=dict(l=20, r=20, t=50, b=20), height=465,
                barmode="group", font=dict(color=TEXT_MAIN, size=PLOT_FONT_SIZE),
                title_font=dict(color=EFE_BLUE, size=PLOT_TITLE_SIZE),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig.update_xaxes(title="", tickangle=-90, categoryorder="array",
                             categoryarray=station_order)
            fig.update_yaxes(title="Pasajeros")
            show_plot(fig, width="stretch")

    st.markdown("</div></div>", unsafe_allow_html=True)


# ================================================================
# 32. RENDERER — OD Estaciones (Biotren)
# ================================================================
@maybe_fragment
def render_od_estaciones(data_path: Path, estaciones: pd.DataFrame):
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>OD Estaciones — Biotren</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>Análisis centrado en una estación: "
        "comportamiento horario, perfil de entradas/salidas y distribución "
        "espacial de viajes dentro del periodo seleccionado.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='map-note'><b>Enfoque:</b> la pestaña prioriza la lectura "
        "de la estación seleccionada con perfil horario, distribución de "
        "destinos/orígenes y mapas de burbujas.</div>",
        unsafe_allow_html=True,
    )

    try:
        od_df, od_path, od_missing, od_files, od_status = load_od_service_data("Biotren", str(data_path))
    except Exception as exc:
        st.error(f"Error cargando OD: {type(exc).__name__}: {exc}")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    folder_name = OD_SERVICE_CONFIG["Biotren"]["folder_candidates"][0]

    if od_status == "no_data" or od_df.empty:
        st.info(
            f"No se encontraron archivos CSV en **{folder_name}**. "
            f"Ruta buscada: **{od_path}**.", icon="ℹ️",
        )
        st.markdown("</div></div>", unsafe_allow_html=True)
        return
    if od_status == "unsupported_format" or od_missing:
        st.warning(
            f"Formato no compatible. Columnas faltantes: **{', '.join(od_missing)}**."
        )
        if od_files:
            st.caption(f"Archivos detectados: {len(od_files)} | carpeta: {od_path}")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_disp = sorted([x for x in od_df["fecha"].dropna().unique() if pd.notna(x)])
    if not fechas_disp:
        st.warning("No existen fechas válidas en la base OD cargada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # Selector de fecha
    fechas_set = set(fechas_disp)
    fecha_default = fechas_disp[-1]
    fecha_key = "od_bt_fecha_cal"
    prev = st.session_state.get(fecha_key)
    if isinstance(prev, date):
        fecha_default = prev if prev in fechas_set else min(
            fechas_disp, key=lambda d: abs((d - prev).days)
        )

    fecha_input = st.date_input(
        "📅 Fecha", value=fecha_default,
        min_value=fechas_disp[0], max_value=fechas_disp[-1],
        format="DD/MM/YYYY", key=fecha_key,
    )
    fecha_sel = fecha_input
    if fecha_sel not in fechas_set:
        fecha_sel = min(fechas_disp, key=lambda d: abs((d - fecha_sel).days))
        st.info(
            f"Fecha sin datos. Se usa la más cercana: "
            f"{pd.to_datetime(fecha_sel).strftime('%d-%m-%Y')}."
        )

    od_fecha = od_df[od_df["fecha"] == fecha_sel].copy()
    if od_fecha.empty:
        st.warning("No existen datos para la fecha seleccionada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # Buckets horarios
    granularity = "Bloques de 1 hora"
    od_fecha["entry_bucket"] = get_time_bucket_series(od_fecha["t_entrada_viaje"], granularity)
    od_fecha["exit_bucket"]  = get_time_bucket_series(od_fecha["t_salida_viaje"],  granularity)
    bucket_order = get_bucket_order(
        od_fecha["entry_bucket"].dropna().tolist() +
        od_fecha["exit_bucket"].dropna().tolist(),
        granularity,
    )
    if not bucket_order:
        st.warning("No existen bloques horarios válidos para la fecha seleccionada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    bucket_display = {b: b.replace("-", " a ") for b in bucket_order}
    default_blocks = st.session_state.get("od_bloques_selector_multi")
    if not isinstance(default_blocks, list) or not default_blocks:
        default_blocks = [bucket_order[0]]
    default_blocks = [b for b in default_blocks if b in bucket_order] or [bucket_order[0]]

    st.markdown("<div class='section-title'>Periodo horario de análisis</div>", unsafe_allow_html=True)
    bloques_sel = st.multiselect(
        "Bloques horarios de análisis",
        options=bucket_order, default=default_blocks,
        format_func=lambda x: bucket_display.get(x, x),
        key="od_bloques_selector_multi",
    )
    if not bloques_sel:
        st.warning("Seleccione al menos un bloque horario para continuar.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    bloques_sel = [b for b in bucket_order if b in bloques_sel]
    bloques_label = ", ".join(bucket_display.get(b, b) for b in bloques_sel)

    # Resúmenes globales del bloque
    entry_sum = (
        od_fecha[od_fecha["entry_bucket"].isin(bloques_sel)]
        .groupby("origen", as_index=False).size()
        .rename(columns={"origen": "estacion", "size": "entradas"})
        .sort_values(["entradas", "estacion"], ascending=[False, True])
    )
    exit_sum = (
        od_fecha[od_fecha["exit_bucket"].isin(bloques_sel)]
        .groupby("destino", as_index=False).size()
        .rename(columns={"destino": "estacion", "size": "salidas"})
        .sort_values(["salidas", "estacion"], ascending=[False, True])
    )

    top_entry = (
        f"{entry_sum.iloc[0]['estacion']} ({fmt_pax(entry_sum.iloc[0]['entradas'])})"
        if not entry_sum.empty else "-"
    )
    top_exit = (
        f"{exit_sum.iloc[0]['estacion']} ({fmt_pax(exit_sum.iloc[0]['salidas'])})"
        if not exit_sum.empty else "-"
    )
    total_entries = int(entry_sum["entradas"].sum()) if not entry_sum.empty else 0
    total_exits   = int(exit_sum["salidas"].sum())   if not exit_sum.empty else 0

    st.markdown(
        f"<div class='filters-summary'><strong>Bloques seleccionados:</strong> "
        f"{bloques_label}</div>",
        unsafe_allow_html=True,
    )
    rm1, rm2, rm3, rm4 = st.columns(4)
    rm1.metric("Entradas período", fmt_pax(total_entries))
    rm2.metric("Salidas período", fmt_pax(total_exits))
    rm3.metric("Mayor entrada", top_entry)
    rm4.metric("Mayor salida", top_exit)

    # Selector de estación
    station_ref = prepare_od_station_reference("Biotren", od_fecha, estaciones)
    station_candidates = sorted(
        set(od_fecha["origen"].dropna().astype(str))
        | set(od_fecha["destino"].dropna().astype(str))
    )
    if not station_candidates:
        st.warning("No existen estaciones disponibles para la selección actual.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    prev_st = st.session_state.get("od_station_selector")
    default_st = prev_st if prev_st in station_candidates else station_candidates[0]
    station_sel = st.selectbox(
        "Estación", options=station_candidates,
        index=station_candidates.index(default_st),
        key="od_station_selector",
    )

    # Perfil horario de la estación
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
    station_flow = pd.concat([station_entries, station_exits], ignore_index=True).dropna(subset=["bucket"])
    station_bucket_order = get_bucket_order(station_flow["bucket"].dropna().tolist(), granularity) or bucket_order

    st.markdown(
        "<div class='section-title'>Perfil horario de la estación seleccionada</div>",
        unsafe_allow_html=True,
    )
    show_plot(
        build_station_flow_chart(station_flow, station_bucket_order, station_sel, granularity),
        width="stretch",
    )

    total_entries_day = int(station_entries["cantidad"].sum()) if not station_entries.empty else 0
    total_exits_day   = int(station_exits["cantidad"].sum())   if not station_exits.empty else 0
    peak_entry = station_entries.sort_values(["cantidad", "bucket"], ascending=[False, True]).head(1)
    peak_exit  = station_exits.sort_values(["cantidad", "bucket"], ascending=[False, True]).head(1)
    peak_entry_lbl = (
        f"{bucket_display.get(peak_entry.iloc[0]['bucket'], peak_entry.iloc[0]['bucket'])} "
        f"({fmt_pax(peak_entry.iloc[0]['cantidad'])})"
        if not peak_entry.empty else "-"
    )
    peak_exit_lbl = (
        f"{bucket_display.get(peak_exit.iloc[0]['bucket'], peak_exit.iloc[0]['bucket'])} "
        f"({fmt_pax(peak_exit.iloc[0]['cantidad'])})"
        if not peak_exit.empty else "-"
    )

    sm1, sm2, sm3, sm4 = st.columns(4)
    sm1.metric("Entradas día", fmt_pax(total_entries_day))
    sm2.metric("Salidas día", fmt_pax(total_exits_day))
    sm3.metric("Hora punta entradas", peak_entry_lbl)
    sm4.metric("Hora punta salidas", peak_exit_lbl)

    # ---------- Índice de polaridad de la estación ----------
    if total_entries_day + total_exits_day > 0:
        polaridad = (
            (total_entries_day - total_exits_day)
            / (total_entries_day + total_exits_day) * 100
        )
        if polaridad > 30:
            tipo_estacion = "🚉 Estación de origen"
            descripcion = (
                "Más entradas que salidas: la mayoría de los pasajeros "
                "comienza su viaje aquí (zona residencial o de origen)."
            )
            color_borde = EFE_BLUE
        elif polaridad < -30:
            tipo_estacion = "🏢 Estación de destino"
            descripcion = (
                "Más salidas que entradas: la mayoría de los pasajeros "
                "termina su viaje aquí (zona laboral, comercial o destino)."
            )
            color_borde = EFE_RED
        else:
            tipo_estacion = "🔄 Estación de transferencia/balanceada"
            descripcion = (
                "Flujo equilibrado de entradas y salidas: estación de paso "
                "o con doble función origen/destino."
            )
            color_borde = SUCCESS

        polaridad_html = (
            f"<div class='efe-summary-row' style='margin-top:0.45rem;'>"
            f"<div class='efe-summary-card' "
            f"style='border-left: 4px solid {color_borde}; grid-column: span 2;'>"
            f"<div class='efe-summary-label'>{tipo_estacion}</div>"
            f"<div class='efe-summary-value'>{polaridad:+.1f}%</div>"
            f"<div class='efe-summary-sub'>{descripcion}</div>"
            f"</div>"
            f"<div class='efe-summary-card'>"
            f"<div class='efe-summary-label'>Índice polaridad</div>"
            f"<div class='efe-summary-value'>{polaridad:+.0f}%</div>"
            f"<div class='efe-summary-sub'>(entradas − salidas)/(entradas + salidas)</div>"
            f"</div>"
            f"</div>"
        )
        st.markdown(polaridad_html, unsafe_allow_html=True)

    # Destinos / orígenes en el período
    dest_df = (
        od_fecha[
            (od_fecha["origen"].astype(str) == str(station_sel)) &
            (od_fecha["entry_bucket"].isin(bloques_sel))
        ]
        .groupby("destino", as_index=False).size()
        .rename(columns={"size": "viajes"})
        .sort_values(["viajes", "destino"], ascending=[False, True])
    )
    orig_df = (
        od_fecha[
            (od_fecha["destino"].astype(str) == str(station_sel)) &
            (od_fecha["exit_bucket"].isin(bloques_sel))
        ]
        .groupby("origen", as_index=False).size()
        .rename(columns={"size": "viajes"})
        .sort_values(["viajes", "origen"], ascending=[False, True])
    )

    if not dest_df.empty:
        dest_df = dest_df[dest_df["destino"].astype(str) != str(station_sel)].copy()
    if not orig_df.empty:
        orig_df = orig_df[orig_df["origen"].astype(str) != str(station_sel)].copy()

    salidas_est  = int(dest_df["viajes"].sum()) if not dest_df.empty else 0
    llegadas_est = int(orig_df["viajes"].sum()) if not orig_df.empty else 0
    pri_dest = (f"{dest_df.iloc[0]['destino']} ({fmt_pax(dest_df.iloc[0]['viajes'])})"
                if not dest_df.empty else "-")
    pri_orig = (f"{orig_df.iloc[0]['origen']} ({fmt_pax(orig_df.iloc[0]['viajes'])})"
                if not orig_df.empty else "-")

    st.markdown(
        "<div class='section-title'>Perfil de viajes de la estación en el periodo seleccionado</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='section-subtitle'><b>{station_sel}</b> · Periodo: {bloques_label} · "
        f"Salidas desde estación: {fmt_pax(salidas_est)} · "
        f"Llegadas hacia estación: {fmt_pax(llegadas_est)}</div>",
        unsafe_allow_html=True,
    )
    dm1, dm2 = st.columns(2)
    dm1.metric("Principal destino", pri_dest)
    dm2.metric("Principal origen", pri_orig)

    bar_l, bar_r = st.columns(2)
    with bar_l:
        fig = build_od_station_bar_chart(
            dest_df, "destino", station_ref,
            f"Destinos desde {station_sel} | {bloques_label}", EFE_BLUE,
        )
        if fig:
            show_plot(fig, width="stretch")
        else:
            st.info("No existen viajes desde la estación en el periodo seleccionado.")
    with bar_r:
        fig = build_od_station_bar_chart(
            orig_df, "origen", station_ref,
            f"Orígenes hacia {station_sel} | {bloques_label}", EFE_RED,
        )
        if fig:
            show_plot(fig, width="stretch")
        else:
            st.info("No existen viajes hacia la estación en el periodo seleccionado.")

    map_l, map_r = st.columns(2)
    with map_l:
        fig = build_od_bubble_map(
            dest_df, "destino", station_ref, station_sel,
            f"Mapa de destinos desde {station_sel} | {bloques_label}", EFE_BLUE,
        )
        if fig:
            show_plot(fig, width="stretch")
        else:
            st.info("Sin coordenadas válidas para el mapa de destinos.")
    with map_r:
        fig = build_od_bubble_map(
            orig_df, "origen", station_ref, station_sel,
            f"Mapa de orígenes hacia {station_sel} | {bloques_label}", EFE_RED,
        )
        if fig:
            show_plot(fig, width="stretch")
        else:
            st.info("Sin coordenadas válidas para el mapa de orígenes.")

    if od_files:
        st.caption(f"Archivos OD cargados: {len(od_files)} | carpeta: {od_path}")
    st.markdown("</div></div>", unsafe_allow_html=True)

# ================================================================
# 33. MENÚ DE CABECERA — TEMA + ⋮ (LIMPIAR CACHÉ)
# ================================================================

def clear_all_caches() -> None:
    """Limpia todo el caché de la aplicación, incluyendo el de sesión."""
    try:
        st.cache_data.clear()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    # Eliminar caches manuales en session_state
    keys_to_drop = [k for k in list(st.session_state.keys()) if k.startswith("_")]
    for k in keys_to_drop:
        try:
            del st.session_state[k]
        except KeyError:
            pass


def render_header():
    """
    Cabecera con título, selector de tema y menú ⋮.
    El menú ⋮ contiene: Limpiar caché y refrescar datos.
    """
    st.session_state.setdefault("dashboard_theme_mode", "☀️ Claro")

    header_left, header_theme, header_menu = st.columns([4.6, 1.1, 0.4])

    with header_theme:
        theme_mode = option_selector(
            "Tema", ["☀️ Claro", "🌙 Oscuro"],
            key="dashboard_theme_mode_selector",
            default=st.session_state.get("dashboard_theme_mode", "☀️ Claro"),
            horizontal=True,
        ) or st.session_state.get("dashboard_theme_mode", "☀️ Claro")
        st.session_state["dashboard_theme_mode"] = theme_mode

    with header_menu:
        st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)
        # Popover con menú de opciones (fallback a expander)
        popover_ctx = st.popover if hasattr(st, "popover") else st.expander
        kw = {} if hasattr(st, "popover") else {"expanded": False}
        with popover_ctx("⋮", **kw):
            st.markdown(
                "<div style='font-size:0.8rem; color:#6B7280; margin-bottom:0.4rem;'>"
                "Acciones de mantenimiento"
                "</div>",
                unsafe_allow_html=True,
            )
            if st.button("🧹 Limpiar caché y recargar",
                         key="btn_clear_cache",
                         width="stretch"):
                clear_all_caches()
                st.success("Caché limpiada. Recargando…")
                st.rerun()
            st.markdown(
                "<div style='height:0.4rem'></div>",
                unsafe_allow_html=True,
            )
            # Botón de exportar a PDF de la vista actual.
            # Usa el diálogo de impresión del navegador (sin dependencias);
            # el usuario elige "Guardar como PDF" como destino de impresión.
            st.markdown(
                """
                <button onclick="window.parent.print();"
                        style="width:100%; background:white; border:1px solid #D7E0EA;
                               color:#002857; font-weight:700; padding:0.5rem 0.85rem;
                               border-radius:8px; cursor:pointer; font-size:0.9rem;">
                    📄 Exportar vista a PDF
                </button>
                """,
                unsafe_allow_html=True,
            )
            st.caption(
                "Imprime la vista actual; en el diálogo del navegador "
                "elija 'Guardar como PDF' como destino."
            )
            st.markdown(
                "<div style='height:0.4rem'></div>",
                unsafe_allow_html=True,
            )
            # Modo seguro: pausa los cálculos pesados (cruce torniquetes,
            # promedios mensuales) hasta que el usuario decida activarlos.
            # Útil cuando el usuario quiere navegar rápido entre filtros
            # sin esperar a que terminen los cálculos en cada cambio.
            safe_mode = st.toggle(
                "🛡️ Modo seguro (pausa cálculos pesados)",
                value=st.session_state.get("safe_mode", False),
                key="safe_mode_toggle",
                help=(
                    "Cuando está activado, los cálculos más costosos "
                    "(cruce torniquetes, promedios mensuales) NO se "
                    "ejecutan automáticamente al cambiar filtros. "
                    "Útil para navegar rápido sin esperar."
                ),
            )
            st.session_state["safe_mode"] = bool(safe_mode)
            st.caption(
                "Use 'Limpiar caché' si el dashboard se cierra "
                "inesperadamente. Use 'Modo seguro' para navegar rápido."
            )

    # Aplicar paleta y CSS según tema seleccionado
    is_dark = "Oscuro" in st.session_state["dashboard_theme_mode"]
    apply_runtime_palette(DARK_COLORS if is_dark else LIGHT_COLORS)
    if is_dark:
        st.markdown(build_dark_overrides_css(COLORS), unsafe_allow_html=True)

    with header_left:
        st.markdown("<div class='hero-minimal'>", unsafe_allow_html=True)
        logo_col, title_col = st.columns([0.72, 5.0])
        with logo_col:
            for logo_path in [
                Path(__file__).resolve().parent / "assets" / "logoefe-azul.png",
                Path(__file__).resolve().parent / "logoefe-azul.png",
            ]:
                if logo_path.exists():
                    st.image(str(logo_path), width="stretch")
                    break
        with title_col:
            st.markdown(
                "<div class='main-title'>KPIs e Iniciativas — Gerencia de Pasajeros</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<div class='subtitle'>Panel ejecutivo para monitorear "
                "desempeño, perfiles de carga y análisis por estación.</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)


# ================================================================
# 34. PREPARACIÓN DE DATOS DE INICIATIVAS
# ================================================================
def prepare_iniciativas(iniciativas: pd.DataFrame, personas: pd.DataFrame) -> pd.DataFrame:
    """Une responsable + flags de criticidad."""
    personas_activas = personas[personas["activo"] == 1].copy()
    out = iniciativas.merge(
        personas_activas[["id_persona", "nombre"]],
        how="left", left_on="responsable_id", right_on="id_persona",
    )

    # Renombrar columnas con sufijos del merge
    if "nombre_y" in out.columns:
        out = out.rename(columns={"nombre_y": "responsable"})
    if "nombre_x" in out.columns:
        out = out.rename(columns={"nombre_x": "nombre_iniciativa"})
    elif "nombre" in out.columns and "responsable" not in out.columns:
        out = out.rename(columns={"nombre": "responsable"})
    if "nombre" in out.columns and "nombre_iniciativa" not in out.columns:
        out = out.rename(columns={"nombre": "nombre_iniciativa"})
    if "responsable" not in out.columns:
        out["responsable"] = "-"
    if "nombre_iniciativa" not in out.columns:
        out["nombre_iniciativa"] = "-"

    today = date.today()
    out["vencida"] = (
        pd.to_datetime(out["fecha_fin"], errors="coerce") < pd.Timestamp(today)
    ) & out["fecha_fin"].notna()
    estado_norm = out["estado"].fillna("").astype(str).str.strip()
    out["critica"] = (
        (estado_norm == "Atrasada") |
        (out["vencida"] & (estado_norm != "Finalizada"))
    )
    return out


# ================================================================
# 35. NAVEGACIÓN PRINCIPAL
# ================================================================
SERVICE_NAV_OPTIONS = [
    "Biotren", "Tren Araucanía", "Laja Talcahuano",
    "Llanquihue Puerto Montt", "Personas",
]
BIOTREN_DETAIL_PAGES = ["KPIs", "Perfil de Carga", "Análisis por Estación"]
STANDARD_SERVICE_PAGES = ["KPIs"]


def render_navigation() -> tuple[str, str]:
    """Devuelve (root_sel, section_sel)."""
    with st.container():
        st.markdown("<div class='nav-panel'>", unsafe_allow_html=True)
        root_sel = option_selector(
            "Servicio / vista", SERVICE_NAV_OPTIONS,
            key="main_root_selector", default="Biotren",
            horizontal=True,
        )
        if root_sel == "Personas":
            section_sel = "Personas"
        else:
            sub = BIOTREN_DETAIL_PAGES if root_sel == "Biotren" else STANDARD_SERVICE_PAGES
            label = option_selector(
                "Navegación", sub, key="main_service_page_selector",
                default=sub[0], horizontal=True,
            )
            section_map = {
                "KPIs": "KPIs por Servicio",
                "Perfil de Carga": "Perfil de Carga",
                "Análisis por Estación": "OD Estaciones",
            }
            section_sel = section_map.get(label, "KPIs por Servicio")
        st.markdown("</div>", unsafe_allow_html=True)
    return root_sel, section_sel


# ================================================================
# 36. MAIN
# ================================================================
def main():
    # CSS global (siempre se aplica)
    render_global_css()

    # Carga de datos (necesario para conocer la fecha de los datos)
    try:
        kpis, iniciativas, personas, servicios, estaciones, afluencia_estacion, data_path = load_data()
    except Exception as exc:
        # Si falla la carga, igual mostramos cabecera básica para acceder al menú ⋮
        render_header()
        st.error(
            f"Error fatal cargando datos base: {type(exc).__name__}: {exc}. "
            f"Use el menú ⋮ → 'Limpiar caché' para reintentar."
        )
        st.stop()

    # Cabecera
    render_header()

    # Preparar iniciativas
    iniciativas = prepare_iniciativas(iniciativas, personas)

    # Lista de servicios disponibles
    if not servicios.empty and "servicio" in servicios.columns:
        servicios_activos = servicios.copy()
        if "activo" in servicios_activos.columns:
            servicios_activos = servicios_activos[servicios_activos["activo"] == 1]
        if "orden" in servicios_activos.columns:
            servicios_activos = servicios_activos.sort_values("orden")
        servicios_lista = servicios_activos["servicio"].dropna().astype(str).tolist()
    else:
        servicios_lista = sorted(kpis["servicio"].dropna().astype(str).unique().tolist())

    # Períodos disponibles
    periodos = sorted(kpis["periodo"].dropna().astype(str).unique().tolist())
    default_period_index = len(periodos) - 1 if periodos else 0

    # Filtros para iniciativas
    estados_ini  = sorted(iniciativas["estado"].dropna().astype(str).unique().tolist())
    prioridades  = sorted(iniciativas["prioridad"].dropna().astype(str).unique().tolist())
    responsables = sorted(iniciativas["responsable"].dropna().astype(str).unique().tolist())

    st.session_state.setdefault("estado_body_filter",      estados_ini)
    st.session_state.setdefault("prioridad_body_filter",   prioridades)
    st.session_state.setdefault("responsable_body_filter", responsables)

    # Navegación
    root_sel, section_sel = render_navigation()
    selected_service_context = root_sel if root_sel != "Personas" else None

    # CRÍTICO: detectar cambio de página y liberar memoria intermedia.
    # Cuando el usuario navega de "OD Estaciones" (con mapas Plotly) a
    # "Perfil de Carga", los traces y figures de mapa permanecen en
    # memoria de Plotly hasta el próximo gc.collect(). En Streamlit Cloud
    # con Python 3.14 + Plotly 6.7 + Pandas 3.0 esto puede acumular
    # cientos de MB de objetos basura entre re-runs y disparar OOM.
    last_section_key = "_last_section_rendered"
    last_section = st.session_state.get(last_section_key)
    if last_section and last_section != section_sel:
        # Cambió de página: limpiar caches volátiles y forzar gc
        for k in list(st.session_state.keys()):
            if k.startswith("_turnstile_match_cache"):
                try:
                    del st.session_state[k]
                except KeyError:
                    pass
        try:
            gc.collect()
        except Exception:
            pass
    st.session_state[last_section_key] = section_sel

    # Dispatch — cada renderer envuelto en try/except para que un crash en
    # una sección no cierre todo el dashboard. Se distingue cuidadosamente
    # entre crashes reales y RerunException/StopException que dispara
    # Streamlit cuando el usuario cambia un widget.
    try:
        if section_sel == "KPIs por Servicio":
            render_resumen_ejecutivo(
                kpis, kpis, servicios_lista, periodos,
                default_period_index,
                target_service=selected_service_context,
            )
        elif section_sel == "Personas":
            render_personas(
                iniciativas, servicios_lista,
                estados_ini, prioridades, responsables,
            )
        elif section_sel == "Perfil de Carga":
            render_perfil_carga(data_path, default_service=selected_service_context)
        elif section_sel == "OD Estaciones":
            render_od_estaciones(data_path, estaciones)
        elif section_sel == "Estaciones":
            render_detalle_servicio(servicios_lista, estaciones, afluencia_estacion)
    except BaseException as exc:
        # Las excepciones internas de Streamlit (rerun/stop) NO son crashes:
        # Streamlit las usa para abortar el script en curso cuando el
        # usuario cambia un widget. Las dejamos propagar normalmente.
        if is_streamlit_internal_exception(exc):
            raise
        import traceback
        st.error(
            f"Ocurrió un error inesperado al mostrar la sección '{section_sel}'. "
            f"Detalle: {type(exc).__name__}: {exc}"
        )
        with st.expander("Ver traza técnica"):
            st.code(traceback.format_exc())
        st.info(
            "Sugerencia: abra el menú ⋮ en la esquina superior derecha y "
            "use 'Limpiar caché y recargar'. Si el error persiste, verifique "
            "la integridad de los archivos CSV en sus carpetas."
        )

    # Liberar memoria al final de cada re-run para evitar acumulación
    # cuando el usuario cambia filtros rápido en sucesión.
    release_memory()

    # Pie de página
    st.markdown("---")
    st.caption(
        "Los archivos CSV se leen automáticamente desde el repositorio de GitHub, "
        "incluyendo carpetas dedicadas para perfiles de carga y datos OD por servicio."
    )


# Streamlit ejecuta el archivo de forma directa (sin importar como módulo
# desde otro punto). Se invoca main() al cargar el script.
main()
