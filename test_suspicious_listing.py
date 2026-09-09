from core.suspicious_listing import evaluate_listing


def test_detects_configured_title_price_and_terms():
    result = evaluate_listing(
        {"title": "Acme Widget Producător, nou", "price": 100, "description": "Doar cu avans pe Telegram."},
        {"watched_titles": "Acme Widget Producător", "max_price": 500,
         "suspicious_terms": "avans\ntelegram"},
    )
    assert result["score"] == 100
    assert {signal["kind"] for signal in result["signals"]} == {"title", "price", "terms"}
    assert len(result["signals"]) >= 3
    assert "Acme Widget" in result["suggested_message"]


def test_does_not_flag_unrelated_listing():
    result = evaluate_listing({"title": "Scaun", "price": 900, "description": "Predare personală."}, {})
    assert result["score"] == 0
    assert result["signals"] == []


def test_respects_selected_reasons():
    result = evaluate_listing(
        {"title": "Acme", "price": 100, "description": "Trimite avans pe Telegram."},
        {"max_price": 500, "suspicious_terms": "avans\ntelegram", "selected_reasons": ["contact_extern"]},
    )
    assert result["score"] == 20
    assert result["signals"][0]["text"] == "Contact sau mutarea conversației în afara platformei"
