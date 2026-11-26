"""
app.py — Observatorio DataImpact (SOLO interfaz Streamlit)
-----------------------------------------------------------
La lógica está separada en /src:
  - src/api_client.py      -> consumo de la API (requests.get)
  - src/data_processor.py  -> limpieza con Pandas/NumPy y columnas calculadas
  - src/visualizations.py  -> funciones de gráficos (Plotly y Seaborn)

Ejecutar en local:  streamlit run app.py
"""
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from src.api_client import URL_DATASET, construir_url, obtener_meses_disponibles, obtener_todos
from src.data_processor import (ORDEN_REGIONES, agregar_variacion_mensual, aplicar_filtros,
                                nombre_mes, procesar, resumen_por_region)
from src.visualizations import CANDADO_MPL, grafico_barras_region, grafico_boxplot, grafico_top_comunas

st.set_page_config(page_title="DataImpact | Subsidio de Discapacidad", page_icon="📊", layout="wide")


# --------------------------------------------------------------------------
# Utilidades de formato (estilo chileno: punto para miles, coma decimal)
# --------------------------------------------------------------------------
def num(x, dec=0):
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pesos(x):
    return "$" + num(x)


def pct(x, dec=1, signo=False):
    return ("+" if signo and x > 0 else "") + num(x, dec) + "%"


def variacion(actual, anterior):
    """Variación porcentual segura (None si no se puede calcular)."""
    if anterior is None or pd.isna(anterior) or anterior == 0:
        return None
    return (actual - anterior) / anterior * 100


# --------------------------------------------------------------------------
# Carga de datos (con caché para no llamar a la API en cada clic)
# --------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def cargar_catalogo():
    return obtener_meses_disponibles()


@st.cache_data(ttl=3600, show_spinner=False)
def cargar_mes(resource_id, anio, mes):
    data_json, origen = obtener_todos(resource_id)
    df_crudo = pd.json_normalize(data_json["result"]["records"])
    df, reporte = procesar(data_json, anio, mes)
    return df, reporte, origen, df_crudo


st.title("📊 DataImpact · Observatorio del Subsidio de Discapacidad")
st.caption("Niñas, niños y adolescentes en situación de discapacidad que reciben el subsidio del "
           "Instituto de Previsión Social (IPS), por comuna · Fuente: API de datos.gob.cl")

try:
    with st.spinner("Consultando la API de datos.gob.cl..."):
        meses, origen_catalogo = cargar_catalogo()
except Exception as e:  # sin API y sin respaldo
    st.error(f"No fue posible conectarse a la API de datos.gob.cl ni encontrar un respaldo local. Detalle: {e}")
    st.stop()

# --------------------------------------------------------------------------
# Barra lateral: filtros
# --------------------------------------------------------------------------
st.sidebar.header("🔎 Filtros")
etiquetas_mes = [nombre_mes(m["anio"], m["mes"]) for m in meses]
idx_mes = st.sidebar.selectbox("Mes de pago", range(len(meses)), format_func=lambda i: etiquetas_mes[i],
                               help="Meses publicados por el IPS en datos.gob.cl (el primero es el más reciente).")
mes_sel = meses[idx_mes]
mes_ant = meses[idx_mes + 1] if idx_mes + 1 < len(meses) else None

try:
    with st.spinner(f"Descargando {etiquetas_mes[idx_mes]}..."):
        df, reporte, origen, df_crudo = cargar_mes(mes_sel["resource_id"], mes_sel["anio"], mes_sel["mes"])
        df_ant = None
        if mes_ant:
            try:
                df_ant = cargar_mes(mes_ant["resource_id"], mes_ant["anio"], mes_ant["mes"])[0]
            except Exception:
                df_ant = None  # si falla el mes anterior, la app sigue sin la comparación
except Exception as e:
    st.error(f"No se pudieron obtener los datos de {etiquetas_mes[idx_mes]}. Detalle: {e}")
    st.stop()

df = agregar_variacion_mensual(df, df_ant)
etiqueta_ant = nombre_mes(mes_ant["anio"], mes_ant["mes"]) if mes_ant and df_ant is not None else None

if "respaldo" in (origen, origen_catalogo):
    st.warning("⚠️ La API de datos.gob.cl no respondió: se muestran los datos de la última descarga guardada.")

regiones_disp = [r for r in ORDEN_REGIONES if r in set(df["region"].astype(str))]
regiones_sel = st.sidebar.multiselect("Región", regiones_disp, default=regiones_disp)
max_benef = int(df["beneficiarios"].max())
rango = st.sidebar.slider("Beneficiarios por comuna", 0, max_benef, (0, max_benef),
                          help="Permite aislar comunas pequeñas o grandes.")
texto = st.sidebar.text_input("Buscar comuna", placeholder="Ej: Temuco")
st.sidebar.caption("Todos los gráficos, métricas y la tabla se actualizan con estos filtros.")

df_f = aplicar_filtros(df, regiones_sel, rango, texto)
df_ant_f = aplicar_filtros(df_ant, regiones_sel, rango, texto) if df_ant is not None else None

# --------------------------------------------------------------------------
# Metodología (escondida en un expander)
# --------------------------------------------------------------------------
with st.expander("📘 Metodología: de dónde vienen los datos y cómo se procesaron"):
    st.markdown(f"""
**Fuente.** Conjunto de datos *Subsidio Discapacidad (SD)* publicado por el **Instituto de Previsión Social (IPS)**
en el portal de datos abiertos del Estado: [{URL_DATASET}]({URL_DATASET}).
Se consume en vivo con la API CKAN de datos.gob.cl (acción `datastore_search`):

`{construir_url(mes_sel['resource_id'])}`

**¿Qué es el subsidio?** Un aporte mensual en dinero para personas **menores de 18 años** en situación de
discapacidad mental, física o sensorial severa y de escasos recursos. Cada registro es una **comuna**, con el
número de beneficiarios (hombres / mujeres) y el monto pagado en el mes (en miles de pesos).

**Procesamiento realizado** (`src/data_processor.py`):
1. **Aplanado** del JSON con `pandas.json_normalize` → {reporte['filas_originales']} filas crudas.
2. **Eliminación de nulos**: se quitaron {reporte['filas_sin_comuna_eliminadas']} filas sin comuna
   (la fila "Total" y la nota al pie que trae la tabla original) y {reporte['filas_invalidas_eliminadas']} filas con valores inválidos.
3. **Conversión de tipos**: los números vienen como texto con formato chileno (`"74.600"`, `"491,667"`);
   se transforman con `pd.to_numeric`, y el período de pago se convierte a fecha con `pd.to_datetime`.
4. **Columnas calculadas**: monto promedio por beneficiario, % de mujeres, brecha hombres–mujeres,
   participación en el total nacional, **variación % respecto al promedio comunal** y
   **variación % respecto al mes anterior** (cruzando dos meses de la API).
5. **Validación**: el total limpio ({num(reporte['total_beneficiarios'])} beneficiarios) coincide con la fila "Total" oficial.

**Limitaciones.** La fuente no informa la población infantil por comuna, por lo que los valores son absolutos
(no tasas). Las comunas con 0 beneficiarios no tienen % de mujeres ni monto promedio (quedan en blanco).
""")

# --------------------------------------------------------------------------
# Pestañas
# --------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📈 Resumen Ejecutivo", "🔬 Análisis Detallado", "🗂️ Datos Crudos"])

if df_f.empty:
    for t in (tab1, tab2, tab3):
        t.info("No hay comunas que cumplan con los filtros seleccionados. Ajusta los filtros de la barra lateral.")
    st.stop()

# Cálculos para las métricas de impacto
total = int(df_f["beneficiarios"].sum())
monto = float(df_f["monto_total_pesos"].sum())
mujeres = int(df_f["mujeres"].sum())
pct_muj = mujeres / total * 100 if total else 0
monto_prom = monto / total if total else 0
prom_comunal = df_f["beneficiarios"].mean()
participacion = total / df["beneficiarios"].sum() * 100
top = df_f.loc[df_f["beneficiarios"].idxmax()]
var_top = variacion(top["beneficiarios"], prom_comunal)
sin_benef = int((df_f["beneficiarios"] == 0).sum())

total_ant = int(df_ant_f["beneficiarios"].sum()) if df_ant_f is not None else None
monto_ant = float(df_ant_f["monto_total_pesos"].sum()) if df_ant_f is not None else None
var_total = variacion(total, total_ant)
var_monto = variacion(monto, monto_ant)
txt_ant = f" vs {etiqueta_ant}" if etiqueta_ant else ""

# ---------------------------------------------------------------- Pestaña 1
with tab1:
    st.subheader(f"Resumen · {etiquetas_mes[idx_mes]}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Beneficiarios", num(total),
              delta=pct(var_total, signo=True) + txt_ant if var_total is not None else None,
              help="Niñas, niños y adolescentes que recibieron el subsidio en el mes.")
    c2.metric("Monto pagado en el mes", "$" + num(monto / 1e6, 1) + " MM",
              delta=pct(var_monto, signo=True) + txt_ant if var_monto is not None else None,
              help="MM = millones de pesos.")
    c3.metric("Monto promedio por beneficiario", pesos(monto_prom))
    c4.metric("% mujeres beneficiarias", pct(pct_muj),
              delta=(f"{num(abs(total - 2 * mujeres))} más "
                     f"{'hombres que mujeres' if total - 2 * mujeres >= 0 else 'mujeres que hombres'}") if total else None,
              delta_color="off")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Comunas en la selección", num(len(df_f)),
              delta=f"{sin_benef} sin beneficiarios" if sin_benef else "todas con beneficiarios", delta_color="off")
    c6.metric("Participación en el total nacional", pct(participacion),
              help="Beneficiarios de la selección / beneficiarios de todo Chile.")
    c7.metric("Promedio de beneficiarios por comuna", num(prom_comunal, 1))
    c8.metric("Comuna con más beneficiarios", top["comuna"],
              delta=(f"{num(top['beneficiarios'])} · {pct(var_top, 0, signo=True)} vs promedio")
              if var_top is not None else None,
              delta_color="off",
              help="Beneficiarios de la comuna y su variación % respecto al promedio comunal de la selección.")

    st.plotly_chart(grafico_barras_region(resumen_por_region(df_f)), width="stretch")

    reg = resumen_por_region(df_f).sort_values("beneficiarios", ascending=False)
    lider = reg.iloc[0]
    st.info(
        f"**Lectura rápida:** {lider['region']} concentra el {pct(lider['beneficiarios'] / total * 100)} de los "
        f"beneficiarios de la selección. Por cada 10 beneficiarios hay {num(pct_muj / 10, 1)} mujeres, "
        f"y el subsidio promedio pagado es de {pesos(monto_prom)} mensuales por persona."
    )

# ---------------------------------------------------------------- Pestaña 2
with tab2:
    st.subheader("Análisis detallado por comuna")
    col_a, col_b = st.columns([2, 1])
    opciones_rank = {"Beneficiarios": "beneficiarios", "Monto mensual": "monto_total_pesos"}
    if etiqueta_ant:
        opciones_rank["Crecimiento vs mes anterior (%)"] = "variacion_mes_anterior_pct"
    var_rank = col_b.radio("Ordenar ranking por", list(opciones_rank.keys()))
    n_top = col_b.slider("Cantidad de comunas", 5, 30, 15)
    col_a.plotly_chart(grafico_top_comunas(df_f, n_top, opciones_rank[var_rank]), width="stretch")

    st.markdown("#### Distribución estadística por región (Seaborn)")
    opciones_box = {"Beneficiarios por comuna": "beneficiarios", "% de mujeres": "pct_mujeres",
                    "Monto promedio por beneficiario": "monto_promedio_pesos"}
    if etiqueta_ant:
        opciones_box["Variación % vs mes anterior"] = "variacion_mes_anterior_pct"
    cb1, cb2 = st.columns([3, 1])
    var_box = cb1.selectbox("Variable a analizar", list(opciones_box.keys()))
    log = cb2.checkbox("Escala logarítmica", value=True,
                       help="Útil para beneficiarios: Santiago y Puente Alto tienen muchos más que comunas rurales.")
    with CANDADO_MPL:  # matplotlib dibuja de a una figura a la vez
        fig_seaborn = grafico_boxplot(df_f, opciones_box[var_box], escala_log=log)
        st.pyplot(fig_seaborn)
        plt.close(fig_seaborn)
    st.caption("Cada punto es una comuna. La caja muestra el 50% central de las comunas y la línea, la mediana.")

    st.markdown("#### Indicadores por región")
    tabla_reg = resumen_por_region(df_f).rename(columns={
        "region": "Región", "comunas": "Comunas", "hombres": "Hombres", "mujeres": "Mujeres",
        "beneficiarios": "Beneficiarios", "monto_total_pesos": "Monto total ($)",
        "mediana_por_comuna": "Mediana por comuna", "monto_promedio_pesos": "Monto promedio ($)",
        "pct_mujeres": "% mujeres"})
    st.dataframe(tabla_reg, hide_index=True, width="stretch",
                 column_config={"Monto total ($)": st.column_config.NumberColumn(format="localized"),
                                "Monto promedio ($)": st.column_config.NumberColumn(format="localized")})

# ---------------------------------------------------------------- Pestaña 3
with tab3:
    st.subheader("Datos procesados")
    st.caption(f"{num(len(df_f))} comunas según los filtros · período {etiquetas_mes[idx_mes]}")
    columnas = ["region", "comuna", "cod_comuna", "hombres", "mujeres", "beneficiarios",
                "monto_total_pesos", "monto_promedio_pesos", "pct_mujeres", "brecha_hombres_mujeres",
                "participacion_nacional_pct", "variacion_vs_promedio_pct", "benef_mes_anterior",
                "variacion_mes_anterior_pct", "periodo"]
    tabla = df_f[columnas].copy()
    tabla["periodo"] = tabla["periodo"].dt.strftime("%Y-%m")
    st.dataframe(tabla, hide_index=True, width="stretch",
                 column_config={"monto_total_pesos": st.column_config.NumberColumn("monto_total ($)", format="localized"),
                                "monto_promedio_pesos": st.column_config.NumberColumn("monto_promedio ($)", format="localized")})

    nombre_archivo = f"subsidio_discapacidad_{mes_sel['anio']}_{mes_sel['mes']:02d}.csv"
    st.download_button("⬇️ Descargar datos filtrados (CSV)",
                       data=tabla.to_csv(index=False).encode("utf-8-sig"),
                       file_name=nombre_archivo, mime="text/csv", type="primary")

    with st.expander("Ver datos crudos tal como llegan de la API (antes de limpiar)"):
        st.caption("Observa que los números vienen como texto y que al final hay una fila 'Total' y una 'Nota'.")
        st.dataframe(df_crudo, hide_index=True, width="stretch")
