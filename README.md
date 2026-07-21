# desk-avatars

A local, self-hosted multi-agent AI system. 3–4 profile-based avatars live on
your desktop, each a specialized agent (job automation, data engineering, …),
sharing a common memory about you and learning from your corrections.

Everything runs locally: your data and the models never leave your machine.
Agents' tools reach exactly as far as the task requires (job sites for the job
agent) and no further.

## Design principles

1. Every agent = system prompt + tools + shared memory, all calling **one**
   shared Ollama service — not one model per avatar.
2. The **LLM decides *what*; deterministic code executes *how*;** a human
   approves before anything irreversible.
3. The avatar (UI) and backend are **always separate processes** speaking a
   fixed websocket contract — see `backend/core/protocol.py`. Locked at Phase 0.
4. Job form-filling is **assisted / human-in-the-loop**, never fully autonomous.

## Stack

- LLM: Ollama + Qwen2.5 32B (local)
- Embeddings: nomic-embed-text (local)
- Vector DB: Chroma
- Behavior log: SQLite
- Web automation: Playwright (free, local)
- Avatar UI: Electron (transparent, always-on-top windows)
- Orchestration: LangGraph

## Structure

```
desk-avatars/
├── avatar/            Electron front-end (thin client — speaks websocket only)
│   ├── src/
│   └── assets/
├── backend/           All Python
│   ├── core/          protocol.py (the contract) + config.py
│   ├── server/        stub echo server now → real orchestrator later
│   ├── agents/        one file per agent (Phase 3+)
│   ├── memory/        RAG store + behavior log (Phase 2, 4)
│   ├── tools/         Playwright, SQL, … (Phase 3+)
│   └── tests/
├── data/              runtime data (gitignored — your profile, DB, logs)
├── docs/              ROADMAP.md
└── scripts/           dev helpers
```

## Roadmap

| Phase | What | Success looks like |
|-------|------|--------------------|
| 0 | Avatar shell + stub backend | Floating avatar echoes your query |
| 1 | Real LLM behind avatar | Genuine conversation via local model |
| 2 | RAG memory | Answers from your own documents |
| 3 | Job agent | Fills a form, you review + submit |
| 4 | Behavior-learning log | Stops repeating corrected mistakes |
| 5 | Orchestrator + Data Eng avatar | Two avatars, correct routing |
| 6 | Agents 3–4 + polish | Full multi-avatar desktop |

See `docs/ROADMAP.md` for detail.

## Getting started (Phase 0)

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m server.stub          # starts the echo server on ws://127.0.0.1:8765

# avatar (separate terminal)
cd avatar
npm install
npm start
```
