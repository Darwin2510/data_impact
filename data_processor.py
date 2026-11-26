"""
data_processor.py
-----------------
Capa de LIMPIEZA Y TRANSFORMACIÓN con Pandas y NumPy.

Pasos de procesar():
 1. Aplanar el JSON de la API con json_normalize (por si hay anidamiento).
 2. Renombrar columnas a nombres claros (snake_case).
 3. Limpiar texto (espacios, celdas vacías -> NaN).
 4. Eliminar nulos: filas sin comuna (la fila "Total" y la fila "Nota" que
    trae la tabla original) y filas con valores numéricos inválidos.
 5. Convertir texto a números (pd.to_numeric) respetando el formato chileno
    ("74.600" = 74600 y "491,667" = 491.667) y crear la fecha del período
    (pd.to_datetime).
 6. Crear columnas calculadas (monto promedio, % mujeres, participación,
    variación % respecto al promedio comunal, etc.).
"""
import numpy as np
import pandas as pd
from pandas import json_normalize

# Códigos oficiales de región (CUT) -> nombre
REGIONES = {
    15: "Arica y Parinacota", 1: "Tarapacá", 2: "Antofagasta", 3: "Atacama",
    4: "Coquimbo", 5: "Valparaíso", 13: "Metropolitana", 6: "O'Higgins",
    7: "Maule", 16: "Ñuble", 8: "Biobío", 9: "La Araucanía", 14: "Los Ríos",
    10: "Los Lagos", 11: "Aysén", 12: "Magallanes",
}
# Orden geográfico de norte a sur (para que los gráficos se lean como el mapa)
ORDEN_REGIONES = list(REGIONES.values())

MESES_ES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
            7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre",
            11: "Noviembre", 12: "Diciembre"}

# Columnas originales de la API -> nombres claros
RENOMBRAR = {
    "Region": "region_cod",
    "Cod Comuna": "cod_comuna",
    "Glosa Comuna": "comuna",
    "Ndeg Hombre": "hombres",
    "Mto.Hombre": "monto_hombres_miles",
    "No Mujer": "mujeres",
    "Mto.Mujer": "monto_mujeres_miles",
    "No": "beneficiarios",
    "Monto m$": "monto_total_miles",
}
COLS_NUMERICAS = ["hombres", "monto_hombres_miles", "mujeres",
                  "monto_mujeres_miles", "beneficiarios", "monto_total_miles"]


def a_numero_cl(serie):
    """Convierte texto con formato numérico chileno a número.

    "74.600" -> 74600   (el punto separa miles)
    "491,667" -> 491.667 (la coma es el decimal)
    Lo que no se pueda convertir queda como NaN (errors="coerce").
    """
    texto = (serie.astype(object).where(serie.notna(), None)
             .map(lambda x: str(x).strip().replace(".", "").replace(",", ".") if x is not None else None))
    return pd.to_numeric(texto, errors="coerce").astype("float64")


def procesar(data_json, anio, mes):
    """Recibe el JSON crudo de la API y devuelve (df_limpio, reporte).

    `reporte` es un dict con lo que hizo la limpieza (para la Metodología).
    """
    # 1. Aplanamos por si hay anidamiento
    df = json_normalize(data_json["result"]["records"])
    reporte = {"filas_originales": len(df), "columnas_originales": list(df.columns)}

    # 2. Renombrar y quedarnos solo con las columnas útiles
    faltantes = [c for c in RENOMBRAR if c not in df.columns]
    if faltantes:
        raise ValueError(f"La API cambió su formato, faltan columnas: {faltantes}")
    df = df.rename(columns=RENOMBRAR)[list(RENOMBRAR.values())]

    # 3. Limpiar texto: quitar espacios y transformar celdas vacías en NaN
    for col in df.columns:
        df[col] = (df[col].astype(object)
                   .map(lambda x: x.strip() if isinstance(x, str) else x)
                   .replace("", np.nan))

    # 4a. Eliminar nulos en las columnas clave (quita la fila "Total" y la "Nota")
    antes = len(df)
    df = df.dropna(subset=["cod_comuna", "comuna", "region_cod"])
    reporte["filas_sin_comuna_eliminadas"] = antes - len(df)

    # 5. Conversión de tipos: texto -> número
    df["region_cod"] = pd.to_numeric(df["region_cod"], errors="coerce").astype("float64")
    for col in COLS_NUMERICAS:
        df[col] = a_numero_cl(df[col])

    # 4b. Eliminar filas que quedaron con NaN (valores imposibles de convertir)
    antes = len(df)
    df = df.dropna()
    df = df[df["region_cod"].isin(REGIONES.keys())]
    reporte["filas_invalidas_eliminadas"] = antes - len(df)

    # Duplicados (por si la API repite una comuna)
    antes = len(df)
    df = df.drop_duplicates(subset="cod_comuna")
    reporte["duplicados_eliminados"] = antes - len(df)

    # Tipos finales
    df = df.astype({"region_cod": int, "hombres": int, "mujeres": int, "beneficiarios": int})
    df["cod_comuna"] = df["cod_comuna"].astype(str)
    df["comuna"] = df["comuna"].str.title()
    df["region"] = pd.Categorical(df["region_cod"].map(REGIONES),
                                  categories=ORDEN_REGIONES, ordered=True)

    # 5b. Conversión a fecha: período al que corresponde el pago
    df["periodo"] = pd.to_datetime(f"{anio}-{mes:02d}-01", format="%Y-%m-%d")

    # 6. Columnas calculadas (NumPy para evitar divisiones por cero)
    benef = df["beneficiarios"].to_numpy(dtype=float)
    df["monto_total_pesos"] = df["monto_total_miles"] * 1000
    df["monto_promedio_pesos"] = np.where(benef > 0, df["monto_total_pesos"] / np.where(benef > 0, benef, 1), np.nan).round(0)
    df["pct_mujeres"] = np.where(benef > 0, df["mujeres"] / np.where(benef > 0, benef, 1) * 100, np.nan).round(1)
    df["brecha_hombres_mujeres"] = df["hombres"] - df["mujeres"]
    total_nacional = df["beneficiarios"].sum()
    df["participacion_nacional_pct"] = (df["beneficiarios"] / total_nacional * 100).round(3)
    promedio_comunal = df["beneficiarios"].mean()
    df["variacion_vs_promedio_pct"] = ((df["beneficiarios"] - promedio_comunal) / promedio_comunal * 100).round(1)

    df = df.sort_values(["region", "comuna"]).reset_index(drop=True)
    reporte.update({
        "filas_finales": len(df),
        "total_beneficiarios": int(total_nacional),
        "promedio_comunal": float(promedio_comunal),
    })
    return df, reporte


def agregar_variacion_mensual(df_actual, df_anterior):
    """Agrega la variación % de beneficiarios de cada comuna vs el mes anterior."""
    if df_anterior is None or df_anterior.empty:
        df_actual["benef_mes_anterior"] = np.nan
        df_actual["variacion_mes_anterior_pct"] = np.nan
        return df_actual
    anterior = df_anterior[["cod_comuna", "beneficiarios"]].rename(
        columns={"beneficiarios": "benef_mes_anterior"})
    df = df_actual.merge(anterior, on="cod_comuna", how="left")
    previo = df["benef_mes_anterior"].to_numpy(dtype=float)
    df["variacion_mes_anterior_pct"] = np.where(
        previo > 0, (df["beneficiarios"] - previo) / np.where(previo > 0, previo, 1) * 100, np.nan).round(1)
    return df


def aplicar_filtros(df, regiones, rango_benef, texto=""):
    """Filtra por región, rango de beneficiarios y nombre de comuna."""
    if df is None:
        return None
    filtro = (df["region"].isin(regiones)
              & df["beneficiarios"].between(rango_benef[0], rango_benef[1]))
    if texto:
        filtro &= df["comuna"].str.contains(texto.strip(), case=False, na=False, regex=False)
    return df[filtro]


def resumen_por_region(df):
    """Tabla agregada por región (para gráficos y para el análisis)."""
    res = (df.groupby("region", observed=True)
             .agg(comunas=("comuna", "count"), hombres=("hombres", "sum"),
                  mujeres=("mujeres", "sum"), beneficiarios=("beneficiarios", "sum"),
                  monto_total_pesos=("monto_total_pesos", "sum"),
                  mediana_por_comuna=("beneficiarios", "median"))
             .reset_index())
    res["monto_promedio_pesos"] = (res["monto_total_pesos"] / res["beneficiarios"].replace(0, np.nan)).round(0)
    res["pct_mujeres"] = (res["mujeres"] / res["beneficiarios"].replace(0, np.nan) * 100).round(1)
    return res


def nombre_mes(anio, mes):
    return f"{MESES_ES[mes]} {anio}"
