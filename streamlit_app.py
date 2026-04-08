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
st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: {BG_LIGHT};
        color: {TEXT_MAIN};
    }}

    header[data-testid="stHeader"] {{
        display: none !important;
    }}

    div[data-testid="stToolbar"] {{
        display: none !important;
    }}

    div[data-testid="stDecoration"] {{
        display: none !important;
    }}

    div[data-testid="stStatusWidget"] {{
        display: none !important;
    }}

    div[data-testid="collapsedControl"] {{
        display: none !important;
    }}

    section[data-testid="stSidebar"] {{
        display: none !important;
    }}

    #MainMenu {{
        visibility: hidden;
    }}

    footer {{
        visibility: hidden;
        height: 0;
    }}

    .main-title {{
        font-size: 2.2rem;
        font-weight: 800;
        color: {EFE_BLUE};
        margin-top: 1.15rem;
        margin-bottom: 0.15rem;
    }}

    .subtitle {{
        font-size: 0.95rem;
        color: {TEXT_MUTED};
        margin-top: 0.45rem;
        margin-bottom: 0.35rem;
    }}

    .top-period-wrapper {{
        margin-top: 1.25rem;
    }}

    .section-title {{
        font-size: 1.2rem;
        font-weight: 700;
        color: {EFE_BLUE};
        margin-top: 0.5rem;
        margin-bottom: 0.6rem;
    }}

    .efe-card {{
        background: {EFE_WHITE};
        border: 1px solid {BORDER};
        border-radius: 16px;
        padding: 18px 18px 14px 18px;
        box-shadow: 0 8px 20px rgba(0, 40, 87, 0.06);
        min-height: 145px;
        transition: transform 0.16s ease, box-shadow 0.16s ease;
    }}

    .efe-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 12px 28px rgba(0, 40, 87, 0.12);
    }}

    .efe-card-title {{
        font-size: 0.9rem;
        color: {TEXT_MUTED};
        margin-bottom: 0.4rem;
    }}

    .efe-card-value {{
        font-size: 1.8rem;
        font-weight: 800;
        color: {EFE_BLUE};
        line-height: 1.1;
        margin-bottom: 0.2rem;
    }}

    .efe-card-meta {{
        font-size: 0.9rem;
        color: {TEXT_MAIN};
        margin-bottom: 0.2rem;
    }}

    .efe-card-delta {{
        font-size: 0.88rem;
        font-weight: 600;
    }}

    .efe-observation {{
        background: #FFF7ED;
        border: 1px solid #FED7AA;
        border-radius: 12px;
        padding: 0.7rem 0.85rem;
        font-size: 0.84rem;
        color: {TEXT_MAIN};
        margin-top: 0.45rem;
        margin-bottom: 0.1rem;
        line-height: 1.35;
    }}

    .efe-observation strong {{
        color: {WARNING};
    }}

    .efe-observation-empty {{
        background: #ECFDF5;
        border: 1px solid #A7F3D0;
        border-radius: 12px;
        padding: 0.7rem 0.85rem;
        font-size: 0.84rem;
        color: {TEXT_MAIN};
        margin-top: 0.45rem;
        margin-bottom: 0.1rem;
        line-height: 1.35;
    }}

    .efe-observation-empty strong {{
        color: {SUCCESS};
    }}

    .small-note {{
        color: {TEXT_MUTED};
        font-size: 0.82rem;
    }}

    .block-container {{
        padding-top: 0.8rem;
        padding-bottom: 1rem;
    }}

    .service-title {{
        font-size: 1.05rem;
        font-weight: 800;
        color: {EFE_BLUE};
        margin: 0.2rem 0 0.8rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 2px solid {BORDER};
    }}

    .map-note {{
        background: #EFF6FF;
        border: 1px solid #BFDBFE;
        border-radius: 12px;
        padding: 0.75rem 0.9rem;
        font-size: 0.85rem;
        color: {TEXT_MAIN};
        margin-bottom: 0.75rem;
    }}

    .nav-panel {{
        background: rgba(255,255,255,0.94);
        border: 1px solid #E2E8F0;
        border-radius: 18px;
        padding: 0.8rem 1rem 0.35rem 1rem;
        margin: 0.35rem 0 1rem 0;
        box-shadow: 0 10px 22px rgba(0, 40, 87, 0.08);
        backdrop-filter: blur(8px);
    }}

    .toolbar-panel {{
        background: rgba(255,255,255,0.88);
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        padding: 0.75rem 0.95rem;
        margin: 0.55rem 0 0.85rem 0;
        box-shadow: 0 8px 18px rgba(0, 40, 87, 0.05);
    }}

    .toolbar-label {{
        font-size: 0.82rem;
        font-weight: 700;
        color: {TEXT_MUTED};
        text-transform: uppercase;
        letter-spacing: 0.03em;
        margin-bottom: 0.2rem;
    }}

    .filters-summary {{
        color: {TEXT_MUTED};
        font-size: 0.84rem;
        margin-top: 0.1rem;
        line-height: 1.35;
    }}

    .filters-summary strong {{
        color: {EFE_BLUE};
    }}


    .sticky-nav-anchor {{
        display: block;
        height: 0;
        margin: 0;
        padding: 0;
    }}

    div[data-testid="stVerticalBlock"]:has(.sticky-nav-anchor) {{
        position: sticky;
        top: 0.65rem;
        z-index: 999;
        background: linear-gradient(180deg, rgba(244,246,248,0.99) 0%, rgba(244,246,248,0.97) 86%, rgba(244,246,248,0.0) 100%);
        padding-top: 0.25rem;
        padding-bottom: 0.35rem;
    }}

    .content-panel {{
        background: transparent;
        animation: fadeSlideIn 0.22s ease-out;
    }}

    @keyframes fadeSlideIn {{
        from {{ opacity: 0; transform: translateY(6px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}


    div[data-testid="stMetric"] {{
        background: {EFE_WHITE};
        border: 1px solid {BORDER};
        padding: 10px 12px;
        border-radius: 14px;
    }}

    div[data-testid="stDataFrame"] {{
        border: 1px solid {BORDER};
        border-radius: 14px;
        overflow: hidden;
    }}
    </style>
    """,
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
    )
    fig.update_xaxes(title="", tickangle=-90, categoryorder="array", categoryarray=category_order)
    fig.update_yaxes(title="")

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
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=760)
        return fig

    # Coordenadas robustas
    plot_df["latitud"] = pd.to_numeric(plot_df["latitud"], errors="coerce")
    plot_df["longitud"] = pd.to_numeric(plot_df["longitud"], errors="coerce")
    plot_df = plot_df.dropna(subset=["latitud", "longitud"]).copy()

    if plot_df.empty:
        fig = go.Figure()
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=760)
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
        height=760,
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

# Los filtros se muestran dentro del cuerpo principal para evitar depender del sidebar
# y limpiar la franja superior de la aplicación.

# =========================================================
# ENCABEZADO Y PERÍODO VISIBLE
# =========================================================
col_logo, col_title, col_periodo = st.columns([1, 4.4, 1.6])

with col_logo:
    logo_candidates = [Path(__file__).resolve().parent / "assets" / "logoefe-azul.png", Path(__file__).resolve().parent / "logoefe-azul.png"]
    for logo_path in logo_candidates:
        if logo_path.exists():
            st.image(str(logo_path), use_container_width=True)
            break

with col_title:
    st.markdown("<div class='main-title'>KPIs e Iniciativas - Gerencia de Pasajeros</div>", unsafe_allow_html=True)
    st.markdown("<div class='subtitle'>Panel de seguimiento ejecutivo de desempeño e iniciativas.</div>", unsafe_allow_html=True)

with col_periodo:
    st.markdown("<div class='top-period-wrapper'></div>", unsafe_allow_html=True)
    periodo_sel = st.selectbox("Período de análisis", options=periodos, index=default_period_index, key="periodo_top")

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

filter_left, filter_right = st.columns([4.2, 1.2])
with filter_right:
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

with filter_left:
    st.markdown("<div class='toolbar-panel'>", unsafe_allow_html=True)
    st.markdown("<div class='toolbar-label'>Filtros activos</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='filters-summary'><strong>Filtros activos:</strong> {active_filter_summary}</div>", unsafe_allow_html=True)
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
        ["Resumen ejecutivo", "KPIs", "Personas", "Detalle Servicio"],
        key="main_nav_selector",
        default="Resumen ejecutivo",
        horizontal=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# RENDER DE SECCIONES
# =========================================================
def render_resumen_ejecutivo():
    st.markdown("<div class='content-panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Resumen ejecutivo</div>", unsafe_allow_html=True)

    servicios_con_datos = [svc for svc in servicios_sel if svc in kpis_f["servicio"].astype(str).unique().tolist()]
    if kpis_f.empty:
        st.warning("No existen KPI para los filtros seleccionados.")
    elif not servicios_con_datos:
        st.warning("No existen servicios con KPI para el período y filtros seleccionados.")
    else:
        cols = st.columns(len(servicios_con_datos))
        for idx, servicio in enumerate(servicios_con_datos):
            servicio_df = kpis_f[kpis_f["servicio"].astype(str) == str(servicio)].copy()
            if "orden" in servicio_df.columns:
                servicio_df = servicio_df.sort_values(["orden", "nombre", "categoria"])
            else:
                servicio_df = servicio_df.sort_values(["nombre", "categoria"])

            with cols[idx]:
                st.markdown(f"<div class='service-title'>{servicio}</div>", unsafe_allow_html=True)
                for _, row in servicio_df.iterrows():
                    render_kpi_card(
                        str(row["nombre"]),
                        fmt_number(row["valor"], row["unidad"], row["nombre"]),
                        f"Meta: {fmt_number(row['meta'], row['unidad'], row['nombre'])}",
                        f"Desviación: {fmt_pct(row['variacion_pct'])}",
                        row["estado"],
                    )
                    render_observation_box(row.get("observacion", None))

    st.markdown("<div class='section-title'>Evolución por servicio</div>", unsafe_allow_html=True)
    nombres_kpi = sorted(kpis_hist["nombre"].dropna().astype(str).unique().tolist())
    resumen_kpi_sel = option_selector(
        "Seleccione KPI para evolución",
        nombres_kpi,
        key="kpi_hist_sel_resumen",
        default=nombres_kpi[0] if nombres_kpi else None,
        horizontal=True,
    )
    hist_sel = kpis_hist[kpis_hist["nombre"] == resumen_kpi_sel].copy()
    hist_sel = scale_kpi_dataframe_for_display(hist_sel, resumen_kpi_sel, ("valor", "meta"))

    unit_hist = None
    if not hist_sel.empty and "unidad" in hist_sel.columns:
        unit_hist = hist_sel["unidad"].dropna().astype(str).iloc[0] if not hist_sel["unidad"].dropna().empty else None

    servicios_hist = [svc for svc in servicios_sel if svc in hist_sel["servicio"].astype(str).unique().tolist()]
    if not servicios_hist:
        st.info("No hay datos históricos para el KPI seleccionado.")
    else:
        for servicio in servicios_hist:
            svc_hist = hist_sel[hist_sel["servicio"].astype(str) == str(servicio)].copy()
            if svc_hist.empty:
                st.info(f"No hay datos de {servicio} para el KPI seleccionado.")
            else:
                svc_hist = svc_hist.groupby("periodo", as_index=False)["valor"].sum()
                fig_svc = build_line_chart(
                    svc_hist,
                    f"{resumen_kpi_sel} - {servicio}",
                    height=380,
                    unit=unit_hist,
                    kpi_name=resumen_kpi_sel,
                    boxed_values=True,
                )
                fig_svc.update_traces(line_color=EFE_BLUE)
                st.plotly_chart(fig_svc, use_container_width=True)
                st.markdown("<div style='height:0.55rem'></div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def render_kpis():
    st.markdown("<div class='content-panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Análisis de KPIs</div>", unsafe_allow_html=True)
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
            fig_bt = build_line_chart(bt_hist, f"{kpi_sel} - Biotren", height=360, unit=hist_kpi["unidad"].dropna().astype(str).iloc[0] if not hist_kpi.empty and "unidad" in hist_kpi.columns and not hist_kpi["unidad"].dropna().empty else None, kpi_name=kpi_sel)
            fig_bt.update_traces(line_color=EFE_BLUE)
            st.plotly_chart(fig_bt, use_container_width=True)
    with col_b:
        otros_hist = hist_kpi[hist_kpi["servicio"].isin(RURAL_SERVICES)].copy()
        if otros_hist.empty:
            st.info("No hay datos de otros servicios para el KPI seleccionado.")
        else:
            otros_hist = otros_hist.groupby(["periodo", "servicio"], as_index=False)["valor"].sum()
            fig_ot = build_line_chart(otros_hist, f"{kpi_sel} - Otros servicios", color="servicio", height=360, unit=hist_kpi["unidad"].dropna().astype(str).iloc[0] if not hist_kpi.empty and "unidad" in hist_kpi.columns and not hist_kpi["unidad"].dropna().empty else None, kpi_name=kpi_sel)
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
                            height=360,
                            xaxis_title="",
                            yaxis_title="",
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
    st.markdown("</div>", unsafe_allow_html=True)


def render_personas():
    st.markdown("<div class='content-panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Vista por persona</div>", unsafe_allow_html=True)
    total_ini = len(iniciativas_f)
    en_curso = int((iniciativas_f["estado"] == "En curso").sum())
    atrasadas = int((iniciativas_f["estado"] == "Atrasada").sum())
    finalizadas = int((iniciativas_f["estado"] == "Finalizada").sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total iniciativas", total_ini)
    m2.metric("En curso", en_curso)
    m3.metric("Atrasadas", atrasadas)
    m4.metric("Finalizadas", finalizadas)

    col_left, col_right = st.columns([1.1, 1])
    with col_left:
        por_responsable = iniciativas_f.groupby("responsable", as_index=False).agg(cantidad=("id_iniciativa", "count"), avance_promedio=("avance_pct", "mean")).sort_values("cantidad", ascending=False)
        if por_responsable.empty:
            st.info("No hay iniciativas para mostrar según los filtros seleccionados.")
        else:
            fig = px.bar(por_responsable, x="responsable", y="cantidad", title="Carga de iniciativas por responsable", text="cantidad")
            fig.update_traces(marker_color=EFE_BLUE)
            fig.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=360)
            fig.update_xaxes(title="")
            fig.update_yaxes(title="Cantidad")
            st.plotly_chart(fig, use_container_width=True)
    with col_right:
        por_prioridad = iniciativas_f["prioridad"].value_counts().reset_index()
        por_prioridad.columns = ["prioridad", "cantidad"]
        if por_prioridad.empty:
            st.info("No hay prioridades para mostrar.")
        else:
            fig2 = px.pie(por_prioridad, names="prioridad", values="cantidad", title="Distribución por prioridad", color="prioridad", color_discrete_map={"Alta": EFE_RED, "Media": WARNING, "Baja": EFE_BLUE})
            fig2.update_layout(paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=360)
            st.plotly_chart(fig2, use_container_width=True)

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

        left_p, right_p = st.columns([1.1, 1])
        with left_p:
            if per_df.empty:
                st.info("No hay iniciativas para el responsable seleccionado.")
            else:
                fig = px.bar(per_df.sort_values("avance_pct"), x="avance_pct", y="nombre_iniciativa", orientation="h", title=f"Avance por iniciativa - {persona_sel}", text="avance_pct")
                fig.update_traces(marker_color=EFE_BLUE)
                fig.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=420)
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
                fig2.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=420, showlegend=False)
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
    st.markdown("</div>", unsafe_allow_html=True)


def render_detalle_servicio():
    st.markdown("<div class='content-panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Detalle Servicio</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='map-note'>"
        "Esta sección muestra la afluencia registrada por estación de forma georreferenciada, con encuadre automático del mapa para el servicio seleccionado y un análisis comparativo por estación."
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
            detalle_servicio_sel = option_selector("Servicio para análisis georreferenciado", servicios_detalle, key="detalle_servicio_selector", default=default_detalle_servicio, horizontal=True)

            periodos_detalle = sorted(afluencia_estacion[afluencia_estacion["servicio"].astype(str) == str(detalle_servicio_sel)]["periodo"].dropna().astype(str).unique().tolist())
            if not periodos_detalle:
                st.warning("No existen períodos disponibles para el servicio seleccionado.")
            else:
                default_detalle_periodo = str(periodo_sel) if str(periodo_sel) in periodos_detalle else periodos_detalle[-1]
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
                top_left, top_right = st.columns([0.85, 1.15])
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

                    st.markdown("<div class='section-title'>Focos de intervención</div>", unsafe_allow_html=True)
                    focos = detail_df[["estacion", "entradas", "meta_entradas", "perdida_pax", "fuga_pct_display"]].copy()
                    focos = focos.sort_values(["perdida_pax", "fuga_pct_display"], ascending=[False, False]).head(10)
                    focos["Afluencia"] = focos["entradas"].apply(fmt_pax)
                    focos["Meta"] = focos["meta_entradas"].apply(fmt_pax)
                    focos["Pérdida"] = focos["perdida_pax"].apply(fmt_pax)
                    focos["Fuga %"] = focos["fuga_pct_display"].apply(fmt_fuga_pct)
                    focos_show = focos[["estacion", "Afluencia", "Meta", "Pérdida", "Fuga %"]].rename(columns={"estacion": "Estación"})
                    st.dataframe(focos_show, use_container_width=True, hide_index=True)

                st.markdown("<div class='section-title'>Comparativo de afluencia y meta por estación</div>", unsafe_allow_html=True)
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
                        height=440,
                        barmode="group",
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
    st.markdown("</div>", unsafe_allow_html=True)


if section_sel == "Resumen ejecutivo":
    render_resumen_ejecutivo()
elif section_sel == "KPIs":
    render_kpis()
elif section_sel == "Personas":
    render_personas()
elif section_sel == "Detalle Servicio":
    render_detalle_servicio()

# =========================================================
# PIE
# =========================================================
st.markdown("---")
st.caption("La aplicación lee automáticamente los archivos CSV contenidos en el repositorio de GitHub.")
