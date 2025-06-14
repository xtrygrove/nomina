#!/usr/bin/env python
# coding: utf-8

import streamlit as st
import pandas as pd
from janitor import clean_names
import warnings
import io # Para manejar bytes en memoria

# Ignorar advertencias (usar con precaución, idealmente se deberían abordar las advertencias específicas)
warnings.filterwarnings(action='ignore')

# --- Constantes ---
DEFAULT_REFERENCE_DATE_STR = '01-01-2025'
DATE_FORMAT = '%d-%m-%Y'
EXCEL_FILENAME = "total_acreedores.xlsx"
EXCEL_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

COLUMNS_TO_DROP_NOMINA = [
    'icono_part_abiertas_comp_', 'cta_contrapartida', 'nº_documento', 'asignacion',
    'simbolo_vencimiento_neto', 'moneda_del_documento', 'doc_compensacion', 'nombre_del_usuario'
]
COLUMNS_TO_DROP_NOMINA_POST_FILTER = ['bloqueo_de_pago', 'via_de_pago']

# --- Funciones de Carga y Limpieza de Datos ---
@st.cache_data # Cache para mejorar rendimiento
def load_nomina_df(uploaded_file):
    """Carga y limpia el archivo de nómina."""
    df = pd.read_excel(uploaded_file)
    df = clean_names(df)
    df = (
        df.astype({'cuenta': 'Int64'})
          .drop(columns=COLUMNS_TO_DROP_NOMINA, errors='ignore')
          .dropna(subset=['cuenta'])
          .query("bloqueo_de_pago != 'A' and via_de_pago != 'C'")
          .drop(columns=COLUMNS_TO_DROP_NOMINA_POST_FILTER, errors='ignore')
    )
    # Formatear fechas a string después de las operaciones necesarias
    df['fecha_de_documento'] = pd.to_datetime(df['fecha_de_documento']).dt.strftime(DATE_FORMAT)
    df['vencimiento_neto'] = pd.to_datetime(df['vencimiento_neto']).dt.strftime(DATE_FORMAT)
    return df

@st.cache_data # Cache para mejorar rendimiento
def load_tesoreria_df(uploaded_file):
    """Carga y limpia el archivo de tesorería."""
    df_tes = pd.read_excel(uploaded_file)
    df_tes = (
        df_tes.rename(columns={'Proveedor': 'cuenta'})
              .pipe(clean_names) # Aplicar clean_names después del rename
              .dropna(subset=['nº_documento_de_pago']) # Usar el nombre limpio si clean_names lo afecta
              .query("importe_pagado_en_ml <= -10000000") # Usar el nombre limpio
              .sort_values(by='importe_pagado_en_ml') # Usar el nombre limpio
              [['cuenta', 'importe_pagado_en_ml']] # Usar nombres limpios
    )
    # Asegurarse que 'cuenta' en tesorería también sea Int64 para consistencia
    if 'cuenta' in df_tes.columns:
        try:
            df_tes['cuenta'] = df_tes['cuenta'].astype('Int64')
        except (ValueError, TypeError):
            st.warning("No se pudo convertir la columna 'cuenta' de Tesorería a tipo numérico entero.")
            # Podrías manejar este caso de otra forma, ej. tratando de limpiar los datos
    return df_tes

# --- Funciones de Procesamiento ---
def process_nomina_data_dates(df_nomina_input, fecha_referencia_dt):
    """Calcula las diferencias de días y añade columnas al DataFrame de nómina."""
    df_processed = df_nomina_input.copy()
    # Las fechas en df_nomina_input ya están como strings formateadas
    df_processed['dias_fecha_documento'] = (
        fecha_referencia_dt - pd.to_datetime(df_processed['fecha_de_documento'], format=DATE_FORMAT)
    ).dt.days
    df_processed['dias_vencimiento'] = (
        fecha_referencia_dt - pd.to_datetime(df_processed['vencimiento_neto'], format=DATE_FORMAT)
    ).dt.days
    return df_processed

# --- Funciones de Generación de Archivos ---
def generate_excel_bytes(df_nomina_base, lista_cuentas_proveedores):
    """Genera un archivo Excel en memoria con una hoja por proveedor."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for cuenta_proveedor in lista_cuentas_proveedores:
            df_sheet = df_nomina_base[df_nomina_base['cuenta'] == cuenta_proveedor]
            # No es necesario el check de df_sheet.empty para mantener comportamiento original
            df_sheet.to_excel(writer, sheet_name=str(cuenta_proveedor), index=False)
    return output.getvalue()

def main():
    """Función principal de la aplicación Streamlit."""
    # --- Configuración de la Página ---
    st.set_page_config(page_title='Pre-nómina', layout='wide')
    st.title('Nómina de Acreedores')

    # --- Sidebar: Entradas del Usuario ---
    st.sidebar.header("Seleccionar fecha de nómina")
    default_date_val = pd.to_datetime(DEFAULT_REFERENCE_DATE_STR, format=DATE_FORMAT).date()
    fecha_referencia_input = st.sidebar.date_input(
        "Selecciona la fecha de referencia", 
        value=default_date_val
    )

    st.sidebar.header("Carga de archivos")
    file_nomina = st.sidebar.file_uploader("Subir archivo de Lista PI Acreedores", type=["xlsx"])
    file_tesoreria = st.sidebar.file_uploader("Subir archivo de Tesorería", type=["xlsx"])

    # --- Lógica Principal de Procesamiento ---
    if file_nomina and file_tesoreria:
        try:
            # Convertir fecha de referencia a Timestamp de pandas para cálculos
            fecha_referencia_dt = pd.to_datetime(fecha_referencia_input)

            # Cargar DataFrames usando funciones cacheadas
            df_nomina_base = load_nomina_df(file_nomina)
            df_tesoreria = load_tesoreria_df(file_tesoreria)

            if df_nomina_base.empty or df_tesoreria.empty:
                st.warning("Uno o ambos archivos están vacíos o no se pudieron procesar correctamente.")
                return

            # Procesar datos de nómina (cálculo de días)
            df_nomina_con_calculos = process_nomina_data_dates(df_nomina_base, fecha_referencia_dt)

            # Obtener lista de proveedores de tesorería (asegurando unicidad)
            lista_proveedores_tesoreria = df_tesoreria['cuenta'].unique().tolist()

            # Filtrar DataFrame de nómina para mostrar
            df_nomina_filtrada_display = df_nomina_con_calculos[
                df_nomina_con_calculos['cuenta'].isin(lista_proveedores_tesoreria)
            ]

            # Mostrar datos filtrados
            st.write("### Datos Filtrados de Acreedores")
            st.dataframe(df_nomina_filtrada_display)

            # Generar y descargar archivo Excel
            # El Excel se genera a partir de df_nomina_base (antes de añadir columnas de días)
            # y usa la lista de proveedores de tesorería para las hojas.
            excel_bytes = generate_excel_bytes(df_nomina_base, lista_proveedores_tesoreria)
            
            st.download_button(
                label="Descargar Excel",
                data=excel_bytes,
                file_name=EXCEL_FILENAME,
                mime=EXCEL_MIME_TYPE
            )
        
        except Exception as e:
            st.error(f"Ocurrió un error durante el procesamiento: {e}")
            st.error("Por favor, verifica los archivos subidos y los formatos esperados.")

    else:
        st.info("Por favor, carga ambos archivos para continuar.")

if __name__ == "__main__":
    main()
