#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT/frontend"

if ! command -v uv >/dev/null 2>&1; then
  echo "[ERROR] uv was not found in the current shell environment."
  echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm was not found in the current shell environment."
  echo "Install Node.js: https://nodejs.org/"
  exit 1
fi

echo "========================================"
echo "  不平 (Buping) - AI 求职助手"
echo "========================================"
echo ""

echo "[1/3] Syncing backend dependencies with uv ..."
cd "$ROOT"
uv sync

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[2/3] Installing frontend dependencies ..."
  cd "$FRONTEND_DIR"
  npm install
else
  echo "[2/3] Frontend dependencies already installed."
fi

echo "[3/3] Starting Buping ..."
echo ""
cd "$ROOT"
PYTHONUNBUFFERED=1 uv run python -m backend.dev_launcher
