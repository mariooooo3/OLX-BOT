"""Configurare interactiva a .env — rulat automat de setup.bat / setup.sh.

OLX_EMAIL/OLX_PASSWORD nu sunt folosite (login-ul e manual, prin fereastra
de browser, din cauza CAPTCHA-ului OLX) — deci nu le cerem aici. Singura
cheie de care are nevoie botul ca sa raspunda este GROQ_API_KEY.
"""
import re
import shutil
from pathlib import Path

ENV_PATH = Path(".env")
EXAMPLE_PATH = Path(".env.example")


def main() -> None:
    if not ENV_PATH.exists():
        shutil.copy(EXAMPLE_PATH, ENV_PATH)

    print()
    print("Cheia Groq e necesara ca botul sa genereze raspunsuri (gratuita,")
    print("cateva secunde): https://console.groq.com/keys")
    try:
        key = input(
            "GROQ_API_KEY (Enter ca sa o completezi mai tarziu manual in .env): "
        ).strip()
    except EOFError:
        key = ""

    if not key:
        print("Sarit — completeaza GROQ_API_KEY manual in .env inainte de a porni botul.")
        return

    text = ENV_PATH.read_text(encoding="utf-8")
    text, n = re.subn(r"(?m)^GROQ_API_KEY=.*$", f"GROQ_API_KEY={key}", text)
    if n == 0:
        text += f"\nGROQ_API_KEY={key}\n"
    ENV_PATH.write_text(text, encoding="utf-8")
    print("Cheie salvata in .env.")


if __name__ == "__main__":
    main()
