"""Teste pentru registrul de erori expus dashboard-ului."""
import unittest

from server import BotRunner


class ErrorCenterTests(unittest.TestCase):
    def test_records_newest_first_and_clears(self) -> None:
        runner = BotRunner()

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

        self.assertEqual(runner.clear_errors(), 2)
        self.assertEqual(runner.get_errors(), [])
        self.assertEqual(runner.errors_for_today(), 0)
        self.assertIsNone(runner.last_error)


if __name__ == "__main__":
    unittest.main()
