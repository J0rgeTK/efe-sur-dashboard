import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date
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
        margin-bottom: 0.1rem;
    }}

    .subtitle {{
        font-size: 0.95rem;
        color: {TEXT_MUTED};
        margin-bottom: 0.2rem;
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
    if pd.isna(value):
        return "-"
    if unit == "CLP":
        return f"$ {value:,.0f}".replace(",", ".")
    if unit == "%":
        return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")
    if unit == "pax":
        return f"{value:,.0f}".replace(",", ".")
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_pct(value):
    if pd.isna(value):
        return "-"
    return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")

def classify_status(value, meta, higher_is_better=True):
    if pd.isna(meta) or meta == 0:
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

def safe_to_datetime(series):
    return pd.to_datetime(series, errors="coerce")

def validate_columns(df, required_cols, label):
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"El archivo {label} no contiene las columnas requeridas: {', '.join(missing)}")
        st.stop()

def get_repo_data_path():
    base = Path(__file__).resolve().parent
    candidates = [
        base / "data",
        base / "datos",
        base,
    ]
    for folder in candidates:
        if (folder / "kpis.csv").exists() and (folder / "iniciativas.csv").exists() and (folder / "personas.csv").exists():
            return folder
    st.error(
        "No se encontraron los archivos kpis.csv, iniciativas.csv y personas.csv en el repositorio. "
        "Ubíquelos en la raíz del proyecto o dentro de una carpeta llamada data."
    )
    st.stop()

def build_line_chart(df, title, color=None, line_dash=None, height=340):
    fig = px.line(
        df,
        x="periodo",
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
        legend_title_text=""
    )
    fig.update_xaxes(title="")
    fig.update_yaxes(title="")
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

    # Tipos
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

    if not servicios.empty and "activo" in servicios.columns:
        servicios["activo"] = pd.to_numeric(servicios["activo"], errors="coerce").fillna(0).astype(int)
        if "orden" in servicios.columns:
            servicios["orden"] = pd.to_numeric(servicios["orden"], errors="coerce")

    return kpis, iniciativas, personas, servicios, data_path

kpis, iniciativas, personas, servicios, data_path = load_data()

# =========================================================
# PREPARACIÓN DE DATOS
# =========================================================
personas_activas = personas[personas["activo"] == 1].copy()

iniciativas = iniciativas.merge(
    personas_activas[["id_persona", "nombre"]],
    how="left",
    left_on="responsable_id",
    right_on="id_persona"
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

# Orden de servicios
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
    st.markdown(
        f"<div class='small-note'>Lectura de archivos desde: <b>{data_path}</b></div>",
        unsafe_allow_html=True,
    )

# =========================================================
# ENCABEZADO Y PERÍODO VISIBLE
# =========================================================
col_logo, col_title, col_periodo = st.columns([1, 4.5, 1.8])

with col_logo:
    logo_candidates = [
        Path(__file__).resolve().parent / "assets" / "logoefe-azul.png",
        Path(__file__).resolve().parent / "logoefe-azul.png",
    ]
    for logo_path in logo_candidates:
        if logo_path.exists():
            st.image(str(logo_path), use_container_width=True)
            break

with col_title:
    st.markdown("<div class='main-title'>Dashboard de KPIs e iniciativas</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='subtitle'>Seleccione el período en la parte superior y use la barra lateral para filtros complementarios.</div>",
        unsafe_allow_html=True,
    )

with col_periodo:
    periodo_sel = st.selectbox("Período de análisis", options=periodos, index=default_period_index, key="periodo_top")

# =========================================================
# FILTRADO
# =========================================================
kpis_f = kpis[
    (kpis["periodo"].astype(str) == str(periodo_sel))
    & (kpis["servicio"].isin(servicios_sel))
].copy()

iniciativas_f = iniciativas[
    (iniciativas["servicio"].isin(servicios_sel))
    & (iniciativas["estado"].isin(estados_ini_sel))
    & (iniciativas["prioridad"].isin(prioridades_sel))
    & (iniciativas["responsable"].isin(responsables_sel))
].copy()

kpis_hist = kpis[kpis["servicio"].isin(servicios_sel)].copy()

if "orden" in kpis_f.columns:
    kpis_f = kpis_f.sort_values(["orden", "servicio", "nombre"])
else:
    kpis_f = kpis_f.sort_values(["nombre", "servicio"])

tabs = st.tabs(["Resumen ejecutivo", "KPIs", "Personas"])

# =========================================================
# TAB 1 - RESUMEN EJECUTIVO
# =========================================================
with tabs[0]:
    st.markdown("<div class='section-title'>Resumen ejecutivo</div>", unsafe_allow_html=True)

    kpi_cards = kpis_f.head(4).copy()
    if kpi_cards.empty:
        st.warning("No existen KPI para los filtros seleccionados.")
    else:
        cols = st.columns(min(4, len(kpi_cards)))
        for idx, (_, row) in enumerate(kpi_cards.iterrows()):
            titulo = f"{row['nombre']} - {row['servicio']}"
            with cols[idx]:
                render_kpi_card(
                    titulo,
                    fmt_number(row["valor"], row["unidad"]),
                    f"Meta: {fmt_number(row['meta'], row['unidad'])}",
                    f"Desviación: {fmt_pct(row['variacion_pct'])}",
                    row["estado"]
                )

    st.markdown("<div class='section-title'>Evolución del KPI</div>", unsafe_allow_html=True)
    nombres_kpi = sorted(kpis_hist["nombre"].dropna().astype(str).unique().tolist())
    if nombres_kpi:
        kpi_hist_sel = st.selectbox("KPI para evolución", options=nombres_kpi, key="kpi_hist_sel_resumen")

        hist_sel = kpis_hist[kpis_hist["nombre"] == kpi_hist_sel].copy()
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
                st.info("No hay datos rurales para el KPI y filtros seleccionados.")
            else:
                hist_rural_plot = hist_rural.groupby(["periodo", "servicio"], as_index=False)["valor"].sum()
                fig_rural = build_line_chart(hist_rural_plot, f"{kpi_hist_sel} - Servicios rurales", color="servicio")
                st.plotly_chart(fig_rural, use_container_width=True)
    else:
        st.info("No hay KPIs disponibles para graficar.")

    st.markdown("<div class='section-title'>Iniciativas críticas</div>", unsafe_allow_html=True)

    criticas = iniciativas_f[iniciativas_f["critica"]].copy()
    criticas = criticas.sort_values(["prioridad", "fecha_fin", "avance_pct"], ascending=[True, True, True])

    if criticas.empty:
        st.info("No existen iniciativas críticas con los filtros actuales.")
    else:
        criticas_table = criticas[[
            "nombre_iniciativa", "responsable", "servicio", "estado", "avance_pct", "fecha_fin", "prioridad"
        ]].rename(columns={
            "nombre_iniciativa": "Iniciativa",
            "responsable": "Responsable",
            "servicio": "Servicio",
            "estado": "Estado",
            "avance_pct": "Avance %",
            "fecha_fin": "Fecha fin",
            "prioridad": "Prioridad",
        })
        st.dataframe(criticas_table, use_container_width=True, hide_index=True)

# =========================================================
# TAB 2 - KPIs
# =========================================================
with tabs[1]:
    st.markdown("<div class='section-title'>Análisis de KPIs</div>", unsafe_allow_html=True)

    nombres_kpi = sorted(kpis["nombre"].dropna().astype(str).unique().tolist())
    kpi_sel = st.selectbox("Seleccione KPI", options=nombres_kpi, key="kpi_analisis")

    hist_kpi = kpis_hist[kpis_hist["nombre"] == kpi_sel].copy()

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
            st.info("No hay datos rurales para el KPI seleccionado.")
        else:
            rural_hist = rural_hist.groupby(["periodo", "servicio"], as_index=False)["valor"].sum()
            fig_rural = build_line_chart(rural_hist, f"{kpi_sel} - Servicios rurales", color="servicio", height=360)
            st.plotly_chart(fig_rural, use_container_width=True)

    st.markdown("<div class='section-title'>Valor vs meta en el período seleccionado</div>", unsafe_allow_html=True)
    actual = kpis_f[kpis_f["nombre"] == kpi_sel].copy()
    if not actual.empty:
        fig_meta = go.Figure()
        fig_meta.add_trace(go.Bar(
            x=actual["servicio"],
            y=actual["valor"],
            name="Valor",
            marker_color=EFE_BLUE
        ))
        fig_meta.add_trace(go.Bar(
            x=actual["servicio"],
            y=actual["meta"],
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
    else:
        st.info("No hay datos para el KPI seleccionado en el período actual.")

    st.markdown("<div class='section-title'>Detalle del KPI</div>", unsafe_allow_html=True)

    detalle_cols = ["servicio", "categoria", "valor", "meta", "unidad", "variacion_pct", "estado"]
    if "observacion" in kpis_f.columns:
        detalle_cols.append("observacion")
    detalle_kpi = kpis_f[kpis_f["nombre"] == kpi_sel][detalle_cols].copy()

    if not detalle_kpi.empty:
        detalle_kpi["Valor"] = detalle_kpi.apply(lambda r: fmt_number(r["valor"], r["unidad"]), axis=1)
        detalle_kpi["Meta"] = detalle_kpi.apply(lambda r: fmt_number(r["meta"], r["unidad"]), axis=1)
        detalle_kpi["Variación"] = detalle_kpi["variacion_pct"].apply(fmt_pct)

        cols_show = ["servicio", "categoria", "Valor", "Meta", "Variación", "estado"]
        rename_map = {
            "servicio": "Servicio",
            "categoria": "Categoría",
            "estado": "Estado",
        }
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
        por_responsable = (
            iniciativas_f.groupby("responsable", as_index=False)
            .agg(cantidad=("id_iniciativa", "count"), avance_promedio=("avance_pct", "mean"))
            .sort_values("cantidad", ascending=False)
        )

        if por_responsable.empty:
            st.info("No hay iniciativas para mostrar según los filtros seleccionados.")
        else:
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
                height=340
            )
            fig.update_xaxes(title="")
            fig.update_yaxes(title="Cantidad")
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        por_prioridad = iniciativas_f["prioridad"].value_counts().reset_index()
        por_prioridad.columns = ["prioridad", "cantidad"]

        if por_prioridad.empty:
            st.info("No hay prioridades disponibles para los filtros seleccionados.")
        else:
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
                height=340
            )
            st.plotly_chart(fig2, use_container_width=True)

    personas_opts = sorted(iniciativas_f["responsable"].dropna().astype(str).unique().tolist())
    if personas_opts:
        st.markdown("<div class='section-title'>Detalle del responsable</div>", unsafe_allow_html=True)
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
        p4.metric("Avance promedio", fmt_pct(avance_prom))

        left_p, right_p = st.columns([1.1, 1])

        with left_p:
            fig = px.bar(
                per_df.sort_values("avance_pct"),
                x="avance_pct",
                y="nombre_iniciativa",
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
                    "Finalizada": SUCCESS,
                    "Pausada": WARNING,
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

        detalle_cols = [
            "nombre_iniciativa", "servicio", "estado", "avance_pct", "fecha_inicio", "fecha_fin", "prioridad"
        ]
        if "criticidad" in per_df.columns:
            detalle_cols.append("criticidad")
        if "comentario" in per_df.columns:
            detalle_cols.append("comentario")

        detalle_persona = per_df[detalle_cols].copy()
        detalle_persona = detalle_persona.rename(columns={
            "nombre_iniciativa": "Iniciativa",
            "servicio": "Servicio",
            "estado": "Estado",
            "avance_pct": "Avance %",
            "fecha_inicio": "Inicio",
            "fecha_fin": "Fin",
            "prioridad": "Prioridad",
            "criticidad": "Criticidad",
            "comentario": "Comentario"
        })
        st.dataframe(detalle_persona, use_container_width=True, hide_index=True)
    else:
        st.warning("No hay responsables disponibles con los filtros actuales.")

# =========================================================
# PIE
# =========================================================
st.markdown("---")
st.caption("La aplicación lee automáticamente los archivos CSV contenidos en el repositorio de GitHub.")
