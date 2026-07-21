"""Central config. Everything tunable lives here so no magic strings leak
into the agents. Later phases add model names, DB paths, etc."""

from pathlib import Path

# --- Websocket server (Phase 0+) ---
WS_HOST = "127.0.0.1"
WS_PORT = 8765

# --- Paths ---
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
PROFILE_DIR = DATA_DIR / "profiles"
VECTOR_STORE_DIR = DATA_DIR / "vector_store"
BEHAVIOR_LOG_DIR = DATA_DIR / "behavior_log"

# --- LLM (Phase 1+) — not used yet, here so it has a home ---
OLLAMA_BASE_URL = "http://localhost:11434/v1"
LLM_MODEL = "qwen2.5:32b"
EMBED_MODEL = "nomic-embed-text"

# --- Known agents (grows over phases) ---
AGENTS = ["job", "data_eng"]
