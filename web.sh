#!/usr/bin/env bash
# The browser version: the agent on :8000 and the Next.js app on :3000.
# Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "run ./setup.sh first" >&2; exit 1; }
[ -d web/node_modules ] || (cd web && npm install)
curl -sf "${QDRANT_URL:-http://localhost:6333}/collections" >/dev/null || { echo "Qdrant is not reachable; run ./setup.sh" >&2; exit 1; }
curl -sf "${QDRANT_URL:-http://localhost:6333}/collections/${HANDBOOK_COLLECTION:-handbook}" >/dev/null || .venv/bin/python agent/seed.py

.venv/bin/python agent/server.py &
AGENT=$!
trap 'kill $AGENT 2>/dev/null' EXIT
for _ in $(seq 1 20); do curl -sf "http://127.0.0.1:${AGENT_PORT:-8000}/healthz" >/dev/null && break; sleep 0.5; done
echo "open http://localhost:3000"
(cd web && AGENT_URL="http://127.0.0.1:${AGENT_PORT:-8000}" exec npx next dev -p 3000)
