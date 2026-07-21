# Roadmap

Backend before avatars — **except Phase 0**, which is a deliberately thin shell
so you get a visible result on day one without wiring UI to logic.

## Phase 0 — Avatar shell + mock backend  ← current
Transparent, always-on-top Electron window with a chat bubble + input. Sends
queries over websocket to a stub server that echoes a canned reply and a fake
`thinking → idle` state transition.
**Done when:** you talk to a floating avatar and it talks back (fake brain).

## Phase 1 — Real LLM behind avatar
Replace the stub with Ollama + Qwen2.5. One avatar, no tools, no memory.
**Done when:** genuine conversation with a local model through the avatar.

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
