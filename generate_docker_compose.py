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
#
# Resurse per container — suprascrie din .env daca implicitul nu se potriveste
# masinii tale (ex. OLX_BOT_MEM_LIMIT=1g pentru cataloage mari):
#   OLX_BOT_MEM_LIMIT (implicit 768m), OLX_BOT_CPUS (implicit 1.0)

x-worker: &worker
  # Aceeasi imagine (acelasi tag) pentru TOATE conturile — Compose o
  # construieste o singura data la `docker compose build`/`up`, nu cate o
  # data per cont. Inainte, fiecare serviciu avea propriul `build:` fara
  # `image:` comun, deci un catalog cu 5 conturi repeta build-ul de 5 ori.
  build:
    context: .
    dockerfile: Dockerfile.worker
  image: olx-bot-worker:latest
  restart: unless-stopped
  # botul poate fi la mijlocul unei operatii Playwright (navigare, citire
  # pagina) cand vine semnalul de oprire — asta nu se intrerupe instant.
  # Fara grace period marit, Docker il omoara cu SIGKILL dupa 10s implicit
  # (verificat: se intampla in practica), iar heartbeat-ul final
  # (running=false) nu mai apuca sa se scrie — contul ramane "pornit" in
  # dashboard pana expira heartbeat-ul vechi (max 3 min).
  stop_grace_period: 60s
  # Chromium headless per container — fara limita, un cont cu o pagina
  # blocata poate epuiza RAM-ul masinii si afecta toate celelalte conturi.
  mem_limit: ${OLX_BOT_MEM_LIMIT:-768m}
  cpus: ${OLX_BOT_CPUS:-1.0}
  # Vezi docker_healthcheck.py: unhealthy DOAR cand heartbeat-ul lipseste sau
  # e prea vechi (bucla blocata) — o sesiune expirata (running=false, scrisa
  # la timp) ramane "healthy", ca autoheal sa nu intre in bucla de restart
  # cat userul nu s-a reconectat inca din dashboard.
  healthcheck:
    test: ["CMD", "python", "docker_healthcheck.py"]
    interval: 30s
    timeout: 5s
    retries: 3
    # cat asteapta la pornire inainte sa conteze un rezultat "unhealthy" —
    # primul heartbeat poate intarzia (pornire browser, verificare sesiune)
    start_period: 90s
  # eticheta pe care serviciul "autoheal" de mai jos il foloseste ca sa
  # stie ce containere sa monitorizeze si sa reporneasca la unhealthy
  labels:
    - "autoheal=true"
  depends_on:
    - autoheal
  # fara asta, driverul implicit json-file NU limiteaza marimea logului —
  # un container care ruleaza saptamani/luni poate umple discul cu loguri
  # de polling repetitiv. 10MB x 3 fisiere = pastreaza ultimele ~30MB per
  # cont, suficient pentru depanare, fara crestere nelimitata.
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"

services:
"""

SERVICE_TEMPLATE = """  {name}:
    <<: *worker
    container_name: olx-bot-{name}
    environment:
      - ACCOUNT_ID={account_id}
    env_file:
      - .env
    volumes:
      - ./data:/app/data
"""

# Un singur container de autoheal pentru toate conturile — monitorizeaza
# healthcheck-ul containerelor etichetate "autoheal=true" (vezi x-worker mai
# sus) si le reporneste cand devin unhealthy (bucla Playwright blocata, nu
# doar cand procesul crapa — caz deja acoperit de `restart: unless-stopped`).
#
# IMPORTANT — increadere: monteaza /var/run/docker.sock, ceea ce ii da acces
# complet la Docker pe masina asta (echivalent root la nivel de host). E un
# tipar comun si o imagine minimala/dedicata exact acestui scop, dar merita
# stiut inainte sa rulezi `docker compose up` cu utilizatori/masini in care
# nu ai incredere completa. Daca preferi sa NU il rulezi, sterge blocul
# "autoheal" si campul "depends_on" din x-worker de mai sus dintr-un
# docker-compose.override.yml — restul functioneaza identic, doar fara
# restart automat pe bucla blocata.
AUTOHEAL_SERVICE = """
  autoheal:
    image: willfarrell/autoheal:latest
    container_name: olx-bot-autoheal
    restart: unless-stopped
    environment:
      - AUTOHEAL_CONTAINER_LABEL=autoheal
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
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
    if not blocks:
        # x-worker ramane definit (neutilizat) chiar si fara conturi — Compose
        # ignora ancorele nereferentiate, iar "services: {}" ramane valid
        yaml_text = HEADER.rstrip() + "\n  {}\n"
    else:
        yaml_text = HEADER + "\n".join(blocks) + AUTOHEAL_SERVICE
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
