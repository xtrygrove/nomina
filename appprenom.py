#!/usr/bin/env python
# coding: utf-8

import streamlit as st
import pandas as pd
import re
import io

# ---------------------------------------------------
# Función para limpiar nombres de columnas
# (reemplazo de janitor.clean_names)
# ---------------------------------------------------
def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # strip, lower
    df.columns = df.columns.str.strip().str.lower()

    # reemplazar espacios y caracteres no alfanuméricos por "_"
    df.columns = [
        re.sub(r"[^0-9a-zA-Z]+", "_", col)
        for col in df.columns
    ]

    # quitar underscores repetidos y extremos
    df.columns = [re.sub(r"_+", "_", col).strip("_") for col in df.columns]
    return df


# Configurar la página
st.set_page_config(page_title='Pre_nómina', layout='wide')
st.title('Detalle de facturas para nómina')

# Sidebar: fecha de referencia
st.sidebar.header("Seleccionar fecha de nómina")
fecha_referencia = st.sidebar.date_input(
    "Selecciona la fecha de referencia",
    value=pd.to_datetime('01-01-2025', format='%d-%m-%Y')
)

# Sidebar: carga de archivos
st.sidebar.header("Carga de archivos")
file_nomina = st.sidebar.file_uploader("Subir archivo de Lista PI Acreedores", type=["xlsx"])
file_tesoreria = st.sidebar.file_uploader("Subir archivo de Tesorería", type=["xlsx"])

# Función caché para carga de archivos
@st.cache_data
def load_excel(file):
    return pd.read_excel(file)

if file_nomina and file_tesoreria:
    # Cargar archivos
    df = load_excel(file_nomina)
    df_tes = load_excel(file_tesoreria)

    # Limpiar nombres de columnas
    df = clean_column_names(df)
    df_tes = clean_column_names(df_tes.rename(columns={'Proveedor': 'cuenta'}))

    # Validar columnas obligatorias
    cols_nomina = ['cuenta', 'fecha_de_documento', 'vencimiento_neto']
    missing_cols = [col for col in cols_nomina if col not in df.columns]
    if missing_cols:
        st.error(f"Faltan columnas obligatorias en archivo de nómina: {missing_cols}")
        st.stop()

    if 'nº_documento_de_pago' not in df_tes.columns or 'importe_pagado_en_ml' not in df_tes.columns:
        st.error("El archivo de Tesorería debe tener 'nº_documento_de_pago' y 'importe_pagado_en_ml'.")
        st.stop()

    # Limpiar y filtrar nómina
    df = (
        df.astype({'cuenta': 'Int64'})
          .drop(columns=[
              'icono_part_abiertas_comp_', 'cta_contrapartida', 'nº_documento', 'asignacion',
              'simbolo_vencimiento_neto', 'moneda_del_documento', 'doc_compensacion', 'nombre_del_usuario'
          ], errors='ignore')
          .dropna(subset=['cuenta'])
          .query("bloqueo_de_pago not in ['A', 'R'] and via_de_pago != 'C'")
          .drop(columns=['bloqueo_de_pago', 'via_de_pago'], errors='ignore')
    )

    # Formatear fechas y manejar errores
    df['fecha_de_documento'] = pd.to_datetime(df['fecha_de_documento'], errors='coerce')
    df['vencimiento_neto'] = pd.to_datetime(df['vencimiento_neto'], errors='coerce')
    df = df.dropna(subset=['fecha_de_documento', 'vencimiento_neto'])

    # Calcular diferencias de días
    fecha_ref_dt = pd.to_datetime(fecha_referencia)
    df['dias_fecha_documento'] = (fecha_ref_dt - df['fecha_de_documento']).dt.days
    df['dias_vencimiento'] = (fecha_ref_dt - df['vencimiento_neto']).dt.days

    # Limpiar tesorería
    df_tes = (
        df_tes.dropna(subset=['nº_documento_de_pago'])
              .query("importe_pagado_en_ml <= -10000000")
              .sort_values(by='importe_pagado_en_ml')
              [['cuenta', 'importe_pagado_en_ml']]
    )

    # Filtrar acreedores
    lista_proveedores = df_tes['cuenta'].dropna().astype('Int64').tolist()
    df_filtered = df[df['cuenta'].isin(lista_proveedores)]

    # Mostrar resultado
    st.write("### Datos Filtrados de Acreedores")
    st.dataframe(df_filtered)

    # Generar archivo Excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for cuenta in lista_proveedores:
            df[df['cuenta'] == cuenta].to_excel(writer, sheet_name=str(cuenta), index=False)
    output.seek(0)

    # Botón de descarga
    st.download_button(
        label="Descargar Excel",
        data=output,
        file_name="total_acreedores.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.success("Archivo generado correctamente. Descárgalo arriba.")
else:
    st.info("Por favor, carga ambos archivos para generar la nómina.")
