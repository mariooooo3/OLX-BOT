import unicodedata

from loguru import logger


def _normalize(text: str) -> str:
    """lowercase + eliminare diacritice, ca 'preț' sa se potriveasca cu 'pret'."""
    text = unicodedata.normalize("NFD", text.lower().strip())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _match_by_ad_title(ad_title: str, products: list) -> dict | None:
    """Asociere stricta anunt <-> produs, dupa titlu.

    Conversatia OLX e legata de un anunt concret, deci titlul anuntului e
    sursa de adevar: produsul din catalog cu acelasi titlu (sau al carui
    titlu se contine reciproc cu al anuntului) e produsul discutat.
    Fara potrivire de titlu NU asociem nimic — informatiile despre alt
    produs nu au voie sa se amestece in raspuns.
    """
    norm_ad = _normalize(ad_title)
    if not norm_ad:
        return None

    exact = [p for p in products if _normalize(p.get("title", "")) == norm_ad]
    if exact:
        logger.debug("Produs asociat dupa titlu (exact): {}", exact[0].get("id"))
        return exact[0]

    contained = [
        p for p in products
        if _normalize(p.get("title", ""))
        and (_normalize(p["title"]) in norm_ad or norm_ad in _normalize(p["title"]))
    ]
    if contained:
        # titlul cel mai lung = potrivirea cea mai specifica
        best = max(contained, key=lambda p: len(p.get("title", "")))
        logger.debug("Produs asociat dupa titlu (includere): {}", best.get("id"))
        return best

    logger.debug("Niciun produs cu titlul anuntului {!r} — fara asociere.", ad_title)
    return None


def match_product(
    message_text: str, products: list, ad_title: str | None = None
) -> dict | None:
    """Gaseste produsul despre care e conversatia.

    Cu `ad_title` (titlul anuntului OLX, extras din conversatie), potrivirea
    e stricta pe titlu — vezi _match_by_ad_title. Fara el (intrari vechi sau
    OLX si-a schimbat interfata), cadem pe euristica initiala: produsul cu
    cele mai multe keywords prezente in mesaj; cu un singur produs in
    catalog, acela e returnat direct.
    """
    if not products:
        return None
    if ad_title:
        return _match_by_ad_title(ad_title, products)

    if len(products) == 1:
        return products[0]

    normalized_message = _normalize(message_text)

    best_product = None
    best_score = 0
    for product in products:
        keywords = product.get("keywords", [])
        score = sum(1 for kw in keywords if _normalize(kw) in normalized_message)
        if score > best_score:
            best_score = score
            best_product = product

    if best_product:
        logger.debug(
            "Produs potrivit: {} (scor {})", best_product.get("id"), best_score
        )
    else:
        logger.debug("Niciun produs potrivit pentru mesaj.")
    return best_product
