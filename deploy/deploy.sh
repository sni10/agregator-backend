#!/usr/bin/env bash
# Deploy (or roll back to) an image built by GitHub Actions:  deploy/deploy.sh <full commit sha>
# Copies compose.prod.yaml + renews.caddy to the server, records the sha in the server's .env (IMAGE_TAG), pulls
# and restarts the stack (the front too once FRONT_TAG is in .env), then reloads the gallery's Caddy, which serves
# renews.me. Migrations run in the container entrypoint before gunicorn starts.
set -euo pipefail

SERVER=${DEPLOY_SERVER:-deploy@198.98.52.9}
DIR=${DEPLOY_DIR:-/srv/renews}
EDGE_DIR=${EDGE_DIR:-/srv/artai}  # the gallery: its Caddy owns ports 80/443
SHA=${1:-}

if [[ ! $SHA =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: $0 <full 40-char commit sha>   (an image ghcr.io/sni10/agregator-backend:<sha> must exist)" >&2
  exit 1
fi

ROOT=$(cd "$(dirname "$0")/.." && pwd)
scp -q "$ROOT/compose.prod.yaml" "$SERVER:$DIR/compose.prod.yaml"
scp -q "$ROOT/deploy/caddy/renews.caddy" "$SERVER:$DIR/caddy/renews.caddy"

ssh "$SERVER" bash -s -- "$DIR" "$SHA" "$EDGE_DIR" <<'REMOTE'
set -euo pipefail
cd "$1"
if grep -q '^IMAGE_TAG=' .env; then sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$2/" .env; else echo "IMAGE_TAG=$2" >> .env; fi
profiles=()
if grep -q '^FRONT_TAG=.' .env; then profiles=(--profile front); fi
compose() { docker compose -f compose.prod.yaml "${profiles[@]}" "$@"; }
compose pull --quiet
compose up -d --remove-orphans
docker compose -f "$3/compose.prod.yaml" exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
compose ps --format '{{.Service}}\t{{.Status}}\t{{.Image}}'
REMOTE
