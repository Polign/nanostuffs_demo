#!/usr/bin/env bash
# Runs the whole demo: baseline without memory, then two chats with Recall, then the history.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"

[ -x "$PY" ] || { echo "run ./setup.sh first" >&2; exit 1; }
if ! curl -sf "$QDRANT_URL/collections" >/dev/null; then
  echo "Qdrant is not reachable at $QDRANT_URL; run ./setup.sh" >&2
  exit 1
fi
if ! curl -sf "${OLLAMA_URL:-http://localhost:11434}/api/tags" >/dev/null && [[ "${DEMO_MODEL:-ollama:qwen3:8b}" == ollama:* ]]; then
  echo "Ollama is not running. Start it, or set DEMO_MODEL=anthropic:claude-opus-5-5 with ANTHROPIC_API_KEY." >&2
  exit 1
fi

TEXT=""
for arg in "$@"; do
  case "$arg" in
    --reset)
      curl -s -X DELETE "$QDRANT_URL/collections/${MEMORY_COLLECTION:-nanostuffs_memory}" >/dev/null
      curl -s -X DELETE "$QDRANT_URL/collections/${MEMORY_COLLECTION:-nanostuffs_memory}_text_priya" >/dev/null
      $PY seed.py ;;
    --typed) TEXT="--typed" ;;   # the typed tools over predicates.json instead of Recall's default text tools
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

# Seed the handbook if it is not there yet.
curl -sf "$QDRANT_URL/collections/${HANDBOOK_COLLECTION:-handbook}" >/dev/null || $PY seed.py

T1="I manage the contractor team in our Germany office. What's the parental leave policy?"
T2="Does it cover contractors?"
T3="What about annual leave?"
T4="I've moved to the UK office since last week."
T5="मेरे कॉन्ट्रैक्टर्स को कितने दिन की छुट्टी मिलेगी?"

echo "### Today: retrieval sees only the message (--no-memory)"
$PY chat.py --user priya --no-memory "$T1" "$T2" "$T3" "$T5" 2>&1 | grep -v Fetching
echo; echo "### With Recall, chat 1 (Monday)"
$PY chat.py --user priya $TEXT "$T1" "$T2" 2>&1 | grep -v Fetching
echo; echo "### With Recall, chat 2 (Wednesday: new chat, new process)"
$PY chat.py --user priya $TEXT "$T3" "$T4" "$T5" 2>&1 | grep -v Fetching
echo; echo "### What Recall holds about priya"
$PY chat.py --user priya $TEXT --history 2>&1 | grep -v Fetching
