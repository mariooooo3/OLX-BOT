@echo off
REM Porneste tot ce trebuie pentru dashboard: server (API) + UI, apoi
REM deschide browserul. Dublu-click sau ruleaza `start.bat` din folder.
cd /d "%~dp0"

echo ============================================
echo   OLX Bot - pornire
echo ============================================
echo.

REM Un dashboard inchis in browser nu opreste neaparat procesele Python/Node.
REM Inchidem instantele vechi de pe porturile aplicatiei, altfel serverul nou
REM nu poate porni si dashboard-ul continua sa ruleze codul vechi din memorie.
echo Curat instantele vechi ale dashboard-ului...
for /f %%P in ('powershell -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty OwningProcess -Unique"') do (
  echo   Opresc serverul vechi de pe portul 8000 ^(PID %%P^)...
  taskkill /PID %%P /T /F >nul 2>&1
)
for /f %%P in ('powershell -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty OwningProcess -Unique"') do (
  echo   Opresc interfata veche de pe portul 8080 ^(PID %%P^)...
  taskkill /PID %%P /T /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

if not exist ".venv\Scripts\python.exe" (
  echo [EROARE] Nu gasesc .venv. Ruleaza mai intai:
  echo     setup.bat
  pause
  exit /b 1
)

if not exist "ui\node_modules" (
  echo [EROARE] Interfata web nu e instalata. Ruleaza mai intai:
  echo     setup.bat
  pause
  exit /b 1
)

if not exist ".env" (
  echo [EROARE] Nu gasesc .env. Ruleaza mai intai:
  echo     setup.bat
  pause
  exit /b 1
)

echo [1/2] Pornesc serverul botului (API pe http://localhost:8000)...
start "OLX Bot - Server" cmd /k ".venv\Scripts\python.exe server.py"

echo [2/2] Pornesc interfata (UI pe http://localhost:8080)...
start "OLX Bot - UI" cmd /k "cd ui && npm run dev"

echo.
echo Astept pornirea interfetei (prima pornire poate dura ~1 min)...
timeout /t 25 /nobreak >nul

start "" http://localhost:8080

echo.
echo ============================================
echo   Gata! S-au deschis 2 ferestre (Server + UI).
echo   Dashboard: http://localhost:8080
echo.
echo   Daca pagina e goala, mai asteapta putin si
echo   apasa Refresh (UI-ul inca se compileaza).
echo   Daca 8080 e ocupat, vezi portul real in
echo   fereastra "OLX Bot - UI".
echo ============================================
echo.
echo Ca sa opresti botul: inchide cele 2 ferestre.
pause
