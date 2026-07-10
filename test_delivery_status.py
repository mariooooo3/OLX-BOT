"""Teste offline pentru confirmarea trimiterii si retry."""
import tempfile
import unittest
from pathlib import Path

from adapters.storage.json_adapter import JSONAdapter


class DeliveryStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = JSONAdapter(Path(tempfile.mkdtemp()))
        self.message = {
            "id": "conv_1",
            "olx_conversation_id": "olx_1",
            "buyer_message": "Mai este disponibil?",
            "bot_response": "Da.",
            "status": "pending",
        }
        self.storage.log_conversation(self.message)

    def test_pending_and_failed_messages_are_retried(self) -> None:
        self.assertFalse(self.storage.is_processed("olx_1", "Mai este disponibil?"))

        self.storage.mark_conversation_status(
            "olx_1", "Mai este disponibil?", "failed"
        )

        self.assertFalse(self.storage.is_processed("olx_1", "Mai este disponibil?"))

    def test_only_confirmed_sent_message_is_deduplicated(self) -> None:
        self.storage.mark_conversation_status(
            "olx_1", "Mai este disponibil?", "sent"
        )

        self.assertTrue(self.storage.is_processed("olx_1", "Mai este disponibil?"))


if __name__ == "__main__":
    unittest.main()
