#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "========================================================"
echo "              Starting Power BI Brain"
echo "========================================================"

# 1. Detect Python 3.11+
PYTHON_CMD=""
for cmd in python3.11 python3.12 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>&1; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] Python 3.11 or newer was not found."
    echo "Please install Python 3.11+."
    exit 1
fi

# 2. Virtual environment
if [ ! -f ".venv/bin/activate" ]; then
    echo "[*] Creating virtual environment in .venv..."
    "$PYTHON_CMD" -m venv .venv
fi

source .venv/bin/activate

# 3. Backend dependencies
if ! python -c "import antlr4, jsonschema; from backend.cli.main import _parser" >/dev/null 2>&1; then
    echo "[*] Installing Power BI Brain backend dependencies..."
    python -m pip install --disable-pip-version-check -e ".[mcp]" || python -m pip install --disable-pip-version-check -e .
fi

# 4. Check / build frontend
if [ ! -f "frontend/dist/index.html" ]; then
    echo "[*] Web UI build not found. Checking Node.js..."
    if command -v npm >/dev/null 2>&1; then
        echo "[*] Installing frontend packages and building UI..."
        (cd frontend && npm install && npm run build)
    else
        echo "[WARNING] Node.js / npm not found. Starting server without built UI."
        echo "          To use the UI, install Node.js 20+ and run:"
        echo "          cd frontend && npm install && npm run build"
    fi
fi

# 5. Open browser in background
(
    # Open the browser when the server answers, not after a fixed pause (up to 30 s on a cold start).
    for _ in $(seq 1 120); do
        if python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=1)" >/dev/null 2>&1; then
            break
        fi
        sleep 0.25
    done
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://127.0.0.1:8000" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
        open "http://127.0.0.1:8000" >/dev/null 2>&1 || true
    fi
) &

# 6. Launch server
python -m backend.cli.main serve "$@"
