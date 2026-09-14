"""Cautare publica de anunturi pe OLX.ro, cu excluderea anunturilor proprii.

Atat pagina de rezultate cat si pagina de detaliu a unui anunt sunt publice
pe OLX -- nu e nevoie de nicio sesiune/login pentru acest modul (spre
deosebire de restul botului, care are nevoie de sesiunea contului pentru
mesagerie). De aceea functiile de aici primesc direct un `page` Playwright
gata deschis, fara sa stie nimic despre conturi/profiluri.

Cum stim ca un anunt e "al meu": pagina de REZULTATE nu arata numele
vanzatorului (verificat practic), doar pagina de DETALIU a fiecarui anunt
il are (data-testid="user-profile-user-name"). Deschidem deci pagina de
detaliu a fiecarui candidat si comparam numele cu cele deja cunoscute ale
conturilor tale conectate (stocate local, de la login -- vezi
core/accounts.py:read_marker) -- fara nicio cerere suplimentara catre OLX
pentru identitatea proprie.
"""
import re
from urllib.parse import quote

from loguru import logger

BASE_URL = "https://www.olx.ro"
SELLER_NAME_SELECTOR = '[data-testid="user-profile-user-name"]'


def _slugify_query(query: str) -> str:
    """Textul cautat -> slug-ul folosit de OLX in URL.

    Format confirmat practic: "iphone 12 pro" => "iphone-12-pro".
    """
    slug = re.sub(r"[^\w\s-]", "", query, flags=re.UNICODE).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    return quote(slug.lower())


def search_url(query: str, page_number: int = 1) -> str:
    slug = _slugify_query(query)
    url = f"{BASE_URL}/oferte/q-{slug}/"
    if page_number > 1:
        url += f"?page={page_number}"
    return url


_PRICE_RE = re.compile(r"([\d.,\s]+)\s*(lei|ron|eur|usd|€|\$)?", re.IGNORECASE)
_CURRENCY_MAP = {"€": "EUR", "$": "USD", "lei": "RON", "ron": "RON", "eur": "EUR", "usd": "USD"}


def _parse_price(price_text: str | None) -> tuple[float | None, str | None]:
    """"1 199 lei" -> (1199.0, "RON"). Best-effort -- daca formatul nu se
    potriveste (ex. "Preț la cerere"), intoarce (None, None) si pastram
    oricum price_text brut pentru afisare."""
    if not price_text:
        return None, None
    match = _PRICE_RE.search(price_text)
    if not match:
        return None, None
    digits = re.sub(r"[.\s]", "", match.group(1)).replace(",", ".")
    try:
        value = float(digits)
    except ValueError:
        return None, None
    currency = _CURRENCY_MAP.get((match.group(2) or "").lower(), None)
    return value, currency


def parse_search_results(page) -> list[dict]:
    """Extrage anunturile din pagina de rezultate curent incarcata in `page`.

    Selectori confirmati practic (data-testid, stabili indiferent de
    layout): l-card (cardul), ad-card-title, ad-price, location-date,
    card-title-link (linkul catre pagina de detaliu).
    """
    raw = page.evaluate(
        """
        () => {
            // .textContent citeste si textul din <style>-uri imbricate (unele
            // carduri promovate au CSS-in-JS inline) -- .innerText respecta
            // randarea si il exclude, verificat practic (a poluat titlul cu
            // reguli CSS la primul test real).
            const text = (el) => el ? el.innerText.trim() : null;
            // titlul are uneori un al doilea rand ascuns doar la desktop
            // (duplicat de pret pentru layout mobil, tot "vizibil" tehnic in
            // viewport-ul headless) -- prima linie e mereu titlul real
            const firstLine = (el) => { const t = text(el); return t ? t.split('\\n')[0].trim() : null; };
            return Array.from(document.querySelectorAll('[data-testid="l-card"]')).map(card => {
                const titleLink = card.querySelector('[data-testid="card-title-link"]')
                    || card.querySelector('a[href*="/d/oferta/"]');
                const priceEl = card.querySelector('[data-testid="ad-price"]');
                const locEl = card.querySelector('[data-testid="location-date"]');
                const titleEl = card.querySelector('[data-testid="ad-card-title"]');
                const href = titleLink ? titleLink.getAttribute('href') : null;
                return {
                    id: card.id || null,
                    title: firstLine(titleEl),
                    price_text: text(priceEl),
                    location_date: text(locEl),
                    url: href ? new URL(href, location.origin).toString().split('?')[0] : null,
                };
            }).filter(x => x.url && x.title);
        }
        """
    )
    results = []
    seen_urls = set()
    for item in raw:
        if item["url"] in seen_urls:
            continue  # acelasi anunt poate aparea de doua ori (promovat + organic)
        seen_urls.add(item["url"])
        price_value, currency = _parse_price(item["price_text"])
        results.append(
            {
                "id": item["id"],
                "title": item["title"],
                "price_text": item["price_text"],
                "price": price_value,
                "currency": currency,
                "location_date": item["location_date"],
                "url": item["url"],
            }
        )
    return results


def fetch_seller_name(page, listing_url: str) -> str | None:
    """Deschide pagina publica a unui anunt si citeste numele vanzatorului.

    None daca pagina nu se incarca la timp sau anuntul a fost sters
    intre timp (ambele posibile, nu tratam ca eroare fatala -- candidatul
    ramane pur si simplu neverificat, deci NU exclus).
    """
    try:
        page.goto(listing_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector(SELLER_NAME_SELECTOR, timeout=8000)
    except Exception as e:
        logger.debug("Nu am putut citi vanzatorul pentru {}: {}", listing_url, e)
        return None
    try:
        el = page.query_selector(SELLER_NAME_SELECTOR)
        # .inner_text(), nu .text_content(): la fel ca in parse_search_results,
        # evita sa citim text ascuns dintr-un <style> imbricat
        text = el.inner_text().strip() if el else None
        return text or None
    except Exception as e:
        logger.debug("Eroare la citirea numelui vanzatorului ({}): {}", listing_url, e)
        return None
