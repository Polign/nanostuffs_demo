"""Document Q&A with per-person memory.

Each turn:
  1. recall   - read what Recall holds about this person (office, role, topic, ...)
  2. rewrite  - the model turns the message into a self-contained search query,
                using those facts, and proposes facts the message states
  3. search   - the query goes to Qdrant (the handbook collection)
  4. answer   - the model answers from the passages, in the user's language
  5. remember - the proposed facts are written to Recall; a new value replaces
                the old one and the old one stays in history

--no-memory skips steps 1, 2 and 5: the raw message goes to Qdrant.

By default memory uses Recall's text tools: the whole message goes to
remember(text), Recall's extraction model (RECALL_EXTRACT_MODEL) works out the
facts and names the predicates itself, and recall(question) reads them back as
sentences. No predicates file is involved.

--typed uses the typed tools instead: the app proposes facts under the fixed
registry in data/predicates.json, and Recall applies the replace rules.

Usage:
  python agent/chat.py --user priya "What is the parental leave policy?" "Does it cover contractors?"
  python agent/chat.py --user priya                # interactive
  python agent/chat.py --user priya --history      # what Recall holds, with what each value replaced
  python agent/chat.py --user priya --typed "..."  # the typed tools over data/predicates.json instead
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

from fastembed import TextEmbedding
from polign_recall import Client
from polign_recall.client import recall_bin
from qdrant_client import QdrantClient

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)   # the repo: data/ and transcripts/ live beside agent/
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
HANDBOOK = os.environ.get("HANDBOOK_COLLECTION", "handbook")
MEMORY = os.environ.get("MEMORY_COLLECTION", "nanostuffs_memory")
EMBEDDER = os.environ.get("EMBEDDER", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
MODEL = os.environ.get("DEMO_MODEL", "ollama:qwen3:8b")
EXTRACT_MODEL = os.environ.get("RECALL_EXTRACT_MODEL",
                               "anthropic:claude-opus-5-5" if os.environ.get("ANTHROPIC_API_KEY") else "ollama:qwen3:8b")
ASK = "Where does the person work, what is their role, who are their questions about, and what policy area are they asking about?"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
RECALL_BIN = os.environ.get("RECALL_BIN") or recall_bin()   # a locally built recall, else the wheel's

PLANNER = """You plan retrieval for a company document assistant (HR and policy handbook).
You are given facts already known about the person, then their latest message.
Return JSON only:
{"query": string, "facts": {"office": string|null, "role": string|null, "language": string|null, "asking_about": string|null, "scope": string|null}}

query: one self-contained English search query for the document index. Resolve "it", "that", "what about" and
implied context from the known facts (office, scope, what they were asking about). Always include the office
when known. Include the scope when the question is about the same people as before. If the message is only a
statement with nothing to look up, make the query the policy area the statement affects.

facts: only what THIS message states or clearly implies; use null otherwise. Never guess.
  office: the office or country the person works from, when the message says so.
  role: their job or responsibility, when the message says so.
  language: the language the message is written in (e.g. English, Hindi, Spanish). Always set.
  asking_about: the policy area of this question (e.g. parental leave, annual leave, expenses). Set when the message asks something.
  scope: who the question is about. "contractors", "full-time employees", or "themselves" when the person asks
  about their own situation (I, me, my, in any language). Set whenever the message makes it clear.

Examples:
Known: office: Germany; scope: contractors; asking_about: parental leave
Message: Does it cover contractors?
{"query": "parental leave policy for contractors in Germany", "facts": {"office": null, "role": null, "language": "English", "asking_about": "parental leave", "scope": "contractors"}}

Known: (nothing yet)
Message: I'm based in the Pune office and I run payroll. What is the sick leave rule?
{"query": "sick leave policy for employees in the Pune office", "facts": {"office": "Pune", "role": "runs payroll", "language": "English", "asking_about": "sick leave", "scope": null}}

Known: office: Pune; role: runs payroll; asking_about: sick leave
Message: We relocated to the Mumbai office last month.
{"query": "sick leave policy for employees in the Mumbai office", "facts": {"office": "Mumbai", "role": null, "language": "English", "asking_about": null, "scope": null}}

Known: office: Spain; scope: interns; asking_about: expenses
Message: मेरे लिए खर्च की सीमा क्या है?
{"query": "expense limit for an employee in the Spain office", "facts": {"office": null, "role": null, "language": "Hindi", "asking_about": "expenses", "scope": "themselves"}}"""

ANSWERER = """You answer questions about company policy using only the passages given.
Answer in the language the user wrote in. Two or three sentences. Name the passage title you used in square
brackets. If the passages do not answer the question, say what is missing instead of guessing.
Facts known about the person are given for context; do not repeat them back unless they change the answer."""


def llm(system: str, user: str, *, json_mode: bool = False) -> str:
    provider, _, model = MODEL.partition(":")
    if provider == "anthropic":
        import anthropic  # pip install anthropic; needs ANTHROPIC_API_KEY
        client = anthropic.Anthropic()
        msg = client.messages.create(model=model or "claude-opus-5-5", max_tokens=1024, system=system,
                                     messages=[{"role": "user", "content": user}],
                                     output_config={"effort": "low"})
        return "".join(b.text for b in msg.content if b.type == "text")
    body = {"model": model or "qwen3:8b", "stream": False, "think": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["format"] = "json"
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)["message"]["content"]


class Assistant:
    def __init__(self, user: str, *, memory: bool = True, text: bool = True):
        self.user = user
        self.text = text
        self.embedder = TextEmbedding(EMBEDDER)
        self.qdrant = QdrantClient(url=QDRANT_URL, api_key=os.environ.get("QDRANT_API_KEY"))
        self.memory = None
        if memory and text:
            # Default Recall: text tools, the extraction model names the predicates.
            # The text tools have no subject, so each person gets a collection.
            cmd = [RECALL_BIN, "-backend", "qdrant", "-url", QDRANT_URL, "mcp", "-write",
                   "-extract-model", EXTRACT_MODEL, "-collection", f"{MEMORY}_text_{user}"]
            self.memory = Client(command=cmd, timeout=300)
        elif memory:
            # Typed tools: the app proposes facts under a fixed registry.
            # Recall keeps its memory in the same Qdrant, in its own collection.
            cmd = [RECALL_BIN, "-backend", "qdrant", "-url", QDRANT_URL, "mcp", "-write", "-typed",
                   "-predicates", os.path.join(ROOT, "data", "predicates.json"), "-collection", MEMORY]
            self.memory = Client(command=cmd)

    def close(self) -> None:
        if self.memory:
            self.memory.close()

    # 1. recall
    def known(self) -> list[str]:
        if not self.memory:
            return []
        lines = []
        if self.text:
            for mem in self.memory.ask(ASK):
                line = mem.text
                if mem.before:
                    line += f" (replaced: {mem.before[0].text})"
                lines.append(line)
            return lines
        for b in self.memory.recall(self.user):
            line = f"{b.predicate}: {b.value}"
            if b.replaced:
                line += f" (replaced {b.replaced[0].value}, stated {b.days_ago} days ago)"
            lines.append(line)
        return lines

    # 2. rewrite
    def plan(self, message: str, known: list[str]) -> dict:
        facts = "\n".join(known) if known else "(nothing yet)"
        raw = llm(PLANNER, f"Known about the person:\n{facts}\n\nLatest message:\n{message}", json_mode=True)
        try:
            plan = json.loads(raw)
        except json.JSONDecodeError:
            plan = {}
        plan.setdefault("query", message)
        plan["facts"] = {k: v for k, v in (plan.get("facts") or {}).items()
                         if isinstance(v, str) and v.strip() and v.lower() != "null"}
        return plan

    # 3. search
    def search(self, query: str, limit: int = 3) -> list[dict]:
        vector = next(iter(self.embedder.embed([query]))).tolist()
        hits = self.qdrant.query_points(HANDBOOK, query=vector, limit=limit).points
        return [{"score": h.score, **h.payload} for h in hits]

    # 4. answer
    def answer(self, message: str, hits: list[dict], known: list[str]) -> str:
        passages = "\n\n".join(f"[{h['title']}]\n{h['text']}" for h in hits)
        facts = "\n".join(known) if known else "(nothing)"
        return llm(ANSWERER, f"Known about the person:\n{facts}\n\nPassages:\n{passages}\n\nUser: {message}").strip()

    # 5. remember
    def remember_text(self, message: str) -> list[str]:
        r = self.memory.remember(text=message)
        out = []
        for x in r.remembered:
            if x.already_known:
                continue
            note = x.text
            if x.replaces:
                note += f"   (replaces {'; '.join(str(e) for e in x.replaces)})"
            out.append(note)
        if not out and r.kept_as_text:
            out.append("(no fact found; text kept as written)")
        return out

    def remember(self, facts: dict) -> list[str]:
        out = []
        for predicate, value in facts.items():
            r = self.memory.remember(self.user, predicate, value)
            if r.already_known:
                continue
            note = f"{predicate} = {value}"
            if r.superseded:
                note += f"   (replaces {r.superseded[0].value})"
            out.append(note)
        return out

    def respond(self, message: str) -> dict:
        """One turn, as data: what memory knew, the query sent to Qdrant, the
        hits, the answer, and what was remembered. turn() prints this; the
        web server returns it as JSON."""
        t0 = time.time()
        known = self.known()
        if self.memory:
            plan = self.plan(message, known)
            query = plan["query"]
        else:
            plan = {"facts": {}}
            query = message
        hits = self.search(query)
        answer = self.answer(message, hits, known)
        remembered: list[str] = []
        if self.memory and self.text:
            remembered = self.remember_text(message)
        elif self.memory and plan["facts"]:
            remembered = self.remember(plan["facts"])
        return {"user": self.user, "message": message, "memory": known if self.memory else None,
                "query": query, "hits": [{"title": h["title"], "lang": h["lang"], "score": round(h["score"], 2)} for h in hits],
                "answer": answer, "remembered": remembered, "seconds": round(time.time() - t0, 1)}

    def turn(self, message: str) -> None:
        print(f"\n{self.user}> {message}")
        r = self.respond(message)
        if r["memory"] is not None:
            print("  memory:   " + ("; ".join(r["memory"]) if r["memory"] else "(nothing yet)"))
            print(f"  query:    {r['query']}")
        else:
            print(f"  query:    {r['query']}   (as typed; no memory)")
        print("  hits:     " + " | ".join(f"{h['title']} ({h['lang']}, {h['score']:.2f})" for h in r["hits"]))
        print(f"  answer:   {r['answer']}")
        for line in r["remembered"]:
            print(f"  remember: {line}")
        print(f"  ({r['seconds']}s)")


def show_history(user: str, text: bool = True) -> None:
    a = Assistant(user, text=text)
    try:
        if text:
            for mem in a.memory.ask("everything known about the person"):
                before = f"    replaced: {' -> '.join(b.text for b in mem.before)}" if mem.before else ""
                print(f"{mem.text}{before}")
            return
        beliefs = a.memory.recall(user)
        if not beliefs:
            print(f"nothing remembered about {user}")
        for b in beliefs:
            chain = [e.value for e in a.memory.history(user, b.predicate)]
            print(f"{b.predicate:13s} {b.value}    history: {' -> '.join(chain)}")
    finally:
        a.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--user", required=True, help="who is chatting; one memory subject per person")
    p.add_argument("--no-memory", action="store_true", help="retrieve on the raw message, without memory")
    p.add_argument("--history", action="store_true", help="print what Recall holds about the user and exit")
    p.add_argument("--typed", action="store_true", help="the typed tools over predicates.json instead of Recall's default text tools")
    p.add_argument("messages", nargs="*", help="scripted turns; none means interactive")
    args = p.parse_args()
    if args.history:
        show_history(args.user, text=not args.typed)
        return
    a = Assistant(args.user, memory=not args.no_memory, text=not args.typed)
    try:
        if args.messages:
            for m in args.messages:
                a.turn(m)
        else:
            print("type a question; empty line to quit")
            while True:
                try:
                    m = input(f"\n{args.user}> ").strip()
                except EOFError:
                    break
                if not m:
                    break
                a.turn(m)
    finally:
        a.close()


if __name__ == "__main__":
    main()
