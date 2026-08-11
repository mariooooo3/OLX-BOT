"""Teste pentru registrul de erori expus dashboard-ului.

Erorile sunt per cont: fiecare BotRunner isi tine propriile incidente, iar
flota le aduna pentru dashboard, cele mai noi primele.
"""
import unittest
from unittest.mock import patch

import server
from server import BotFleet, BotRunner


class ErrorCenterTests(unittest.TestCase):
    def test_records_newest_first_and_clears(self) -> None:
        runner = BotRunner("acc_test")

        runner.record_error("prima eroare")
        runner.record_error("a doua eroare")

        errors = runner.get_errors()
        self.assertEqual(runner.errors_for_today(), 2)
        self.assertEqual([error["message"] for error in errors], [
            "a doua eroare",
            "prima eroare",
        ])
        self.assertTrue(all(error["id"].startswith("err_") for error in errors))
        self.assertTrue(all(error["timestamp"] for error in errors))
        # fiecare eroare stie pe ce cont a aparut — cu mai multi boti activi,
        # o eroare fara cont nu spune nimic
        self.assertTrue(all(error["account_id"] == "acc_test" for error in errors))
        self.assertTrue(all(error["account_label"] for error in errors))

        self.assertEqual(runner.clear_errors(), 2)
        self.assertEqual(runner.get_errors(), [])
        self.assertEqual(runner.errors_for_today(), 0)
        self.assertIsNone(runner.last_error)

    def test_fleet_merges_errors_newest_first(self) -> None:
        """Erorile mai multor conturi ajung intr-o singura lista, ordonata
        dupa timp — nu dupa ordinea conturilor."""
        fleet = BotFleet()
        first = fleet.get("acc_unu")
        second = fleet.get("acc_doi")

        first.record_error("veche, cont 1")
        second.record_error("noua, cont 2")

        merged = fleet.all_errors()
        self.assertEqual(
            [e["message"] for e in merged], ["noua, cont 2", "veche, cont 1"]
        )
        self.assertEqual(
            [e["account_id"] for e in merged], ["acc_doi", "acc_unu"]
        )
        self.assertEqual(fleet.clear_errors(), 2)
        self.assertEqual(fleet.all_errors(), [])

    def test_runner_starts_idle(self) -> None:
        """Un runner creat nu porneste nimic — flota il creeaza si doar ca sa
        raporteze starea unui cont oprit."""
        runner = BotRunner("acc_test")
        self.assertFalse(runner.running)
        self.assertFalse(runner.stopping)
        self.assertIsNone(runner.active_llm)
        status = runner.status()
        self.assertEqual(status["account_id"], "acc_test")
        self.assertFalse(status["running"])


class DBMultiAccountTests(unittest.TestCase):
    """Backendul db separa datele pe conturi (account_id pe fiecare rand —
    vezi adapters/storage/db_adapter.py), deci mai multe conturi pot rula
    simultan si pe db, nu doar pe json. Fostele teste de-aici verificau
    restrictia veche (respingere la al doilea cont pe db); acum verificam
    opusul — ca pornirea NU mai e blocata."""

    def test_start_connected_allows_multiple_db_accounts(self) -> None:
        accounts = {
            "active": "acc_unu",
            "accounts": [
                {"id": "acc_unu", "label": "Unu", "profile_dir": "profil_unu"},
                {"id": "acc_doi", "label": "Doi", "profile_dir": "profil_doi"},
            ],
        }
        fleet = BotFleet()

        with (
            patch.object(server.config, "STORAGE_BACKEND", "db"),
            patch("server.load_accounts", return_value=accounts),
            patch("server.account_connected", return_value=True),
            patch.object(BotRunner, "start") as start,
        ):
            started = fleet.start_connected()

        self.assertEqual(set(started), {"acc_unu", "acc_doi"})
        self.assertEqual(start.call_count, 2)

    def test_start_account_allows_second_db_account(self) -> None:
        fleet = BotFleet()

        with (
            patch.object(server.config, "STORAGE_BACKEND", "db"),
            patch.object(fleet, "running_ids", return_value={"acc_unu"}),
            patch.object(BotRunner, "start") as start,
        ):
            fleet.start_account("acc_doi")  # nu ridica nimic

        start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
