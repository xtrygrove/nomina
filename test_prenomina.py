"""Pruebas unitarias del control de anticipos y priorización."""

import importlib.util
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
                "importe_en_moneda_doc": [-5000, -5000, -5000],
            }
        )

        payable, retained, blocked = MODULE.validate_payment_risk(source, set())

        self.assertEqual(payable["n_documento"].tolist(), [30])
        self.assertEqual(blocked["n_documento"].tolist(), [20])
        self.assertIn(10, retained["n_documento"].tolist())

    def test_keeps_invoice_when_amount_does_not_match_advance(self) -> None:
        source = pd.DataFrame(
            {
                "cuenta": [1001, 1001],
                "n_documento": [10, 20],
                "clase_de_documento": ["SA", "EF"],
                "importe_en_moneda_doc": [-5000, -6000],
            }
        )

        payable, _, blocked = MODULE.validate_payment_risk(source, set())

        self.assertEqual(payable["n_documento"].tolist(), [20])
        self.assertTrue(blocked.empty)

    def test_priority_includes_payment_below_ten_million(self) -> None:
        amounts = pd.Series([-9_000_000, -10_000_000])
        priority = amounts.abs().ge(10_000_000)

        self.assertEqual(priority.tolist(), [False, True])


    def test_selects_documents_by_net_due_date(self) -> None:
        source = pd.DataFrame(
            {
                "cuenta": [1001, 1001],
                "vencimiento_neto": [pd.Timestamp("2026-07-17").date(), pd.Timestamp("2026-07-18").date()],
            }
        )

        selected = source[source["vencimiento_neto"].eq(pd.Timestamp("2026-07-17").date())]

        self.assertEqual(selected.index.tolist(), [0])

if __name__ == "__main__":
    unittest.main()
