#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import streamlit as st
import pandas as pd
from janitor import clean_names

# Configurar la página
st.set_page_config(page_title='Pre_nomina', layout='wide')
st.title('Detalle de facturas para nómina')

# Seleccionar fecha
st.sidebar.header("Seleccionar fecha de nómina")
fecha_referencia = st.sidebar.date_input("Selecciona la fecha de referencia", value=pd.to_datetime('01-01-2025', format='%d-%m-%Y'))

# Cargar archivos
st.sidebar.header("Carga de archivos")
file_nomina = st.sidebar.file_uploader("Subir archivo de Lista PI Acreedores", type=["xlsx"])
file_tesoreria = st.sidebar.file_uploader("Subir archivo de Tesorería", type=["xlsx"])

if file_nomina and file_tesoreria:
    # Cargar y limpiar el archivo de nómina
    df = pd.read_excel(file_nomina)
    df = clean_names(df)
    
    # Filtrar y limpiar datos
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
    
    # Formatear fechas
    df['fecha_de_documento'] = pd.to_datetime(df['fecha_de_documento']).dt.strftime('%d-%m-%Y')
    df['vencimiento_neto'] = pd.to_datetime(df['vencimiento_neto']).dt.strftime('%d-%m-%Y')
    
    # Calcular diferencias de días con la fecha seleccionada por el usuario
    fecha_referencia = pd.to_datetime(fecha_referencia)  # Convertir a datetime
    df['dias_fecha_documento'] = (fecha_referencia - pd.to_datetime(df['fecha_de_documento'], format='%d-%m-%Y')).dt.days
    df['dias_vencimiento'] = (fecha_referencia - pd.to_datetime(df['vencimiento_neto'], format='%d-%m-%Y')).dt.days
    
    # Cargar y limpiar el archivo de tesorería
    df_tes = pd.read_excel(file_tesoreria)
    df_tes = (
        df_tes.rename(columns={'Proveedor': 'cuenta'})
              .pipe(clean_names)
              .dropna(subset='nº_documento_de_pago')
              .query("importe_pagado_en_ml <= -10000000")
              .sort_values(by='importe_pagado_en_ml')
              [['cuenta', 'importe_pagado_en_ml']]
    )
    
    # Filtrar el DataFrame de nómina con los proveedores de tesorería
    lista_proveedores = df_tes['cuenta'].tolist()
    df_filtered = df[df['cuenta'].isin(lista_proveedores)]
    
    # Mostrar los datos filtrados
    st.write("### Datos Filtrados de Acreedores")
    st.dataframe(df_filtered)
    
    # Crear y descargar el archivo Excel
    with pd.ExcelWriter('total_acreedores.xlsx', engine='xlsxwriter') as writer:
        for cuenta in lista_proveedores:
            df[df['cuenta'] == cuenta].to_excel(writer, sheet_name=str(cuenta), index=False)
    
    with open('total_acreedores.xlsx', 'rb') as f:
        st.download_button(
            label="Descargar Excel",
            data=f,
            file_name="total_acreedores.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

