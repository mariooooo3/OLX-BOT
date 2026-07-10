@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   OLX Bot - instalare automata
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [EROARE] Python nu e instalat sau nu e in PATH.
  echo Descarca de la https://www.python.org/downloads/
  echo IMPORTANT: la instalare bifeaza "Add python.exe to PATH".
  pause
  exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
  echo [EROARE] Node.js nu e instalat sau nu e in PATH.
  echo Descarca versiunea LTS de la https://nodejs.org/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/6] Creez mediul virtual Python...
  python -m venv .venv
) else (
  echo [1/6] Mediul virtual exista deja, sar peste.
)

echo [2/6] Instalez pachetele Python...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet --disable-pip-version-check
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
  echo [EROARE] Instalarea pachetelor Python a esuat.
  pause
  exit /b 1
)

echo [3/6] Instalez Chromium pentru Playwright ^(poate dura cateva minute^)...
".venv\Scripts\python.exe" -m playwright install chromium

echo [4/6] Descarc modelul de embeddings pentru FAQ ^(~220MB, o singura data^)...
".venv\Scripts\python.exe" -m adapters.embeddings.fastembed_adapter

echo [5/6] Instalez interfata web ^(npm install^)...
pushd ui
call npm install
popd

echo [6/6] Configurez .env...
".venv\Scripts\python.exe" setup_env.py

echo.
echo ============================================
echo   Instalare completa!
echo   Urmatorul pas: start.bat
echo ============================================
pause
