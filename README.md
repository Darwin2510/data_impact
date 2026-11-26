# 📊 DataImpact · Observatorio del Subsidio de Discapacidad

Aplicación web en **Streamlit** que consume en vivo la **API pública de datos.gob.cl**, limpia los datos con
**Pandas/NumPy** y los presenta con **Plotly** y **Seaborn** para apoyar la toma de decisiones sobre el
*Subsidio de Discapacidad* que paga el Instituto de Previsión Social (IPS) a niñas, niños y adolescentes
(menores de 18 años) en situación de discapacidad mental, física o sensorial severa y de escasos recursos.

**🔗 App en la nube:** `https://<tu-app>.streamlit.app` *(reemplazar después de desplegar)*

## ¿A quién ayuda y qué decisión permite tomar?

| Usuario | Decisión que apoya |
|---|---|
| Municipios / Oficinas de Discapacidad (OMIL, DIDECO) | Dónde reforzar la difusión del subsidio y la atención de familias: comunas con pocos beneficiarios en relación al promedio comunal o con caída respecto del mes anterior. |
| Seremis y gobiernos regionales | Comparar regiones (norte → sur) y detectar concentraciones y brechas de cobertura. |
| Organizaciones de la sociedad civil y apoderados | Conocer el alcance real del beneficio en su comuna y el monto mensual promedio. |
| Periodistas / estudiantes | Descargar datos limpios y verificables (CSV) para sus propios análisis. |

## Fuente de datos (API)

- Dataset: *Subsidio Discapacidad (SD)* — IPS: <https://datos.gob.cl/dataset/e5f941cd-ef4e-4498-b862-c9cdbaa0248b>
- Catálogo de meses: `https://datos.gob.cl/api/3/action/package_show?id=e5f941cd-ef4e-4498-b862-c9cdbaa0248b`
- Datos de un mes (ej. enero 2026): `https://datos.gob.cl/api/3/action/datastore_search?resource_id=347e6ed7-4667-4e95-92be-417c47cecff4`

La app detecta automáticamente los meses publicados (recursos `SD_MMAAAA`), así que se actualiza sola cuando el IPS publica un mes nuevo.

## Arquitectura

```
data_impact/
├── app.py                  # Solo la interfaz (Streamlit): filtros, pestañas, métricas
├── requirements.txt        # Dependencias con versión fija
├── README.md
├── .gitignore
├── .streamlit/config.toml  # Tema de la app
├── data/                   # Respaldo automático de la última respuesta de la API
├── src/
│   ├── api_client.py       # requests.get a la API de datos.gob.cl (paginación + respaldo)
│   ├── data_processor.py   # Limpieza con Pandas/NumPy y columnas calculadas
│   └── visualizations.py   # Funciones de gráficos (Plotly y Seaborn)
└── tools/
    └── probar_backend.py   # Prueba automática de todo el flujo (API → limpieza → app)
```

Flujo: `api_client.obtener_todos()` → JSON → `data_processor.procesar()` (json_normalize, nulos, tipos,
columnas calculadas) → `aplicar_filtros()` según la barra lateral → `visualizations.*(df_filtrado)` → `app.py`.

## Limpieza aplicada (Reto 1)

1. `json_normalize` para aplanar `result.records`.
2. Eliminación de nulos: se quitan la fila **"Total"** y la **nota al pie** que vienen dentro de la tabla, y filas inválidas.
3. Conversión de tipos: los números vienen como texto en formato chileno (`"74.600"`, `"491,667"`) → `pd.to_numeric`;
   el período de pago → `pd.to_datetime`.
4. Columnas calculadas: `monto_promedio_pesos`, `pct_mujeres`, `brecha_hombres_mujeres`,
   `participacion_nacional_pct`, `variacion_vs_promedio_pct` y `variacion_mes_anterior_pct`.
5. Validación: el total limpio coincide con la fila "Total" oficial del IPS.

## Interfaz (Retos 2, 3 y 4)

- **Barra lateral:** mes de pago, región, rango de beneficiarios por comuna y buscador de comuna. Filtran **todo**.
- **📈 Resumen Ejecutivo:** 8 `st.metric` de impacto (variación % vs mes anterior, monto promedio, % mujeres,
  participación nacional, comuna con más beneficiarios y su variación % respecto al promedio comunal) + gráfico **Plotly**.
- **🔬 Análisis Detallado:** ranking Plotly de comunas + **boxplot Seaborn** (`st.pyplot`) que reacciona a los filtros + tabla por región.
- **🗂️ Datos Crudos:** tabla procesada, **botón de descarga CSV** y los datos crudos de la API antes de limpiar.
- **📘 Metodología** dentro de un `st.expander`.

## Cómo ejecutar en local

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
Prueba automática: `python tools/probar_backend.py` (debe terminar en `TODO OK ✅`).

En Mac también puedes hacer doble clic en `1_instalar_y_probar.command` y luego en `2_ejecutar_app.command`.

## Despliegue en Streamlit Community Cloud (Reto 5)

1. Crear un repositorio **público** en GitHub (ej. `data_impact`) y subir esta carpeta:
   ```bash
   git init
   git add .
   git commit -m "DataImpact: observatorio subsidio discapacidad"
   git branch -M main
   git remote add origin https://github.com/<tu_usuario>/data_impact.git
   git push -u origin main
   ```
2. Entrar a <https://share.streamlit.io> con la cuenta de GitHub → **Create app** → *Deploy a public app from GitHub*.
3. Repository: `<tu_usuario>/data_impact` · Branch: `main` · Main file path: `app.py`.
4. En **Advanced settings** elegir la misma versión de Python usada en local (ver más abajo) → **Deploy**.
5. Copiar la URL `https://....streamlit.app` y pegarla arriba en este README.

> Para evitar el aviso *"App is sleeping"*, abrir la app unos minutos antes de presentar.

## Librerías y por qué se usan

| Librería | Uso |
|---|---|
| `requests` | Consumir la API REST de datos.gob.cl. |
| `pandas` | `json_normalize`, limpieza, conversión de tipos, agrupaciones y filtros. |
| `numpy` | Cálculos vectorizados seguros (`np.where` evita divisiones por cero). |
| `plotly` | Gráficos interactivos (hover, zoom) en el resumen y el ranking. |
| `seaborn` / `matplotlib` | Gráfico estadístico (boxplot + puntos) de la distribución por región. |
| `streamlit` | Interfaz web: pestañas, expander, métricas, filtros, descarga. |
