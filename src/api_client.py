"""
src/api_client.py
-------------
Capa de ACCESO A DATOS: aquí vive el requests.get que consume la API pública
de datos.gob.cl (plataforma CKAN).

Conjunto de datos: "Subsidio Discapacidad (SD)" del Instituto de Previsión
Social (IPS). Cada mes el IPS publica un recurso (tabla) con los beneficiarios
y montos pagados por comuna.

Funciones:
- obtener_datos(url): hace UNA petición GET y devuelve el JSON como dict.
- obtener_meses_disponibles(): lee el catálogo del dataset (package_show) y
  devuelve la lista de meses publicados con su resource_id.
- obtener_todos(resource_id): descarga todos los registros de un mes usando
  paginación (limit/offset) con la acción datastore_search.

Si la API no responde (portal caído o sin internet) se usa un respaldo local
en /data guardado la última vez que la API funcionó, para que la app no se caiga.
"""
import json
import re
from pathlib import Path

import requests

BASE_API = "https://datos.gob.cl/api/3/action"
PACKAGE_ID = "e5f941cd-ef4e-4498-b862-c9cdbaa0248b"  # Subsidio Discapacidad (SD) - IPS
URL_DATASET = "https://datos.gob.cl/dataset/" + PACKAGE_ID
DIR_RESPALDO = Path(__file__).resolve().parent.parent / "data"

# Los recursos recientes se llaman "SD_012026", "SD-092025", etc. (mes + año)
PATRON_NOMBRE = re.compile(r"^SD[_-](\d{2})(\d{4})$")


def construir_url(resource_id, limit=1000, offset=0):
    """Arma la URL de consulta de la API (acción datastore_search)."""
    return f"{BASE_API}/datastore_search?resource_id={resource_id}&limit={limit}&offset={offset}"


def obtener_datos(url, timeout=30):
    """Hace la petición GET y devuelve el JSON como diccionario de Python."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()  # error si el código HTTP no es 200
    data = json.loads(response.text)
    if not data.get("success", False):
        raise ValueError(f"La API respondió success=false: {data.get('error')}")
    return data


# ---------------------------------------------------------------- respaldo
def _guardar_respaldo(nombre, contenido):
    try:
        DIR_RESPALDO.mkdir(parents=True, exist_ok=True)
        (DIR_RESPALDO / nombre).write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # en la nube el disco puede no permitir escritura: no es crítico


def _leer_respaldo(nombre):
    ruta = DIR_RESPALDO / nombre
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return None


# ---------------------------------------------------------------- catálogo
def obtener_meses_disponibles():
    """Devuelve (lista_de_meses, origen).

    Cada mes es un dict {"nombre", "resource_id", "anio", "mes"} ordenado del
    más reciente al más antiguo. Solo incluye recursos consultables por API
    (datastore_active = True).
    """
    try:
        data = obtener_datos(f"{BASE_API}/package_show?id={PACKAGE_ID}")
        meses = []
        for recurso in data["result"]["resources"]:
            coincide = PATRON_NOMBRE.match((recurso.get("name") or "").strip())
            if coincide and recurso.get("datastore_active"):
                mes, anio = int(coincide.group(1)), int(coincide.group(2))
                meses.append({"nombre": recurso["name"].strip(), "resource_id": recurso["id"],
                              "anio": anio, "mes": mes})
        if not meses:
            raise ValueError("El catálogo no tiene meses consultables")
        meses.sort(key=lambda m: (m["anio"], m["mes"]), reverse=True)
        _guardar_respaldo("catalogo.json", meses)
        return meses, "api"
    except Exception:
        respaldo = _leer_respaldo("catalogo.json")
        if respaldo:
            return respaldo, "respaldo"
        raise


# ---------------------------------------------------------------- datos del mes
def obtener_todos(resource_id, tam_pagina=1000, max_registros=100_000):
    """Descarga TODOS los registros de un recurso usando paginación.

    Devuelve (data_json, origen). data_json tiene la misma forma que la API:
    {"result": {"records": [...], "fields": [...], "total": N}}
    """
    try:
        registros, campos, offset, total = [], [], 0, 0
        while True:
            data = obtener_datos(construir_url(resource_id, tam_pagina, offset))
            resultado = data["result"]
            campos = resultado.get("fields", campos)
            total = resultado.get("total", total) or 0
            lote = resultado.get("records", [])
            registros.extend(lote)
            offset += tam_pagina
            if not lote or len(registros) >= total or len(registros) >= max_registros:
                break
        data_json = {"result": {"records": registros, "fields": campos, "total": total}}
        _guardar_respaldo(f"respaldo_{resource_id}.json", data_json)
        return data_json, "api"
    except Exception:
        respaldo = _leer_respaldo(f"respaldo_{resource_id}.json")
        if respaldo:
            return respaldo, "respaldo"
        raise
