"""Teste pentru registrul financiar si calculele de profitabilitate."""
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import server
from adapters.storage.db_adapter import DBAdapter
from adapters.storage.json_adapter import JSONAdapter
from core.finance import build_finance_report, normalize_transaction


def transaction(**changes) -> dict:
    base = {
        "id": "tx_1",
        "product_id": "prod_1",
        "kind": "purchase",
        "quantity": 1,
        "unit_price": 100,
        "vat_rate": 20,
        "vat_included": False,
        "vat_deductible": False,
        "occurred_at": "2026-01-01",
        "note": "",
        "created_at": "2026-01-01T10:00:00+00:00",
    }
    return base | changes


class BarrierJSONAdapter(JSONAdapter):
    """Adaptor de test care sincronizeaza doua citiri la aceeasi granita."""

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        self.audit_barrier: threading.Barrier | None = None
        self.barrier_on_filtered = False

    def get_finance_transactions(self, product_id: str | None = None) -> list:
        snapshot = super().get_finance_transactions(product_id)
        should_wait = self.audit_barrier is not None and (
            (self.barrier_on_filtered and product_id is not None)
            or (not self.barrier_on_filtered and product_id is None)
        )
        if should_wait:
            try:
                self.audit_barrier.wait(timeout=0.2)
            except threading.BrokenBarrierError:
                pass
        return snapshot


class FinanceCalculationTests(unittest.TestCase):
    def test_balances_profit_stock_and_sell_through(self) -> None:
        products = [{
            "id": "prod_1",
            "title": "Telefon",
            "price": 220,
            "currency": "RON",
            "vat": {"included": False, "deductible": False, "rate": 20},
        }]
        transactions = [
            transaction(
                id="buy",
                quantity=10,
                unit_price=120,
                vat_included=True,
                vat_deductible=True,
            ),
            transaction(
                id="sell",
                kind="sale",
                quantity=4,
                unit_price=200,
                occurred_at="2026-01-11",
            ),
            transaction(
                id="cost",
                kind="expense",
                unit_price=50,
                occurred_at="2026-01-02",
            ),
        ]

        report = build_finance_report(products, transactions)
        item = report["products"][0]

        self.assertEqual(item["purchase_cost"], 1000)
        self.assertEqual(item["sales_revenue"], 800)
        self.assertEqual(item["additional_costs"], 50)
        self.assertEqual(item["stock_quantity"], 6)
        self.assertEqual(item["sell_through_rate"], 40)
        self.assertEqual(item["inventory_value"], 600)
        self.assertEqual(item["realized_profit"], 350)
        self.assertEqual(item["cash_balance"], -250)
        self.assertEqual(item["projected_profit"], 1070)
        self.assertEqual(item["recoverable_vat"], 200)
        self.assertEqual(item["average_days_to_sale"], 10)

    def test_nondeductible_vat_stays_in_purchase_cost(self) -> None:
        products = [{"id": "prod_1", "title": "Produs", "price": 0}]
        report = build_finance_report(
            products,
            [transaction(vat_included=True, vat_deductible=False)],
        )

        self.assertEqual(report["products"][0]["purchase_cost"], 100)
        self.assertEqual(report["products"][0]["recoverable_vat"], 0)

    def test_invalid_transaction_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Cantitatea"):
            normalize_transaction(transaction(quantity=0))

    def test_later_purchase_does_not_change_realized_profit(self) -> None:
        product = {
            "id": "prod_1",
            "title": "Produs",
            "price": 1200,
            "currency": "RON",
            "vat": {},
        }
        before = build_finance_report(
            [product],
            [
                transaction(id="buy_1", unit_price=100),
                transaction(
                    id="sale_1",
                    kind="sale",
                    unit_price=200,
                    occurred_at="2026-01-02",
                ),
            ],
        )["products"][0]
        after = build_finance_report(
            [product],
            [
                transaction(id="buy_1", unit_price=100),
                transaction(
                    id="sale_1",
                    kind="sale",
                    unit_price=200,
                    occurred_at="2026-01-02",
                ),
                transaction(
                    id="buy_2",
                    unit_price=1000,
                    occurred_at="2026-02-01",
                ),
            ],
        )["products"][0]

        self.assertEqual(before["realized_profit"], 100)
        self.assertEqual(after["realized_profit"], 100)
        self.assertEqual(after["inventory_value"], 1000)

    def test_mixed_currencies_have_separate_summaries(self) -> None:
        products = [
            {"id": "prod_1", "title": "Lei", "price": 100, "currency": "RON"},
            {"id": "prod_2", "title": "Euro", "price": 100, "currency": "EUR"},
        ]
        report = build_finance_report(
            products,
            [
                transaction(id="ron", product_id="prod_1"),
                transaction(id="eur", product_id="prod_2"),
            ],
        )

        self.assertTrue(report["summary"]["mixed_currencies"])
        self.assertIsNone(report["summary"]["invested"])
        by_currency = {
            item["currency"]: item for item in report["currency_summaries"]
        }
        self.assertEqual(by_currency["RON"]["invested"], 100)
        self.assertEqual(by_currency["EUR"]["invested"], 100)


class FinanceJSONStorageTests(unittest.TestCase):
    def test_transactions_round_trip_and_delete(self) -> None:
        storage = JSONAdapter(Path(tempfile.mkdtemp()))
        saved = storage.save_finance_transaction(transaction())

        self.assertEqual(storage.get_finance_transactions(), [saved])
        storage.delete_finance_transaction(saved["id"])
        self.assertEqual(storage.get_finance_transactions(), [])

    def test_concurrent_writes_keep_both_transactions(self) -> None:
        storage = BarrierJSONAdapter(Path(tempfile.mkdtemp()))
        storage.audit_barrier = threading.Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(
                pool.map(
                    storage.save_finance_transaction,
                    [transaction(id="tx_1"), transaction(id="tx_2")],
                )
            )
        storage.audit_barrier = None

        self.assertEqual(
            {item["id"] for item in storage.get_finance_transactions()},
            {"tx_1", "tx_2"},
        )


class FinanceDBStorageTests(unittest.TestCase):
    def test_transactions_round_trip(self) -> None:
        db_path = Path(tempfile.mkdtemp()) / "finance.db"
        storage = DBAdapter(f"sqlite:///{db_path.as_posix()}")

        saved = storage.save_finance_transaction(transaction())

        self.assertEqual(storage.get_finance_transactions(), [saved])


class FinanceAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = JSONAdapter(Path(tempfile.mkdtemp()))
        self.storage.save_product({
            "id": "prod_1",
            "title": "Telefon",
            "price": 200,
            "currency": "RON",
            "stock": 1,
        })
        self.accounts = {
            "active": "acc_1",
            "accounts": [{
                "id": "acc_1",
                "label": "Cont test",
                "profile_dir": "profil_test",
            }],
        }

    def test_purchase_is_saved_and_reported(self) -> None:
        with (
            patch("server.load_accounts", return_value=self.accounts),
            patch("server.config.build_storage", return_value=self.storage),
        ):
            saved = server.save_finance_transaction(
                transaction(id="", quantity=3),
                "acc_1",
            )
            report = server.get_finance("acc_1")

        self.assertEqual(saved["account_id"], "acc_1")
        self.assertEqual(report["summary"]["purchase_quantity"], 3)

    def test_sale_cannot_exceed_financial_stock(self) -> None:
        with (
            patch("server.load_accounts", return_value=self.accounts),
            patch("server.config.build_storage", return_value=self.storage),
        ):
            with self.assertRaises(HTTPException) as raised:
                server.save_finance_transaction(
                    transaction(id="", kind="sale", quantity=1),
                    "acc_1",
                )

        self.assertEqual(raised.exception.status_code, 409)

    def test_concurrent_sales_accept_only_available_stock(self) -> None:
        storage = BarrierJSONAdapter(Path(tempfile.mkdtemp()))
        storage.save_product({
            "id": "prod_1",
            "title": "Telefon",
            "price": 200,
            "currency": "RON",
        })
        storage.save_finance_transaction(transaction(id="buy"))
        storage.barrier_on_filtered = True
        storage.audit_barrier = threading.Barrier(2)
        body = transaction(id="", kind="sale", unit_price=200)

        def sell() -> str:
            try:
                server.save_finance_transaction(body, "acc_1")
                return "accepted"
            except HTTPException as exc:
                return f"rejected:{exc.status_code}"

        with (
            patch("server.load_accounts", return_value=self.accounts),
            patch("server.config.build_storage", return_value=storage),
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: sell(), range(2)))
        storage.audit_barrier = None

        self.assertEqual(results.count("accepted"), 1)
        self.assertEqual(results.count("rejected:409"), 1)
        self.assertEqual(
            len(
                [
                    item
                    for item in storage.get_finance_transactions()
                    if item["kind"] == "sale"
                ]
            ),
            1,
        )

    def test_db_separates_data_per_account(self) -> None:
        """Backendul db imparte tabelele intre conturi (account_id pe fiecare
        rand) — vezi adapters/storage/db_adapter.py. Doua conturi in acelasi
        DB nu-si vad reciproc produsele/tranzactiile, dar raportul "toate
        conturile" le insumeaza pe amandoua."""
        db_path = Path(tempfile.mkdtemp()) / "finance.db"
        db_url = f"sqlite:///{db_path.as_posix()}"
        store_1 = DBAdapter(db_url, account_id="acc_1")
        store_2 = DBAdapter(db_url, account_id="acc_2")
        store_1.save_product(
            {"id": "prod_1", "title": "Telefon", "price": 100, "currency": "RON"}
        )
        store_2.save_product(
            {"id": "prod_2", "title": "Laptop", "price": 200, "currency": "RON"}
        )
        store_1.save_finance_transaction(transaction(id="tx_1", product_id="prod_1"))
        store_2.save_finance_transaction(transaction(id="tx_2", product_id="prod_2"))

        accounts = {
            "active": "acc_1",
            "accounts": [
                {"id": "acc_1", "label": "Cont unu", "profile_dir": "p1"},
                {"id": "acc_2", "label": "Cont doi", "profile_dir": "p2"},
            ],
        }
        storages = {"acc_1": store_1, "acc_2": store_2}

        with (
            patch("server.load_accounts", return_value=accounts),
            patch("server.config.build_storage", side_effect=lambda aid: storages[aid]),
            patch.object(server.config, "STORAGE_BACKEND", "db"),
        ):
            combined = server.get_finance()
            scoped = server.get_finance("acc_1")

        self.assertEqual(combined["summary"]["product_count"], 2)
        self.assertEqual(scoped["summary"]["product_count"], 1)
        self.assertEqual(
            [p["product_id"] for p in scoped["products"]], ["prod_1"]
        )
        # separare si la nivelul adaptorului, nu doar in raportul agregat
        self.assertEqual([p["id"] for p in store_1.get_products()], ["prod_1"])
        self.assertEqual([p["id"] for p in store_2.get_products()], ["prod_2"])

    def test_product_with_finance_history_cannot_be_deleted(self) -> None:
        self.storage.save_finance_transaction(transaction(id="buy"))

        with (
            patch("server.load_accounts", return_value=self.accounts),
            patch("server.config.build_storage", return_value=self.storage),
        ):
            with self.assertRaises(HTTPException) as raised:
                server.delete_product("prod_1", "acc_1")

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(len(self.storage.get_products()), 1)


class FinanceRegressionTests(unittest.TestCase):
    """Cazuri care au fost defecte o data — sa nu se intoarca."""

    def test_fractional_quantity_is_rejected_not_truncated(self) -> None:
        """int(1.9) dadea 1 tacit: cantitatea gresita se salva ca si cum ar
        fi fost trimisa corect."""
        with self.assertRaises(ValueError):
            normalize_transaction(transaction(quantity=1.9))
        with self.assertRaises(ValueError):
            normalize_transaction(transaction(quantity="2.5"))
        self.assertEqual(normalize_transaction(transaction(quantity=3))["quantity"], 3)

    def test_transaction_keeps_its_own_currency(self) -> None:
        """Schimbarea monedei produsului nu mai reeticheteaza istoricul:
        600 RON nu devine 600 EUR fara conversie."""
        entries = [
            normalize_transaction(transaction(currency="RON", unit_price=600))
            | {"account_id": "acc_1"}
        ]
        for currency in ("RON", "EUR"):
            report = build_finance_report(
                [{"id": "prod_1", "title": "AC", "currency": currency,
                  "price": 1000, "vat": {}, "account_id": "acc_1"}],
                entries,
            )
            self.assertEqual(report["transactions"][0]["currency"], "RON")
            self.assertEqual(report["products"][0]["ledger_currencies"], ["RON"])

    def test_orphan_transactions_stay_in_the_balance(self) -> None:
        """Tranzactiile fara produs in catalog nu mai dispar din balanta."""
        entries = [
            normalize_transaction(
                transaction(id="tx_orfan", product_id="prod_sters", kind="sale",
                            quantity=5, unit_price=999, vat_rate=0)
            )
            | {"account_id": "acc_1"}
        ]
        report = build_finance_report(
            [{"id": "prod_1", "title": "AC", "currency": "RON", "price": 100,
              "vat": {}, "account_id": "acc_1"}],
            entries,
        )
        self.assertEqual(len(report["transactions"]), 1)
        self.assertEqual(report["summary"]["sales_revenue"], 4995.0)
        orphans = [p for p in report["products"] if p["missing_product"]]
        self.assertEqual(len(orphans), 1)
        self.assertIn("prod_sters", orphans[0]["title"])

    def test_projected_revenue_excludes_vat_even_when_not_deductible(self) -> None:
        """`deductible` descrie daca factura de VANZARE e deductibila pentru
        cumparator (core/product_schema.py) — nu schimba cu nimic obligatia
        vanzatorului de a vira TVA-ul incasat. Profitul proiectat pentru
        stocul ramas trebuia sa scada TVA-ul oricum, la fel ca la o vanzare
        reala (_effective_amount); scadea doar cand deductible=True, adica
        NICIODATA pe setarile implicite ale unui produs nou (empty_product:
        deductible=False) — supraestima profitul proiectat cu exact TVA-ul.
        """
        products = [{
            "id": "prod_1", "title": "Telefon", "price": 121, "currency": "RON",
            "vat": {"included": True, "deductible": False, "rate": 21},
            "account_id": "acc_1",
        }]
        entries = [
            normalize_transaction(transaction(
                id="buy", kind="purchase", quantity=1, unit_price=60,
                vat_included=True, vat_deductible=True, vat_rate=21,
            ))
            | {"account_id": "acc_1"}
        ]
        report = build_finance_report(products, entries)
        metric = report["products"][0]
        self.assertEqual(metric["stock_quantity"], 1)
        # 121 RON cu TVA 21% inclus -> 100 RON net, nu 121
        self.assertEqual(metric["projected_revenue"], 100.0)


if __name__ == "__main__":
    unittest.main()
