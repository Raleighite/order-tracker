#!/usr/bin/env bash
# Development helper script for the Order Tracker project
# Usage:
#   ./scripts/dev.sh up      - build and start the test server (uses docker-compose.temp.yml -> port 5001)
#   ./scripts/dev.sh down    - stop the test server
#   ./scripts/dev.sh rebuild - rebuild the image and restart
#   ./scripts/dev.sh smoke   - run a smoke test (create vendor, create order, verify endpoints)
#   ./scripts/dev.sh open    - open the app in the default browser

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.temp.yml"
HOST_PORT=5001
APP_URL="http://localhost:${HOST_PORT}"

function up() {
  echo "Starting dev server (port ${HOST_PORT})..."
  docker compose -f "$COMPOSE_FILE" up --build -d
  echo "Waiting for server to be online..."
  for i in {1..20}; do
    if curl -sSf "$APP_URL/" >/dev/null 2>&1; then
      echo "Server is up"
      return
    fi
    sleep 1
  done
  echo "Server did not start in time" >&2
  exit 1
}

function down() {
  echo "Stopping dev server..."
  docker compose -f "$COMPOSE_FILE" down
}

function rebuild() {
  echo "Rebuilding and restarting dev server..."
  docker compose -f "$COMPOSE_FILE" up --build -d
}

function open_browser() {
  if command -v open >/dev/null 2>&1; then
    open "$APP_URL"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$APP_URL"
  else
    echo "Open your browser at: $APP_URL"
  fi
}

function smoke() {
  echo "Running smoke test against $APP_URL"
  # create vendor
  STATUS=$(curl -sS -o /dev/null -w "%{http_code}" -X POST -d "name=Smoke+Vendor&platform=Test&contact_email=smoke@example.com" "$APP_URL/api/vendors")
  echo "Create vendor returned $STATUS"
  if [ "$STATUS" != "200" ]; then
    echo "Failed to create vendor" >&2
    exit 1
  fi

  # lookup vendor id (assume last vendor)
  VENDORS_JSON=$(curl -sS "$APP_URL/api/vendors")
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  else
    PY=python
  fi
  VENDOR_ID=$(echo "$VENDORS_JSON" | $PY -c "import sys, json; data=json.load(sys.stdin); print(data['vendors'][-1]['id'])")
  echo "Created vendor id: $VENDOR_ID"

  # create order
  CSRF=$(curl -sS -c /tmp/order_tracker_cookies.txt "$APP_URL/add" | $PY -c "import re,sys; html=sys.stdin.read(); m=re.search(r'name=\"csrf_token\" value=\"([^\"]+)\"', html); print(m.group(1) if m else '')")
  if [ -z "$CSRF" ]; then
    echo "Failed to extract CSRF token" >&2
    exit 1
  fi
  STATUS=$(curl -sS -o /dev/null -w "%{http_code}" -X POST "$APP_URL/add" -b /tmp/order_tracker_cookies.txt -d "csrf_token=${CSRF}&vendor_id=${VENDOR_ID}&status=Pending&tracking_number=SMOKE-CLI&product[]=SmokeItem&quantity[]=1&cost[]=4.50")
  echo "Create order returned $STATUS"
  if [ "$STATUS" != "302" ]; then
    echo "Failed to create order" >&2
    exit 1
  fi

  # verify vendor page
  HTML=$(curl -sS "$APP_URL/vendor/${VENDOR_ID}")
  if echo "$HTML" | grep -q "SmokeItem"; then
    echo "Smoke test passed: vendor and order visible"
  else
    echo "Smoke test failed: vendor page doesn't show the order" >&2
    exit 1
  fi
}

case "${1-}" in
  up) up ;; 
  down) down ;; 
  rebuild) rebuild ;; 
  smoke) smoke ;; 
  open) open_browser ;; 
  *) echo "Usage: $0 {up|down|rebuild|smoke|open}"; exit 2 ;;
esac
