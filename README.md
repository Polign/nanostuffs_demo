# Follow-up questions in enterprise RAG, with Recall by Polign

A small demo for Nanostuffs. The setup mirrors theirs: documents in Qdrant, a
multilingual embedder, a chat per person. The problem it addresses: a
follow-up question ("Does it cover contractors?", "What about annual leave?")
reaches the retriever without the context that makes it answerable.

What the demo adds is one memory per person, kept by
[Recall](https://github.com/Polign/recall) inside the same Qdrant. Before
retrieval the app asks Recall what it knows about the person (office, role,
what they were asking about) and rewrites the message into a self-contained
query. After answering it hands the whole message to Recall, whose extraction
model works out the facts and files them. A new value replaces the old one and
the old one stays in history, so "I moved to the UK office" changes every
later answer and someone can still see when it changed.

## Run it

Requirements: Docker (for Qdrant), Python 3.10+, and a model for the chat's
rewrite and answer steps: `qwen3:8b` through a local [Ollama](https://ollama.com)
by default, or set `DEMO_MODEL=anthropic:claude-opus-5-5` with
`ANTHROPIC_API_KEY` (`pip install anthropic` in the venv). Recall's extraction
model is Claude when `ANTHROPIC_API_KEY` is set, else the local qwen3
(`RECALL_EXTRACT_MODEL` overrides). Claude is strongly recommended for
extraction.

```sh
./setup.sh      # starts Qdrant, makes the venv, checks the models, seeds the handbook
./demo.sh       # baseline, then two chats with memory, then the history
```

`./demo.sh --reset` wipes the memory collections and reseeds the handbook.
`transcript.txt` is the output of one run with Claude extracting.

`./demo.sh --typed` runs the same turns on Recall's typed tools instead: the
app proposes facts under the fixed registry in `predicates.json` and Recall
applies the replace rules. This is the path for a team that wants to control
exactly what gets remembered. `transcript-typed.txt` is one run of that.

Interactive, as any user:

```sh
.venv/bin/python chat.py --user priya
.venv/bin/python chat.py --user priya --history      # what is remembered, and what each value replaced
.venv/bin/python chat.py --user priya --no-memory "Does it cover contractors?"   # today's behaviour
.venv/bin/python chat.py --user priya --typed "What about annual leave?"          # typed tools instead
```

## What is in here

| File | What it is |
| --- | --- |
| `handbook.json` | 12 policy chunks for a fictional company, three languages |
| `seed.py` | Embeds the chunks with `paraphrase-multilingual-MiniLM-L12-v2` and loads them into the `handbook` collection. Stands in for the existing document pipeline. |
| `predicates.json` | The registry for `--typed` mode: five things to remember about a person, plus a free-text `note`. Unused in the default text mode, where the extractor names predicates itself. |
| `chat.py` | The per-turn loop: recall, rewrite, search, answer, remember. The Recall part is `known()` and `remember_text()` (default) or `remember()` (`--typed`). |
| `demo.sh` | The scripted run. |

## How the turn works

```
message ──► Recall: what do we know about this person? ──► model: rewrite into a
            (office, role, scope, topic; with what each        self-contained query,
             value replaced)                                   propose new facts
                                                                      │
                 answer ◄── model, from the passages ◄── Qdrant search (handbook)
                   │
                   └──► Recall: remember the proposed facts (old values kept in history)
```

Recall runs as a small process beside the app (`recall -backend qdrant mcp
-extract-model ...`), reached through the `polign-recall` Python client. Its
collections live in the same Qdrant as the handbook, one per person in text
mode. The app never decides what to forget: the extractor sees what memory
already holds and names what a new statement replaces, Recall checks that
against the record, and `--history` reads the chain back.

## Honest notes

- Within one chat, passing the last few turns to the rewrite step solves the
  first follow-up on its own. Memory earns its place on the second chat, the
  long chat whose start has scrolled out of the window, and the correction.
- The planner and answerer here use a local 8B model with thinking off, so each
  turn takes 3 to 5 seconds on a laptop. With the model they already run the
  cost is two short calls per turn.
- The embedder is a small multilingual model chosen so the demo runs offline.
  Cross-language hits are visible in the baseline (a Hindi question finds
  German and English passages) but the ranking is rough; their own embedder
  replaces it in `seed.py` and `chat.py`.
- The 8B planner does not reliably flip `scope` to the person themselves when
  a manager who has been asking about contractors asks about their own leave,
  even with an example in the prompt. A stronger model, or the chat history
  in the rewrite prompt, covers this; test it with the real model first.
- Recall on Qdrant uses vector search only for its own reads (no keyword
  ranking) and cannot resume agents. Neither matters here: reads are by
  subject, one person.
- Text mode needs recall 0.19.0 or later. Before that release the extractor
  did not see what memory already held, so "I've moved to the UK office"
  landed beside "works in the Germany office" instead of replacing it.
  `RECALL_BIN` points the demo at a locally built recall when needed.
