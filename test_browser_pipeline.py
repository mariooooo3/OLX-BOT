"""Teste offline pentru selectia si citirea inbox-ului OLX."""
import unittest

from playwright.sync_api import sync_playwright

from adapters.olx.browser_client import BrowserClient


class BrowserPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self) -> None:
        self.page = self.browser.new_page()
        self.client = BrowserClient()
        self.client._page = self.page

    def tearDown(self) -> None:
        self.page.close()

    def test_message_poll_forces_explicit_selling_inbox_url(self) -> None:
        class RecordingPage:
            navigated_to = None

            def goto(self, url: str, **_kwargs) -> None:
                self.navigated_to = url

            @staticmethod
            def wait_for_selector(*_args, **_kwargs) -> None:
                raise TimeoutError

            @staticmethod
            def query_selector_all(_selector: str) -> list:
                return []

        page = RecordingPage()
        self.client._page = page
        self.client.chat_url = "https://www.olx.ro/myaccount/answers/"
        self.client._human_pause = lambda *_args: None
        self.client._conversation_ids_to_scan = lambda: []

        self.assertEqual(self.client.get_new_messages(), [])

        self.assertEqual(
            page.navigated_to,
            "https://www.olx.ro/myaccount/answers/?my_ads=1",
        )

    def test_scans_only_unread_conversations(self) -> None:
        self.page.set_content("""
            <h2 data-testid="unread-section-title">Necitite</h2>
            <div data-testid="conversations-list-item-new"></div>
            <h2 data-testid="read-section-title">Citite</h2>
            <div data-testid="conversations-list-item-old"></div>
        """)

        self.assertEqual(
            self.client._conversation_ids_to_scan(),
            ["new"],
        )

    def test_ignores_conversation_when_latest_message_was_sent(self) -> None:
        self.page.set_content("""
            <div data-testid="received-message"><span data-testid="message">Salut</span></div>
            <div data-testid="sent-message"><span data-testid="message">Bună ziua</span></div>
        """)

        self.assertIsNone(self.client._latest_received_message_text())

    def test_returns_latest_message_when_it_was_received(self) -> None:
        self.page.set_content("""
            <div data-testid="sent-message"><span data-testid="message">Bună ziua</span></div>
            <div data-testid="received-message"><span data-testid="message">Mai este?</span></div>
        """)

        self.assertEqual(self.client._latest_received_message_text(), "Mai este?")

    def test_ignores_received_message_when_ad_is_inactive(self) -> None:
        self.page.set_content("""
            <div data-testid="context-title">INACTIV\n\niphone 15 pro</div>
            <div data-testid="received-message">
                <span data-testid="message">Am o eroare la finalizarea comenzii</span>
            </div>
        """)

        self.assertIsNone(
            self.client._message_from_open_conversation("conversation-inactiva")
        )

    def test_send_reply_removes_dashes_at_olx_boundary(self) -> None:
        class RecordingPage:
            filled_text = None

            @staticmethod
            def goto(*_args, **_kwargs) -> None:
                pass

            @staticmethod
            def wait_for_selector(*_args, **_kwargs) -> None:
                pass

            def fill(self, _selector: str, text: str) -> None:
                self.filled_text = text

            @staticmethod
            def click(*_args, **_kwargs) -> None:
                pass

        page = RecordingPage()
        self.client._page = page
        self.client._human_pause = lambda *_args: None

        self.client.send_reply("conversation-active", "Da -- sigur — este disponibil.")

        self.assertEqual(page.filled_text, "Da sigur este disponibil.")


if __name__ == "__main__":
    unittest.main()
