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

# --- LLM (Phase 1+) ---
# Ollama's NATIVE api, not the /v1 OpenAI-compatible layer. The compat layer
# silently drops `keep_alive` (verified: it reports the default 5m no matter what
# you send), and keeping the model resident is the difference between a pet that
# answers instantly and one that stalls ~15s on the first word of every
# conversation. The native api also streams as plain NDJSON, which is less
# ceremony than SSE.
OLLAMA_BASE_URL = "http://localhost:11434"

# VRAM budget on this machine is 8GB (RTX 4070 Laptop). Q4_K_M sizes:
#   7-8B  ~4.7GB  fits comfortably, 30-50 tok/s   <- pick from here
#   14B   ~9GB    spills, ~10-15 tok/s, borderline
#   32B   ~20GB   spills badly, 1-3 tok/s, unusable
# qwen2.5:7b, because tool-calling is now load-bearing: llama3 is rejected
# outright by Ollama with "does not support tools", which rules out the
# read_screen tool entirely. It also follows the brevity instructions better.
# llama3:latest still works for plain chat if you want to switch back.
LLM_MODEL = "qwen2.5:7b"

# How long Ollama keeps the model in VRAM after a request. Generous on purpose.
LLM_KEEP_ALIVE = "30m"

# Hard ceiling on a reply. The bubble is 260px wide — long answers are a bug.
LLM_MAX_TOKENS = 220
LLM_TEMPERATURE = 0.8

# Fail fast enough that the avatar can say something instead of hanging.
LLM_CONNECT_TIMEOUT_S = 5.0
LLM_STREAM_TIMEOUT_S = 120.0

# Turns of history kept per connection (user+assistant pairs). Phase 2 replaces
# this crude window with RAG retrieval.
LLM_HISTORY_TURNS = 8

EMBED_MODEL = "nomic-embed-text"

# --- Screen reading: the read_screen tool (Phase 1.5) ---
# The widest-reaching tool in the project, so every limit below is enforced in
# code rather than asked for in a prompt. Set ENABLED to False and the avatar goes
# back to knowing only the window title.
SCREEN_READ_ENABLED = True

# Character budget for OCR text handed to the model. The model runs at a 4096
# token context; a full window of text is easily 1500+ tokens, so this is what
# keeps screen content from evicting the conversation.
SCREEN_MAX_CHARS = 3000

# Floor on time between reads. Stops a confused model looping on captures.
SCREEN_MIN_INTERVAL_S = 3.0
SCREEN_TIMEOUT_S = 20.0

# Substrings matched case-insensitively against "<process name> <window title>".
# Checked before content is handed to the model. Both halves matter: a banking
# site has an innocuous process name, a password manager an innocuous title.
# Tune this to taste — it errs toward refusing.
SCREEN_BLOCKLIST = [
    # credential managers
    "1password", "bitwarden", "lastpass", "keepass", "dashlane", "keeper password",
    "authenticator", "password",
    # private browsing
    "incognito", "inprivate", "private browsing",
    # money
    "bank", "paypal", "coinbase", "wallet", "seed phrase",
    # OS credential surfaces
    "credential", "windows security",
]

# --- Known agents (grows over phases) ---
AGENTS = ["job", "data_eng"]
