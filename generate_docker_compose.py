"""Genereaza docker-compose.yml automat din data/accounts.json — ca nimeni
sa nu mai editeze YAML de mana ca sa mute conturi in Docker (vezi
docs/docker-multi-cont.md).

Un serviciu per cont CONECTAT (contul trebuie sa aiba deja login facut din
dashboard — vezi motivul in bot_worker.py / login.py: containerul nu poate
rezolva CAPTCHA-ul de login, doar continua o sesiune deja creata).

Rulare:
    python generate_docker_compose.py
    python generate_docker_compose.py --include-disconnected  # + placeholder-e pt neconectate
    python generate_docker_compose.py --out docker-compose.yml --force

Idempotent si sigur de rulat oricand: regenereaza tot fisierul din
accounts.json curent — daca ai personalizat manual docker-compose.yml
(resurse, VPN etc.), pastreaza acele modificari separat (ex. un
docker-compose.override.yml), ca sa nu le pierzi la o regenerare.
"""
import argparse
import re
import sys
from pathlib import Path

from core.accounts import account_connected, account_display_name, load_accounts

HEADER = """# GENERAT AUTOMAT de `python generate_docker_compose.py` din
# data/accounts.json — NU edita direct campurile de mai jos (ACCOUNT_ID,
# lista de servicii), se pierd la urmatoarea regenerare. Pentru personalizari
# (resurse, VPN, alte variabile), foloseste docker-compose.override.yml —
# Docker Compose il aplica automat peste acest fisier, fara sa-l atinga.
#
# Regenerare:  python generate_docker_compose.py --force
# Pornire:     docker compose up -d              (toate conturile)
#              docker compose up -d <serviciu>   (doar unul)
# Detalii:     docs/docker-multi-cont.md

services:
"""

SERVICE_TEMPLATE = """  {name}:
    build:
      context: .
      dockerfile: Dockerfile.worker
    container_name: olx-bot-{name}
    environment:
      - ACCOUNT_ID={account_id}
    env_file:
      - .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
    # botul poate fi la mijlocul unei operatii Playwright (navigare, citire
    # pagina) cand vine semnalul de oprire — asta nu se intrerupe instant.
    # Fara grace period marit, Docker il omoara cu SIGKILL dupa 10s implicit
    # (verificat: se intampla in practica), iar heartbeat-ul final
    # (running=false) nu mai apuca sa se scrie — contul ramane "pornit" in
    # dashboard pana expira heartbeat-ul vechi (max 3 min).
    stop_grace_period: 60s
    # fara asta, driverul implicit json-file NU limiteaza marimea logului —
    # un container care ruleaza saptamani/luni poate umple discul cu loguri
    # de polling repetitiv. 10MB x 3 fisiere = pastreaza ultimele ~30MB per
    # cont, suficient pentru depanare, fara crestere nelimitata.
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
"""


def service_name(account_id: str) -> str:
    """Nume de serviciu Docker Compose valid — literele/cifrele/underscore
    din id-ul contului sunt deja compatibile (acc_xxxxxx), dar normalizam
    oricum ca sigurantei in fata unor id-uri viitoare cu alt format.

    Publica (nu _service_name): folosita si de server.py, ca butoanele
    "Porneste in Docker" din dashboard sa targeteze acelasi nume de
    serviciu pe care il genereaza acest fisier.
    """
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", account_id).lower()


def build_compose_yaml(include_disconnected: bool = False) -> tuple[str, list[str], list[str]]:
    accounts = load_accounts()["accounts"]
    included, skipped = [], []
    blocks = []
    for account in accounts:
        connected = account_connected(account)
        if not connected and not include_disconnected:
            skipped.append(account_display_name(account))
            continue
        blocks.append(SERVICE_TEMPLATE.format(
            name=service_name(account["id"]),
            account_id=account["id"],
        ))
        included.append(f"{account_display_name(account)} ({account['id']})"
                        + ("" if connected else " — NECONECTAT, fa login intai"))
    yaml_text = HEADER + "\n".join(blocks) if blocks else HEADER.rstrip() + "\n  {}\n"
    return yaml_text, included, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", default="docker-compose.yml",
        help="fisierul de scris (implicit docker-compose.yml)",
    )
    parser.add_argument(
        "--include-disconnected", action="store_true",
        help="genereaza si servicii pentru conturi neconectate inca (le poti "
             "porni abia dupa ce faci login din dashboard)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="suprascrie fisierul de iesire daca exista deja",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    if out_path.exists() and not args.force:
        print(
            f"{out_path} exista deja — foloseste --force ca sa-l suprascrii "
            "(personalizarile tale ar trebui sa fie oricum in "
            "docker-compose.override.yml, nu in fisierul generat)."
        )
        sys.exit(1)

    yaml_text, included, skipped = build_compose_yaml(args.include_disconnected)

    if not included:
        print(
            "Niciun cont conectat gasit in data/accounts.json. "
            "Conecteaza cel putin un cont din dashboard inainte sa generezi "
            "docker-compose.yml (sau ruleaza cu --include-disconnected ca "
            "sa vezi oricum structura)."
        )
        sys.exit(1)

    out_path.write_text(yaml_text, encoding="utf-8")

    print(f"Scris {out_path} cu {len(included)} cont(uri):")
    for label in included:
        print(f"  - {label}")
    if skipped:
        print(f"\nSarite (neconectate — fa login din dashboard intai): {', '.join(skipped)}")
    print(
        "\nUrmatorii pasi:\n"
        "  1. Opreste din dashboard fiecare cont pe care il muti in Docker.\n"
        "  2. docker compose build\n"
        "  3. docker compose up -d\n"
        "  4. docker compose logs -f   (sa vezi ca merge)\n"
    )


if __name__ == "__main__":
    main()
