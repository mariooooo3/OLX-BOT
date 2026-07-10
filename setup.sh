#!/usr/bin/env bash
# Instalare automata (Mac/Linux). Ruleaza cu: bash setup.sh
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  OLX Bot - instalare automata"
echo "============================================"
echo

PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "[EROARE] Python nu e instalat sau nu e in PATH."
  echo "Descarca de la https://www.python.org/downloads/"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "[EROARE] Node.js nu e instalat sau nu e in PATH."
  echo "Descarca versiunea LTS de la https://nodejs.org/"
  exit 1
fi

if [ ! -f ".venv/bin/python" ]; then
  echo "[1/5] Creez mediul virtual Python..."
  "$PYTHON" -m venv .venv
else
  echo "[1/5] Mediul virtual exista deja, sar peste."
fi

echo "[2/5] Instalez pachetele Python..."
.venv/bin/python -m pip install --upgrade pip --quiet --disable-pip-version-check
.venv/bin/python -m pip install -r requirements.txt --quiet --disable-pip-version-check

echo "[3/5] Instalez Chromium pentru Playwright (poate dura cateva minute)..."
.venv/bin/python -m playwright install chromium

echo "[4/5] Instalez interfata web (npm install)..."
(cd ui && npm install)

echo "[5/5] Configurez .env..."
.venv/bin/python setup_env.py

echo
echo "============================================"
echo "  Instalare completa!"
echo "  Urmatorul pas: bash start.sh"
echo "============================================"
