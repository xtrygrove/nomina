# Nómina semanal de pagos

Aplicación Streamlit para validar la nómina de pagos semanal de Tesorería contra la Lista PI de Acreedores antes de su liberación.

## Flujo operativo

1. Carga la nómina de pagos enviada por Tesorería para el viernes correspondiente.
2. La aplicación toma sus proveedores como universo de pago.
3. Incluye partidas con `Vencimiento neto` menor o igual a la fecha de nómina seleccionada: vencidas y con vencimiento hasta el viernes de pago.
4. Consulta posibles anticipos `AB`/`SA` del proveedor, aun cuando tengan otra fecha.
5. Ejecuta controles de duplicidad, notas y anticipos.
5. Exporta el detalle validado por proveedor.

## Elegibilidad de documentos

La Lista PI es el universo de documentos abiertos de SAP. Una partida puede entrar a la nómina sólo si:

- no tiene `Bloqueo de pago = A`;
- no tiene `Vía de pago = C`; y
- su `Vencimiento neto` es menor o igual a la fecha de nómina.

## Prioridad y exportación

Los pagos por un importe absoluto igual o superior a $10.000.000 se marcan como prioritarios y se ordenan primero. Esta regla no excluye pagos menores de la revisión.

El Excel descargable incluye una hoja sólo para los acreedores cuyo total de documentos aptos alcanza un importe absoluto igual o superior a $10.000.000.

## Control preventivo de anticipos

Los importes negativos representan deuda de la empresa hacia el proveedor.

- `EC` y `ED`: se excluyen de la propuesta.
- `AB` y `SA`: se retienen para revisión como posibles anticipos o documentos contables.
- Para cada `AB`/`SA`, la aplicación busca una factura propuesta del mismo proveedor con el mismo importe absoluto.
- Ante una coincidencia exacta, bloquea la factura y muestra el número del documento SAP relacionado.
- Las clases de documento de pagos ya registrados se pueden configurar desde la barra lateral.
- Una referencia que contiene `FACTORING` identifica una factura cedida a la cuenta de factoring correspondiente. Se informa, pero no se excluye automáticamente.

## Ejecución

```bash
pip install -r requirements.txt
streamlit run "prenomina streamlit.py"
```

## Requisitos

- Python 3.10 o superior
- streamlit
- pandas
- openpyxl
- xlsxwriter
