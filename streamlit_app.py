import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, timedelta
import plotly.express as px
import plotly.graph_objects as go

# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================
st.set_page_config(
    page_title="EFE Sur | KPIs e Iniciativas",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# PALETA DE COLORES
# =========================================================
EFE_BLUE = "#000D57"
EFE_RED = "#FF0016"
EFE_WHITE = "#396BB6"
BG_LIGHT = "#FFFFFFB9"
BORDER = "#FFFFFF"
TEXT_MAIN = "#000000"
TEXT_MUTED = "#000000"
SUCCESS = "#0D187E"
WARNING = "#D97706"
DANGER = "#B91C1C"

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
        font-size: 3rem;
        font-weight: 800;
        color: {EFE_BLUE};
        margin-bottom: 0.1rem;
    }}

    .subtitle {{
        font-size: 0.95rem;
        color: {TEXT_MUTED};
        margin-bottom: 1.2rem;
    }}

    .section-title {{
        font-size: 1.25rem;
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
        font-size: 0.92rem;
        color: {TEXT_MUTED};
        margin-bottom: 0.4rem;
    }}

    .efe-card-value {{
        font-size: 1.9rem;
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

    .efe-pill {{
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
        color: white;
    }}

    .small-note {{
        color: {TEXT_MUTED};
        font-size: 0.82rem;
    }}

    .block-container {{
        padding-top: 1.2rem;
        padding-bottom: 1rem;
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
def fmt_number(value, unit=""):
    if unit == "CLP":
        return f"$ {value:,.0f}".replace(",", ".")
    if unit == "%":
        return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")
    if unit == "pax":
        return f"{value:,.0f}".replace(",", ".")
    return f"{value:,.0f}".replace(",", ".")

def fmt_pct(value):
    return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")

def classify_status(value, meta, higher_is_better=True):
    if meta == 0:
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
    }.get(status, TEXT_MUTED)

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

def estado_badge(estado):
    color = status_color(estado)
    return f'<span class="efe-pill" style="background:{color};">{estado}</span>'

# =========================================================
# DATOS DEMO / CARGA CSV
# =========================================================
@st.cache_data
def create_demo_data():
    np.random.seed(42)

    servicios = ["Biotren", "Laja-Talcahuano", "Tren Araucanía"]
    personas = pd.DataFrame(
        [
            [1, "Jorge", "Ingeniero de Estudio", "Gerencia de Pasajeros"],
            [2, "Ana", "Analista Comercial", "Comercial"],
            [3, "Carlos", "Coordinador Operacional", "Operaciones"],
            [4, "María", "Analista de Datos", "Planificación"],
            [5, "Fernanda", "Jefa de Proyecto", "Proyectos"],
            [6, "Luis", "Analista de Gestión", "Control"],
            [7, "Paula", "Encargada de Iniciativas", "Comercial"],
            [8, "Sebastián", "Ingeniero de Planificación", "Planificación"],
        ],
        columns=["id_persona", "nombre", "cargo", "area"]
    )

    months = pd.period_range("2025-10", "2026-09", freq="M").astype(str)

    rows = []
    id_kpi = 1

    base_map = {
        "Biotren": {"Pasajeros": 120000, "Ingresos": 47000000, "Puntualidad": 94.0, "Ocupación": 78.0},
        "Laja-Talcahuano": {"Pasajeros": 26000, "Ingresos": 6200000, "Puntualidad": 92.5, "Ocupación": 65.0},
        "Tren Araucanía": {"Pasajeros": 18000, "Ingresos": 3800000, "Puntualidad": 90.5, "Ocupación": 61.0},
    }

    meta_map = {
        "Pasajeros": 1.03,
        "Ingresos": 1.02,
        "Puntualidad": 95.0,
        "Ocupación": 75.0,
    }

    for period_idx, periodo in enumerate(months):
        seasonal = 1 + 0.03 * np.sin(period_idx / 2)
        for servicio in servicios:
            for nombre in ["Pasajeros", "Ingresos", "Puntualidad", "Ocupación"]:
                base = base_map[servicio][nombre]

                if nombre in ["Pasajeros", "Ingresos"]:
                    noise = np.random.uniform(-0.06, 0.07)
                    value = base * seasonal * (1 + noise)
                    meta = base * meta_map[nombre] * (1 + 0.01 * period_idx)
                    unit = "pax" if nombre == "Pasajeros" else "CLP"
                    higher_is_better = True
                else:
                    noise = np.random.uniform(-0.03, 0.03)
                    value = base * (1 + noise)
                    meta = meta_map[nombre]
                    unit = "%"
                    higher_is_better = True

                estado = classify_status(value, meta, higher_is_better)
                variacion = ((value - meta) / meta) * 100 if meta != 0 else 0

                rows.append(
                    [
                        id_kpi,
                        nombre,
                        "Operación" if nombre in ["Pasajeros", "Puntualidad", "Ocupación"] else "Finanzas",
                        servicio,
                        round(value, 2),
                        round(meta, 2),
                        unit,
                        periodo,
                        round(variacion, 2),
                        estado,
                    ]
                )
                id_kpi += 1

    kpis = pd.DataFrame(
        rows,
        columns=[
            "id_kpi", "nombre", "categoria", "servicio", "valor", "meta",
            "unidad", "periodo", "variacion_pct", "estado"
        ]
    )

    iniciativas_rows = []
    estados = ["Planificada", "En curso", "Atrasada", "Finalizada"]
    prioridades = ["Alta", "Media", "Baja"]
    nombres_iniciativas = [
        "Dashboard KPIs Gerencia",
        "Seguimiento Integración Bus",
        "Actualización Itinerario Biotren",
        "Modelo de Control de Itinerario",
        "Optimización Medios de Pago",
        "Plan de Comunicación Comercial",
        "Seguimiento Puntualidad",
        "Tablero de Afluencia",
        "Análisis de Tarifa Óptima",
        "Licitación Espacios Comerciales",
        "Plan de Evasión",
        "Control de Cruces Ruta 160",
        "Seguimiento de Encuesta",
        "Reporte Ejecutivo Mensual",
        "Monitoreo Recaudación",
        "Sistema de Alertas KPIs",
        "Cierre de Brechas Operativas",
        "Seguimiento de Proyectos 2026",
        "Control de Oferta y Capacidad",
        "Tablero de Iniciativas por Persona"
    ]

    base_date = date(2026, 1, 1)

    for idx, nombre in enumerate(nombres_iniciativas, start=1):
        responsable_id = np.random.choice(personas["id_persona"])
        servicio = np.random.choice(servicios)
        prioridad = np.random.choice(prioridades, p=[0.35, 0.45, 0.20])
        estado = np.random.choice(estados, p=[0.20, 0.45, 0.15, 0.20])

        start_offset = np.random.randint(0, 160)
        duration = np.random.randint(40, 160)
        fecha_inicio = base_date + timedelta(days=int(start_offset))
        fecha_fin = fecha_inicio + timedelta(days=int(duration))

        if estado == "Planificada":
            avance = np.random.randint(0, 20)
        elif estado == "En curso":
            avance = np.random.randint(20, 85)
        elif estado == "Atrasada":
            avance = np.random.randint(15, 75)
        else:
            avance = 100

        iniciativas_rows.append(
            [
                idx,
                nombre,
                responsable_id,
                servicio,
                estado,
                avance,
                fecha_inicio,
                fecha_fin,
                prioridad,
                f"Observación demo {idx}"
            ]
        )

    iniciativas = pd.DataFrame(
        iniciativas_rows,
        columns=[
            "id_iniciativa", "nombre", "responsable_id", "servicio", "estado",
            "avance_pct", "fecha_inicio", "fecha_fin", "prioridad", "comentario"
        ]
    )

    return kpis, iniciativas, personas

@st.cache_data
def load_data():
    base_path = Path("data_demo")
    kpis_path = base_path / "kpis_demo.csv"
    iniciativas_path = base_path / "iniciativas_demo.csv"
    personas_path = base_path / "personas_demo.csv"

    if kpis_path.exists() and iniciativas_path.exists() and personas_path.exists():
        kpis = pd.read_csv(kpis_path)
        iniciativas = pd.read_csv(iniciativas_path)
        personas = pd.read_csv(personas_path)

        if "fecha_inicio" in iniciativas.columns:
            iniciativas["fecha_inicio"] = pd.to_datetime(iniciativas["fecha_inicio"]).dt.date
        if "fecha_fin" in iniciativas.columns:
            iniciativas["fecha_fin"] = pd.to_datetime(iniciativas["fecha_fin"]).dt.date

        return kpis, iniciativas, personas

    return create_demo_data()

kpis, iniciativas, personas = load_data()

# =========================================================
# PREPARACIÓN DE DATOS
# =========================================================
iniciativas = iniciativas.merge(personas[["id_persona", "nombre"]], how="left", left_on="responsable_id", right_on="id_persona")
iniciativas = iniciativas.rename(columns={"nombre_y": "responsable"} if "nombre_y" in iniciativas.columns else {})
if "nombre" in iniciativas.columns and "responsable" not in iniciativas.columns:
    iniciativas = iniciativas.rename(columns={"nombre": "responsable"})

today = date.today()
iniciativas["vencida"] = iniciativas["fecha_fin"].apply(lambda x: x < today)
iniciativas["critica"] = iniciativas.apply(lambda r: (r["estado"] == "Atrasada") or (r["vencida"] and r["estado"] != "Finalizada"), axis=1)

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown(f"<div class='section-title'>Filtros</div>", unsafe_allow_html=True)

    periodos = sorted(kpis["periodo"].unique().tolist())
    periodo_sel = st.selectbox("Período", options=periodos, index=len(periodos) - 1)

    servicios = sorted(kpis["servicio"].unique().tolist())
    servicios_sel = st.multiselect("Servicio", options=servicios, default=servicios)

    estados_ini = sorted(iniciativas["estado"].unique().tolist())
    estados_ini_sel = st.multiselect("Estado iniciativa", options=estados_ini, default=estados_ini)

    prioridades_sel = st.multiselect(
        "Prioridad",
        options=["Alta", "Media", "Baja"],
        default=["Alta", "Media", "Baja"]
    )

    responsables_sel = st.multiselect(
        "Responsable",
        options=sorted(iniciativas["responsable"].dropna().unique().tolist()),
        default=sorted(iniciativas["responsable"].dropna().unique().tolist())
    )

    st.markdown("---")
    st.markdown("<div class='small-note'>La app usa datos demo si no encuentra archivos en <b>data_demo/</b>.</div>", unsafe_allow_html=True)

# =========================================================
# FILTRADO
# =========================================================
kpis_f = kpis[(kpis["periodo"] == periodo_sel) & (kpis["servicio"].isin(servicios_sel))].copy()

iniciativas_f = iniciativas[
    (iniciativas["servicio"].isin(servicios_sel))
    & (iniciativas["estado"].isin(estados_ini_sel))
    & (iniciativas["prioridad"].isin(prioridades_sel))
    & (iniciativas["responsable"].isin(responsables_sel))
].copy()

kpis_hist = kpis[kpis["servicio"].isin(servicios_sel)].copy()

# =========================================================
# ENCABEZADO
# =========================================================
col_logo, col_title = st.columns([1, 6])

with col_logo:
    logo_path = Path("assets/logoefe-azul.png")
    if logo_path.exists():
        st.image(str(logo_path), use_container_width=True)

with col_title:
    st.markdown("<div class='main-title'>Demo visual de KPIs e iniciativas</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='subtitle'>Período seleccionado: <b>{periodo_sel}</b> | "
        f"Servicios: <b>{', '.join(servicios_sel)}</b></div>",
        unsafe_allow_html=True
    )

tabs = st.tabs(["Resumen ejecutivo", "KPIs", "Iniciativas", "Personas"])

# =========================================================
# TAB 1 - RESUMEN EJECUTIVO
# =========================================================
with tabs[0]:
    st.markdown("<div class='section-title'>Resumen ejecutivo</div>", unsafe_allow_html=True)

    def get_agg_metric(name, mode="sum"):
        df = kpis_f[kpis_f["nombre"] == name]
        if df.empty:
            return None
        unit = df["unidad"].iloc[0]
        if mode == "sum":
            value = df["valor"].sum()
            meta = df["meta"].sum()
        else:
            value = df["valor"].mean()
            meta = df["meta"].mean()
        variacion = ((value - meta) / meta) * 100 if meta != 0 else 0
        status = classify_status(value, meta)
        return {"value": value, "meta": meta, "unit": unit, "var": variacion, "status": status}

    pasajeros = get_agg_metric("Pasajeros", "sum")
    ingresos = get_agg_metric("Ingresos", "sum")
    puntualidad = get_agg_metric("Puntualidad", "mean")
    ocupacion = get_agg_metric("Ocupación", "mean")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        render_kpi_card(
            "Pasajeros",
            fmt_number(pasajeros["value"], pasajeros["unit"]),
            f"Meta: {fmt_number(pasajeros['meta'], pasajeros['unit'])}",
            f"Desviación: {fmt_pct(pasajeros['var'])}",
            pasajeros["status"]
        )

    with c2:
        render_kpi_card(
            "Ingresos",
            fmt_number(ingresos["value"], ingresos["unit"]),
            f"Meta: {fmt_number(ingresos['meta'], ingresos['unit'])}",
            f"Desviación: {fmt_pct(ingresos['var'])}",
            ingresos["status"]
        )

    with c3:
        render_kpi_card(
            "Puntualidad promedio",
            fmt_number(puntualidad["value"], puntualidad["unit"]),
            f"Meta: {fmt_number(puntualidad['meta'], puntualidad['unit'])}",
            f"Desviación: {fmt_pct(puntualidad['var'])}",
            puntualidad["status"]
        )

    with c4:
        render_kpi_card(
            "Ocupación promedio",
            fmt_number(ocupacion["value"], ocupacion["unit"]),
            f"Meta: {fmt_number(ocupacion['meta'], ocupacion['unit'])}",
            f"Desviación: {fmt_pct(ocupacion['var'])}",
            ocupacion["status"]
        )

    st.markdown("")

    left, right = st.columns([1.6, 1])

    with left:
        hist_pas = kpis_hist[kpis_hist["nombre"] == "Pasajeros"].groupby("periodo", as_index=False)["valor"].sum()
        fig = px.line(
            hist_pas,
            x="periodo",
            y="valor",
            markers=True,
            title="Evolución de pasajeros"
        )
        fig.update_traces(line_color=EFE_BLUE)
        fig.update_layout(
            plot_bgcolor=EFE_WHITE,
            paper_bgcolor=EFE_WHITE,
            margin=dict(l=20, r=20, t=50, b=20),
            height=360
        )
        fig.update_xaxes(title="")
        fig.update_yaxes(title="Pasajeros")
        st.plotly_chart(fig, use_container_width=True)

    with right:
        estados_count = iniciativas_f["estado"].value_counts().reset_index()
        estados_count.columns = ["estado", "cantidad"]

        fig2 = px.bar(
            estados_count,
            x="estado",
            y="cantidad",
            title="Iniciativas por estado",
            color="estado",
            color_discrete_map={
                "Planificada": TEXT_MUTED,
                "En curso": EFE_BLUE,
                "Atrasada": EFE_RED,
                "Finalizada": SUCCESS
            }
        )
        fig2.update_layout(
            plot_bgcolor=EFE_WHITE,
            paper_bgcolor=EFE_WHITE,
            margin=dict(l=20, r=20, t=50, b=20),
            height=360,
            showlegend=False
        )
        fig2.update_xaxes(title="")
        fig2.update_yaxes(title="Cantidad")
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<div class='section-title'>Iniciativas críticas</div>", unsafe_allow_html=True)

    criticas = iniciativas_f[iniciativas_f["critica"]].copy()
    criticas = criticas.sort_values(["prioridad", "fecha_fin", "avance_pct"], ascending=[True, True, True])

    if criticas.empty:
        st.info("No existen iniciativas críticas con los filtros actuales.")
    else:
        criticas_show = criticas[["nombre_x", "responsable", "servicio", "estado", "avance_pct", "fecha_fin", "prioridad"]].copy() if "nombre_x" in criticas.columns else criticas[["id_iniciativa", "responsable", "servicio", "estado", "avance_pct", "fecha_fin", "prioridad"]].copy()

        if "nombre_x" in criticas_show.columns:
            criticas_show = criticas_show.rename(columns={"nombre_x": "Iniciativa"})
        else:
            criticas_show = criticas_show.rename(columns={"id_iniciativa": "ID"})

        criticas_table = criticas[["id_iniciativa", "responsable", "servicio", "estado", "avance_pct", "fecha_fin", "prioridad"]].copy()
        criticas_table.insert(1, "Iniciativa", criticas["nombre_x"] if "nombre_x" in criticas.columns else criticas["id_iniciativa"].astype(str))
        criticas_table = criticas_table.drop(columns=["id_iniciativa"])
        criticas_table = criticas_table.rename(columns={
            "responsable": "Responsable",
            "servicio": "Servicio",
            "estado": "Estado",
            "avance_pct": "Avance %",
            "fecha_fin": "Fecha fin",
            "prioridad": "Prioridad"
        })
        st.dataframe(criticas_table, use_container_width=True, hide_index=True)

# =========================================================
# TAB 2 - KPIs
# =========================================================
with tabs[1]:
    st.markdown("<div class='section-title'>Análisis de KPIs</div>", unsafe_allow_html=True)

    kpi_sel = st.selectbox("Seleccione KPI", options=["Pasajeros", "Ingresos", "Puntualidad", "Ocupación"])

    hist_kpi = kpis_hist[kpis_hist["nombre"] == kpi_sel].copy()

    col_a, col_b = st.columns([1.4, 1])

    with col_a:
        fig = px.line(
            hist_kpi,
            x="periodo",
            y="valor",
            color="servicio",
            markers=True,
            title=f"Evolución de {kpi_sel} por servicio"
        )
        fig.update_layout(
            plot_bgcolor=EFE_WHITE,
            paper_bgcolor=EFE_WHITE,
            margin=dict(l=20, r=20, t=50, b=20),
            height=380
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        actual = kpis_f[kpis_f["nombre"] == kpi_sel].copy()
        if not actual.empty:
            compare_df = actual.copy()
            fig_meta = go.Figure()
            fig_meta.add_trace(go.Bar(
                x=compare_df["servicio"],
                y=compare_df["valor"],
                name="Valor",
                marker_color=EFE_BLUE
            ))
            fig_meta.add_trace(go.Bar(
                x=compare_df["servicio"],
                y=compare_df["meta"],
                name="Meta",
                marker_color=EFE_RED
            ))
            fig_meta.update_layout(
                barmode="group",
                title=f"Valor vs meta - {periodo_sel}",
                plot_bgcolor=EFE_WHITE,
                paper_bgcolor=EFE_WHITE,
                margin=dict(l=20, r=20, t=50, b=20),
                height=380
            )
            st.plotly_chart(fig_meta, use_container_width=True)

    st.markdown("<div class='section-title'>Detalle del KPI</div>", unsafe_allow_html=True)

    detalle_kpi = kpis_f[kpis_f["nombre"] == kpi_sel][
        ["servicio", "categoria", "valor", "meta", "unidad", "variacion_pct", "estado"]
    ].copy()

    if not detalle_kpi.empty:
        detalle_kpi["valor_fmt"] = detalle_kpi.apply(lambda r: fmt_number(r["valor"], r["unidad"]), axis=1)
        detalle_kpi["meta_fmt"] = detalle_kpi.apply(lambda r: fmt_number(r["meta"], r["unidad"]), axis=1)
        detalle_kpi["variación"] = detalle_kpi["variacion_pct"].apply(fmt_pct)

        detalle_show = detalle_kpi[["servicio", "categoria", "valor_fmt", "meta_fmt", "variación", "estado"]].rename(columns={
            "servicio": "Servicio",
            "categoria": "Categoría",
            "valor_fmt": "Valor",
            "meta_fmt": "Meta",
            "estado": "Estado"
        })
        st.dataframe(detalle_show, use_container_width=True, hide_index=True)

# =========================================================
# TAB 3 - INICIATIVAS
# =========================================================
with tabs[2]:
    st.markdown("<div class='section-title'>Seguimiento de iniciativas</div>", unsafe_allow_html=True)

    total_ini = len(iniciativas_f)
    en_curso = int((iniciativas_f["estado"] == "En curso").sum())
    atrasadas = int((iniciativas_f["estado"] == "Atrasada").sum())
    finalizadas = int((iniciativas_f["estado"] == "Finalizada").sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total iniciativas", total_ini)
    m2.metric("En curso", en_curso)
    m3.metric("Atrasadas", atrasadas)
    m4.metric("Finalizadas", finalizadas)

    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        por_responsable = (
            iniciativas_f.groupby("responsable", as_index=False)
            .agg(cantidad=("id_iniciativa", "count"), avance_promedio=("avance_pct", "mean"))
            .sort_values("cantidad", ascending=False)
        )

        fig = px.bar(
            por_responsable,
            x="responsable",
            y="cantidad",
            title="Carga de iniciativas por responsable",
            text="cantidad"
        )
        fig.update_traces(marker_color=EFE_BLUE)
        fig.update_layout(
            plot_bgcolor=EFE_WHITE,
            paper_bgcolor=EFE_WHITE,
            margin=dict(l=20, r=20, t=50, b=20),
            height=360
        )
        fig.update_xaxes(title="")
        fig.update_yaxes(title="Cantidad")
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        por_prioridad = iniciativas_f["prioridad"].value_counts().reset_index()
        por_prioridad.columns = ["prioridad", "cantidad"]

        fig2 = px.pie(
            por_prioridad,
            names="prioridad",
            values="cantidad",
            title="Distribución por prioridad",
            color="prioridad",
            color_discrete_map={
                "Alta": EFE_RED,
                "Media": WARNING,
                "Baja": EFE_BLUE
            }
        )
        fig2.update_layout(
            paper_bgcolor=EFE_WHITE,
            margin=dict(l=20, r=20, t=50, b=20),
            height=360
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<div class='section-title'>Listado de iniciativas</div>", unsafe_allow_html=True)

    show_ini = iniciativas_f.copy()
    nombre_col = "nombre_x" if "nombre_x" in show_ini.columns else None
    if nombre_col is None:
        possible_name_cols = [c for c in show_ini.columns if "nombre" in c.lower() and c != "responsable"]
        nombre_col = possible_name_cols[0] if possible_name_cols else "id_iniciativa"

    show_ini["Estado visual"] = show_ini["estado"].apply(estado_badge)
    show_ini["Avance %"] = show_ini["avance_pct"].astype(str) + "%"
    show_ini["Vencida"] = show_ini["vencida"].map({True: "Sí", False: "No"})

    table_ini = show_ini[[nombre_col, "responsable", "servicio", "estado", "avance_pct", "fecha_inicio", "fecha_fin", "prioridad", "vencida"]].copy()
    table_ini = table_ini.rename(columns={
        nombre_col: "Iniciativa",
        "responsable": "Responsable",
        "servicio": "Servicio",
        "estado": "Estado",
        "avance_pct": "Avance %",
        "fecha_inicio": "Inicio",
        "fecha_fin": "Fin",
        "prioridad": "Prioridad",
        "vencida": "Vencida"
    })
    st.dataframe(table_ini, use_container_width=True, hide_index=True)

# =========================================================
# TAB 4 - PERSONAS
# =========================================================
with tabs[3]:
    st.markdown("<div class='section-title'>Vista por persona</div>", unsafe_allow_html=True)

    personas_opts = sorted(iniciativas_f["responsable"].dropna().unique().tolist())
    if personas_opts:
        persona_sel = st.selectbox("Seleccione responsable", options=personas_opts)

        per_df = iniciativas_f[iniciativas_f["responsable"] == persona_sel].copy()

        total_p = len(per_df)
        finalizadas_p = int((per_df["estado"] == "Finalizada").sum())
        atrasadas_p = int((per_df["estado"] == "Atrasada").sum())
        avance_prom = float(per_df["avance_pct"].mean()) if not per_df.empty else 0

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Asignadas", total_p)
        p2.metric("Finalizadas", finalizadas_p)
        p3.metric("Atrasadas", atrasadas_p)
        p4.metric("Avance promedio", f"{avance_prom:,.1f}%".replace(",", "X").replace(".", ",").replace("X", "."))

        left_p, right_p = st.columns([1.1, 1])

        with left_p:
            base_name_col = "nombre_x" if "nombre_x" in per_df.columns else None
            if base_name_col is None:
                possible_name_cols = [c for c in per_df.columns if "nombre" in c.lower() and c != "responsable"]
                base_name_col = possible_name_cols[0] if possible_name_cols else "id_iniciativa"

            fig = px.bar(
                per_df.sort_values("avance_pct"),
                x="avance_pct",
                y=base_name_col,
                orientation="h",
                title=f"Avance por iniciativa - {persona_sel}",
                text="avance_pct"
            )
            fig.update_traces(marker_color=EFE_BLUE)
            fig.update_layout(
                plot_bgcolor=EFE_WHITE,
                paper_bgcolor=EFE_WHITE,
                margin=dict(l=20, r=20, t=50, b=20),
                height=420
            )
            fig.update_xaxes(title="Avance %")
            fig.update_yaxes(title="")
            st.plotly_chart(fig, use_container_width=True)

        with right_p:
            estado_persona = per_df["estado"].value_counts().reset_index()
            estado_persona.columns = ["estado", "cantidad"]

            fig2 = px.bar(
                estado_persona,
                x="estado",
                y="cantidad",
                title="Distribución por estado",
                color="estado",
                color_discrete_map={
                    "Planificada": TEXT_MUTED,
                    "En curso": EFE_BLUE,
                    "Atrasada": EFE_RED,
                    "Finalizada": SUCCESS
                }
            )
            fig2.update_layout(
                plot_bgcolor=EFE_WHITE,
                paper_bgcolor=EFE_WHITE,
                margin=dict(l=20, r=20, t=50, b=20),
                height=420,
                showlegend=False
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("<div class='section-title'>Detalle por responsable</div>", unsafe_allow_html=True)

        detalle_persona = per_df[[base_name_col, "servicio", "estado", "avance_pct", "fecha_inicio", "fecha_fin", "prioridad", "comentario"]].copy()
        detalle_persona = detalle_persona.rename(columns={
            base_name_col: "Iniciativa",
            "servicio": "Servicio",
            "estado": "Estado",
            "avance_pct": "Avance %",
            "fecha_inicio": "Inicio",
            "fecha_fin": "Fin",
            "prioridad": "Prioridad",
            "comentario": "Comentario"
        })
        st.dataframe(detalle_persona, use_container_width=True, hide_index=True)
    else:
        st.warning("No hay responsables disponibles con los filtros actuales.")

# =========================================================
# PIE
# =========================================================
st.markdown("---")
st.caption("Demo visual para validación de estructura, gráficos, filtros y patrones de visualización.")