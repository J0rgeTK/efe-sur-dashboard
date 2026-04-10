
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date
import unicodedata
import math
import plotly.express as px
import plotly.graph_objects as go

# Nota: para reducir al máximo el chrome superior en Streamlit Community Cloud,
# este archivo está pensado para complementarse con .streamlit/config.toml
# usando [client] toolbarMode = "minimal".

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
# PALETA DE COLORES
# =========================================================
EFE_BLUE = "#002857"
EFE_RED = "#FF0016"
EFE_WHITE = "#FFFFFF"
BG_LIGHT = "#F4F6F8"
BORDER = "#D9E1E8"
TEXT_MAIN = "#1F2937"
TEXT_MUTED = "#6B7280"
SUCCESS = "#0F766E"
WARNING = "#D97706"
DANGER = "#B91C1C"
MAP_SCALE = "Reds"

RURAL_SERVICES = ["Laja Talcahuano", "Tren Araucanía", "Llanquihue Puerto Montt"]

# =========================================================
# ESTILOS CSS
# =========================================================
_css = """
<style>
.stApp {
    background:
        radial-gradient(circle at top left, rgba(0, 40, 87, 0.05) 0%, rgba(0, 40, 87, 0.00) 22%),
        linear-gradient(180deg, #F7F9FC 0%, #EEF3F8 100%);
    color: __TEXT_MAIN__;
}

header[data-testid="stHeader"] {
    display: none !important;
}

div[data-testid="stToolbar"] {
    display: none !important;
}

div[data-testid="stDecoration"] {
    display: none !important;
}

div[data-testid="stStatusWidget"] {
    display: none !important;
}

div[data-testid="collapsedControl"] {
    display: none !important;
}

section[data-testid="stSidebar"] {
    display: none !important;
}

#MainMenu {
    visibility: hidden;
}

footer {
    visibility: hidden;
    height: 0;
}

.block-container {
    padding-top: 0.35rem;
    padding-bottom: 0.8rem;
    padding-left: 1.4rem;
    padding-right: 1.4rem;
}

.hero-shell {
    background: linear-gradient(135deg, rgba(255,255,255,0.97) 0%, rgba(245,249,253,0.97) 100%);
    border: 1px solid #DDE6EF;
    border-radius: 28px;
    padding: 0.95rem 1.1rem 0.9rem 1.1rem;
    box-shadow: 0 18px 44px rgba(0, 40, 87, 0.08);
    margin-bottom: 0.5rem;
}

.hero-kicker {
    display: inline-block;
    background: rgba(0, 40, 87, 0.08);
    color: __EFE_BLUE__;
    border: 1px solid rgba(0, 40, 87, 0.10);
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    margin-bottom: 0.5rem;
}

.hero-side-note {
    color: __TEXT_MUTED__;
    font-size: 0.82rem;
    margin-top: 0.35rem;
}

.main-title {
    font-size: 2.35rem;
    font-weight: 850;
    color: __EFE_BLUE__;
    margin-top: 0.05rem;
    margin-bottom: 0.18rem;
    line-height: 1.08;
}

.subtitle {
    font-size: 0.94rem;
    color: __TEXT_MUTED__;
    margin-top: 0.25rem;
    margin-bottom: 0.05rem;
}

.top-period-wrapper {
    margin-top: 0.2rem;
}

.section-shell {
    background: rgba(255,255,255,0.96);
    border: 1px solid #DFE7EF;
    border-radius: 24px;
    padding: 0.9rem 0.95rem 0.85rem 0.95rem;
    box-shadow: 0 10px 26px rgba(0, 40, 87, 0.06);
    margin: 0.25rem 0 0.8rem 0;
}

.section-title {
    font-size: 1.06rem;
    font-weight: 800;
    color: __EFE_BLUE__;
    margin-top: 0rem;
    margin-bottom: 0.5rem;
}

.section-subtitle {
    font-size: 0.86rem;
    color: __TEXT_MUTED__;
    margin-top: -0.3rem;
    margin-bottom: 0.5rem;
}

.efe-card {
    background: linear-gradient(180deg, #FFFFFF 0%, #FCFDFE 100%);
    border: 1px solid #DCE5EE;
    border-radius: 20px;
    padding: 0.9rem 0.95rem 0.8rem 0.95rem;
    box-shadow: 0 12px 28px rgba(0, 40, 87, 0.06);
    min-height: 136px;
    transition: transform 0.16s ease, box-shadow 0.16s ease;
    margin-bottom: 0.45rem;
}

.efe-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 16px 34px rgba(0, 40, 87, 0.10);
}

.efe-card-title {
    font-size: 0.88rem;
    color: __TEXT_MUTED__;
    margin-bottom: 0.45rem;
    font-weight: 600;
}

.efe-card-value {
    font-size: 2.0rem;
    font-weight: 850;
    color: __EFE_BLUE__;
    line-height: 1.05;
    margin-bottom: 0.18rem;
}

.efe-card-meta {
    font-size: 0.92rem;
    color: __TEXT_MAIN__;
    margin-bottom: 0.22rem;
}

.efe-card-delta {
    font-size: 0.92rem;
    font-weight: 700;
}

.efe-observation {
    background: #FFF7ED;
    border: 1px solid #FED7AA;
    border-radius: 14px;
    padding: 0.72rem 0.88rem;
    font-size: 0.84rem;
    color: __TEXT_MAIN__;
    margin-top: 0.25rem;
    margin-bottom: 0.1rem;
    line-height: 1.38;
}

.efe-observation strong {
    color: __WARNING__;
}

.efe-observation-empty {
    background: #ECFDF5;
    border: 1px solid #A7F3D0;
    border-radius: 14px;
    padding: 0.72rem 0.88rem;
    font-size: 0.84rem;
    color: __TEXT_MAIN__;
    margin-top: 0.25rem;
    margin-bottom: 0.1rem;
    line-height: 1.38;
}

.efe-observation-empty strong {
    color: __SUCCESS__;
}

.service-title {
    font-size: 1.05rem;
    font-weight: 850;
    color: __EFE_BLUE__;
    margin: 0.15rem 0 0.75rem 0;
    padding-bottom: 0.45rem;
    border-bottom: 2px solid #E6EDF5;
}

.small-note {
    color: __TEXT_MUTED__;
    font-size: 0.8rem;
}

.map-note {
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 16px;
    padding: 0.78rem 0.95rem;
    font-size: 0.85rem;
    color: __TEXT_MAIN__;
    margin-bottom: 0.55rem;
    line-height: 1.4;
}

.toolbar-panel {
    background: rgba(255,255,255,0.96);
    border: 1px solid #DFE7EF;
    border-radius: 22px;
    padding: 0.7rem 0.9rem;
    margin: 0.08rem 0 0.55rem 0;
    box-shadow: 0 10px 24px rgba(0, 40, 87, 0.06);
}

.toolbar-label {
    font-size: 0.74rem;
    font-weight: 800;
    color: __TEXT_MUTED__;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.3rem;
}

.filters-summary {
    color: __TEXT_MAIN__;
    font-size: 0.93rem;
    margin-top: 0.1rem;
    line-height: 1.4;
}

.filters-summary strong {
    color: __EFE_BLUE__;
}

.filter-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-top: 0.4rem;
}

.filter-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.38rem 0.7rem;
    border-radius: 999px;
    background: #F1F5F9;
    border: 1px solid #D8E2EC;
    color: __EFE_BLUE__;
    font-size: 0.8rem;
    font-weight: 700;
}

.filter-chip.soft {
    background: #EEF4FB;
}



.nav-panel {
    background: rgba(255,255,255,0.97);
    border: 1px solid #DFE7EF;
    border-radius: 22px;
    padding: 0.65rem 0.85rem 0.2rem 0.85rem;
    margin: 0.08rem 0 0.6rem 0;
    box-shadow: 0 12px 26px rgba(0, 40, 87, 0.08);
    backdrop-filter: blur(10px);
}

.sticky-nav-anchor {
    display: block;
    height: 0;
    margin: 0;
    padding: 0;
}

div[data-testid="stVerticalBlock"]:has(.sticky-nav-anchor) {
    position: sticky;
    top: 0.35rem;
    z-index: 999;
    background: linear-gradient(180deg, rgba(247,249,252,0.99) 0%, rgba(247,249,252,0.96) 85%, rgba(247,249,252,0.0) 100%);
    padding-top: 0.2rem;
    padding-bottom: 0.15rem;
}

.content-panel {
    background: transparent;
    animation: fadeSlideIn 0.22s ease-out;
}

@keyframes fadeSlideIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
}

div[data-baseweb="select"] > div {
    border-radius: 16px !important;
    border-color: #D7E0EA !important;
    background: rgba(255,255,255,0.98) !important;
    min-height: 48px !important;
    box-shadow: none !important;
}

div[data-baseweb="tag"] {
    border-radius: 999px !important;
}

div[data-testid="stMetric"] {
    background: linear-gradient(180deg, #FFFFFF 0%, #FCFDFE 100%);
    border: 1px solid #DFE7EF;
    padding: 0.7rem 0.85rem;
    border-radius: 18px;
    box-shadow: 0 10px 24px rgba(0, 40, 87, 0.05);
}

div[data-testid="stDataFrame"] {
    border: 1px solid #DFE7EF;
    border-radius: 18px;
    overflow: hidden;
    box-shadow: 0 10px 24px rgba(0, 40, 87, 0.05);
}

div[data-testid="stPlotlyChart"] {
    background: rgba(255,255,255,0.98);
    border: 1px solid #DFE7EF;
    border-radius: 22px;
    padding: 0.3rem;
    box-shadow: 0 10px 24px rgba(0, 40, 87, 0.05);
    margin-bottom: 0.18rem;
}

div[data-testid="stAlert"] {
    border-radius: 16px;
    border: 1px solid #D7E0EA;
}

.stButton > button,
.stDownloadButton > button {
    border-radius: 999px !important;
    border: 1px solid #D7E0EA !important;
    background: #FFFFFF !important;
    color: __EFE_BLUE__ !important;
    font-weight: 700 !important;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    border-color: __EFE_BLUE__ !important;
    color: __EFE_BLUE__ !important;
    box-shadow: 0 8px 18px rgba(0, 40, 87, 0.08);
}
</style>
"""

st.markdown(
    _css
    .replace("__TEXT_MAIN__", TEXT_MAIN)
    .replace("__TEXT_MUTED__", TEXT_MUTED)
    .replace("__EFE_BLUE__", EFE_BLUE)
    .replace("__SUCCESS__", SUCCESS)
    .replace("__WARNING__", WARNING),
    unsafe_allow_html=True,
)



# =========================================================
# UTILIDADES
# =========================================================
def normalize_text(text):
    text = "" if text is None else str(text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.strip().lower()


def abbreviate_station_label(name):
    raw = "" if name is None else str(name).strip()
    if raw == "":
        return ""

    cleaned = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.replace("-", " ").replace("/", " ")
    stopwords = {"de", "del", "la", "las", "los", "y", "el", "san", "santa"}
    parts = [p for p in cleaned.split() if p and p.lower() not in stopwords]

    if len(parts) >= 2:
        abbr = "".join(part[0] for part in parts[:3]).upper()
        if len(abbr) >= 2:
            return abbr

    token = parts[0] if parts else cleaned.replace(" ", "")
    token = "".join(ch for ch in token if ch.isalnum())
    return token[:3].upper()


def compact_station_name(name):
    raw = "" if name is None else str(name).strip()
    if raw == "":
        return ""

    parts = raw.split()
    if len(raw) <= 14:
        return raw.upper()
    if len(parts) >= 2:
        first = parts[0]
        second = parts[1]
        if len(first) <= 9:
            second_short = second if len(second) <= 5 else second[:5] + "."
            return f"{first} {second_short}".upper()
        return f"{first[:9]}. {second[:4]}.".upper()
    return (raw[:14] + "…").upper()


def build_station_map_text(name, pax_value):
    return f"{compact_station_name(name)}<br>{fmt_pax(pax_value)}"


def is_occupancy_rate_kpi(kpi_name):
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


def fmt_number(value, unit="", kpi_name=None):
    if pd.isna(value):
        return "-"
    if unit == "%" or is_occupancy_rate_kpi(kpi_name):
        value = maybe_scale_percent(value)
    if unit == "CLP":
        return f"$ {value:,.0f}".replace(",", ".")
    if unit == "%" or is_occupancy_rate_kpi(kpi_name):
        return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")
    if unit == "pax":
        return f"{value:,.0f}".replace(",", ".")
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(value):
    if pd.isna(value):
        return "-"
    return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pax(value):
    if pd.isna(value):
        return "-"
    return f"{float(value):,.0f}".replace(",", ".")


def fmt_fuga_pct(value):
    if pd.isna(value):
        return "-"
    value = maybe_scale_percent(value)
    return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def format_service_id(value):
    if pd.isna(value):
        return "-"
    try:
        value_float = float(value)
        if value_float.is_integer():
            return str(int(value_float))
        return f"{value_float:g}"
    except Exception:
        return str(value).strip()


PROFILE_SERVICE_CONFIG = {
    "Biotren": {
        "folder_candidates": ["perfil_bt", ".perfil-bt", ".perfil_bt"],
        "description": "Formato base implementado para Biotren.",
    },
    "Tren Araucanía": {
        "folder_candidates": ["perfil_ta", "perfil_tren_araucania", ".perfil-ta", ".perfil_tren_araucania"],
        "description": "Preparado para futura incorporación del formato de perfil de carga.",
    },
    "Laja Talcahuano": {
        "folder_candidates": ["perfil_lt", "perfil_laja_talcahuano", ".perfil-lt", ".perfil_laja_talcahuano"],
        "description": "Preparado para futura incorporación del formato de perfil de carga.",
    },
    "Llanquihue Puerto Montt": {
        "folder_candidates": ["perfil_lpm", "perfil_llanquihue_puerto_montt", ".perfil-lpm", ".perfil_llanquihue_puerto_montt"],
        "description": "Preparado para futura incorporación del formato de perfil de carga.",
    },
}


def get_profile_folder_candidates(service_name, data_path):
    base = Path(__file__).resolve().parent
    config = PROFILE_SERVICE_CONFIG.get(service_name, {})
    folder_names = config.get("folder_candidates", [])
    candidates = []
    for folder_name in folder_names:
        candidates.extend([
            base / folder_name,
            data_path / folder_name,
        ])

    unique = []
    seen = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def get_default_profile_folder_name(service_name):
    config = PROFILE_SERVICE_CONFIG.get(service_name, {})
    folder_names = config.get("folder_candidates", [])
    return folder_names[0] if folder_names else "perfil_carga"


def get_station_order_from_profile(df):
    if df.empty or "estacion" not in df.columns:
        return []
    temp = df.copy()
    temp["event_time"] = temp["t_arr_est"].fillna(temp["t_dep_est"])
    temp["estacion"] = temp["estacion"].fillna("").astype(str).str.strip()
    temp = temp[temp["estacion"] != ""]

    if temp.empty:
        return []

    if temp["event_time"].notna().any():
        order = (
            temp.groupby("estacion", as_index=False)["event_time"]
            .min()
            .sort_values(["event_time", "estacion"])
        )["estacion"].tolist()
    else:
        order = temp["estacion"].tolist()

    return list(dict.fromkeys(order))


def build_perfil_carga_chart(service_df, titulo):
    plot_df = service_df.copy()
    station_order = get_station_order_from_profile(plot_df)
    if station_order:
        plot_df["estacion"] = pd.Categorical(plot_df["estacion"], categories=station_order, ordered=True)
        plot_df = plot_df.sort_values("estacion")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=plot_df["estacion"],
            y=plot_df["B_embarque"],
            name="Suben",
            marker_color=EFE_BLUE,
            hovertemplate="<b>%{x}</b><br>Suben: %{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=plot_df["estacion"],
            y=plot_df["D_bajadas"],
            name="Bajan",
            marker_color=EFE_RED,
            hovertemplate="<b>%{x}</b><br>Bajan: %{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df["estacion"],
            y=plot_df["L_out_abordo"],
            mode="lines+markers",
            name="A bordo",
            line=dict(color=SUCCESS, width=3),
            marker=dict(size=8),
            hovertemplate="<b>%{x}</b><br>A bordo: %{y:,.0f}<extra></extra>",
        )
    )

    capacidad_series = pd.to_numeric(plot_df.get("capacidad_tren"), errors="coerce")
    if capacidad_series.notna().any():
        capacidad = float(capacidad_series.dropna().iloc[0])
        fig.add_trace(
            go.Scatter(
                x=plot_df["estacion"],
                y=[capacidad] * len(plot_df),
                mode="lines",
                name="Capacidad tren",
                line=dict(color=TEXT_MUTED, width=2, dash="dash"),
                hovertemplate="Capacidad: %{y:,.0f}<extra></extra>",
            )
        )

    fig.update_layout(
        title=titulo,
        plot_bgcolor=EFE_WHITE,
        paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20),
        height=460,
        barmode="group",
        font=dict(color=TEXT_MAIN),
        title_font=dict(color=EFE_BLUE, size=16),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array", categoryarray=station_order if station_order else None)
    fig.update_yaxes(title="Pasajeros")
    return fig


def build_perfil_abordo_comparativo_chart(day_df, titulo):
    plot_df = day_df.copy()
    if plot_df.empty:
        fig = go.Figure()
        fig.update_layout(
            title=titulo,
            plot_bgcolor=EFE_WHITE,
            paper_bgcolor=EFE_WHITE,
            margin=dict(l=20, r=20, t=55, b=20),
            height=520,
        )
        return fig

    plot_df["event_time"] = plot_df["t_arr_est"].fillna(plot_df["t_dep_est"])
    station_order = get_station_order_from_profile(plot_df)
    if station_order:
        plot_df["estacion"] = pd.Categorical(plot_df["estacion"], categories=station_order, ordered=True)

    servicio_order = (
        plot_df.groupby("servicio_label", as_index=False)["event_time"]
        .min()
        .sort_values(["event_time", "servicio_label"])["servicio_label"]
        .astype(str)
        .tolist()
    )
    if servicio_order:
        plot_df["servicio_label"] = pd.Categorical(plot_df["servicio_label"], categories=servicio_order, ordered=True)

    plot_df = plot_df.sort_values(["servicio_label", "estacion", "event_time"])

    fig = px.line(
        plot_df,
        x="estacion",
        y="L_out_abordo",
        color="servicio_label",
        markers=True,
        category_orders={
            "estacion": station_order,
            "servicio_label": servicio_order,
        },
        title=titulo,
    )
    fig.update_traces(
        mode="lines+markers",
        line=dict(width=2),
        marker=dict(size=6),
        hovertemplate="<b>%{x}</b><br>Servicio: %{fullData.name}<br>A bordo: %{y:,.0f}<extra></extra>",
    )
    fig.update_layout(
        plot_bgcolor=EFE_WHITE,
        paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20),
        height=560,
        font=dict(color=TEXT_MAIN),
        title_font=dict(color=EFE_BLUE, size=16),
        legend_title_text="Servicio",
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.01),
        hovermode="x unified",
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array", categoryarray=station_order if station_order else None)
    fig.update_yaxes(title="Pasajeros a bordo")
    return fig


def classify_status(value, meta, higher_is_better=True):
    if pd.isna(meta) or meta == 0 or pd.isna(value):
        return "ok"

    ratio = value / meta if higher_is_better else meta / value if value != 0 else 0

    if ratio >= 1:
        return "ok"
    if ratio >= 0.95:
        return "alerta"
    return "critico"


def status_color(status):
    return {
        "ok": SUCCESS,
        "alerta": WARNING,
        "critico": DANGER,
        "Planificada": TEXT_MUTED,
        "En curso": EFE_BLUE,
        "Atrasada": DANGER,
        "Finalizada": SUCCESS,
        "Pausada": WARNING,
    }.get(str(status).strip(), TEXT_MUTED)


def render_kpi_card(title, value, meta, delta_text, status):
    color = status_color(status)
    html = f"""
    <div class="efe-card" style="border-left: 6px solid {color};">
        <div class="efe-card-title">{title}</div>
        <div class="efe-card-value">{value}</div>
        <div class="efe-card-meta">{meta}</div>
        <div class="efe-card-delta" style="color:{color};">{delta_text}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_observation_box(observacion):
    txt = "" if observacion is None else str(observacion).strip()
    if not txt or txt.lower() == "nan":
        st.markdown(
            "<div class='efe-observation-empty'><strong>Observación:</strong> Sin observaciones</div>",
            unsafe_allow_html=True,
        )
        return
    st.markdown(f"<div class='efe-observation'><strong>Observación:</strong> {txt}</div>", unsafe_allow_html=True)





def build_filter_chip_row(servicios_sel, servicios_lista, estados_ini_sel, estados_ini, prioridades_sel, prioridades, responsables_sel, responsables):
    chips = []
    if len(servicios_sel) != len(servicios_lista):
        chips.append(f"<span class='filter-chip'>Servicios: {len(servicios_sel)}</span>")
    if len(estados_ini_sel) != len(estados_ini):
        chips.append(f"<span class='filter-chip soft'>Estados: {len(estados_ini_sel)}</span>")
    if len(prioridades_sel) != len(prioridades):
        chips.append(f"<span class='filter-chip'>Prioridades: {len(prioridades_sel)}</span>")
    if len(responsables_sel) != len(responsables):
        chips.append(f"<span class='filter-chip soft'>Responsables: {len(responsables_sel)}</span>")
    if not chips:
        chips.append("<span class='filter-chip soft'>Sin filtros adicionales</span>")
    return "<div class='filter-chip-row'>" + "".join(chips) + "</div>"


def option_selector(label, options, key, default=None, horizontal=True):
    if not options:
        return None
    if default is None or default not in options:
        default = options[0]
    try:
        selected = st.pills(
            label,
            options=options,
            selection_mode="single",
            default=default,
            key=key,
        )
        return selected if selected is not None else default
    except Exception:
        default_index = options.index(default)
        return st.radio(label, options=options, index=default_index, key=f"{key}_radio", horizontal=horizontal)


def summarize_active_filters(servicios_sel, servicios_lista, estados_ini_sel, estados_ini, prioridades_sel, prioridades, responsables_sel, responsables):
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


def safe_to_datetime(series):
    return pd.to_datetime(series, errors="coerce")


def validate_columns(df, required_cols, label):
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"El archivo {label} no contiene las columnas requeridas: {', '.join(missing)}")
        st.stop()


def get_repo_data_path():
    base = Path(__file__).resolve().parent
    candidates = [base / "data", base / "datos", base]
    for folder in candidates:
        if (folder / "kpis.csv").exists() and (folder / "iniciativas.csv").exists() and (folder / "personas.csv").exists():
            return folder
    st.error(
        "No se encontraron los archivos kpis.csv, iniciativas.csv y personas.csv en el repositorio. "
        "Ubíquelos en la raíz del proyecto o dentro de una carpeta llamada data."
    )
    st.stop()


def periodo_to_date(value):
    value = "" if value is None else str(value).strip()
    if not value:
        return pd.NaT
    if len(value) == 7:
        value = value + "-01"
    return pd.to_datetime(value, errors="coerce")


def periodo_to_label(value):
    meses = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
             7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}
    dt = periodo_to_date(value)
    if pd.isna(dt):
        return str(value)
    return f"{meses.get(int(dt.month), str(dt.month))}-{str(dt.year)[2:]}"


def build_line_chart(df, title, color=None, line_dash=None, height=340, unit=None, kpi_name=None, boxed_values=True):
    plot_df = df.copy()
    plot_df["periodo_date"] = plot_df["periodo"].apply(periodo_to_date)
    plot_df = plot_df.sort_values(["periodo_date", "periodo"])
    plot_df["periodo_label"] = plot_df["periodo"].apply(periodo_to_label)
    category_order = list(dict.fromkeys(plot_df["periodo_label"].dropna().tolist()))
    plot_df["valor_label"] = plot_df["valor"].apply(lambda v: fmt_number(v, unit or "", kpi_name))

    fig = px.line(
        plot_df,
        x="periodo_label",
        y="valor",
        color=color,
        line_dash=line_dash,
        markers=True,
        title=title,
    )
    fig.update_traces(
        text=None,
        marker=dict(size=9),
        line=dict(width=3)
    )
    fig.update_layout(
        plot_bgcolor=EFE_WHITE,
        paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20),
        height=height,
        legend_title_text="",
        font=dict(color=TEXT_MAIN),
        title_font=dict(size=16, color=EFE_BLUE),
        hovermode="x unified",
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array", categoryarray=category_order, showgrid=False)
    fig.update_yaxes(title="", gridcolor="#E8EEF4", zeroline=False)

    if boxed_values and not plot_df.empty:
        annotation_cols = ["periodo_label", "valor", "valor_label"]
        if color and color in plot_df.columns:
            annotation_cols.append(color)
        annot_df = plot_df[annotation_cols].copy()
        for _, row in annot_df.iterrows():
            xshift = 0
            if color and color in annot_df.columns:
                group_name = str(row[color])
                if len(group_name) % 2 == 0:
                    xshift = 10
                else:
                    xshift = -10
            fig.add_annotation(
                x=row["periodo_label"],
                y=row["valor"],
                text=row["valor_label"],
                showarrow=False,
                yshift=18,
                xshift=xshift,
                font=dict(size=10, color=EFE_BLUE),
                bgcolor="rgba(255,255,255,0.92)",
                bordercolor=BORDER,
                borderwidth=1,
                borderpad=3,
                align="center",
            )
    return fig


def scale_kpi_dataframe_for_display(df, kpi_name, value_columns=("valor",)):
    df = df.copy()
    if is_occupancy_rate_kpi(kpi_name):
        for col in value_columns:
            if col in df.columns:
                df[col] = df[col].apply(maybe_scale_percent)
    return df


def infer_station_path(df_map):
    route_df = df_map.dropna(subset=["latitud", "longitud"]).copy()
    if len(route_df) < 2:
        return route_df

    coords = route_df[["latitud", "longitud"]].astype(float).to_numpy()

    def dist(i, j):
        return (coords[i][0] - coords[j][0]) ** 2 + (coords[i][1] - coords[j][1]) ** 2

    max_pair = (0, 1)
    max_d = -1
    for i in range(len(coords)):
        for j in range(i + 1, len(coords)):
            d = dist(i, j)
            if d > max_d:
                max_d = d
                max_pair = (i, j)

    start = min(max_pair, key=lambda idx: (coords[idx][1], coords[idx][0]))
    unvisited = set(range(len(coords)))
    order = [start]
    unvisited.remove(start)

    while unvisited:
        current = order[-1]
        nxt = min(unvisited, key=lambda idx: dist(current, idx))
        order.append(nxt)
        unvisited.remove(nxt)

    return route_df.iloc[order].copy()



def compute_map_bounds(df_map):
    lat_min = float(df_map["lat_float"].min())
    lat_max = float(df_map["lat_float"].max())
    lon_min = float(df_map["lon_float"].min())
    lon_max = float(df_map["lon_float"].max())

    lat_range = lat_max - lat_min
    lon_range = lon_max - lon_min

    # Expansión mínima para evitar encuadres degenerados en servicios con pocas estaciones
    min_lat_pad = 0.01
    min_lon_pad = 0.02

    lat_pad = max(lat_range * 0.08, min_lat_pad)
    lon_pad = max(lon_range * 0.16, min_lon_pad)

    return dict(
        south=lat_min - lat_pad,
        north=lat_max + lat_pad,
        west=lon_min - lon_pad,
        east=lon_max + lon_pad,
    )



import pandas as pd
import plotly.graph_objects as go

# Nota: para reducir al máximo el chrome superior en Streamlit Community Cloud,
# este archivo está pensado para complementarse con .streamlit/config.toml
# usando [client] toolbarMode = "minimal".

EFE_BLUE = "#002857"
EFE_WHITE = "#FFFFFF"

def build_station_map(valid_map_df: pd.DataFrame) -> go.Figure:
    """
    Construye el mapa georreferenciado de estaciones con:
    - encuadre automático suficientemente amplio para ver todas las estaciones;
    - solo nombre de estación visible en el mapa;
    - tamaño del punto según afluencia registrada (columna entradas);
    - hover de apoyo con nombre, afluencia y meta.
    """

    plot_df = valid_map_df.copy()

    if plot_df.empty:
        fig = go.Figure()
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=700)
        return fig

    # Coordenadas robustas
    plot_df["latitud"] = pd.to_numeric(plot_df["latitud"], errors="coerce")
    plot_df["longitud"] = pd.to_numeric(plot_df["longitud"], errors="coerce")
    plot_df = plot_df.dropna(subset=["latitud", "longitud"]).copy()

    if plot_df.empty:
        fig = go.Figure()
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=700)
        return fig

    # Nombre visible en mapa
    plot_df["label_mapa"] = (
        plot_df["estacion"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # Afluencia registrada: el archivo usa la columna "entradas"
    plot_df["entradas"] = pd.to_numeric(plot_df.get("entradas"), errors="coerce").fillna(0)
    plot_df["meta_entradas"] = pd.to_numeric(plot_df.get("meta_entradas"), errors="coerce")

    # Tamaño de marcadores según afluencia, manteniendo rango legible
    afluencia = plot_df["entradas"]
    if len(afluencia) > 1 and float(afluencia.max()) > float(afluencia.min()):
        plot_df["marker_size"] = 10 + ((afluencia - afluencia.min()) / (afluencia.max() - afluencia.min())) * 18
    else:
        plot_df["marker_size"] = 14

    # Encuadre automático amplio para incluir todas las estaciones
    min_lat = float(plot_df["latitud"].min())
    max_lat = float(plot_df["latitud"].max())
    min_lon = float(plot_df["longitud"].min())
    max_lon = float(plot_df["longitud"].max())

    lat_span = max(max_lat - min_lat, 0.01)
    lon_span = max(max_lon - min_lon, 0.01)

    lat_pad = max(lat_span * 0.18, 0.015)
    lon_pad = max(lon_span * 0.70, 0.04)

    bounds = {
        "west": min_lon - lon_pad,
        "east": max_lon + lon_pad,
        "south": min_lat - lat_pad,
        "north": max_lat + lat_pad,
    }

    fig = go.Figure()

    fig.add_trace(
        go.Scattermapbox(
            lat=plot_df["latitud"].astype(float),
            lon=plot_df["longitud"].astype(float),
            mode="markers+text",
            text=plot_df["label_mapa"],
            textposition="top right",
            textfont=dict(
                size=12,
                color=EFE_BLUE,
                family="Arial, sans-serif"
            ),
            marker=dict(
                size=plot_df["marker_size"],
                color=EFE_BLUE,
                opacity=0.88,
                sizemode="diameter",
                symbol="circle"
            ),
            customdata=plot_df[["estacion", "entradas", "meta_entradas"]].fillna(""),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]:,.0f}<br>"
                "Meta: %{customdata[2]:,.0f}"
                "<extra></extra>"
            ),
            showlegend=False
        )
    )

    fig.update_layout(
        mapbox=dict(
            style="white-bg",
            layers=[
                dict(
                    sourcetype="raster",
                    source=[
                        "https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"
                    ],
                    below="traces"
                )
            ],
            bounds=bounds
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=700,
        showlegend=False
    )

    return fig

# =========================================================
# CARGA DE DATOS
# =========================================================
@st.cache_data
def load_data():
    data_path = get_repo_data_path()

    kpis = pd.read_csv(data_path / "kpis.csv")
    iniciativas = pd.read_csv(data_path / "iniciativas.csv")
    personas = pd.read_csv(data_path / "personas.csv")

    servicios_path = data_path / "servicios.csv"
    servicios = pd.read_csv(servicios_path) if servicios_path.exists() else pd.DataFrame()

    estaciones_path = data_path / "estaciones.csv"
    estaciones = pd.read_csv(estaciones_path) if estaciones_path.exists() else pd.DataFrame()

    afluencia_estacion_path = data_path / "afluencia_estacion.csv"
    afluencia_estacion = pd.read_csv(afluencia_estacion_path) if afluencia_estacion_path.exists() else pd.DataFrame()

    validate_columns(
        kpis,
        ["id_kpi", "nombre", "categoria", "servicio", "valor", "meta", "unidad", "periodo", "variacion_pct", "estado"],
        "kpis.csv",
    )
    validate_columns(
        iniciativas,
        ["id_iniciativa", "nombre", "responsable_id", "servicio", "estado", "avance_pct", "fecha_inicio", "fecha_fin", "prioridad"],
        "iniciativas.csv",
    )
    validate_columns(
        personas,
        ["id_persona", "nombre", "cargo", "area", "activo"],
        "personas.csv",
    )
    if not estaciones.empty:
        validate_columns(
            estaciones,
            ["id_estacion", "estacion", "servicio", "comuna", "region", "latitud", "longitud", "orden_trazado", "activa"],
            "estaciones.csv",
        )
    if not afluencia_estacion.empty:
        validate_columns(
            afluencia_estacion,
            ["id_afluencia_estacion", "periodo", "servicio", "id_estacion", "entradas", "meta_entradas", "perdida_pax", "fuga_pct"],
            "afluencia_estacion.csv",
        )

    kpis["valor"] = pd.to_numeric(kpis["valor"], errors="coerce")
    kpis["meta"] = pd.to_numeric(kpis["meta"], errors="coerce")
    kpis["variacion_pct"] = pd.to_numeric(kpis["variacion_pct"], errors="coerce")
    if "orden" in kpis.columns:
        kpis["orden"] = pd.to_numeric(kpis["orden"], errors="coerce")

    iniciativas["avance_pct"] = pd.to_numeric(iniciativas["avance_pct"], errors="coerce")
    iniciativas["fecha_inicio"] = safe_to_datetime(iniciativas["fecha_inicio"]).dt.date
    iniciativas["fecha_fin"] = safe_to_datetime(iniciativas["fecha_fin"]).dt.date

    personas["activo"] = pd.to_numeric(personas["activo"], errors="coerce").fillna(0).astype(int)
    if "orden" in personas.columns:
        personas["orden"] = pd.to_numeric(personas["orden"], errors="coerce")

    if not servicios.empty:
        if "activo" in servicios.columns:
            servicios["activo"] = pd.to_numeric(servicios["activo"], errors="coerce").fillna(0).astype(int)
        if "orden" in servicios.columns:
            servicios["orden"] = pd.to_numeric(servicios["orden"], errors="coerce")

    if not estaciones.empty:
        estaciones["latitud"] = pd.to_numeric(estaciones["latitud"], errors="coerce")
        estaciones["longitud"] = pd.to_numeric(estaciones["longitud"], errors="coerce")
        estaciones["orden_trazado"] = pd.to_numeric(estaciones["orden_trazado"], errors="coerce")
        estaciones["activa"] = pd.to_numeric(estaciones["activa"], errors="coerce").fillna(0).astype(int)

    if not afluencia_estacion.empty:
        afluencia_estacion["entradas"] = pd.to_numeric(afluencia_estacion["entradas"], errors="coerce")
        afluencia_estacion["meta_entradas"] = pd.to_numeric(afluencia_estacion["meta_entradas"], errors="coerce")
        afluencia_estacion["perdida_pax"] = pd.to_numeric(afluencia_estacion["perdida_pax"], errors="coerce")
        afluencia_estacion["fuga_pct"] = pd.to_numeric(afluencia_estacion["fuga_pct"], errors="coerce")

    return kpis, iniciativas, personas, servicios, estaciones, afluencia_estacion, data_path


@st.cache_data
def load_profile_service_data(service_name, data_path_str):
    data_path = Path(data_path_str)
    required_cols = [
        "fecha", "linea", "direccion", "servicio", "estacion",
        "t_arr_est", "t_dep_est", "capacidad_tren", "D_bajadas",
        "B_embarque", "L_out_abordo"
    ]

    perfil_folder = None
    csv_files = []
    for candidate in get_profile_folder_candidates(service_name, data_path):
        if candidate.exists() and candidate.is_dir():
            files = sorted(candidate.glob("*.csv"))
            if files:
                perfil_folder = candidate
                csv_files = files
                break
            if perfil_folder is None:
                perfil_folder = candidate

    if not csv_files:
        fallback_folder = perfil_folder if perfil_folder is not None else Path(data_path) / get_default_profile_folder_name(service_name)
        return pd.DataFrame(), str(fallback_folder), required_cols, [], "no_data"

    frames = []
    loaded_files = []
    for csv_file in csv_files:
        try:
            temp = pd.read_csv(csv_file)
            temp["archivo_origen"] = csv_file.name
            frames.append(temp)
            loaded_files.append(csv_file.name)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(), str(perfil_folder), required_cols, loaded_files, "read_error"

    perfil_df = pd.concat(frames, ignore_index=True)
    missing = [c for c in required_cols if c not in perfil_df.columns]
    if missing:
        return perfil_df, str(perfil_folder), missing, loaded_files, "unsupported_format"

    perfil_df["fecha"] = pd.to_datetime(perfil_df["fecha"], errors="coerce").dt.date
    perfil_df["linea"] = perfil_df["linea"].fillna("").astype(str).str.strip()
    perfil_df["direccion"] = perfil_df["direccion"].fillna("").astype(str).str.strip()
    perfil_df["estacion"] = perfil_df["estacion"].fillna("").astype(str).str.strip()
    perfil_df["servicio_label"] = perfil_df["servicio"].apply(format_service_id)

    for time_col in ["t_arr_est", "t_dep_est"]:
        perfil_df[time_col] = pd.to_datetime(perfil_df[time_col], errors="coerce")

    numeric_cols = [
        "capacidad_tren", "A_llegadas_anden", "D_bajadas", "Demanda_anden",
        "Capacidad_disponible", "B_embarque", "R_quedados", "Q_out_cola",
        "L_in_abordo", "L_out_abordo"
    ]
    for col in numeric_cols:
        if col in perfil_df.columns:
            perfil_df[col] = pd.to_numeric(perfil_df[col], errors="coerce")

    perfil_df = perfil_df.dropna(subset=["fecha"]).copy()
    return perfil_df, str(perfil_folder), [], loaded_files, "ok"


kpis, iniciativas, personas, servicios, estaciones, afluencia_estacion, data_path = load_data()

# =========================================================
# PREPARACIÓN DE DATOS
# =========================================================
personas_activas = personas[personas["activo"] == 1].copy()

iniciativas = iniciativas.merge(
    personas_activas[["id_persona", "nombre"]],
    how="left",
    left_on="responsable_id",
    right_on="id_persona",
)
iniciativas = iniciativas.rename(columns={"nombre_y": "responsable"} if "nombre_y" in iniciativas.columns else {})
if "nombre" in iniciativas.columns and "responsable" not in iniciativas.columns:
    iniciativas = iniciativas.rename(columns={"nombre": "responsable"})
if "nombre_x" in iniciativas.columns:
    iniciativas = iniciativas.rename(columns={"nombre_x": "nombre_iniciativa"})
elif "nombre" in iniciativas.columns:
    iniciativas = iniciativas.rename(columns={"nombre": "nombre_iniciativa"})

today = date.today()
iniciativas["vencida"] = iniciativas["fecha_fin"].apply(lambda x: (x is not None) and pd.notna(x) and x < today)
iniciativas["critica"] = iniciativas.apply(
    lambda r: (str(r["estado"]).strip() == "Atrasada") or (bool(r["vencida"]) and str(r["estado"]).strip() != "Finalizada"),
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

# =========================================================
# FILTROS PRINCIPALES
# =========================================================
periodos = sorted(kpis["periodo"].dropna().astype(str).unique().tolist())
default_period_index = len(periodos) - 1 if periodos else 0

# =========================================================
# ENCABEZADO Y PERÍODO VISIBLE
# =========================================================
st.markdown("<div class='hero-shell'>", unsafe_allow_html=True)
hero_left, hero_right = st.columns([4.8, 1.55])

with hero_left:
    logo_col, title_col = st.columns([0.9, 4.6])
    with logo_col:
        logo_candidates = [Path(__file__).resolve().parent / "assets" / "logoefe-azul.png", Path(__file__).resolve().parent / "logoefe-azul.png"]
        for logo_path in logo_candidates:
            if logo_path.exists():
                st.image(str(logo_path), use_container_width=True)
                break
    with title_col:
        st.markdown("<div class='hero-kicker'>Seguimiento ejecutivo</div>", unsafe_allow_html=True)
        st.markdown("<div class='main-title'>KPIs e Iniciativas - Gerencia de Pasajeros</div>", unsafe_allow_html=True)
        st.markdown("<div class='subtitle'>Panel ejecutivo para monitorear desempeño, gestión de iniciativas, estaciones y perfiles de carga por servicio.</div>", unsafe_allow_html=True)

with hero_right:
    st.markdown("<div class='top-period-wrapper'></div>", unsafe_allow_html=True)
    periodo_sel = st.selectbox("Período de análisis", options=periodos, index=default_period_index, key="periodo_top")
    st.markdown("<div class='hero-side-note'>Vista ejecutiva compacta para seguimiento y lectura rápida.</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# FILTROS Y NAVEGACIÓN
# =========================================================
estados_ini = sorted(iniciativas["estado"].dropna().astype(str).unique().tolist())
prioridades = sorted(iniciativas["prioridad"].dropna().astype(str).unique().tolist())
responsables = sorted(iniciativas["responsable"].dropna().astype(str).unique().tolist())

servicios_sel = servicios_lista
estados_ini_sel = estados_ini
prioridades_sel = prioridades
responsables_sel = responsables

toolbar_left, toolbar_right = st.columns([4.6, 1.0])
with toolbar_right:
    popover_context = st.popover if hasattr(st, "popover") else st.expander
    popover_label = "Filtros"
    popover_kwargs = {"expanded": False} if popover_context is st.expander else {}
    with popover_context(popover_label, **popover_kwargs):
        servicios_sel = st.multiselect(
            "Servicio",
            options=servicios_lista,
            default=servicios_lista,
            key="servicios_body_filter",
        )
        estados_ini_sel = st.multiselect(
            "Estado iniciativa",
            options=estados_ini,
            default=estados_ini,
            key="estado_body_filter",
        )
        prioridades_sel = st.multiselect(
            "Prioridad",
            options=prioridades,
            default=prioridades,
            key="prioridad_body_filter",
        )
        responsables_sel = st.multiselect(
            "Responsable",
            options=responsables,
            default=responsables,
            key="responsable_body_filter",
        )
        if st.button("Restablecer filtros", key="reset_filters_btn", use_container_width=True):
            st.session_state["servicios_body_filter"] = servicios_lista
            st.session_state["estado_body_filter"] = estados_ini
            st.session_state["prioridad_body_filter"] = prioridades
            st.session_state["responsable_body_filter"] = responsables
            st.rerun()
        st.caption(f"Origen de datos: {data_path}")

servicios_sel = servicios_sel or servicios_lista
estados_ini_sel = estados_ini_sel or estados_ini
prioridades_sel = prioridades_sel or prioridades
responsables_sel = responsables_sel or responsables

active_filter_summary = summarize_active_filters(
    servicios_sel,
    servicios_lista,
    estados_ini_sel,
    estados_ini,
    prioridades_sel,
    prioridades,
    responsables_sel,
    responsables,
)
active_filter_chips = build_filter_chip_row(
    servicios_sel,
    servicios_lista,
    estados_ini_sel,
    estados_ini,
    prioridades_sel,
    prioridades,
    responsables_sel,
    responsables,
)

with toolbar_left:
    st.markdown("<div class='toolbar-panel'>", unsafe_allow_html=True)
    st.markdown(f"<div class='filters-summary'><strong>Filtros activos:</strong> {active_filter_summary}</div>", unsafe_allow_html=True)
    st.markdown(active_filter_chips, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# FILTRADO
# =========================================================
kpis_f = kpis[(kpis["periodo"].astype(str) == str(periodo_sel)) & (kpis["servicio"].isin(servicios_sel))].copy()
iniciativas_f = iniciativas[(iniciativas["servicio"].isin(servicios_sel)) & (iniciativas["estado"].isin(estados_ini_sel)) & (iniciativas["prioridad"].isin(prioridades_sel)) & (iniciativas["responsable"].isin(responsables_sel))].copy()
kpis_hist = kpis[kpis["servicio"].isin(servicios_sel)].copy()

if "orden" in kpis_f.columns:
    kpis_f = kpis_f.sort_values(["orden", "servicio", "nombre"])
else:
    kpis_f = kpis_f.sort_values(["nombre", "servicio"])

# =========================================================
# NAVEGACIÓN PRINCIPAL
# =========================================================
with st.container():
    st.markdown("<span class='sticky-nav-anchor'></span>", unsafe_allow_html=True)
    st.markdown("<div class='nav-panel'>", unsafe_allow_html=True)
    section_sel = option_selector(
        "Navegación",
        ["Resumen ejecutivo", "KPIs", "Personas", "Estaciones", "Perfil de Carga", "OD Estaciones"],
        key="main_nav_selector",
        default="Resumen ejecutivo",
        horizontal=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# RENDER DE SECCIONES
# =========================================================
def render_resumen_ejecutivo():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Resumen ejecutivo</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Síntesis de KPIs del período seleccionado y evolución histórica para el servicio visible.</div>", unsafe_allow_html=True)

    servicios_con_datos = [svc for svc in servicios_sel if svc in kpis_f["servicio"].astype(str).unique().tolist()]
    if kpis_f.empty:
        st.warning("No existen KPI para los filtros seleccionados.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return
    if not servicios_con_datos:
        st.warning("No existen servicios con KPI para el período y filtros seleccionados.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    resumen_servicio_sel = option_selector(
        "Servicio visible",
        servicios_con_datos,
        key="resumen_servicio_selector",
        default=servicios_con_datos[0],
        horizontal=True,
    )

    servicio_df = kpis_f[kpis_f["servicio"].astype(str) == str(resumen_servicio_sel)].copy()
    if "orden" in servicio_df.columns:
        servicio_df = servicio_df.sort_values(["orden", "nombre", "categoria"])
    else:
        servicio_df = servicio_df.sort_values(["nombre", "categoria"])

    st.markdown(f"<div class='service-title'>{resumen_servicio_sel}</div>", unsafe_allow_html=True)

    if servicio_df.empty:
        st.info("No hay KPIs disponibles para el servicio seleccionado.")
    else:
        cols_por_fila = 3 if len(servicio_df) >= 3 else max(1, len(servicio_df))
        for i in range(0, len(servicio_df), cols_por_fila):
            row_df = servicio_df.iloc[i:i + cols_por_fila]
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
    hist_service = kpis_hist[kpis_hist["servicio"].astype(str) == str(resumen_servicio_sel)].copy()
    nombres_kpi = sorted(hist_service["nombre"].dropna().astype(str).unique().tolist())
    resumen_kpi_sel = option_selector(
        "KPI a visualizar",
        nombres_kpi,
        key="kpi_hist_sel_resumen",
        default=nombres_kpi[0] if nombres_kpi else None,
        horizontal=True,
    )

    if not nombres_kpi or not resumen_kpi_sel:
        st.info("No hay datos históricos para el servicio seleccionado.")
    else:
        hist_sel = hist_service[hist_service["nombre"] == resumen_kpi_sel].copy()
        hist_sel = scale_kpi_dataframe_for_display(hist_sel, resumen_kpi_sel, ("valor", "meta"))
        unit_hist = None
        if not hist_sel.empty and "unidad" in hist_sel.columns:
            unidad_series = hist_sel["unidad"].dropna().astype(str)
            unit_hist = unidad_series.iloc[0] if not unidad_series.empty else None

        if hist_sel.empty:
            st.info("No hay datos históricos para el KPI seleccionado.")
        else:
            hist_plot = hist_sel.groupby("periodo", as_index=False)["valor"].sum()
            fig_svc = build_line_chart(
                hist_plot,
                f"{resumen_kpi_sel} - {resumen_servicio_sel}",
                height=370,
                unit=unit_hist,
                kpi_name=resumen_kpi_sel,
                boxed_values=True,
            )
            fig_svc.update_traces(line_color=EFE_BLUE)
            st.plotly_chart(fig_svc, use_container_width=True)

    st.markdown("</div></div>", unsafe_allow_html=True)


def render_kpis():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Análisis de KPIs</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Evolución, contraste con meta y detalle del indicador seleccionado.</div>", unsafe_allow_html=True)
    nombres_kpi = sorted(kpis["nombre"].dropna().astype(str).unique().tolist())
    kpi_sel = option_selector("Seleccione KPI", nombres_kpi, key="kpi_analisis", default=nombres_kpi[0] if nombres_kpi else None, horizontal=True)
    hist_kpi = kpis_hist[kpis_hist["nombre"] == kpi_sel].copy()
    hist_kpi = scale_kpi_dataframe_for_display(hist_kpi, kpi_sel, ("valor", "meta"))

    st.markdown("<div class='section-title'>Evolución por grupos de servicio</div>", unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        bt_hist = hist_kpi[hist_kpi["servicio"] == "Biotren"].copy()
        if bt_hist.empty:
            st.info("No hay datos de Biotren para el KPI seleccionado.")
        else:
            bt_hist = bt_hist.groupby("periodo", as_index=False)["valor"].sum()
            fig_bt = build_line_chart(bt_hist, f"{kpi_sel} - Biotren", height=340, unit=hist_kpi["unidad"].dropna().astype(str).iloc[0] if not hist_kpi.empty and "unidad" in hist_kpi.columns and not hist_kpi["unidad"].dropna().empty else None, kpi_name=kpi_sel)
            fig_bt.update_traces(line_color=EFE_BLUE)
            st.plotly_chart(fig_bt, use_container_width=True)
    with col_b:
        otros_hist = hist_kpi[hist_kpi["servicio"].isin(RURAL_SERVICES)].copy()
        if otros_hist.empty:
            st.info("No hay datos de otros servicios para el KPI seleccionado.")
        else:
            otros_hist = otros_hist.groupby(["periodo", "servicio"], as_index=False)["valor"].sum()
            fig_ot = build_line_chart(otros_hist, f"{kpi_sel} - Otros servicios", color="servicio", height=340, unit=hist_kpi["unidad"].dropna().astype(str).iloc[0] if not hist_kpi.empty and "unidad" in hist_kpi.columns and not hist_kpi["unidad"].dropna().empty else None, kpi_name=kpi_sel)
            st.plotly_chart(fig_ot, use_container_width=True)

    st.markdown("<div class='section-title'>Valor vs meta por servicio</div>", unsafe_allow_html=True)
    actual = kpis_f[kpis_f["nombre"] == kpi_sel].copy()
    actual = scale_kpi_dataframe_for_display(actual, kpi_sel, ("valor", "meta"))
    if not actual.empty:
        servicios_actuales = [svc for svc in servicios_sel if svc in actual["servicio"].astype(str).unique().tolist()]
        if not servicios_actuales:
            servicios_actuales = actual["servicio"].dropna().astype(str).unique().tolist()

        cols_por_fila = 2 if len(servicios_actuales) > 1 else 1
        for i in range(0, len(servicios_actuales), cols_por_fila):
            row_services = servicios_actuales[i:i + cols_por_fila]
            row_cols = st.columns(cols_por_fila)
            for j, servicio in enumerate(row_services):
                servicio_df = actual[actual["servicio"].astype(str) == str(servicio)].copy()
                with row_cols[j]:
                    if servicio_df.empty:
                        st.info(f"No hay datos para {servicio}.")
                    else:
                        fig_meta = go.Figure()
                        fig_meta.add_trace(go.Bar(
                            x=["Valor", "Meta"],
                            y=[servicio_df["valor"].sum(), servicio_df["meta"].sum()],
                            marker_color=[EFE_BLUE, EFE_RED],
                            text=[fmt_number(servicio_df["valor"].sum(), servicio_df["unidad"].iloc[0], kpi_sel),
                                  fmt_number(servicio_df["meta"].sum(), servicio_df["unidad"].iloc[0], kpi_sel)],
                            textposition="outside",
                            showlegend=False,
                        ))
                        fig_meta.update_layout(
                            title=f"{servicio} - {periodo_sel}",
                            plot_bgcolor=EFE_WHITE,
                            paper_bgcolor=EFE_WHITE,
                            margin=dict(l=20, r=20, t=50, b=20),
                            height=340,
                            xaxis_title="",
                            yaxis_title="",
                            font=dict(color=TEXT_MAIN),
                            title_font=dict(color=EFE_BLUE, size=16),
                        )
                        st.plotly_chart(fig_meta, use_container_width=True)
        st.caption("Cada gráfico compara el valor observado y la meta del KPI seleccionado por servicio.")
    else:
        st.info("No hay datos para el KPI seleccionado en el período actual.")

    st.markdown("<div class='section-title'>Detalle del KPI</div>", unsafe_allow_html=True)
    detalle_cols = ["servicio", "categoria", "valor", "meta", "unidad", "variacion_pct", "estado"]
    if "observacion" in kpis_f.columns:
        detalle_cols.append("observacion")
    detalle_kpi = kpis_f[kpis_f["nombre"] == kpi_sel][detalle_cols].copy()
    if not detalle_kpi.empty:
        detalle_kpi["Valor"] = detalle_kpi.apply(lambda r: fmt_number(r["valor"], r["unidad"], kpi_sel), axis=1)
        detalle_kpi["Meta"] = detalle_kpi.apply(lambda r: fmt_number(r["meta"], r["unidad"], kpi_sel), axis=1)
        detalle_kpi["Variación"] = detalle_kpi["variacion_pct"].apply(fmt_pct)
        show_cols = ["servicio", "categoria", "Valor", "Meta", "Variación", "estado"]
        rename_map = {"servicio": "Servicio", "categoria": "Categoría", "estado": "Estado"}
        if "observacion" in detalle_kpi.columns:
            show_cols.append("observacion")
            rename_map["observacion"] = "Observación"
        detalle_show = detalle_kpi[show_cols].rename(columns=rename_map)
        st.dataframe(detalle_show, use_container_width=True, hide_index=True)
    else:
        st.info("No existe detalle para el KPI seleccionado.")
    st.markdown("</div></div>", unsafe_allow_html=True)


def render_personas():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Vista por persona</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Seguimiento de iniciativas, avance y estado por responsable.</div>", unsafe_allow_html=True)
    total_ini = len(iniciativas_f)
    en_curso = int((iniciativas_f["estado"] == "En curso").sum())
    atrasadas = int((iniciativas_f["estado"] == "Atrasada").sum())
    finalizadas = int((iniciativas_f["estado"] == "Finalizada").sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total iniciativas", total_ini)
    m2.metric("En curso", en_curso)
    m3.metric("Atrasadas", atrasadas)
    m4.metric("Finalizadas", finalizadas)

    personas_opts = sorted(iniciativas_f["responsable"].dropna().astype(str).unique().tolist())
    persona_sel = option_selector("Seleccione responsable", personas_opts, key="persona_selector", default=personas_opts[0] if personas_opts else None, horizontal=True)
    if personas_opts and persona_sel:
        per_df = iniciativas_f[iniciativas_f["responsable"] == persona_sel].copy()
        total_p = len(per_df)
        finalizadas_p = int((per_df["estado"] == "Finalizada").sum())
        atrasadas_p = int((per_df["estado"] == "Atrasada").sum())
        avance_prom = float(per_df["avance_pct"].mean()) if not per_df.empty else 0

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Asignadas", total_p)
        p2.metric("Finalizadas", finalizadas_p)
        p3.metric("Atrasadas", atrasadas_p)
        p4.metric("Avance promedio", fmt_pct(avance_prom))

        left_p, right_p = st.columns([1.2, 0.8])
        with left_p:
            if per_df.empty:
                st.info("No hay iniciativas para el responsable seleccionado.")
            else:
                fig = px.bar(per_df.sort_values("avance_pct"), x="avance_pct", y="nombre_iniciativa", orientation="h", title=f"Avance por iniciativa - {persona_sel}", text="avance_pct")
                fig.update_traces(marker_color=EFE_BLUE)
                fig.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=420, font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16))
                fig.update_xaxes(title="Avance %")
                fig.update_yaxes(title="")
                st.plotly_chart(fig, use_container_width=True)
        with right_p:
            estado_persona = per_df["estado"].value_counts().reset_index()
            estado_persona.columns = ["estado", "cantidad"]
            if estado_persona.empty:
                st.info("No hay estados para mostrar.")
            else:
                fig2 = px.bar(estado_persona, x="estado", y="cantidad", title="Distribución por estado", color="estado", color_discrete_map={"Planificada": TEXT_MUTED, "En curso": EFE_BLUE, "Atrasada": EFE_RED, "Finalizada": SUCCESS, "Pausada": WARNING})
                fig2.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=420, font=dict(color=TEXT_MAIN), title_font=dict(color=EFE_BLUE, size=16), showlegend=False)
                st.plotly_chart(fig2, use_container_width=True)

        st.markdown("<div class='section-title'>Detalle por responsable</div>", unsafe_allow_html=True)
        detalle_cols = ["nombre_iniciativa", "servicio", "estado", "avance_pct", "fecha_inicio", "fecha_fin", "prioridad", "comentario"]
        if "criticidad" in per_df.columns:
            detalle_cols.insert(-1, "criticidad")
        detalle_persona = per_df[detalle_cols].copy()
        rename_map = {
            "nombre_iniciativa": "Iniciativa",
            "servicio": "Servicio",
            "estado": "Estado",
            "avance_pct": "Avance %",
            "fecha_inicio": "Inicio",
            "fecha_fin": "Fin",
            "prioridad": "Prioridad",
            "comentario": "Comentario",
        }
        if "criticidad" in detalle_persona.columns:
            rename_map["criticidad"] = "Criticidad"
        detalle_persona = detalle_persona.rename(columns=rename_map)
        st.dataframe(detalle_persona, use_container_width=True, hide_index=True)
    else:
        st.warning("No hay responsables disponibles con los filtros actuales.")
    st.markdown("</div></div>", unsafe_allow_html=True)


def render_detalle_servicio():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Estaciones</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Afluencia por estación y lectura territorial del servicio seleccionado.</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='map-note'>"
        "Esta sección muestra la afluencia registrada por estación de forma georreferenciada, junto con una comparación entre afluencia observada y meta por estación."
        "</div>",
        unsafe_allow_html=True,
    )

    if estaciones.empty or afluencia_estacion.empty:
        st.info("Para habilitar esta vista, agregue los archivos estaciones.csv y afluencia_estacion.csv al repositorio.")
    else:
        estaciones_activas = estaciones[estaciones["activa"] == 1].copy()
        servicios_detalle = sorted(list(set(estaciones_activas["servicio"].dropna().astype(str).tolist()) & set(afluencia_estacion["servicio"].dropna().astype(str).tolist())))
        servicios_detalle = [s for s in servicios_lista if s in servicios_detalle] or servicios_detalle
        if not servicios_detalle:
            st.warning("No existen servicios comunes entre estaciones.csv y afluencia_estacion.csv.")
        else:
            default_detalle_servicio = servicios_detalle[0]
            if len(servicios_sel) == 1 and servicios_sel[0] in servicios_detalle:
                default_detalle_servicio = servicios_sel[0]
            sel_col1, sel_col2 = st.columns([1.35, 1])
            with sel_col1:
                detalle_servicio_sel = option_selector("Servicio para análisis georreferenciado", servicios_detalle, key="detalle_servicio_selector", default=default_detalle_servicio, horizontal=True)

            periodos_detalle = sorted(afluencia_estacion[afluencia_estacion["servicio"].astype(str) == str(detalle_servicio_sel)]["periodo"].dropna().astype(str).unique().tolist())
            if not periodos_detalle:
                st.warning("No existen períodos disponibles para el servicio seleccionado.")
            else:
                default_detalle_periodo = str(periodo_sel) if str(periodo_sel) in periodos_detalle else periodos_detalle[-1]
                with sel_col2:
                    detalle_periodo_sel = option_selector("Período de detalle", periodos_detalle, key="detalle_periodo_selector", default=default_detalle_periodo, horizontal=True)

                estaciones_srv = estaciones_activas[estaciones_activas["servicio"].astype(str) == str(detalle_servicio_sel)].copy()
                if "orden_trazado" in estaciones_srv.columns:
                    estaciones_srv = estaciones_srv.sort_values(["orden_trazado", "estacion"])
                else:
                    estaciones_srv = estaciones_srv.sort_values("estacion")

                afluencia_srv = afluencia_estacion[(afluencia_estacion["servicio"].astype(str) == str(detalle_servicio_sel)) & (afluencia_estacion["periodo"].astype(str) == str(detalle_periodo_sel))].copy()

                detail_df = estaciones_srv.merge(afluencia_srv, how="left", on=["id_estacion", "servicio"], suffixes=("_est", "_afl"))
                detail_df["entradas"] = pd.to_numeric(detail_df.get("entradas"), errors="coerce")
                detail_df["meta_entradas"] = pd.to_numeric(detail_df.get("meta_entradas"), errors="coerce")
                detail_df["perdida_pax"] = pd.to_numeric(detail_df.get("perdida_pax"), errors="coerce")
                detail_df["fuga_pct"] = pd.to_numeric(detail_df.get("fuga_pct"), errors="coerce")
                detail_df["fuga_pct_display"] = detail_df["fuga_pct"].apply(maybe_scale_percent)
                detail_df["observacion_estacion"] = detail_df.get("observacion_est", detail_df.get("observacion_x", None))
                detail_df["observacion_afluencia"] = detail_df.get("observacion_afl", detail_df.get("observacion_y", None))

                valid_map_df = detail_df.dropna(subset=["latitud", "longitud"]).copy()
                bar_df = detail_df[["estacion", "entradas", "meta_entradas"]].copy()
                if "orden_trazado" in detail_df.columns:
                    temp_order = detail_df[["estacion", "orden_trazado"]].copy()
                    temp_order["orden_trazado"] = pd.to_numeric(temp_order["orden_trazado"], errors="coerce")
                    temp_order = temp_order.sort_values(["orden_trazado", "estacion"])
                    station_order = temp_order["estacion"].dropna().astype(str).tolist()
                else:
                    station_order = sorted(bar_df["estacion"].dropna().astype(str).tolist())
                bar_df["entradas"] = pd.to_numeric(bar_df["entradas"], errors="coerce").fillna(0)
                bar_df["meta_entradas"] = pd.to_numeric(bar_df["meta_entradas"], errors="coerce").fillna(0)

                top_left, top_right = st.columns([0.95, 1.05])
                with top_left:
                    if valid_map_df.empty:
                        st.warning("No existen coordenadas válidas para graficar las estaciones del servicio seleccionado.")
                    else:
                        map_fig = build_station_map(valid_map_df)
                        st.plotly_chart(map_fig, use_container_width=True)
                with top_right:
                    total_entradas = detail_df["entradas"].sum(min_count=1)
                    total_meta = detail_df["meta_entradas"].sum(min_count=1)
                    total_perdida = detail_df["perdida_pax"].sum(min_count=1)
                    fuga_prom = detail_df["fuga_pct_display"].mean()

                    m1, m2 = st.columns(2)
                    m3, m4 = st.columns(2)
                    m1.metric("Afluencia", fmt_pax(total_entradas))
                    m2.metric("Meta afluencia", fmt_pax(total_meta))
                    m3.metric("Pérdida total", fmt_pax(total_perdida))
                    m4.metric("Fuga promedio", fmt_fuga_pct(fuga_prom))

                    if bar_df.empty:
                        st.info("No hay datos de afluencia o meta para el período seleccionado.")
                    else:
                        fig_bar = go.Figure()
                        fig_bar.add_trace(go.Bar(x=bar_df["estacion"], y=bar_df["entradas"], name="Afluencia registrada", marker_color=EFE_BLUE))
                        fig_bar.add_trace(go.Bar(x=bar_df["estacion"], y=bar_df["meta_entradas"], name="Meta", marker_color=EFE_RED))
                        fig_bar.update_layout(
                            title="Afluencia registrada vs meta por estación",
                            plot_bgcolor=EFE_WHITE,
                            paper_bgcolor=EFE_WHITE,
                            margin=dict(l=20, r=20, t=50, b=20),
                            height=465,
                            barmode="group",
                            font=dict(color=TEXT_MAIN),
                            title_font=dict(color=EFE_BLUE, size=16),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        )
                        fig_bar.update_xaxes(title="", tickangle=-90, categoryorder="array", categoryarray=station_order)
                        fig_bar.update_yaxes(title="Pasajeros")
                        st.plotly_chart(fig_bar, use_container_width=True)

                st.markdown("<div class='section-title'>Detalle de estaciones</div>", unsafe_allow_html=True)
                detail_table = detail_df[["estacion", "comuna", "region", "entradas", "meta_entradas", "perdida_pax", "fuga_pct_display", "observacion_afluencia", "observacion_estacion"]].copy()
                detail_table["Afluencia"] = detail_table["entradas"].apply(fmt_pax)
                detail_table["Meta afluencia"] = detail_table["meta_entradas"].apply(fmt_pax)
                detail_table["Pérdida pax"] = detail_table["perdida_pax"].apply(fmt_pax)
                detail_table["Fuga %"] = detail_table["fuga_pct_display"].apply(fmt_fuga_pct)
                detail_table = detail_table[["estacion", "comuna", "region", "Afluencia", "Meta afluencia", "Pérdida pax", "Fuga %", "observacion_afluencia", "observacion_estacion"]].rename(columns={"estacion": "Estación", "comuna": "Comuna", "region": "Región", "observacion_afluencia": "Obs. afluencia", "observacion_estacion": "Obs. estación"})
                st.dataframe(detail_table, use_container_width=True, hide_index=True)
    st.markdown("</div></div>", unsafe_allow_html=True)


def render_perfil_carga():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Perfil de Carga</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>Lectura diaria por servicio para revisar pasajeros a bordo, embarques y bajadas por estación, con un comparativo agregado de todos los servicios del día cuando el formato se encuentra implementado.</div>",
        unsafe_allow_html=True,
    )

    service_options = list(PROFILE_SERVICE_CONFIG.keys())
    sel_service_col, sel_date_col, info_col = st.columns([1.15, 1.05, 1.8])
    with sel_service_col:
        profile_service_sel = st.selectbox(
            "Servicio de perfil",
            options=service_options,
            index=0,
            key="profile_service_root_selector",
        )

    perfil_df, perfil_path, perfil_missing_cols, perfil_files, perfil_status = load_profile_service_data(
        profile_service_sel,
        str(data_path),
    )

    folder_name = get_default_profile_folder_name(profile_service_sel)
    service_desc = PROFILE_SERVICE_CONFIG.get(profile_service_sel, {}).get("description", "")

    with info_col:
        st.markdown(
            f"<div class='map-note'><b>Carpeta esperada:</b> {folder_name}<br>{service_desc}</div>",
            unsafe_allow_html=True,
        )

    if perfil_status == "no_data" or perfil_df.empty:
        with sel_date_col:
            st.selectbox(
                "📅 Fecha disponible",
                options=[],
                index=None,
                placeholder="Sin fechas disponibles",
                key="perfil_fecha_selector_empty",
            )
        st.info(
            f"No se encontraron archivos CSV para <b>{profile_service_sel}</b>. Cree la carpeta <b>{folder_name}</b> en el repositorio y agregue allí los archivos diarios. Ruta buscada: <b>{perfil_path}</b>.",
            icon="ℹ️",
        )
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    if perfil_status == "unsupported_format" or perfil_missing_cols:
        with sel_date_col:
            fechas_temp = sorted(pd.to_datetime(perfil_df.get("fecha"), errors="coerce").dropna().dt.date.unique().tolist(), reverse=True) if "fecha" in perfil_df.columns else []
            st.selectbox(
                "📅 Fecha disponible",
                options=fechas_temp,
                format_func=lambda d: pd.to_datetime(d).strftime("%d-%m-%Y") if pd.notna(d) else "-",
                index=0 if fechas_temp else None,
                placeholder="Sin fechas válidas",
                key="perfil_fecha_selector_unsupported",
            )
        st.warning(
            f"Se encontraron archivos para <b>{profile_service_sel}</b>, pero el formato aún no es compatible con esta vista. Columnas faltantes: <b>{', '.join(perfil_missing_cols)}</b>."
        )
        if perfil_files:
            st.caption(f"Archivos detectados: {len(perfil_files)} | carpeta origen: {perfil_path}")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_disponibles = sorted(perfil_df["fecha"].dropna().unique().tolist(), reverse=True)
    if not fechas_disponibles:
        with sel_date_col:
            st.selectbox(
                "📅 Fecha disponible",
                options=[],
                index=None,
                placeholder="Sin fechas válidas",
                key="perfil_fecha_selector_no_dates",
            )
        st.warning("No existen fechas válidas dentro de los archivos de perfil de carga.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_disponibles = sorted(fechas_disponibles)
    fechas_set = set(fechas_disponibles)
    fecha_default = fechas_disponibles[-1]
    fecha_key = f"perfil_fecha_cal_{profile_service_sel}"
    fecha_prev = st.session_state.get(fecha_key)
    if isinstance(fecha_prev, date):
        if fecha_prev in fechas_set:
            fecha_default = fecha_prev
        else:
            fecha_default = min(fechas_disponibles, key=lambda d: abs((d - fecha_prev).days))

    with sel_date_col:
        fecha_sel_input = st.date_input(
            "📅 Fecha",
            value=fecha_default,
            min_value=fechas_disponibles[0],
            max_value=fechas_disponibles[-1],
            format="DD/MM/YYYY",
            key=fecha_key,
            help="Seleccione una fecha desde el calendario. Si no existen datos para esa fecha, se utilizará automáticamente la fecha disponible más cercana.",
        )

    fecha_sel = fecha_sel_input
    if fecha_sel not in fechas_set:
        fecha_sel = min(fechas_disponibles, key=lambda d: abs((d - fecha_sel).days))
        st.info(
            f"La fecha seleccionada no tiene datos cargados para {profile_service_sel}. "
            f"Se utiliza la fecha disponible más cercana: {pd.to_datetime(fecha_sel).strftime('%d-%m-%Y')}."
        )

    perfil_fecha = perfil_df[perfil_df["fecha"] == fecha_sel].copy()

    lineas_disp = sorted([x for x in perfil_fecha["linea"].dropna().astype(str).unique().tolist() if x])
    direcciones_base = []
    servicios_base = []

    row_sel_2a, row_sel_2b, row_sel_2c = st.columns([0.9, 1.15, 1.15])
    with row_sel_2a:
        linea_sel = option_selector(
            "Línea",
            lineas_disp,
            key=f"perfil_linea_selector_{profile_service_sel}",
            default=lineas_disp[0] if lineas_disp else None,
            horizontal=True,
        )

    perfil_linea = perfil_fecha[perfil_fecha["linea"].astype(str) == str(linea_sel)].copy() if linea_sel else perfil_fecha.iloc[0:0].copy()
    direcciones_disp = sorted([x for x in perfil_linea["direccion"].dropna().astype(str).unique().tolist() if x])
    with row_sel_2b:
        direccion_sel = option_selector(
            "Dirección",
            direcciones_disp,
            key=f"perfil_direccion_selector_{profile_service_sel}",
            default=direcciones_disp[0] if direcciones_disp else None,
            horizontal=True,
        )

    perfil_dir = perfil_linea[perfil_linea["direccion"].astype(str) == str(direccion_sel)].copy() if direccion_sel else perfil_linea.iloc[0:0].copy()
    servicios_disp = sorted(perfil_dir["servicio_label"].dropna().astype(str).unique().tolist(), key=lambda x: (len(x), x))
    with row_sel_2c:
        servicio_sel = st.selectbox(
            "Servicio específico",
            options=servicios_disp,
            index=0 if servicios_disp else None,
            placeholder="Sin servicios disponibles",
            key=f"perfil_servicio_selector_{profile_service_sel}",
        ) if servicios_disp else None

    if perfil_dir.empty or not servicio_sel:
        st.warning("No existen datos para la combinación de servicio, fecha, línea y dirección seleccionada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    perfil_servicio = perfil_dir[perfil_dir["servicio_label"].astype(str) == str(servicio_sel)].copy()
    perfil_servicio["event_time"] = perfil_servicio["t_arr_est"].fillna(perfil_servicio["t_dep_est"])
    station_order = get_station_order_from_profile(perfil_servicio)
    if station_order:
        perfil_servicio["estacion"] = pd.Categorical(perfil_servicio["estacion"], categories=station_order, ordered=True)
        perfil_servicio = perfil_servicio.sort_values(["estacion", "event_time"])

    total_embarque = perfil_servicio["B_embarque"].sum(min_count=1)
    total_bajadas = perfil_servicio["D_bajadas"].sum(min_count=1)
    max_abordo = perfil_servicio["L_out_abordo"].max()
    capacidad = perfil_servicio["capacidad_tren"].dropna().iloc[0] if "capacidad_tren" in perfil_servicio.columns and perfil_servicio["capacidad_tren"].dropna().any() else None

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Servicios del día", perfil_dir["servicio_label"].nunique())
    m2.metric("Embarques del servicio", fmt_pax(total_embarque))
    m3.metric("Bajadas del servicio", fmt_pax(total_bajadas))
    m4.metric("Máximo a bordo", fmt_pax(max_abordo))

    titulo_grafico = f"{profile_service_sel} | {linea_sel} | {direccion_sel} | Servicio {servicio_sel}"
    fig = build_perfil_carga_chart(perfil_servicio, titulo_grafico)
    st.plotly_chart(fig, use_container_width=True)

    if capacidad is not None and pd.notna(max_abordo) and float(capacidad) != 0:
        ocupacion_max = (float(max_abordo) / float(capacidad)) * 100
        st.caption(f"Capacidad tren: {fmt_pax(capacidad)} pasajeros. Ocupación máxima observada: {fmt_pct(ocupacion_max)}.")
    elif perfil_files:
        st.caption(f"Archivos cargados: {len(perfil_files)} | carpeta origen: {perfil_path}")

    st.markdown("<div class='section-title'>Comparativo diario de pasajeros a bordo</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>Se muestra la evolución de <b>L_out_abordo</b> para todos los servicios de la fecha, línea y dirección seleccionadas.</div>",
        unsafe_allow_html=True,
    )
    fig_comp = build_perfil_abordo_comparativo_chart(
        perfil_dir,
        f"{profile_service_sel} | {linea_sel} | {direccion_sel} | Todos los servicios del día"
    )
    st.plotly_chart(fig_comp, use_container_width=True)

    st.markdown("<div class='section-title'>Detalle por estación</div>", unsafe_allow_html=True)
    detalle_cols = [
        "estacion", "t_arr_est", "t_dep_est", "B_embarque", "D_bajadas",
        "L_in_abordo", "L_out_abordo", "Capacidad_disponible", "R_quedados", "Q_out_cola", "archivo_origen"
    ]
    detalle_cols = [c for c in detalle_cols if c in perfil_servicio.columns]
    detalle = perfil_servicio[detalle_cols].copy()

    if "t_arr_est" in detalle.columns:
        detalle["Llegada"] = pd.to_datetime(detalle["t_arr_est"], errors="coerce").dt.strftime("%H:%M:%S").fillna("-")
    if "t_dep_est" in detalle.columns:
        detalle["Salida"] = pd.to_datetime(detalle["t_dep_est"], errors="coerce").dt.strftime("%H:%M:%S").fillna("-")
    if "B_embarque" in detalle.columns:
        detalle["Suben"] = detalle["B_embarque"].apply(fmt_pax)
    if "D_bajadas" in detalle.columns:
        detalle["Bajan"] = detalle["D_bajadas"].apply(fmt_pax)
    if "L_in_abordo" in detalle.columns:
        detalle["A bordo entrada"] = detalle["L_in_abordo"].apply(fmt_pax)
    if "L_out_abordo" in detalle.columns:
        detalle["A bordo salida"] = detalle["L_out_abordo"].apply(fmt_pax)
    if "Capacidad_disponible" in detalle.columns:
        detalle["Cap. disponible"] = detalle["Capacidad_disponible"].apply(fmt_pax)
    if "R_quedados" in detalle.columns:
        detalle["Quedados"] = detalle["R_quedados"].apply(fmt_pax)
    if "Q_out_cola" in detalle.columns:
        detalle["Cola salida"] = detalle["Q_out_cola"].apply(fmt_pax)
    if "archivo_origen" in detalle.columns:
        detalle = detalle.rename(columns={"archivo_origen": "Archivo"})

    columnas_mostrar = [
        c for c in ["estacion", "Llegada", "Salida", "Suben", "Bajan", "A bordo entrada", "A bordo salida", "Cap. disponible", "Quedados", "Cola salida", "Archivo"]
        if c in detalle.columns
    ]
    detalle_show = detalle[columnas_mostrar].rename(columns={"estacion": "Estación"})
    st.dataframe(detalle_show, use_container_width=True, hide_index=True)
    st.markdown("</div></div>", unsafe_allow_html=True)


OD_SERVICE_CONFIG = {
    "Biotren": {
        "folder_candidates": ["od_bt", ".od_bt"],
        "description": "Base transaccional OD para analizar entradas, salidas y patrones horarios por estación.",
    },
}


def get_od_folder_candidates(service_name, data_path):
    base = Path(__file__).resolve().parent
    config = OD_SERVICE_CONFIG.get(service_name, {})
    folder_names = config.get("folder_candidates", [])
    candidates = []
    for folder_name in folder_names:
        candidates.extend([
            base / folder_name,
            data_path / folder_name,
        ])

    unique = []
    seen = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def get_default_od_folder_name(service_name):
    config = OD_SERVICE_CONFIG.get(service_name, {})
    folder_names = config.get("folder_candidates", [])
    return folder_names[0] if folder_names else "od_data"


@st.cache_data
def load_od_service_data(service_name, data_path_str):
    data_path = Path(data_path_str)
    required_cols = ["origen", "destino", "linea", "t_entrada_viaje", "t_salida_viaje"]

    od_folder = None
    csv_files = []
    for candidate in get_od_folder_candidates(service_name, data_path):
        if candidate.exists() and candidate.is_dir():
            files = sorted(candidate.glob("*.csv"))
            if files:
                od_folder = candidate
                csv_files = files
                break
            if od_folder is None:
                od_folder = candidate

    if not csv_files:
        fallback_folder = od_folder if od_folder is not None else Path(data_path) / get_default_od_folder_name(service_name)
        return pd.DataFrame(), str(fallback_folder), required_cols, [], "no_data"

    frames = []
    loaded_files = []
    for csv_file in csv_files:
        try:
            temp = pd.read_csv(csv_file, low_memory=False)
            temp["archivo_origen"] = csv_file.name
            frames.append(temp)
            loaded_files.append(csv_file.name)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(), str(od_folder), required_cols, loaded_files, "read_error"

    od_df = pd.concat(frames, ignore_index=True)
    missing = [c for c in required_cols if c not in od_df.columns]
    if missing:
        return od_df, str(od_folder), missing, loaded_files, "unsupported_format"

    for col in ["origen", "destino", "linea", "direccion"]:
        if col not in od_df.columns:
            od_df[col] = ""
        od_df[col] = od_df[col].fillna("").astype(str).str.strip()

    for col in ["t_entrada_viaje", "t_salida_viaje"]:
        od_df[col] = pd.to_datetime(od_df[col], errors="coerce")

    if "dia_proceso" in od_df.columns:
        od_df["fecha"] = pd.to_datetime(od_df["dia_proceso"], errors="coerce").dt.date
    else:
        od_df["fecha"] = od_df["t_entrada_viaje"].dt.date

    if "servicio_final" in od_df.columns:
        od_df["servicio_label"] = od_df["servicio_final"].apply(format_service_id)
    elif "servicio" in od_df.columns:
        od_df["servicio_label"] = od_df["servicio"].apply(format_service_id)
    else:
        od_df["servicio_label"] = "-"

    if "tarjeta_id" in od_df.columns:
        od_df["tarjeta_id"] = pd.to_numeric(od_df["tarjeta_id"], errors="coerce")
    if "viaje_idx" in od_df.columns:
        od_df["viaje_idx"] = pd.to_numeric(od_df["viaje_idx"], errors="coerce")

    od_df = od_df.dropna(subset=["fecha"])
    return od_df, str(od_folder), [], loaded_files, "ok"


def classify_operational_period(ts):
    if pd.isna(ts):
        return None
    hour_value = ts.hour + (ts.minute / 60.0)
    if 6 <= hour_value < 9:
        return "Punta Mañana"
    if 9 <= hour_value < 17:
        return "Valle"
    if 17 <= hour_value < 21:
        return "Punta Tarde"
    return "Fuera de periodo"


def get_time_bucket_series(timestamp_series, granularity):
    ts = pd.to_datetime(timestamp_series, errors="coerce")
    if granularity == "Periodos operacionales":
        return ts.apply(classify_operational_period)

    hours = 1 if granularity == "Bloques de 1 hora" else 2
    start = ts.dt.floor(f"{hours}h")
    end = start + pd.Timedelta(hours=hours)
    labels = start.dt.strftime("%H:%M") + "-" + end.dt.strftime("%H:%M")
    return labels.where(start.notna(), None)


def get_bucket_order(bucket_values, granularity):
    values = [v for v in bucket_values if pd.notna(v)]
    if granularity == "Periodos operacionales":
        ordered = ["Punta Mañana", "Valle", "Punta Tarde", "Fuera de periodo"]
        return [v for v in ordered if v in set(values)]

    def sort_key(label):
        try:
            start_label = str(label).split("-")[0]
            hh, mm = start_label.split(":")
            return int(hh), int(mm)
        except Exception:
            return (99, 99)

    return sorted(list(dict.fromkeys(values)), key=sort_key)


def build_od_events(day_df, granularity):
    entries = day_df[["origen", "t_entrada_viaje"]].copy()
    entries.columns = ["estacion", "timestamp"]
    entries["tipo"] = "Entradas"

    exits = day_df[["destino", "t_salida_viaje"]].copy()
    exits.columns = ["estacion", "timestamp"]
    exits["tipo"] = "Salidas"

    events = pd.concat([entries, exits], ignore_index=True)
    events["estacion"] = events["estacion"].fillna("").astype(str).str.strip()
    events = events[events["estacion"] != ""].copy()
    events["timestamp"] = pd.to_datetime(events["timestamp"], errors="coerce")
    events = events.dropna(subset=["timestamp"]).copy()
    events["bucket"] = get_time_bucket_series(events["timestamp"], granularity)
    events = events.dropna(subset=["bucket"]).copy()
    return events


def build_station_flow_chart(flow_df, bucket_order, station_name, granularity):
    fig = go.Figure()
    station_plot = flow_df.copy()
    if bucket_order:
        station_plot["bucket"] = pd.Categorical(station_plot["bucket"], categories=bucket_order, ordered=True)
        station_plot = station_plot.sort_values("bucket")

    for tipo, color in [("Entradas", EFE_BLUE), ("Salidas", EFE_RED)]:
        temp = station_plot[station_plot["tipo"] == tipo]
        fig.add_trace(
            go.Bar(
                x=temp["bucket"],
                y=temp["cantidad"],
                name=tipo,
                marker_color=color,
                hovertemplate="<b>%{x}</b><br>" + tipo + ": %{y:,.0f}<extra></extra>",
            )
        )

    total_temp = (
        station_plot.groupby("bucket", as_index=False)["cantidad"]
        .sum()
    )
    if bucket_order:
        total_temp["bucket"] = pd.Categorical(total_temp["bucket"], categories=bucket_order, ordered=True)
        total_temp = total_temp.sort_values("bucket")

    fig.add_trace(
        go.Scatter(
            x=total_temp["bucket"],
            y=total_temp["cantidad"],
            mode="lines+markers",
            name="Movimientos totales",
            line=dict(color=SUCCESS, width=3),
            marker=dict(size=8),
            hovertemplate="<b>%{x}</b><br>Total: %{y:,.0f}<extra></extra>",
        )
    )

    fig.update_layout(
        title=f"{station_name} | {granularity}",
        plot_bgcolor=EFE_WHITE,
        paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20),
        height=430,
        barmode="group",
        font=dict(color=TEXT_MAIN),
        title_font=dict(color=EFE_BLUE, size=16),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array", categoryarray=bucket_order if bucket_order else None)
    fig.update_yaxes(title="Transacciones")
    return fig


def build_od_heatmap(events_df, bucket_order, heatmap_mode):
    if events_df.empty:
        fig = go.Figure()
        fig.update_layout(
            plot_bgcolor=EFE_WHITE,
            paper_bgcolor=EFE_WHITE,
            margin=dict(l=20, r=20, t=40, b=20),
            height=420,
        )
        return fig

    plot_df = events_df.copy()
    if heatmap_mode != "Movimientos totales":
        plot_df = plot_df[plot_df["tipo"] == heatmap_mode].copy()

    agg = (
        plot_df.groupby(["estacion", "bucket"], as_index=False)
        .size()
        .rename(columns={"size": "cantidad"})
    )
    if agg.empty:
        fig = go.Figure()
        fig.update_layout(
            plot_bgcolor=EFE_WHITE,
            paper_bgcolor=EFE_WHITE,
            margin=dict(l=20, r=20, t=40, b=20),
            height=420,
        )
        return fig

    station_order = (
        agg.groupby("estacion")["cantidad"]
        .sum()
        .sort_values(ascending=False)
        .index
        .tolist()
    )
    pivot = (
        agg.pivot(index="estacion", columns="bucket", values="cantidad")
        .fillna(0)
        .reindex(index=station_order)
    )
    if bucket_order:
        existing_columns = [c for c in bucket_order if c in pivot.columns]
        pivot = pivot.reindex(columns=existing_columns)

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale="Blues",
            hovertemplate="<b>%{y}</b><br>%{x}<br>Transacciones: %{z:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"Mapa de calor | {heatmap_mode}",
        plot_bgcolor=EFE_WHITE,
        paper_bgcolor=EFE_WHITE,
        margin=dict(l=20, r=20, t=55, b=20),
        height=max(420, 120 + 26 * len(pivot.index)),
        font=dict(color=TEXT_MAIN),
        title_font=dict(color=EFE_BLUE, size=16),
    )
    fig.update_xaxes(title="")
    fig.update_yaxes(title="")
    return fig


def render_od_estaciones():
    st.markdown("<div class='content-panel'><div class='section-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>OD Estaciones - Biotren</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>Análisis detallado de entradas, salidas y patrones temporales por estación a partir de transacciones origen-destino. La lectura se realiza desde la carpeta <b>od_bt</b> del repositorio.</div>",
        unsafe_allow_html=True,
    )

    od_service_sel = "Biotren"
    od_df, od_path, od_missing_cols, od_files, od_status = load_od_service_data(
        od_service_sel,
        str(data_path),
    )
    folder_name = get_default_od_folder_name(od_service_sel)

    info_col_a, info_col_b = st.columns([1.2, 2.8])
    with info_col_a:
        st.markdown(
            f"<div class='map-note'><b>Carpeta esperada:</b> {folder_name}</div>",
            unsafe_allow_html=True,
        )
    with info_col_b:
        st.markdown(
            "<div class='map-note'><b>Enfoque:</b> esta vista permite analizar concentraciones de entradas y salidas por estación según periodos operacionales o bloques horarios de 1 y 2 horas.</div>",
            unsafe_allow_html=True,
        )

    if od_status == "no_data" or od_df.empty:
        st.info(
            f"No se encontraron archivos CSV para la vista OD de <b>{od_service_sel}</b>. Cree la carpeta <b>{folder_name}</b> en el repositorio y agregue allí los archivos diarios. Ruta buscada: <b>{od_path}</b>.",
            icon="ℹ️",
        )
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    if od_status == "unsupported_format" or od_missing_cols:
        st.warning(
            f"Se encontraron archivos OD, pero el formato aún no es compatible con esta vista. Columnas faltantes: <b>{', '.join(od_missing_cols)}</b>."
        )
        if od_files:
            st.caption(f"Archivos detectados: {len(od_files)} | carpeta origen: {od_path}")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_disponibles = sorted([x for x in od_df["fecha"].dropna().unique().tolist() if pd.notna(x)])
    if not fechas_disponibles:
        st.warning("No existen fechas válidas en la base OD cargada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    fechas_set = set(fechas_disponibles)
    fecha_default = fechas_disponibles[-1]
    fecha_key = "od_bt_fecha_cal"
    fecha_prev = st.session_state.get(fecha_key)
    if isinstance(fecha_prev, date):
        if fecha_prev in fechas_set:
            fecha_default = fecha_prev
        else:
            fecha_default = min(fechas_disponibles, key=lambda d: abs((d - fecha_prev).days))

    row_filters_1a, row_filters_1b, row_filters_1c = st.columns([1.0, 1.1, 1.3])
    with row_filters_1a:
        fecha_input = st.date_input(
            "📅 Fecha",
            value=fecha_default,
            min_value=fechas_disponibles[0],
            max_value=fechas_disponibles[-1],
            format="DD/MM/YYYY",
            key=fecha_key,
            help="Si la fecha seleccionada no tiene datos cargados, se utilizará automáticamente la fecha disponible más cercana.",
        )

    fecha_sel = fecha_input
    if fecha_sel not in fechas_set:
        fecha_sel = min(fechas_disponibles, key=lambda d: abs((d - fecha_sel).days))
        st.info(
            f"La fecha seleccionada no tiene datos cargados para la base OD. "
            f"Se utiliza la fecha disponible más cercana: {pd.to_datetime(fecha_sel).strftime('%d-%m-%Y')}."
        )

    od_fecha = od_df[od_df["fecha"] == fecha_sel].copy()
    lineas_disp = sorted([x for x in od_fecha["linea"].dropna().astype(str).unique().tolist() if x])
    with row_filters_1b:
        linea_sel = option_selector(
            "Línea",
            lineas_disp,
            key="od_linea_selector",
            default=lineas_disp[0] if lineas_disp else None,
            horizontal=True,
        )

    od_linea = od_fecha[od_fecha["linea"].astype(str) == str(linea_sel)].copy() if linea_sel else od_fecha.iloc[0:0].copy()
    direcciones_disp = sorted([x for x in od_linea["direccion"].dropna().astype(str).unique().tolist() if x])
    with row_filters_1c:
        if direcciones_disp:
            direccion_sel = option_selector(
                "Dirección",
                direcciones_disp,
                key="od_direccion_selector",
                default=direcciones_disp[0] if direcciones_disp else None,
                horizontal=True,
            )
        else:
            direccion_sel = None
            st.markdown("<div class='small-note'>No hay direcciones disponibles en la base filtrada.</div>", unsafe_allow_html=True)

    od_filtrado = od_linea.copy()
    if direccion_sel:
        od_filtrado = od_filtrado[od_filtrado["direccion"].astype(str) == str(direccion_sel)].copy()

    station_candidates = sorted(list(set(od_filtrado["origen"].dropna().astype(str).tolist()) | set(od_filtrado["destino"].dropna().astype(str).tolist())))
    row_filters_2a, row_filters_2b, row_filters_2c = st.columns([1.3, 1.6, 1.1])
    with row_filters_2a:
        station_sel = st.selectbox(
            "Estación",
            options=station_candidates,
            index=0 if station_candidates else None,
            placeholder="Sin estaciones disponibles",
            key="od_station_selector",
        ) if station_candidates else None

    with row_filters_2b:
        granularity_sel = option_selector(
            "Segmentación temporal",
            ["Periodos operacionales", "Bloques de 1 hora", "Bloques de 2 horas"],
            key="od_granularity_selector",
            default="Bloques de 1 hora",
            horizontal=True,
        )

    with row_filters_2c:
        heatmap_mode = option_selector(
            "Mapa de calor",
            ["Movimientos totales", "Entradas", "Salidas"],
            key="od_heatmap_mode_selector",
            default="Movimientos totales",
            horizontal=True,
        )

    if od_filtrado.empty or not station_sel:
        st.warning("No existen datos para la combinación de fecha, línea, dirección y estación seleccionada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    events_df = build_od_events(od_filtrado, granularity_sel)
    if events_df.empty:
        st.warning("No fue posible construir eventos horarios con la base OD filtrada.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    bucket_order = get_bucket_order(events_df["bucket"].tolist(), granularity_sel)

    station_events = events_df[events_df["estacion"].astype(str) == str(station_sel)].copy()
    flow_df = (
        station_events.groupby(["bucket", "tipo"], as_index=False)
        .size()
        .rename(columns={"size": "cantidad"})
    )

    total_entries = int((od_filtrado["origen"].astype(str) == str(station_sel)).sum())
    total_exits = int((od_filtrado["destino"].astype(str) == str(station_sel)).sum())

    peak_entries = flow_df[flow_df["tipo"] == "Entradas"].sort_values("cantidad", ascending=False).head(1)
    peak_exits = flow_df[flow_df["tipo"] == "Salidas"].sort_values("cantidad", ascending=False).head(1)

    peak_entries_label = "-"
    peak_exits_label = "-"
    if not peak_entries.empty:
        peak_entries_label = f"{peak_entries.iloc[0]['bucket']} ({fmt_pax(peak_entries.iloc[0]['cantidad'])})"
    if not peak_exits.empty:
        peak_exits_label = f"{peak_exits.iloc[0]['bucket']} ({fmt_pax(peak_exits.iloc[0]['cantidad'])})"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Entradas estación", fmt_pax(total_entries))
    m2.metric("Salidas estación", fmt_pax(total_exits))
    m3.metric("Punta de entrada", peak_entries_label)
    m4.metric("Punta de salida", peak_exits_label)

    fig_station = build_station_flow_chart(flow_df, bucket_order, station_sel, granularity_sel)
    st.plotly_chart(fig_station, use_container_width=True)

    detalle_bucket = (
        flow_df.pivot(index="bucket", columns="tipo", values="cantidad")
        .fillna(0)
        .reset_index()
        if not flow_df.empty else pd.DataFrame(columns=["bucket", "Entradas", "Salidas"])
    )
    if not detalle_bucket.empty:
        for col in ["Entradas", "Salidas"]:
            if col not in detalle_bucket.columns:
                detalle_bucket[col] = 0
        detalle_bucket["Total"] = detalle_bucket.get("Entradas", 0) + detalle_bucket.get("Salidas", 0)
        detalle_bucket["bucket"] = pd.Categorical(detalle_bucket["bucket"], categories=bucket_order, ordered=True)
        detalle_bucket = detalle_bucket.sort_values("bucket")
        detalle_show = detalle_bucket.copy()
        for col in ["Entradas", "Salidas", "Total"]:
            detalle_show[col] = detalle_show[col].apply(fmt_pax)
        detalle_show = detalle_show.rename(columns={"bucket": "Tramo"})
        st.dataframe(detalle_show, use_container_width=True, hide_index=True)

    lower_left, lower_right = st.columns([1.45, 1.0])
    with lower_left:
        fig_heatmap = build_od_heatmap(events_df, bucket_order, heatmap_mode)
        st.plotly_chart(fig_heatmap, use_container_width=True)

    concentration_df = (
        events_df.groupby(["estacion", "bucket"], as_index=False)
        .size()
        .rename(columns={"size": "cantidad"})
        .sort_values(["cantidad", "estacion"], ascending=[False, True])
        .head(12)
    )
    concentration_df["Transacciones"] = concentration_df["cantidad"].apply(fmt_pax)
    concentration_show = concentration_df[["estacion", "bucket", "Transacciones"]].rename(
        columns={"estacion": "Estación", "bucket": "Tramo"}
    )

    destinos_df = (
        od_filtrado[od_filtrado["origen"].astype(str) == str(station_sel)]
        .groupby("destino", as_index=False)
        .size()
        .rename(columns={"size": "viajes"})
        .sort_values("viajes", ascending=False)
        .head(10)
    )
    destinos_df["Viajes"] = destinos_df["viajes"].apply(fmt_pax)
    destinos_show = destinos_df[["destino", "Viajes"]].rename(columns={"destino": "Destino"})

    origenes_df = (
        od_filtrado[od_filtrado["destino"].astype(str) == str(station_sel)]
        .groupby("origen", as_index=False)
        .size()
        .rename(columns={"size": "viajes"})
        .sort_values("viajes", ascending=False)
        .head(10)
    )
    origenes_df["Viajes"] = origenes_df["viajes"].apply(fmt_pax)
    origenes_show = origenes_df[["origen", "Viajes"]].rename(columns={"origen": "Origen"})

    with lower_right:
        st.markdown("<div class='section-title'>Mayores concentraciones</div>", unsafe_allow_html=True)
        st.dataframe(concentration_show, use_container_width=True, hide_index=True)

    bottom_left, bottom_right = st.columns(2)
    with bottom_left:
        st.markdown(f"<div class='section-title'>Principales destinos desde {station_sel}</div>", unsafe_allow_html=True)
        st.dataframe(destinos_show, use_container_width=True, hide_index=True)
    with bottom_right:
        st.markdown(f"<div class='section-title'>Principales orígenes hacia {station_sel}</div>", unsafe_allow_html=True)
        st.dataframe(origenes_show, use_container_width=True, hide_index=True)

    if od_files:
        st.caption(f"Archivos OD cargados: {len(od_files)} | carpeta origen: {od_path}")

    st.markdown("</div></div>", unsafe_allow_html=True)


if section_sel == "Resumen ejecutivo":
    render_resumen_ejecutivo()
elif section_sel == "KPIs":
    render_kpis()
elif section_sel == "Personas":
    render_personas()
elif section_sel == "Estaciones":
    render_detalle_servicio()
elif section_sel == "Perfil de Carga":
    render_perfil_carga()
elif section_sel == "OD Estaciones":
    render_od_estaciones()

# =========================================================
# PIE
# =========================================================
st.markdown("---")
st.caption("La aplicación lee automáticamente los archivos CSV contenidos en el repositorio de GitHub, incluyendo carpetas dedicadas para perfiles de carga por servicio.")
