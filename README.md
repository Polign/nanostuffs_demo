# Document Q&A with per-person memory

A retrieval-augmented assistant over a policy handbook, with one memory per
person kept by [Recall](https://github.com/Polign/recall) in the same Qdrant
as the documents. Before retrieval the assistant asks Recall what it knows
about the person and rewrites the message into a self-contained query. After
answering it hands the message to Recall, whose extraction model files the
facts. A new value replaces the old one and the old one stays in history.

Stack: Qdrant, a multilingual embedder, a Python agent, a Next.js front end.

## Setup

Requirements: Docker, Python 3.10+, Node 20+, and a model for the rewrite
and answer steps. By default that is `qwen3:8b` through a local
[Ollama](https://ollama.com); set `DEMO_MODEL=anthropic:claude-opus-5-5` with
`ANTHROPIC_API_KEY` to use Claude (`pip install anthropic` in the venv).
Recall's extraction model is Claude when `ANTHROPIC_API_KEY` is set, else the
local qwen3; `RECALL_EXTRACT_MODEL` overrides.

```sh
./setup.sh      # starts Qdrant, creates the venv, checks the models, seeds the handbook
./demo.sh       # scripted run: without memory, then two chats with memory, then the history
./web.sh        # the browser version: Next.js on :3000, the agent on :8000
```

`./demo.sh --reset` wipes the memory collections and reseeds the handbook.
`./demo.sh --typed` runs the same turns with the typed tools and the fixed
registry in `data/predicates.json`. Saved runs of both are in `transcripts/`.

Interactive, as any user:

```sh
.venv/bin/python agent/chat.py --user priya
.venv/bin/python agent/chat.py --user priya --history
.venv/bin/python agent/chat.py --user priya --no-memory "Does it cover contractors?"
```

## Layout

```
setup.sh, demo.sh, web.sh   setup, the scripted CLI run, the browser demo
agent/
  chat.py                   the per-turn loop: recall, rewrite, search, answer, remember; also the CLI
  server.py                 the same loop as an HTTP service
  seed.py                   embeds the handbook and loads it into Qdrant
data/
  handbook.json             12 policy chunks, in English, German and Spanish
  predicates.json           the registry for --typed mode
web/                        the Next.js app: sign-in, chat, memory panel
transcripts/                saved CLI runs
```

## How a turn works

```
message ──► Recall: what is known about this person ──► model: rewrite into a
                                                         self-contained query
                                                                │
          answer ◄── model, from the passages ◄── Qdrant search (handbook)
            │
            └──► Recall: remember(text); the extractor files the facts and
                 names what they replace
```

Recall runs as a process beside the agent (`recall -backend qdrant mcp
-extract-model ...`), reached through the `polign-recall` Python client, one
collection per person. The Recall calls in `chat.py` are `known()` and
`remember_text()`; with `--typed`, `remember()`.

## Browser

`agent/server.py` serves the loop over HTTP, one Recall client per person:

```
POST /chat     {"userId": "...", "message": "...", "memory": true}
GET  /history?userId=...
POST /reset    {"userId": "..."}
```

`web/` is a Next.js app. Its route handlers read the signed-in user from the
session cookie and forward the message to the agent; the browser never calls
the agent or Recall directly. Each answer expands to show what memory knew,
the query sent to Qdrant, the passages, and what was remembered. A side panel
shows what Recall holds about the person. "New chat" clears the screen, not
the memory.

| Route handler | Does |
| --- | --- |
| `POST /api/session` | signs in; the name is kept in an httpOnly cookie |
| `POST /api/chat` | forwards `{userId, message, memory}` to the agent |
| `GET /api/history` | what Recall holds about the signed-in person, with what each value replaced |
| `DELETE /api/history` | drops the person's memory collection |

`AGENT_URL` points the app at an agent elsewhere.

## Configuration

| Variable | Default | Used by |
| --- | --- | --- |
| `QDRANT_URL`, `QDRANT_API_KEY` | `http://localhost:6333` | seed, agent, Recall |
| `EMBEDDER` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | seed, agent |
| `DEMO_MODEL` | `ollama:qwen3:8b` | rewrite and answer |
| `RECALL_EXTRACT_MODEL` | `anthropic:claude-opus-5-5` when the key is set, else `ollama:qwen3:8b` | Recall extraction |
| `RECALL_BIN` | the `polign-recall` wheel's binary | a locally built `recall` |
| `AGENT_URL` | `http://127.0.0.1:8000` | the Next.js route handlers |

Recall 0.19.0 or later is required.
