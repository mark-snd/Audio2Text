#!/bin/bash
# Publish an HTML file from output/ to Cloudflare Pages (projectc-dashboard)
# Usage: ./scripts/publish.sh output/some_file.html [project-name]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WRANGLER="$ROOT_DIR/web/worker/node_modules/.bin/wrangler"

HTML_FILE="$1"
PROJECT_NAME="${2:-projectc-dashboard}"

if [ -z "$HTML_FILE" ]; then
  echo "Usage: ./scripts/publish.sh <html-file> [project-name]"
  echo "  e.g. ./scripts/publish.sh output/2026-05-21_ProjectC_progress.html"
  exit 1
fi

if [ ! -f "$HTML_FILE" ]; then
  echo "Error: file not found — $HTML_FILE"
  exit 1
fi

if [ ! -f "$WRANGLER" ]; then
  echo "Error: wrangler not found at $WRANGLER"
  echo "Run: cd web/worker && npm install"
  exit 1
fi

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

cp "$HTML_FILE" "$TMPDIR/index.html"

"$WRANGLER" pages deploy "$TMPDIR" \
  --project-name "$PROJECT_NAME" \
  --commit-dirty=true

echo ""
echo "✅ https://${PROJECT_NAME}.pages.dev"
