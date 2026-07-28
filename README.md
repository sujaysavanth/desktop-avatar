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

- LLM: Ollama, native `/api/chat` (local). Model choice is VRAM-bound — see
  `backend/core/config.py`; on 8GB use a 7–8B, not a 32B.
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
│   └── src/
│       ├── main.js        one transparent window spanning every display
│       ├── preload.js     bridge: click-through, screen geometry, focused app
│       ├── characters/    one file per character (art + joints + capabilities)
│       ├── character.js   rig driver — turns a pose into SVG joint angles
│       ├── behavior.js    roaming state machine, surfaces, physics
│       └── renderer.js    frame loop, websocket, pointer input
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
| 0 | Roaming avatar + stub backend | She walks your desktop and echoes your query |
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
python -m server.app           # real LLM server on ws://127.0.0.1:8765
# or: python -m server.stub    # canned echo — no GPU, for working on the avatar
# or: python -m tests.test_llm # test suite (--fast skips the live model)

# avatar (separate terminal)
cd avatar
npm install
npm start
```

She lands on the taskbar and starts roaming on her own. Click her to open the
chat box (Esc closes it, ✕ quits), drag her anywhere and she'll fall to the
floor, and `Ctrl+Alt+Q` quits from anywhere.

Note on `npm start`: it goes through `scripts/start.js` rather than calling
`electron .` directly. VS Code's integrated terminal exports
`ELECTRON_RUN_AS_NODE=1`, which makes the electron binary run as plain Node — so
`require("electron")` returns a path string instead of the API and the app dies
on startup. The launcher strips that variable first.

## How the roaming works

The window is a single transparent, always-on-top surface spanning every
display, and it is **click-through by default** — the character moves inside the
window rather than the window moving around the desktop. The renderer flips the
window interactive only while your pointer is actually over her, so your clicks
land on whatever is really underneath.

Behavior is a deterministic state machine (idle → walk → climb → hang → sit →
sleep → drag → fall) running at 60fps in the renderer, with no LLM in the frame
loop. The backend can push an `intent` to bias the *next* transition — the avatar
decides nothing about *how* it moves, and roams perfectly well with the backend
down. Which app has focus is polled by one long-lived PowerShell process and sent
to the backend as `context`, which is what gives it something to be proactive
about.

Position is tracked as an **anchor** — the midpoint of the character's feet —
rather than the element's corner, and the character is attached to a **surface**
(floor, ceiling, or either side wall). `placement()` in `behavior.js` converts
anchor + surface into a transform, rotating 90° onto a wall and 180° onto the
ceiling. That indirection is what lets one piece of movement code drive both
walking and wall-crawling.

## Characters

A character is a data file in `avatar/src/characters/` — art, joint positions,
poses, walk amplitudes, and a `capabilities` list. `character.js` is a driver
that knows none of it specifically; features are detected, so a rig with no mouth
or eyes (a rigid mask) nods its head to talk instead of crashing.

```bash
npm start                          # the wall-crawler (default)
npm start -- --character=chibi     # the placeholder girl
```

`capabilities` is the interesting field, because it gates *behaviour*, not just
looks. `climb` and `hang` unlock the wall and ceiling surfaces; without them a
character turns around at a screen edge instead of going up it, and drops to the
floor if you throw it at a wall. The spider has no `sit`/`sleep` — a wall-crawler
doesn't nap on your taskbar.

To add one: copy an existing file, register it on `window.CHARACTERS`, add a
`<script>` tag in `index.html` before `character.js`, and declare what it can do.
Required element ids in the rig are `#flip`, `#bob`, and one group per joint;
`#eyes-open`/`#eyes-shut`/`#mouth` are optional.
