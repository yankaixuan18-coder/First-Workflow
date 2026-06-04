#!/usr/bin/env bash
# One-click launcher for Mac / Linux.
# Usage: double-click (after `chmod +x start.sh`) or run `./start.sh`
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "     Amazon 选品采集工具 | Product Research Collector"
echo "============================================================"

# 1. Check Python
echo "[1/6] Checking Python ..."
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[ERROR] Python is not installed. Install Python 3.10+ from https://www.python.org/downloads/"
    exit 1
fi
echo "      Found: $($PY --version)"

# 2. Virtual environment
echo "[2/6] Preparing virtual environment ..."
if [ ! -f ".venv/bin/python" ]; then
    echo "      Creating .venv ... (first run is slower)"
    $PY -m venv .venv
fi
VENV_PY=".venv/bin/python"

# 3. Dependencies
echo "[3/6] Installing dependencies ..."
if [ ! -f ".venv/.deps_installed" ]; then
    echo "      Installing, please wait ... (first run takes a few minutes)"
    "$VENV_PY" -m pip install --upgrade pip >/dev/null
    "$VENV_PY" -m pip install -r requirements.txt
    echo "      Browser driver ready (using your installed Microsoft Edge)."
    touch ".venv/.deps_installed"
    echo "      Dependencies installed."
else
    echo "      Already installed."
fi

# 4. Config
echo "[4/6] Checking configuration ..."
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
    echo "      Created .env from template — edit it to set your Chrome path."
fi

# 5. Reminder
echo "[5/6] Reminder: CLOSE all Edge windows before collecting."

# 6. Launch + open browser
echo "[6/6] Starting the app at http://localhost:5000 ..."
( sleep 3
  if command -v open >/dev/null 2>&1; then open http://localhost:5000
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:5000
  fi ) &

exec "$VENV_PY" main.py
