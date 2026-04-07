#!/usr/bin/env python
# coding: utf-8

import streamlit as st
import pandas as pd
import re
import io


def clean_names(df: pd.DataFrame) -> pd.DataFrame:
    """Limpia nombres de columnas sin depender de pyjanitor."""
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    df.columns = [re.sub(r"[^0-9a-zA-Z]+", "_", col) for col in df.columns]
    df.columns = [re.sub(r"_+", "_", col).strip("_") for col in df.columns]
    return df


# --- Constantes ---
DEFAULT_REFERENCE_DATE_STR = "01-01-2026"
DATE_FORMAT = "%d-%m-%Y"
EXCEL_FILENAME = "total_acreedores.xlsx"
EXCEL_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

COLUMNS_TO_DROP_NOMINA = [
    "icono_part_abiertas_comp",
    "cta_contrapartida",
    "n_documento",
    "asignaci_n",
    "s_mbolo_vencimiento_neto",
    "moneda_del_documento",
    "doc_compensaci_n",
    "nombre_del_usuario",
]
COLUMNS_TO_DROP_NOMINA_POST_FILTER = ["bloqueo_de_pago", "v_a_de_pago"]


# --- Funciones de Carga y Limpieza de Datos ---
@st.cache_data
def load_nomina_df(uploaded_file):
    """Carga y limpia el archivo de nómina (Lista PI Acreedores)."""
    df = pd.read_excel(uploaded_file)
    df = clean_names(df)  # Limpia nombres de columnas

    # Filtrar y limpiar datos
    df = (
        df.astype({"cuenta": "Int64"})
        .drop(columns=COLUMNS_TO_DROP_NOMINA, errors="ignore")
        .dropna(subset=["cuenta"])
    )
    if "bloqueo_de_pago" in df.columns and "v_a_de_pago" in df.columns:
        df = df.query("bloqueo_de_pago != 'A' and v_a_de_pago != 'C'")
    df = df.drop(columns=COLUMNS_TO_DROP_NOMINA_POST_FILTER, errors="ignore")

    # Convertir fechas a solo date (sin hora)
    for col in ["fe_contabilizaci_n", "fecha_de_documento", "vencimiento_neto"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    return df


@st.cache_data
def load_tesoreria_df(uploaded_file):
    """Carga y limpia el archivo de Tesorería."""
    df_tes = pd.read_excel(uploaded_file)
    df_tes = df_tes.rename(columns={"Proveedor": "cuenta"})
    df_tes = clean_names(df_tes)  # Aplicar clean_names después del rename

    # Usar nombres de columna limpios por janitor
    # 'nº_documento_de_pago' -> 'n_documento_de_pago'
    # 'importe_pagado_en_ml' ya está limpio
    df_tes = (
        df_tes.dropna(subset=["n_documento_de_pago"])  # Usar nombre limpio
        .query("importe_pagado_en_ml <= -10000000")
        .sort_values(by="importe_pagado_en_ml")[["cuenta", "importe_pagado_en_ml"]]
    )
    # Asegurar que 'cuenta' en tesorería también sea Int64 para consistencia
    if "cuenta" in df_tes.columns:
        try:
            df_tes["cuenta"] = df_tes["cuenta"].astype("Int64")
        except (ValueError, TypeError):
            st.error(
                "No se pudo convertir la columna 'cuenta' de Tesorería a tipo numérico entero. Verifique que la columna 'Proveedor' contiene solo valores numéricos."
            )
            st.stop()
    return df_tes


# --- Funciones de Procesamiento ---
def process_nomina_data_dates(df_nomina_input, fecha_referencia_dt):
    """Calcula las diferencias de días y añade columnas al DataFrame de nómina."""
    df_processed = df_nomina_input.copy()

    ref_date = (
        fecha_referencia_dt.date()
        if hasattr(fecha_referencia_dt, "date")
        else fecha_referencia_dt
    )
    if "fecha_de_documento" in df_processed.columns:
        df_processed["dias_fecha_documento"] = df_processed["fecha_de_documento"].apply(
            lambda d: (ref_date - d).days if pd.notna(d) else None
        )
    if "vencimiento_neto" in df_processed.columns:
        df_processed["dias_vencimiento"] = df_processed["vencimiento_neto"].apply(
            lambda d: (ref_date - d).days if pd.notna(d) else None
        )
    return df_processed


# --- Funciones de Generación de Archivos ---
def generate_excel_bytes(df_data_for_excel, lista_cuentas_proveedores):
    """Genera un archivo Excel en memoria con una hoja por proveedor."""
    # Construir mapeo cuenta -> nombre_1
    if "nombre_1" in df_data_for_excel.columns:
        nombre_map = (
            df_data_for_excel[["cuenta", "nombre_1"]]
            .drop_duplicates("cuenta")
            .set_index("cuenta")["nombre_1"]
            .to_dict()
        )
    else:
        nombre_map = {}

    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine="xlsxwriter") as writer:
        for cuenta_proveedor in lista_cuentas_proveedores:
            df_sheet = df_data_for_excel[
                df_data_for_excel["cuenta"] == cuenta_proveedor
            ]
            if not df_sheet.empty:  # Solo crear hoja si hay datos para ese proveedor
                raw_name = str(nombre_map.get(cuenta_proveedor, cuenta_proveedor))
                sheet_name = re.sub(r"[:/\\?*\[\]]", "_", raw_name)[:31]
                df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)
    return output_buffer.getvalue()


def main():
    """Función principal de la aplicación Streamlit."""
    # --- Configuración de la Página ---
    st.set_page_config(page_title="Pre-nómina", layout="wide")
    st.title("Nómina de Acreedores")

    # --- Sidebar: Entradas del Usuario ---
    st.sidebar.header("Seleccionar fecha de nómina")
    default_date_val = pd.to_datetime(
        DEFAULT_REFERENCE_DATE_STR, format=DATE_FORMAT
    ).date()
    fecha_referencia_input = st.sidebar.date_input(
        "Selecciona la fecha de referencia", value=default_date_val
    )

    st.sidebar.header("Carga de archivos")
    file_nomina = st.sidebar.file_uploader(
        "Subir archivo de Lista PI Acreedores", type=["xlsx"]
    )
    file_tesoreria = st.sidebar.file_uploader(
        "Subir archivo de Tesorería", type=["xlsx"]
    )

    # --- Lógica Principal de Procesamiento ---
    if file_nomina and file_tesoreria:
        try:
            # Convertir fecha de referencia (datetime.date) a Timestamp de pandas para cálculos
            fecha_referencia_dt = pd.to_datetime(fecha_referencia_input)

            # Cargar DataFrames usando funciones cacheadas
            df_nomina_base = load_nomina_df(file_nomina)
            df_tesoreria = load_tesoreria_df(file_tesoreria)

            if df_nomina_base.empty or df_tesoreria.empty:
                st.warning(
                    "Uno o ambos archivos están vacíos o no se pudieron procesar correctamente. Por favor, verifique los archivos."
                )
                return  # Detener ejecución si los datos base no son válidos

            # Procesar datos de nómina (cálculo de días)
            df_nomina_con_calculos = process_nomina_data_dates(
                df_nomina_base, fecha_referencia_dt
            )

            # Obtener lista única de proveedores de tesorería
            lista_proveedores_tesoreria = df_tesoreria["cuenta"].unique().tolist()

            # Filtrar DataFrame de nómina para mostrar en la UI
            df_nomina_filtrada_display = df_nomina_con_calculos[
                df_nomina_con_calculos["cuenta"].isin(lista_proveedores_tesoreria)
            ]

            # Mostrar datos filtrados
            st.write("### Datos Filtrados de Acreedores")
            st.dataframe(df_nomina_filtrada_display)

            # Generar y descargar archivo Excel
            # El Excel se genera a partir de df_nomina_con_calculos y usa la lista de proveedores de tesorería.
            excel_bytes = generate_excel_bytes(
                df_nomina_con_calculos, lista_proveedores_tesoreria
            )

            if excel_bytes:  # Solo mostrar botón si se generó contenido
                st.download_button(
                    label="Descargar Excel",
                    data=excel_bytes,
                    file_name=EXCEL_FILENAME,
                    mime=EXCEL_MIME_TYPE,
                )
            else:
                st.info(
                    "No se generaron datos para el archivo Excel (posiblemente no hay proveedores comunes o datos para ellos)."
                )

        except Exception as e:
            st.error(f"Ocurrió un error durante el procesamiento: {e}")
            st.error(
                "Por favor, revise los archivos subidos y asegúrese de que tengan el formato y las columnas esperadas."
            )
            # Para depuración, podrías añadir:
            # import traceback
            # st.error(traceback.format_exc())

    else:
        st.info(
            "Por favor, carga ambos archivos ('Lista PI Acreedores' y 'Tesorería') para continuar."
        )


if __name__ == "__main__":
    main()
