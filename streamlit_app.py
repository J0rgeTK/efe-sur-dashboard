import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date
import unicodedata
import math
import plotly.express as px
import plotly.graph_objects as go

# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================
st.set_page_config(
    page_title="EFE Sur | KPIs e Iniciativas - Gerencia de Pasajeros",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="expanded",
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

    .small-note {{
        color: {TEXT_MUTED};
        font-size: 0.82rem;
    }}

    .block-container {{
        padding-top: 2rem;
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


def build_line_chart(df, title, color=None, line_dash=None, height=340):
    plot_df = df.copy()
    plot_df["periodo_date"] = plot_df["periodo"].apply(periodo_to_date)
    plot_df = plot_df.sort_values(["periodo_date", "periodo"])
    plot_df["periodo_label"] = plot_df["periodo"].apply(periodo_to_label)
    category_order = list(dict.fromkeys(plot_df["periodo_label"].dropna().tolist()))

    fig = px.line(
        plot_df,
        x="periodo_label",
        y="valor",
        color=color,
        line_dash=line_dash,
        markers=True,
        title=title,
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


def compute_map_view(df_map):
    lat_min, lat_max = float(df_map["latitud"].min()), float(df_map["latitud"].max())
    lon_min, lon_max = float(df_map["longitud"].min()), float(df_map["longitud"].max())

    center = {"lat": (lat_min + lat_max) / 2, "lon": (lon_min + lon_max) / 2}

    lat_range = max(lat_max - lat_min, 0.002)
    lon_range = max(lon_max - lon_min, 0.002)
    max_range = max(lat_range, lon_range)

    zoom = 9.6 - math.log(max_range, 2)
    zoom = max(6.9, min(14.8, zoom))

    return center, zoom


def build_station_map(df_map):
    plot_df = df_map.copy()
    center, zoom = compute_map_view(plot_df)

    plot_df["afluencia_size"] = pd.to_numeric(plot_df["entradas"], errors="coerce").fillna(0).clip(lower=0)
    max_val = float(plot_df["afluencia_size"].max()) if len(plot_df) else 0
    if max_val <= 0:
        plot_df["marker_size"] = 10
    else:
        plot_df["marker_size"] = 9 + (plot_df["afluencia_size"] / max_val) * 20

    plot_df["hover_afluencia"] = plot_df["entradas"].apply(fmt_pax)
    plot_df["hover_meta"] = plot_df["meta_entradas"].apply(fmt_pax)
    plot_df["label_station"] = plot_df["estacion"].apply(compact_station_name).fillna("")
    plot_df["label_value"] = plot_df["entradas"].apply(fmt_pax).fillna("")
    plot_df["map_text"] = plot_df.apply(
        lambda r: f"{r['label_station']}<br>{r['label_value']}" if str(r['label_station']).strip() else "",
        axis=1,
    )
    plot_df["lat_float"] = pd.to_numeric(plot_df["latitud"], errors="coerce")
    plot_df["lon_float"] = pd.to_numeric(plot_df["longitud"], errors="coerce")
    plot_df = plot_df.dropna(subset=["lat_float", "lon_float"]).copy()

    fig = go.Figure()
    fig.add_trace(
        go.Scattermapbox(
            lat=plot_df["lat_float"].tolist(),
            lon=plot_df["lon_float"].tolist(),
            mode="markers+text",
            text=plot_df["map_text"].tolist(),
            textposition="top right",
            textfont=dict(size=11, color="#17324D", family="Arial, sans-serif"),
            marker=dict(
                size=plot_df["marker_size"].tolist(),
                color=EFE_BLUE,
                opacity=0.92,
                sizemode="diameter",
                symbol="circle",
            ),
            customdata=plot_df[["estacion", "servicio", "hover_afluencia", "hover_meta"]].fillna("").values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Servicio: %{customdata[1]}<br>"
                "%{customdata[2]}<br>"
                "Meta: %{customdata[3]}<extra></extra>"
            ),
            showlegend=False,
        )
    )

    fig.update_layout(
        mapbox=dict(
            style="white-bg",
            layers=[
                dict(
                    sourcetype="raster",
                    sourceattribution="© OpenStreetMap contributors © CARTO",
                    source=[
                        "https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png",
                        "https://b.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png",
                        "https://c.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png",
                    ],
                    below="traces",
                )
            ],
            center=center,
            zoom=zoom,
        ),
        margin=dict(l=8, r=8, t=20, b=8),
        paper_bgcolor=EFE_WHITE,
        height=920,
        showlegend=False,
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

with st.sidebar:
    st.markdown("<div class='section-title'>Filtros complementarios</div>", unsafe_allow_html=True)

    servicios_sel = st.multiselect("Servicio", options=servicios_lista, default=servicios_lista)

    estados_ini = sorted(iniciativas["estado"].dropna().astype(str).unique().tolist())
    estados_ini_sel = st.multiselect("Estado iniciativa", options=estados_ini, default=estados_ini)

    prioridades = sorted(iniciativas["prioridad"].dropna().astype(str).unique().tolist())
    prioridades_sel = st.multiselect("Prioridad", options=prioridades, default=prioridades)

    responsables = sorted(iniciativas["responsable"].dropna().astype(str).unique().tolist())
    responsables_sel = st.multiselect("Responsable", options=responsables, default=responsables)

    st.markdown("---")
    st.markdown(f"<div class='small-note'>Lectura de archivos desde: <b>{data_path}</b></div>", unsafe_allow_html=True)

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
# FILTRADO
# =========================================================
kpis_f = kpis[(kpis["periodo"].astype(str) == str(periodo_sel)) & (kpis["servicio"].isin(servicios_sel))].copy()
iniciativas_f = iniciativas[(iniciativas["servicio"].isin(servicios_sel)) & (iniciativas["estado"].isin(estados_ini_sel)) & (iniciativas["prioridad"].isin(prioridades_sel)) & (iniciativas["responsable"].isin(responsables_sel))].copy()
kpis_hist = kpis[kpis["servicio"].isin(servicios_sel)].copy()

if "orden" in kpis_f.columns:
    kpis_f = kpis_f.sort_values(["orden", "servicio", "nombre"])
else:
    kpis_f = kpis_f.sort_values(["nombre", "servicio"])

tabs = st.tabs(["Resumen ejecutivo", "KPIs", "Personas", "Detalle Servicio"])

# =========================================================
# TAB 1 - RESUMEN EJECUTIVO
# =========================================================
with tabs[0]:
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
                    if "observacion" in servicio_df.columns:
                        render_observation_box(row.get("observacion"))
                    st.markdown("<div style='height: 0.55rem;'></div>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>Evolución del KPI</div>", unsafe_allow_html=True)
    nombres_kpi = sorted(kpis_hist["nombre"].dropna().astype(str).unique().tolist())
    if nombres_kpi:
        kpi_hist_sel = option_selector("KPI para evolución", nombres_kpi, key="kpi_hist_sel_resumen", default=nombres_kpi[0], horizontal=True)
        hist_sel = kpis_hist[kpis_hist["nombre"] == kpi_hist_sel].copy()
        hist_sel = scale_kpi_dataframe_for_display(hist_sel, kpi_hist_sel, ("valor", "meta"))
        hist_bt = hist_sel[hist_sel["servicio"] == "Biotren"].copy()
        hist_rural = hist_sel[hist_sel["servicio"].isin(RURAL_SERVICES)].copy()

        col_bt, col_rural = st.columns(2)
        with col_bt:
            if hist_bt.empty:
                st.info("No hay datos de Biotren para el KPI y filtros seleccionados.")
            else:
                hist_bt_plot = hist_bt.groupby(["periodo"], as_index=False)["valor"].sum()
                fig_bt = build_line_chart(hist_bt_plot, f"{kpi_hist_sel} - Biotren")
                fig_bt.update_traces(line_color=EFE_BLUE)
                st.plotly_chart(fig_bt, use_container_width=True)

        with col_rural:
            if hist_rural.empty:
                st.info("No hay datos de otros servicios para el KPI y filtros seleccionados.")
            else:
                hist_rural_plot = hist_rural.groupby(["periodo", "servicio"], as_index=False)["valor"].sum()
                fig_rural = build_line_chart(hist_rural_plot, f"{kpi_hist_sel} - Otros servicios", color="servicio")
                st.plotly_chart(fig_rural, use_container_width=True)
    else:
        st.info("No hay KPIs disponibles para graficar.")

    st.markdown("<div class='section-title'>Iniciativas críticas</div>", unsafe_allow_html=True)
    criticas = iniciativas_f[iniciativas_f["critica"]].copy().sort_values(["prioridad", "fecha_fin", "avance_pct"], ascending=[True, True, True])
    if criticas.empty:
        st.info("No existen iniciativas críticas con los filtros actuales.")
    else:
        criticas_table = criticas[["nombre_iniciativa", "responsable", "servicio", "estado", "avance_pct", "fecha_fin", "prioridad"]].rename(columns={
            "nombre_iniciativa": "Iniciativa", "responsable": "Responsable", "servicio": "Servicio", "estado": "Estado", "avance_pct": "Avance %", "fecha_fin": "Fecha fin", "prioridad": "Prioridad"
        })
        st.dataframe(criticas_table, use_container_width=True, hide_index=True)

# =========================================================
# TAB 2 - KPIs
# =========================================================
with tabs[1]:
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
            fig_bt = build_line_chart(bt_hist, f"{kpi_sel} - Biotren", height=360)
            fig_bt.update_traces(line_color=EFE_BLUE)
            st.plotly_chart(fig_bt, use_container_width=True)
    with col_b:
        rural_hist = hist_kpi[hist_kpi["servicio"].isin(RURAL_SERVICES)].copy()
        if rural_hist.empty:
            st.info("No hay datos de otros servicios para el KPI seleccionado.")
        else:
            rural_hist = rural_hist.groupby(["periodo", "servicio"], as_index=False)["valor"].sum()
            fig_rural = build_line_chart(rural_hist, f"{kpi_sel} - Otros servicios", color="servicio", height=360)
            st.plotly_chart(fig_rural, use_container_width=True)

    st.markdown("<div class='section-title'>Valor vs meta en el período seleccionado</div>", unsafe_allow_html=True)
    actual = kpis_f[kpis_f["nombre"] == kpi_sel].copy()
    actual = scale_kpi_dataframe_for_display(actual, kpi_sel, ("valor", "meta"))
    if not actual.empty:
        fig_meta = go.Figure()
        fig_meta.add_trace(go.Bar(x=actual["servicio"], y=actual["valor"], name="Valor", marker_color=EFE_BLUE))
        fig_meta.add_trace(go.Bar(x=actual["servicio"], y=actual["meta"], name="Meta", marker_color=EFE_RED))
        fig_meta.update_layout(barmode="group", title=f"Valor vs meta - {periodo_sel}", plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=380)
        st.plotly_chart(fig_meta, use_container_width=True)
    else:
        st.info("No hay datos para el KPI seleccionado en el período actual.")

    st.markdown("<div class='section-title'>Detalle del KPI</div>", unsafe_allow_html=True)
    detalle_cols = ["nombre", "servicio", "categoria", "valor", "meta", "unidad", "variacion_pct", "estado"]
    if "observacion" in kpis_f.columns:
        detalle_cols.append("observacion")
    detalle_kpi = kpis_f[kpis_f["nombre"] == kpi_sel][detalle_cols].copy()
    if not detalle_kpi.empty:
        detalle_kpi["Valor"] = detalle_kpi.apply(lambda r: fmt_number(r["valor"], r["unidad"], r["nombre"]), axis=1)
        detalle_kpi["Meta"] = detalle_kpi.apply(lambda r: fmt_number(r["meta"], r["unidad"], r["nombre"]), axis=1)
        detalle_kpi["Variación"] = detalle_kpi["variacion_pct"].apply(fmt_pct)
        cols_show = ["servicio", "categoria", "Valor", "Meta", "Variación", "estado"]
        rename_map = {"servicio": "Servicio", "categoria": "Categoría", "estado": "Estado"}
        if "observacion" in detalle_kpi.columns:
            cols_show.append("observacion")
            rename_map["observacion"] = "Observación"
        detalle_show = detalle_kpi[cols_show].rename(columns=rename_map)
        st.dataframe(detalle_show, use_container_width=True, hide_index=True)
    else:
        st.info("No existe detalle para el KPI seleccionado.")

# =========================================================
# TAB 3 - PERSONAS
# =========================================================
with tabs[2]:
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
            fig.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=340)
            fig.update_xaxes(title="")
            fig.update_yaxes(title="Cantidad")
            st.plotly_chart(fig, use_container_width=True)
    with col_right:
        por_prioridad = iniciativas_f["prioridad"].value_counts().reset_index()
        por_prioridad.columns = ["prioridad", "cantidad"]
        if por_prioridad.empty:
            st.info("No hay prioridades para graficar.")
        else:
            fig2 = px.pie(por_prioridad, names="prioridad", values="cantidad", title="Distribución por prioridad", color="prioridad", color_discrete_map={"Alta": EFE_RED, "Media": WARNING, "Baja": EFE_BLUE})
            fig2.update_layout(paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=340)
            st.plotly_chart(fig2, use_container_width=True)

    personas_opts = sorted(iniciativas_f["responsable"].dropna().astype(str).unique().tolist())
    if personas_opts:
        persona_sel = option_selector("Seleccione responsable", personas_opts, key="persona_selector", default=personas_opts[0], horizontal=True)
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
            fig = px.bar(per_df.sort_values("avance_pct"), x="avance_pct", y="nombre_iniciativa", orientation="h", title=f"Avance por iniciativa - {persona_sel}", text="avance_pct")
            fig.update_traces(marker_color=EFE_BLUE)
            fig.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=420)
            fig.update_xaxes(title="Avance %")
            fig.update_yaxes(title="")
            st.plotly_chart(fig, use_container_width=True)
        with right_p:
            estado_persona = per_df["estado"].value_counts().reset_index()
            estado_persona.columns = ["estado", "cantidad"]
            fig2 = px.bar(estado_persona, x="estado", y="cantidad", title="Distribución por estado", color="estado", color_discrete_map={"Planificada": TEXT_MUTED, "En curso": EFE_BLUE, "Atrasada": EFE_RED, "Finalizada": SUCCESS, "Pausada": WARNING})
            fig2.update_layout(plot_bgcolor=EFE_WHITE, paper_bgcolor=EFE_WHITE, margin=dict(l=20, r=20, t=50, b=20), height=420, showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("<div class='section-title'>Detalle por responsable</div>", unsafe_allow_html=True)
        detalle_persona = per_df[["nombre_iniciativa", "servicio", "estado", "avance_pct", "fecha_inicio", "fecha_fin", "prioridad", "criticidad", "comentario"]].copy()
        detalle_persona = detalle_persona.rename(columns={"nombre_iniciativa": "Iniciativa", "servicio": "Servicio", "estado": "Estado", "avance_pct": "Avance %", "fecha_inicio": "Inicio", "fecha_fin": "Fin", "prioridad": "Prioridad", "criticidad": "Criticidad", "comentario": "Comentario"})
        st.dataframe(detalle_persona, use_container_width=True, hide_index=True)
    else:
        st.warning("No hay responsables disponibles con los filtros actuales.")

# =========================================================
# TAB 4 - DETALLE SERVICIO
# =========================================================
with tabs[3]:
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
        servicios_detalle = sorted(
            list(
                set(estaciones_activas["servicio"].dropna().astype(str).tolist())
                & set(afluencia_estacion["servicio"].dropna().astype(str).tolist())
            )
        )
        servicios_detalle = [s for s in servicios_lista if s in servicios_detalle] or servicios_detalle
        if not servicios_detalle:
            st.warning("No existen servicios comunes entre estaciones.csv y afluencia_estacion.csv.")
        else:
            default_detalle_servicio = servicios_detalle[0]
            if len(servicios_sel) == 1 and servicios_sel[0] in servicios_detalle:
                default_detalle_servicio = servicios_sel[0]
            detalle_servicio_sel = option_selector(
                "Servicio para análisis georreferenciado",
                servicios_detalle,
                key="detalle_servicio_selector",
                default=default_detalle_servicio,
                horizontal=True,
            )

            periodos_detalle = sorted(
                afluencia_estacion[afluencia_estacion["servicio"].astype(str) == str(detalle_servicio_sel)]["periodo"].dropna().astype(str).unique().tolist()
            )
            if not periodos_detalle:
                st.warning("No existen períodos disponibles para el servicio seleccionado.")
            else:
                default_detalle_periodo = str(periodo_sel) if str(periodo_sel) in periodos_detalle else periodos_detalle[-1]
                detalle_periodo_sel = option_selector(
                    "Período de detalle",
                    periodos_detalle,
                    key="detalle_periodo_selector",
                    default=default_detalle_periodo,
                    horizontal=True,
                )

                estaciones_srv = estaciones_activas[estaciones_activas["servicio"].astype(str) == str(detalle_servicio_sel)].copy()
                if "orden_trazado" in estaciones_srv.columns:
                    estaciones_srv = estaciones_srv.sort_values(["orden_trazado", "estacion"])
                else:
                    estaciones_srv = estaciones_srv.sort_values("estacion")

                afluencia_srv = afluencia_estacion[
                    (afluencia_estacion["servicio"].astype(str) == str(detalle_servicio_sel))
                    & (afluencia_estacion["periodo"].astype(str) == str(detalle_periodo_sel))
                ].copy()

                detail_df = estaciones_srv.merge(
                    afluencia_srv,
                    how="left",
                    on=["id_estacion", "servicio"],
                    suffixes=("_est", "_afl"),
                )
                detail_df["entradas"] = pd.to_numeric(detail_df.get("entradas"), errors="coerce")
                detail_df["meta_entradas"] = pd.to_numeric(detail_df.get("meta_entradas"), errors="coerce")
                detail_df["perdida_pax"] = pd.to_numeric(detail_df.get("perdida_pax"), errors="coerce")
                detail_df["fuga_pct"] = pd.to_numeric(detail_df.get("fuga_pct"), errors="coerce")
                detail_df["fuga_pct_display"] = detail_df["fuga_pct"].apply(maybe_scale_percent)
                detail_df["entradas_fmt"] = detail_df["entradas"].apply(fmt_pax)
                detail_df["meta_entradas_fmt"] = detail_df["meta_entradas"].apply(fmt_pax)
                detail_df["perdida_pax_fmt"] = detail_df["perdida_pax"].apply(fmt_pax)
                detail_df["fuga_pct_fmt"] = detail_df["fuga_pct"].apply(fmt_fuga_pct)
                detail_df["observacion_estacion"] = detail_df.get("observacion_est", detail_df.get("observacion_x", None))
                detail_df["observacion_afluencia"] = detail_df.get("observacion_afl", detail_df.get("observacion_y", None))

                valid_map_df = detail_df.dropna(subset=["latitud", "longitud"]).copy()

                top_left, top_right = st.columns([0.9, 1.1])
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
                    fig_bar.add_trace(
                        go.Bar(
                            x=bar_df["estacion"],
                            y=bar_df["entradas"],
                            name="Afluencia registrada",
                            marker_color=EFE_BLUE,
                        )
                    )
                    fig_bar.add_trace(
                        go.Bar(
                            x=bar_df["estacion"],
                            y=bar_df["meta_entradas"],
                            name="Meta",
                            marker_color=EFE_RED,
                        )
                    )
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
                detail_table = detail_df[[
                    "estacion", "comuna", "region", "entradas", "meta_entradas", "perdida_pax", "fuga_pct_display", "observacion_afluencia", "observacion_estacion"
                ]].copy()
                detail_table["Afluencia"] = detail_table["entradas"].apply(fmt_pax)
                detail_table["Meta afluencia"] = detail_table["meta_entradas"].apply(fmt_pax)
                detail_table["Pérdida pax"] = detail_table["perdida_pax"].apply(fmt_pax)
                detail_table["Fuga %"] = detail_table["fuga_pct_display"].apply(fmt_fuga_pct)
                detail_table = detail_table[[
                    "estacion", "comuna", "region", "Afluencia", "Meta afluencia", "Pérdida pax", "Fuga %", "observacion_afluencia", "observacion_estacion"
                ]].rename(columns={
                    "estacion": "Estación",
                    "comuna": "Comuna",
                    "region": "Región",
                    "observacion_afluencia": "Obs. afluencia",
                    "observacion_estacion": "Obs. estación",
                })
                st.dataframe(detail_table, use_container_width=True, hide_index=True)

# =========================================================
# PIE
# =========================================================
st.markdown("---")
st.caption("La aplicación lee automáticamente los archivos CSV contenidos en el repositorio de GitHub.")
