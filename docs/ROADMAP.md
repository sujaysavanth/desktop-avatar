# Roadmap

Backend before avatars — **except Phase 0**, which is a deliberately thin shell
so you get a visible result on day one without wiring UI to logic.

## Phase 0 — Roaming avatar + mock backend  ← done
One transparent, always-on-top, click-through window spanning every display. A
rigged SVG character roams it under a deterministic state machine, is draggable,
and opens a chat bubble + input on click. Sends queries over websocket to a stub
server that echoes a canned reply and a fake `thinking → idle` transition, and
receives unsolicited `intent` nudges keyed to whichever app has focus.
**Done when:** she walks your desktop, reacts to what you're in, and talks back
(fake brain).

## Phase 1 — Real LLM behind avatar  ← done
`server/app.py` streams from Ollama's native `/api/chat` via `reply_chunk` /
`reply_end`, keeps the model resident in VRAM (`keep_alive`), holds a short
per-connection history, and generates proactive nudges from the focused app.
A GPU lock keeps background nudges from queueing ahead of what you typed.
One avatar, no tools, no persistent memory.
**Done when:** genuine conversation with a local model through the avatar. ✔

Sizing note learned here: model choice is VRAM-bound, not preference-bound. On
8GB a 32B spills to system RAM and generates at 1–3 tok/s. A 7–8B stays fully on
the GPU at 40+ tok/s, which is the difference between a pet and a progress bar.

## Phase 2 — RAG memory (teach it about you)
Chroma + nomic-embed. Ingest resume / notes.
**Done when:** "what are my skills?" pulls from your documents.

## Phase 3 — Job agent capability
Playwright extract → LLM map → deterministic fill → human review gate. Stops
before submit.
**Done when:** point it at a form, review, submit yourself.

## Phase 4 — Behavior-learning log
Capture corrections at every review gate; feed back as few-shot examples.
**Done when:** it stops repeating a mistake you corrected.

## Phase 5 — Orchestrator + Data Eng avatar
LangGraph router; multiple avatars share memory and route tasks.
**Done when:** two working avatars, correct routing.

## Phase 6 — Agents 3–4 + polish
Clone the agent skeleton with new tools; refine avatar animations/states.
**Done when:** the full 3–4 avatar desktop.

## The invariant

Every agent is the same shape: **system prompt + tools + shared memory**, all
calling one LLM service, all gated by human review. That uniformity is what
makes going from one agent to four tractable instead of quadrupling the work.
