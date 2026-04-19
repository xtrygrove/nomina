# Nómina de Acreedores — Pre-nómina de Pago a Proveedores

Aplicación web desarrollada con **Streamlit** para generar la pre-nómina de pago a proveedores (acreedores), cruzando datos del reporte de partidas abiertas con el reporte de Tesorería.

## Descripción

El proceso consiste en:

1. Cargar el archivo **Lista PI Acreedores** con las partidas abiertas de proveedores.
2. Cargar el archivo de **Tesorería** con los pagos realizados.
3. La aplicación filtra, cruza y calcula los días de antigüedad de cada documento respecto a una fecha de referencia.
4. Se puede visualizar el resultado en pantalla y descargar un **Excel** con una hoja por proveedor.

## Estructura del Proyecto

```
nomina/
├── prenomina streamlit.py   # Aplicación principal Streamlit
├── appprenom.py             # Script auxiliar de procesamiento
├── requirements.txt         # Dependencias del proyecto
└── README.md                # Este archivo
```

## Requisitos

- Python 3.9+
- Las dependencias listadas en `requirements.txt`:

```
streamlit
pandas
xlsxwriter
openpyxl
```

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
streamlit run "prenomina streamlit.py"
```

Luego en el navegador:

1. En el panel lateral, selecciona la **fecha de referencia** para el cálculo de días.
2. Sube el archivo **Lista PI Acreedores** (`.xlsx`).
3. Sube el archivo de **Tesorería** (`.xlsx`).
4. Visualiza la tabla filtrada y descarga el Excel con el botón **Descargar Excel**.

## Archivos de Entrada Esperados

### Lista PI Acreedores
Columnas requeridas (después de limpieza de nombres):

| Columna | Descripción |
|---|---|
| `cuenta` | Código de proveedor |
| `nombre_1` | Nombre del proveedor |
| `fecha_de_documento` | Fecha del documento contable |
| `vencimiento_neto` | Fecha de vencimiento neto |
| `bloqueo_de_pago` | Indicador de bloqueo (se excluye valor `A`) |
| `v_a_de_pago` | Vía de pago (se excluye valor `C`) |

### Tesorería
Columnas requeridas:

| Columna original | Columna limpia | Descripción |
|---|---|---|
| `Proveedor` | `cuenta` | Código de proveedor |
| `Nº Documento de Pago` | `n_documento_de_pago` | Número de documento |
| `Importe Pagado en ML` | `importe_pagado_en_ml` | Importe pagado (filtra ≤ -10.000.000) |

## Salida

- **Pantalla:** tabla con los acreedores que aparecen en Tesorería, con columnas adicionales `dias_fecha_documento` y `dias_vencimiento`.
- **Excel (`total_acreedores.xlsx`):** una hoja por proveedor, con el nombre del proveedor como nombre de hoja.
