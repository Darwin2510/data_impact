"""
visualizations.py
-----------------
Capa de GRÁFICOS. Cada función recibe un DataFrame (ya filtrado desde app.py)
y devuelve una figura. Así los gráficos reaccionan a los filtros.

- Plotly (interactivos): barras por región y ranking de comunas.
- Seaborn (estadístico): boxplot de la distribución por región.
"""
import matplotlib

matplotlib.use("Agg")  # backend sin ventana (necesario en servidores como Streamlit Cloud)
import threading

import matplotlib.pyplot as plt
import plotly.express as px
import seaborn as sns
from matplotlib.ticker import FuncFormatter, NullFormatter

# matplotlib no es seguro con varios hilos (Streamlit atiende cada usuario en un
# hilo): este candado hace que las figuras se dibujen de a una.
CANDADO_MPL = threading.RLock()

COLOR_HOMBRES = "#2E86AB"
COLOR_MUJERES = "#E4572E"


def grafico_barras_region(df_region):
    """Plotly: beneficiarios por región (norte a sur), apilado hombres/mujeres."""
    largo = df_region.melt(id_vars="region", value_vars=["hombres", "mujeres"],
                           var_name="Sexo", value_name="Beneficiarios")
    largo["Sexo"] = largo["Sexo"].str.capitalize()
    fig = px.bar(
        largo, x="region", y="Beneficiarios", color="Sexo", barmode="stack",
        color_discrete_map={"Hombres": COLOR_HOMBRES, "Mujeres": COLOR_MUJERES},
        labels={"region": "Región (norte → sur)"},
        title="Beneficiarios del Subsidio de Discapacidad por región",
    )
    fig.update_layout(xaxis_tickangle=-35, legend_title_text="", hovermode="x unified",
                      margin=dict(t=60, b=10))
    return fig


def grafico_top_comunas(df, n=15, variable="beneficiarios"):
    """Plotly: ranking de las N comunas con mayor valor en `variable`."""
    etiquetas = {
        "beneficiarios": "Beneficiarios",
        "monto_total_pesos": "Monto mensual ($)",
        "variacion_mes_anterior_pct": "Variación vs mes anterior (%)",
    }
    top = df.dropna(subset=[variable]).nlargest(n, variable).sort_values(variable)
    fig = px.bar(
        top, x=variable, y="comuna", orientation="h", color="region",
        hover_data={"beneficiarios": ":,", "pct_mujeres": True, "monto_promedio_pesos": ":,.0f"},
        labels={variable: etiquetas.get(variable, variable), "comuna": "", "region": "Región",
                "pct_mujeres": "% mujeres", "monto_promedio_pesos": "Monto promedio ($)"},
        title=f"Top {len(top)} comunas por {etiquetas.get(variable, variable).lower()}",
    )
    # Mantener el orden por valor aunque las barras estén coloreadas por región
    fig.update_yaxes(categoryorder="array", categoryarray=top["comuna"].tolist())
    fig.update_layout(height=max(380, 28 * len(top)), margin=dict(t=60, b=10))
    return fig


def grafico_boxplot(df, variable="beneficiarios", escala_log=False):
    """Seaborn: distribución por comuna dentro de cada región (boxplot + puntos)."""
    etiquetas = {
        "beneficiarios": "Beneficiarios por comuna",
        "pct_mujeres": "% de mujeres beneficiarias",
        "variacion_mes_anterior_pct": "Variación % vs mes anterior",
        "monto_promedio_pesos": "Monto promedio por beneficiario ($)",
    }
    datos = df.dropna(subset=[variable])
    datos = datos.assign(region=datos["region"].cat.remove_unused_categories())

    fig, ax = plt.subplots(figsize=(11, 5.5))
    sns.boxplot(data=datos, x="region", y=variable, ax=ax, color="#9ecae1",
                showfliers=False, linewidth=1)
    sns.stripplot(data=datos, x="region", y=variable, ax=ax, color="#08306b",
                  size=3, alpha=0.55, jitter=0.25)
    if escala_log and variable == "beneficiarios":
        ax.set_yscale("symlog", linthresh=10)
        ax.set_ylim(bottom=0)  # no existen comunas con beneficiarios negativos
        ax.set_yticks([0, 10, 100, 1000])
    # Etiquetas numéricas simples (formato chileno). Evita la notación matemática
    # de matplotlib, que puede fallar cuando Streamlit dibuja en varios hilos.
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", ".")))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Región (norte → sur)")
    ax.set_ylabel(etiquetas.get(variable, variable))
    ax.set_title(f"Distribución de «{etiquetas.get(variable, variable)}» por región")
    ax.tick_params(axis="x", rotation=40)
    for etiqueta in ax.get_xticklabels():
        etiqueta.set_horizontalalignment("right")
    sns.despine(fig)
    fig.tight_layout()
    return fig
