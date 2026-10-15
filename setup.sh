#!/usr/bin/env bash
# One-time setup: Qdrant in Docker, a Python venv with the demo's packages,
# a model for the chat, and the handbook seeded into Qdrant.
set -euo pipefail
cd "$(dirname "$0")"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"

step() { printf '\n== %s\n' "$*"; }

step "Qdrant"
if curl -sf "$QDRANT_URL/collections" >/dev/null; then
  echo "already running at $QDRANT_URL"
elif command -v docker >/dev/null; then
  docker start qdrant >/dev/null 2>&1 || docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant >/dev/null
  for _ in $(seq 1 30); do curl -sf "$QDRANT_URL/collections" >/dev/null && break; sleep 1; done
  curl -sf "$QDRANT_URL/collections" >/dev/null || { echo "Qdrant did not come up; see: docker logs qdrant" >&2; exit 1; }
  echo "started container qdrant at $QDRANT_URL"
else
  echo "no Qdrant at $QDRANT_URL and no docker to start one" >&2; exit 1
fi

step "Python packages"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade "qdrant-client" "fastembed" "polign-recall>=0.19.0"
echo "polign-recall $(.venv/bin/pip show polign-recall | awk '/^Version/{print $2}') (brings the recall server)"

step "Models"
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ANTHROPIC_API_KEY is set: Recall extracts with Claude (RECALL_EXTRACT_MODEL overrides)"
else
  echo "ANTHROPIC_API_KEY is not set: Recall extracts with the local qwen3:8b through Ollama (slower, weaker)"
fi
if [[ "${DEMO_MODEL:-ollama:qwen3:8b}" == ollama:* ]] || [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  command -v ollama >/dev/null || { echo "ollama is not installed; install it or set DEMO_MODEL=anthropic:claude-opus-5-5 with ANTHROPIC_API_KEY" >&2; exit 1; }
  curl -sf "${OLLAMA_URL:-http://localhost:11434}/api/tags" >/dev/null || { echo "ollama is not running; start it (ollama serve)" >&2; exit 1; }
  ollama list | grep -q '^qwen3:8b' || ollama pull qwen3:8b
  echo "ollama qwen3:8b ready for the chat's rewrite and answer steps"
fi

step "Handbook"
.venv/bin/python seed.py

printf '\nReady. Run the demo:\n  ./demo.sh\n'
