"""Calcule pentru gestiunea achizitiilor, vanzarilor si costurilor.

Registrul pastreaza fiecare miscare separat. Preturile istorice nu sunt
suprascrise, astfel incat profitul si rata de vanzare raman verificabile.
"""
from datetime import date
from decimal import Decimal, InvalidOperation


TRANSACTION_KINDS = ("purchase", "sale", "expense")


def _decimal(value, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} trebuie să fie un număr valid.") from exc
    if not number.is_finite():
        raise ValueError(f"{field} trebuie să fie un număr valid.")
    return number


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def normalize_transaction(transaction: dict) -> dict:
    """Valideaza si aduce o tranzactie la forma persistata."""
    kind = str(transaction.get("kind") or "").strip().lower()
    if kind not in TRANSACTION_KINDS:
        raise ValueError("Tipul tranzacției trebuie să fie achiziție, vânzare sau cost.")

    product_id = str(transaction.get("product_id") or "").strip()
    if not product_id:
        raise ValueError("Selectează produsul tranzacției.")

    quantity_raw = 1 if kind == "expense" else transaction.get("quantity", 0)
    # int(1.9) da 1 tacit — o cantitate gresita s-ar salva ca si cum ar fi
    # fost trimisa corect. Refuzam explicit valorile care nu sunt intregi.
    quantity_number = _decimal(quantity_raw, "Cantitatea")
    if quantity_number != quantity_number.to_integral_value():
        raise ValueError("Cantitatea trebuie să fie un număr întreg.")
    quantity = int(quantity_number)
    if quantity <= 0:
        raise ValueError("Cantitatea trebuie să fie mai mare decât zero.")

    unit_price = _decimal(transaction.get("unit_price", 0), "Prețul")
    if unit_price < 0:
        raise ValueError("Prețul nu poate fi negativ.")

    vat_rate = _decimal(transaction.get("vat_rate", 0), "Cota TVA")
    if vat_rate < 0 or vat_rate > 100:
        raise ValueError("Cota TVA trebuie să fie între 0 și 100.")

    occurred_at = str(transaction.get("occurred_at") or "").strip()
    try:
        date.fromisoformat(occurred_at)
    except ValueError as exc:
        raise ValueError("Data tranzacției nu este validă.") from exc

    vat_included = bool(transaction.get("vat_included", False))
    vat_deductible = (
        bool(transaction.get("vat_deductible", False))
        if kind != "sale" and vat_included
        else False
    )

    return {
        "id": str(transaction.get("id") or "").strip(),
        "product_id": product_id,
        # moneda se ingheata pe tranzactie: daca se schimba moneda produsului,
        # sumele deja inregistrate raman in moneda in care au fost facute
        # (altfel 600 RON ar aparea retroactiv ca 600 EUR, fara conversie)
        "currency": str(transaction.get("currency") or "").strip().upper() or "RON",
        "kind": kind,
        "quantity": quantity,
        "unit_price": _money(unit_price),
        "vat_rate": float(vat_rate),
        "vat_included": vat_included,
        "vat_deductible": vat_deductible,
        "occurred_at": occurred_at,
        "note": str(transaction.get("note") or "").strip()[:500],
        "created_at": str(transaction.get("created_at") or "").strip(),
    }


def _gross(transaction: dict) -> Decimal:
    return Decimal(str(transaction["unit_price"])) * Decimal(transaction["quantity"])


def _vat_amount(transaction: dict) -> Decimal:
    if not transaction.get("vat_included"):
        return Decimal("0")
    rate = Decimal(str(transaction.get("vat_rate") or 0))
    if rate <= 0:
        return Decimal("0")
    gross = _gross(transaction)
    return gross - gross / (Decimal("1") + rate / Decimal("100"))


def _effective_amount(transaction: dict) -> Decimal:
    gross = _gross(transaction)
    vat = _vat_amount(transaction)
    if transaction["kind"] == "sale":
        return gross - vat
    if transaction.get("vat_deductible"):
        return gross - vat
    return gross


def _average_days_to_sale(transactions: list[dict]) -> float | None:
    """Asociaza FIFO unitatile vandute cu loturile cumparate."""
    purchases = [
        [date.fromisoformat(t["occurred_at"]), t["quantity"]]
        for t in sorted(transactions, key=lambda item: (item["occurred_at"], item["created_at"]))
        if t["kind"] == "purchase"
    ]
    sales = [
        t
        for t in sorted(transactions, key=lambda item: (item["occurred_at"], item["created_at"]))
        if t["kind"] == "sale"
    ]
    purchase_index = 0
    weighted_days = 0
    matched_quantity = 0

    for sale in sales:
        remaining = sale["quantity"]
        sale_date = date.fromisoformat(sale["occurred_at"])
        while remaining > 0 and purchase_index < len(purchases):
            purchase_date, available = purchases[purchase_index]
            matched = min(remaining, available)
            weighted_days += max((sale_date - purchase_date).days, 0) * matched
            matched_quantity += matched
            remaining -= matched
            purchases[purchase_index][1] -= matched
            if purchases[purchase_index][1] == 0:
                purchase_index += 1

    if not matched_quantity:
        return None
    return round(weighted_days / matched_quantity, 1)


def _fifo_cost_basis(transactions: list[dict]) -> tuple[Decimal, Decimal]:
    """Calculeaza costul vandut si stocul ramas folosind loturi FIFO."""
    purchases = [
        [transaction["quantity"], _effective_amount(transaction) / Decimal(transaction["quantity"])]
        for transaction in sorted(
            transactions,
            key=lambda item: (
                item["occurred_at"],
                item["created_at"],
                item["id"],
            ),
        )
        if transaction["kind"] == "purchase"
    ]
    sold_quantity = sum(
        transaction["quantity"]
        for transaction in transactions
        if transaction["kind"] == "sale"
    )
    purchase_index = 0
    remaining_to_match = sold_quantity
    realized_cogs = Decimal("0")

    while remaining_to_match > 0 and purchase_index < len(purchases):
        available, unit_cost = purchases[purchase_index]
        matched = min(remaining_to_match, available)
        realized_cogs += Decimal(matched) * unit_cost
        remaining_to_match -= matched
        purchases[purchase_index][0] -= matched
        if purchases[purchase_index][0] == 0:
            purchase_index += 1

    inventory_value = sum(
        (Decimal(quantity) * unit_cost for quantity, unit_cost in purchases),
        Decimal("0"),
    )
    return realized_cogs, inventory_value


def _projected_unit_revenue(product: dict) -> Decimal:
    """Venitul net (fara TVA) al UNEI bucati din stocul ramas, la pretul
    curent din catalog.

    Depinde doar de `vat.included` — daca pretul afisat include TVA, acel
    TVA nu e venitul vanzatorului (trebuie virat statului) INDIFERENT daca
    factura e "deductibila" pentru cumparator. `deductible` descrie cu totul
    altceva (vezi core/product_schema.py: daca vanzatorul emite factura cu
    TVA deductibil pentru cumparator) si nu schimba cu nimic obligatia de a
    vira TVA-ul incasat. Trebuie sa fie consistent cu _effective_amount(),
    care la o vanzare REALA scade mereu TVA-ul cand vat_included e True,
    fara sa se uite la `deductible` — altfel profitul proiectat pentru stocul
    ramas ar fi calculat pe alta baza decat profitul realizat din vanzarile
    deja facute (bug confirmat: supraestima profitul proiectat cu exact
    valoarea TVA, pentru orice produs cu setarile implicite `deductible:
    False`).
    """
    price = Decimal(str(product.get("price") or 0))
    vat = product.get("vat") or {}
    if vat.get("included"):
        rate = Decimal(str(vat.get("rate") or 0))
        if rate > 0:
            return price / (Decimal("1") + rate / Decimal("100"))
    return price


def _item_key(item: dict, id_field: str) -> tuple[str, str]:
    return str(item.get("account_id") or ""), str(item.get(id_field) or "")


def _orphan_product(key: tuple[str, str], entries: list[dict]) -> dict:
    """Produs-substitut pentru tranzactii ramase fara produs in catalog.

    Nu are pret, deci nu produce venit estimat — doar aduce inapoi in
    balanta sumele deja cheltuite sau incasate.
    """
    account_id, product_id = key
    first = entries[0] if entries else {}
    return {
        "id": product_id,
        "title": f"Produs șters ({product_id})",
        "currency": first.get("currency") or "RON",
        "price": 0,
        "vat": {},
        "account_id": account_id,
        "account_label": first.get("account_label"),
        "missing": True,
    }


def build_finance_report(products: list[dict], transactions: list[dict]) -> dict:
    """Calculeaza balanta globala si indicatorii fiecarui produs."""
    normalized = []
    for raw in transactions:
        try:
            normalized.append(normalize_transaction(raw) | {
                "account_id": raw.get("account_id"),
                "account_label": raw.get("account_label"),
            })
        except ValueError:
            continue

    by_product: dict[tuple[str, str], list[dict]] = {}
    for transaction in normalized:
        key = _item_key(transaction, "product_id")
        by_product.setdefault(key, []).append(transaction)

    # Tranzactiile al caror produs nu mai exista primesc un rand propriu.
    # Fara asta, sumele lor dispareau tacit din balanta: cel mai prost mod
    # de a afla ca protectia la stergere a avut o scapare e sa constati ca
    # nu-ti mai ies banii.
    known_keys = {_item_key(product, "id") for product in products}
    orphans = [
        _orphan_product(key, entries)
        for key, entries in sorted(by_product.items())
        if key not in known_keys
    ]

    product_metrics = []
    decorated_transactions = []
    for product in list(products) + orphans:
        key = _item_key(product, "id")
        entries = by_product.get(key, [])
        purchases = [t for t in entries if t["kind"] == "purchase"]
        sales = [t for t in entries if t["kind"] == "sale"]
        expenses = [t for t in entries if t["kind"] == "expense"]

        purchased_quantity = sum(t["quantity"] for t in purchases)
        sold_quantity = sum(t["quantity"] for t in sales)
        stock_quantity = max(purchased_quantity - sold_quantity, 0)
        purchase_cost = sum((_effective_amount(t) for t in purchases), Decimal("0"))
        sales_revenue = sum((_effective_amount(t) for t in sales), Decimal("0"))
        expense_cost = sum((_effective_amount(t) for t in expenses), Decimal("0"))
        average_cost = (
            purchase_cost / Decimal(purchased_quantity)
            if purchased_quantity
            else Decimal("0")
        )
        realized_cogs, inventory_value = _fifo_cost_basis(entries)
        realized_profit = sales_revenue - realized_cogs - expense_cost
        invested = purchase_cost + expense_cost
        cash_balance = sales_revenue - invested
        projected_revenue = (
            _projected_unit_revenue(product) * Decimal(stock_quantity)
        )
        projected_profit = sales_revenue + projected_revenue - invested
        sell_through_rate = (
            Decimal(sold_quantity) * Decimal("100") / Decimal(purchased_quantity)
            if purchased_quantity
            else Decimal("0")
        )
        margin_rate = (
            realized_profit * Decimal("100") / sales_revenue
            if sales_revenue
            else Decimal("0")
        )
        realized_investment = realized_cogs + expense_cost
        roi = (
            realized_profit * Decimal("100") / realized_investment
            if realized_investment
            else Decimal("0")
        )
        recoverable_vat = sum(
            (
                _vat_amount(t)
                for t in purchases + expenses
                if t.get("vat_deductible")
            ),
            Decimal("0"),
        )
        sales_vat = sum((_vat_amount(t) for t in sales), Decimal("0"))

        metric = {
            "product_id": product.get("id"),
            "title": product.get("title") or "Produs fără titlu",
            "currency": product.get("currency") or "RON",
            "sale_price": float(product.get("price") or 0),
            "vat_rate": float((product.get("vat") or {}).get("rate") or 0),
            "sale_vat_included": bool(
                (product.get("vat") or {}).get("included")
                and (product.get("vat") or {}).get("deductible")
            ),
            "account_id": product.get("account_id"),
            "account_label": product.get("account_label"),
            "purchase_quantity": purchased_quantity,
            "sold_quantity": sold_quantity,
            "stock_quantity": stock_quantity,
            "sell_through_rate": round(float(sell_through_rate), 1),
            "average_purchase_price": _money(average_cost),
            "average_sale_price": _money(
                sales_revenue / Decimal(sold_quantity)
                if sold_quantity
                else Decimal("0")
            ),
            "purchase_cost": _money(purchase_cost),
            "sales_revenue": _money(sales_revenue),
            "additional_costs": _money(expense_cost),
            "invested": _money(invested),
            "cash_balance": _money(cash_balance),
            "realized_profit": _money(realized_profit),
            "margin_rate": round(float(margin_rate), 1),
            "roi": round(float(roi), 1),
            "inventory_value": _money(inventory_value),
            "projected_revenue": _money(projected_revenue),
            "projected_profit": _money(projected_profit),
            "recoverable_vat": _money(recoverable_vat),
            "sales_vat": _money(sales_vat),
            "vat_balance": _money(sales_vat - recoverable_vat),
            "average_days_to_sale": _average_days_to_sale(entries),
            "transaction_count": len(entries),
            # produsul e sters din catalog, dar banii lui raman in balanta
            "missing_product": bool(product.get("missing")),
            # monedele in care s-au facut efectiv miscarile: daca difera de
            # moneda produsului, totalurile aduna sume in monede diferite
            "ledger_currencies": sorted(
                {str(t.get("currency") or "RON") for t in entries}
            ),
        }
        product_metrics.append(metric)

        for transaction in entries:
            vat_amount = _vat_amount(transaction)
            decorated_transactions.append(
                transaction
                | {
                    "product_title": metric["title"],
                    # moneda tranzactiei, nu cea curenta a produsului
                    "currency": transaction.get("currency") or metric["currency"],
                    "gross_total": _money(_gross(transaction)),
                    "vat_amount": _money(vat_amount),
                    "net_total": _money(_effective_amount(transaction)),
                }
            )

    summary_fields = (
        "purchase_cost",
        "sales_revenue",
        "additional_costs",
        "invested",
        "cash_balance",
        "realized_profit",
        "inventory_value",
        "projected_revenue",
        "projected_profit",
        "recoverable_vat",
        "sales_vat",
        "vat_balance",
    )
    def summarize(items: list[dict], currency: str | None) -> dict:
        purchased_total = sum(item["purchase_quantity"] for item in items)
        sold_total = sum(item["sold_quantity"] for item in items)
        return {
            field: round(sum(float(item[field]) for item in items), 2)
            for field in summary_fields
        } | {
            "currency": currency,
            "purchase_quantity": purchased_total,
            "sold_quantity": sold_total,
            "stock_quantity": sum(item["stock_quantity"] for item in items),
            "sell_through_rate": round(
                sold_total * 100 / purchased_total if purchased_total else 0,
                1,
            ),
            "product_count": len(items),
            "active_product_count": sum(
                1 for item in items if item["transaction_count"] > 0
            ),
        }

    products_by_currency: dict[str, list[dict]] = {}
    for item in product_metrics:
        products_by_currency.setdefault(item["currency"], []).append(item)
    currency_summaries = [
        summarize(products_by_currency[currency], currency)
        for currency in sorted(products_by_currency)
    ]

    if len(currency_summaries) == 1:
        summary = currency_summaries[0] | {"mixed_currencies": False}
    elif len(currency_summaries) > 1:
        summary = summarize(product_metrics, None)
        summary.update({field: None for field in summary_fields})
        summary["mixed_currencies"] = True
    else:
        summary = summarize([], "RON") | {"mixed_currencies": False}

    product_metrics.sort(
        key=lambda item: (item["realized_profit"], item["sell_through_rate"]),
        reverse=True,
    )
    decorated_transactions.sort(
        key=lambda item: (item["occurred_at"], item["created_at"]),
        reverse=True,
    )
    return {
        "summary": summary,
        "currency_summaries": currency_summaries,
        "products": product_metrics,
        "transactions": decorated_transactions,
    }
