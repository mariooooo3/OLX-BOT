#!/usr/bin/env bash
# Porneste tot ce trebuie pentru dashboard: server (API) + UI, apoi
# deschide browserul. Ruleaza cu: bash start.sh
cd "$(dirname "$0")"

echo "============================================"
echo "  OLX Bot - pornire"
echo "============================================"
echo

if [ ! -f ".venv/bin/python" ]; then
  echo "[EROARE] Nu gasesc .venv. Ruleaza mai intai:"
  echo "    bash setup.sh"
  exit 1
fi

if [ ! -d "ui/node_modules" ]; then
  echo "[EROARE] Interfata web nu e instalata. Ruleaza mai intai:"
  echo "    bash setup.sh"
  exit 1
fi

mkdir -p logs

echo "Curat instantele vechi ale dashboard-ului..."
for port in 8000 8080; do
  pid=$(lsof -ti tcp:$port 2>/dev/null || true)
  if [ -n "$pid" ]; then
    echo "  Opresc procesul vechi de pe portul $port (PID $pid)..."
    kill -9 $pid 2>/dev/null || true
  fi
done

echo "[1/2] Pornesc serverul botului (API pe http://localhost:8000)..."
.venv/bin/python server.py > logs/server.out.log 2>&1 &
SERVER_PID=$!

echo "[2/2] Pornesc interfata (UI pe http://localhost:8080)..."
(cd ui && npm run dev > ../logs/ui.out.log 2>&1 &)

echo
echo "Astept pornirea interfetei (prima pornire poate dura ~1 min)..."
sleep 20

URL="http://localhost:8080"
if command -v open >/dev/null 2>&1; then
  open "$URL" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
fi

echo
echo "============================================"
echo "  Gata! Dashboard: $URL"
echo "  Daca pagina e goala, mai asteapta putin si"
echo "  da Refresh (UI-ul inca se compileaza)."
echo
echo "  Ca sa opresti botul:"
echo "    kill $SERVER_PID"
echo "    (si procesul 'npm run dev' pornit de acest script)"
echo "============================================"
