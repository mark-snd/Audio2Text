#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

if lsof -ti:5173 >/dev/null 2>&1 || lsof -ti:8787 >/dev/null 2>&1; then
  echo "Audio2Text is already running."
  open "http://localhost:5173"
  exit 0
fi

cleanup() {
  trap - EXIT INT TERM
  echo ""
  echo "Stopping servers..."
  kill "$WORKER_PID" "$FRONTEND_PID" 2>/dev/null
  wait "$WORKER_PID" "$FRONTEND_PID" 2>/dev/null
  echo "Done."
}
trap cleanup INT TERM

echo "Starting Worker (port 8787)..."
cd "$ROOT/worker"
npx wrangler dev --port 8787 &
WORKER_PID=$!

echo "Starting Frontend (port 5173)..."
cd "$ROOT/frontend"
npm run dev -- --port 5173 &
FRONTEND_PID=$!

echo ""
echo "========================================"
echo "  http://localhost:5173"
echo "  Passcode: SnD2025"
echo "========================================"
echo "Ctrl+C to stop"
echo ""

wait "$WORKER_PID" "$FRONTEND_PID"
