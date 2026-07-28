"""Pruebas unitarias del control de anticipos y priorización."""

import importlib.util
import io
from pathlib import Path
import unittest

import pandas as pd


MODULE_PATH = Path(__file__).with_name("prenomina streamlit.py")
SPEC = importlib.util.spec_from_file_location("prenomina_streamlit", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PaymentRiskTests(unittest.TestCase):
    def test_blocks_invoice_with_same_supplier_and_absolute_amount(self) -> None:
        source = pd.DataFrame(
            {
                "cuenta": [1001, 1001, 1002],
                "n_documento": [10, 20, 30],
                "clase_de_documento": ["AB", "EF", "EF"],
                # El AB va en positivo: es un anticipo ya contabilizado (pagado).
                "importe_en_moneda_doc": [5000, -5000, -5000],
            }
        )

        payable, retained, blocked = MODULE.validate_payment_risk(source)

        self.assertEqual(payable["n_documento"].tolist(), [30])
        self.assertEqual(blocked["n_documento"].tolist(), [20])
        self.assertIn(10, retained["n_documento"].tolist())

    def test_negative_sign_advance_does_not_block_payment(self) -> None:
        """Un AB/SA en negativo no acredita un anticipo ya pagado."""
        source = pd.DataFrame(
            {
                "cuenta": [1001, 1001],
                "n_documento": [10, 20],
                "clase_de_documento": ["AB", "EF"],
                "importe_en_moneda_doc": [-5000, -5000],
            }
        )

        payable, _, blocked = MODULE.validate_payment_risk(source)

        self.assertEqual(payable["n_documento"].tolist(), [10, 20])
        self.assertTrue(blocked.empty)

    def test_keeps_invoice_when_amount_does_not_match_advance(self) -> None:
        source = pd.DataFrame(
            {
                "cuenta": [1001, 1001],
                "n_documento": [10, 20],
                "clase_de_documento": ["SA", "EF"],
                "importe_en_moneda_doc": [-5000, -6000],
            }
        )

        payable, _, blocked = MODULE.validate_payment_risk(source)

        self.assertEqual(payable["n_documento"].tolist(), [10, 20])
        self.assertTrue(blocked.empty)

    def test_priority_includes_payment_below_ten_million(self) -> None:
        amounts = pd.Series([-9_000_000, -10_000_000])
        priority = amounts.abs().ge(10_000_000)

        self.assertEqual(priority.tolist(), [False, True])


    def test_excludes_blocked_and_payment_method_c_documents(self) -> None:
        source = pd.DataFrame(
            {
                "bloqueo_de_pago": ["", "A", "", None],
                "v_a_de_pago": ["", "", "C", None],
            }
        )

        eligible = MODULE.filter_eligible_payment_documents(source)

        self.assertEqual(eligible.index.tolist(), [0, 3])

    def test_includes_documents_due_on_or_before_payroll_date(self) -> None:
        source = pd.DataFrame(
            {
                "vencimiento_neto": [
                    pd.Timestamp("2026-07-14").date(),
                    pd.Timestamp("2026-07-17").date(),
                    pd.Timestamp("2026-07-18").date(),
                ]
            }
        )

        selected = source[
            source["vencimiento_neto"].le(pd.Timestamp("2026-07-17").date())
        ]

        self.assertEqual(selected.index.tolist(), [0, 1])

    def test_exports_only_creditors_with_total_at_least_ten_million(self) -> None:
        source = pd.DataFrame(
            {
                "cuenta": [1001, 1001, 1002],
                "importe_en_moneda_doc": [-6_000_000, -4_000_000, -9_999_999],
            }
        )

        exportable = MODULE.get_exportable_creditors(source)

        self.assertEqual(exportable, [1001])

    def test_marks_factoring_references_without_excluding_them(self) -> None:
        source = pd.DataFrame({"referencia": ["FACTORING CESION", "Factura normal"]})

        marked = MODULE.mark_factoring_references(source)

        self.assertEqual(marked["referencia_factoring"].tolist(), [True, False])

    def test_export_sheets_follow_payment_total_order(self) -> None:
        payroll_documents = pd.DataFrame(
            {
                "cuenta": [1001, 1002, 1001, 1003],
                "nombre_1": ["Bosch", "Logística", "Bosch", "Menor"],
                "importe_en_moneda_doc": [-7_000_000, -20_000_000, -4_000_000, -9_000_000],
            }
        )

        exportable = MODULE.get_exportable_creditors(payroll_documents)
        excel_bytes = MODULE.generate_excel_bytes(payroll_documents, exportable)

        self.assertEqual(exportable, [1002, 1001])
        self.assertEqual(
            pd.ExcelFile(io.BytesIO(excel_bytes)).sheet_names,
            ["Logística", "Bosch"],
        )

    def test_future_advance_blocks_matching_payroll_invoice(self) -> None:
        payroll = pd.DataFrame(
            {
                "cuenta": [1001],
                "n_documento": [20],
                "clase_de_documento": ["EF"],
                "importe_en_moneda_doc": [-5_000],
            }
        )
        advances = pd.DataFrame(
            {
                "cuenta": [1001],
                "n_documento": [10],
                "clase_de_documento": ["AB"],
                # Positivo: anticipo ya contabilizado (pagado) contra el acreedor.
                "importe_en_moneda_doc": [5_000],
            }
        )

        payable, _, blocked = MODULE.validate_payment_risk(
            payroll,
            advance_source=advances,
        )

        self.assertTrue(payable.empty)
        self.assertEqual(blocked["n_documento"].tolist(), [20])


    def test_export_omits_internal_control_columns(self) -> None:
        source = pd.DataFrame(
            {
                "cuenta": [1001],
                "nombre_1": ["Proveedor"],
                "importe_en_moneda_doc": [-10_000_000],
                "referencia_factoring": [False],
                "monto_comparacion": [10_000_000],
                "es_anticipo_potencial": [False],
                "estado_validacion": ["APTO_PARA_CRUCE"],
                "documentos_anticipo_relacionados": [""],
            }
        )

        excel_bytes = MODULE.generate_excel_bytes(source, [1001])
        exported = pd.read_excel(io.BytesIO(excel_bytes))

        self.assertTrue(
            set(MODULE.EXPORT_COLUMNS_TO_EXCLUDE).isdisjoint(exported.columns)
        )

if __name__ == "__main__":
    unittest.main()
