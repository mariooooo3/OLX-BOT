"""HEALTHCHECK Docker pentru bot_worker.py.

Verifica daca heartbeat-ul contului (scris de bot_worker.py la fiecare ciclu
de polling, vezi core/accounts.py -> write_bot_heartbeat) e recent. Rulat de
Docker la interval fix (vezi generate_docker_compose.py); starea rezultata
apare in `docker ps` si poate fi folosita de un serviciu de autoheal extern
(vezi serviciul "autoheal" generat) ca sa REPORNEASCA automat un container
BLOCAT — caz pe care `restart: unless-stopped` singur nu-l acopera, fiindca
acela reactioneaza doar cand procesul chiar se termina (crapa), nu cand
ramane agatat (ex. o pagina Playwright care nu mai raspunde niciodata).

Distinctie importanta: absenta/vechimea heartbeat-ului = unhealthy (bucla nu
mai avanseaza deloc). running=False scris LA TIMP (sesiune expirata, asteapta
re-login din dashboard) e o stare normala, cu heartbeat proaspat — NU
declanseaza restart, ca sa nu intram intr-o bucla de restart inutila cat timp
userul nu s-a reconectat inca.

Foloseste ACCOUNT_ID din mediu, la fel ca bot_worker.py.
"""
import os
import sys

from core.accounts import find_account, load_accounts, load_settings, read_bot_heartbeat


def main() -> int:
    account_id = os.environ.get("ACCOUNT_ID", "").strip()
    if not account_id:
        return 1

    account = find_account(load_accounts(), account_id)
    poll_interval = int(load_settings(account).get("poll_interval_seconds", 45)) if account else 45
    # Marja: un ciclu poate dura mai mult decat poll_interval (navigare
    # Playwright pe mai multe conversatii, pauze "umane" intre mesaje), plus
    # o reincercare. 3x pragul normal, cu un minim pentru conturi cu interval
    # de poll foarte scurt, ca sa nu declansam fals-pozitive.
    max_age = max(180, poll_interval * 3)

    heartbeat = read_bot_heartbeat(account_id, max_age_seconds=max_age)
    return 0 if heartbeat is not None else 1


if __name__ == "__main__":
    sys.exit(main())
