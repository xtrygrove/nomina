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
    "asignaci_n",
    "s_mbolo_vencimiento_neto",
    "moneda_del_documento",
    "doc_compensaci_n",
    "nombre_del_usuario",
]
COLUMNS_TO_DROP_NOMINA_POST_FILTER = ["bloqueo_de_pago", "v_a_de_pago"]

# Control preventivo de pagos duplicados por anticipos.
DOCUMENT_TYPE_COLUMN_CANDIDATES = (
    "clase_de_documento", "tipo_de_documento", "clase_documento", "tipo_documento",
)
PAYMENT_DOCUMENT_TYPES = frozenset({"KZ", "ZP"})
CREDIT_DEBIT_NOTE_DOCUMENT_TYPES = frozenset({"EC", "ED"})
GENERIC_ACCOUNTING_DOCUMENT_TYPES = frozenset({"AB", "SA"})


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
    df_tes = df_tes.dropna(subset=["n_documento_de_pago"]).copy()
    df_tes["importe_pagado_en_ml"] = pd.to_numeric(
        df_tes["importe_pagado_en_ml"], errors="coerce"
    )
    df_tes = df_tes.dropna(subset=["importe_pagado_en_ml"])
    # Los $10 MM son prioridad de revisión, no un filtro de exclusión.
    df_tes["prioridad_monto"] = df_tes["importe_pagado_en_ml"].abs().ge(10_000_000)
    df_tes = df_tes.sort_values(
        by=["prioridad_monto", "importe_pagado_en_ml"],
        ascending=[False, True],
    )[["cuenta", "importe_pagado_en_ml", "prioridad_monto"]]
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
def get_document_type_column(df: pd.DataFrame) -> str:
    """Obtiene la columna SAP que contiene la clase de documento."""
    for column in DOCUMENT_TYPE_COLUMN_CANDIDATES:
        if column in df.columns:
            return column
    raise ValueError("No se encontró la columna de clase de documento SAP.")


def get_amount_column(df: pd.DataFrame) -> str:
    """Obtiene la columna de importe de la Lista PI."""
    candidates = [column for column in df.columns if column.startswith("importe_en_moneda")]
    if len(candidates) != 1:
        raise ValueError("No se pudo identificar de forma unívoca la columna de importe.")
    return candidates[0]


def validate_payment_risk(
    df_nomina: pd.DataFrame,
    payment_document_types: set[str] | frozenset[str] = PAYMENT_DOCUMENT_TYPES,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Bloquea facturas duplicadas por anticipos del mismo proveedor e importe."""
    document_type_column = get_document_type_column(df_nomina)
    amount_column = get_amount_column(df_nomina)
    validated_df = df_nomina.copy()
    validated_df["clase_documento_sap"] = (
        validated_df[document_type_column].fillna("").astype(str).str.strip().str.upper()
    )
    validated_df["monto_comparacion"] = (
        pd.to_numeric(validated_df[amount_column], errors="coerce").abs().round(0)
    )
    payment_types = {item.strip().upper() for item in payment_document_types if item.strip()}
    generic_mask = validated_df["clase_documento_sap"].isin(GENERIC_ACCOUNTING_DOCUMENT_TYPES)
    validated_df["estado_validacion"] = "APTO_PARA_CRUCE"
    validated_df.loc[
        validated_df["clase_documento_sap"].isin(payment_types | CREDIT_DEBIT_NOTE_DOCUMENT_TYPES),
        "estado_validacion",
    ] = "EXCLUIDO_RIESGO_DUPLICIDAD"
    validated_df.loc[generic_mask, "estado_validacion"] = "RETENIDO_REVISION_ANTICIPO"
    validated_df["documentos_anticipo_relacionados"] = ""

    advances = validated_df[generic_mask].copy()
    invoices = validated_df[validated_df["estado_validacion"].eq("APTO_PARA_CRUCE")].copy()
    advances["indice_anticipo"] = advances.index
    invoices["indice_factura"] = invoices.index
    matches = advances.merge(
        invoices, on=["cuenta", "monto_comparacion"], how="inner",
        suffixes=("_anticipo", "_factura"),
    )
    if not matches.empty:
        advance_references = (
            matches.groupby("indice_factura")["n_documento_anticipo"]
            .apply(lambda docs: ", ".join(sorted({str(doc) for doc in docs})))
            .to_dict()
        )
        validated_df.loc[
            validated_df.index.isin(matches["indice_anticipo"]), "estado_validacion"
        ] = "ANTICIPO_COINCIDE_FACTURA"
        validated_df.loc[
            validated_df.index.isin(advance_references), "estado_validacion"
        ] = "BLOQUEADO_COINCIDENCIA_ANTICIPO"
        for invoice_index, references in advance_references.items():
            validated_df.loc[
                invoice_index, "documentos_anticipo_relacionados"
            ] = references

    retained_df = validated_df[validated_df["estado_validacion"].ne("APTO_PARA_CRUCE")].copy()
    blocked_invoices_df = validated_df[
        validated_df["estado_validacion"].eq("BLOQUEADO_COINCIDENCIA_ANTICIPO")
    ].copy()
    payable_df = validated_df[validated_df["estado_validacion"].eq("APTO_PARA_CRUCE")].copy()
    return payable_df, retained_df, blocked_invoices_df
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

            payment_types_input = st.sidebar.text_input(
                "Clases SAP de pago ya registrado",
                value=", ".join(sorted(PAYMENT_DOCUMENT_TYPES)),
                help="Confirma estos códigos con la parametrización SAP local.",
            )
            payment_types = {
                item.strip().upper() for item in payment_types_input.split(",") if item.strip()
            }
            # La nómina de Tesorería define el universo real a validar.
            lista_proveedores_tesoreria = df_tesoreria["cuenta"].unique().tolist()
            df_nomina_propuesta = df_nomina_base[
                df_nomina_base["cuenta"].isin(lista_proveedores_tesoreria)
            ].copy()
            if df_nomina_propuesta.empty:
                st.warning(
                    "No se encontraron partidas abiertas en Lista PI para los "
                    "proveedores incluidos en la nómina de Tesorería."
                )
                return

            df_nomina_validada, df_documentos_retenidos, df_facturas_bloqueadas = (
                validate_payment_risk(df_nomina_propuesta, payment_types)
            )

            st.write("### Control preventivo de duplicidad")
            if df_facturas_bloqueadas.empty:
                st.success(
                    "No se detectaron facturas con coincidencia exacta de proveedor "
                    "e importe contra documentos AB/SA."
                )
            else:
                st.error(
                    f"Se bloquearon {len(df_facturas_bloqueadas):,} facturas por "
                    "coincidir con un anticipo AB/SA del mismo proveedor."
                )
                st.dataframe(df_facturas_bloqueadas, use_container_width=True, hide_index=True)
            if not df_documentos_retenidos.empty:
                st.warning(
                    f"Se retuvieron {len(df_documentos_retenidos):,} documentos "
                    "antes del cruce. Revísalos antes de liberar pagos."
                )
                st.dataframe(df_documentos_retenidos, use_container_width=True, hide_index=True)

            # Procesar solamente documentos aptos para pago.
            df_nomina_con_calculos = process_nomina_data_dates(
                df_nomina_validada, fecha_referencia_dt
            )

            st.caption(
                "La nómina semanal de Tesorería es la base del proceso. "
                "Los pagos iguales o superiores a $10 MM se marcan como prioritarios."
            )
            st.metric(
                "Pagos prioritarios (≥ $10 MM)",
                int(df_tesoreria["prioridad_monto"].sum()),
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
