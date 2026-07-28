// Renderer: the glue. Runs the frame loop, owns the websocket, and translates
// pointer input into behavior calls.
//
// Three jobs, in order of subtlety:
//   1. Frame loop — ask Behavior for a position, write one transform.
//   2. Click-through arbitration — the window is transparent and covers the
//      whole desktop, so we must tell main to make it interactive ONLY while the
//      pointer is over the character. We get mousemove even while click-through
//      (main passes `forward: true`), but not mousedown — so hover has to be
//      computed geometrically and flipped *before* the user clicks.
//   3. Websocket to the backend, honoring the contract in core/protocol.py.

const WS_URL = "ws://127.0.0.1:8765";
const AGENT = "job";

// Which character to be. Registered ids live in characters/ — currently "spider"
// and "chibi". Override at launch:  npm start -- --character=chibi
const CHARACTER =
  new URLSearchParams(location.search).get("character") || "spider";

const el = {
  avatar: document.getElementById("avatar"),
  panel: document.getElementById("panel"),
  dot: document.getElementById("state-dot"),
  bubble: document.getElementById("bubble"),
  chat: document.getElementById("chat"),
  input: document.getElementById("msg"),
  send: document.getElementById("send"),
  quit: document.getElementById("quit"),
};

// ------------------------------------------------------------- speech bubble --

let bubbleTimer = null;
let streaming = false;

// Show the bubble and cancel any pending dismissal. While a reply is streaming
// there is deliberately NO dismiss timer — a slow model must not have its
// sentence hidden out from under it mid-generation.
function showBubble() {
  el.bubble.classList.remove("hidden");
  clearTimeout(bubbleTimer);
}

// Longer text stays up longer; floor of 3s, ceiling of 12s.
function dismissAfter(text, holdMs) {
  const ms = holdMs ?? Math.min(12000, Math.max(3000, text.length * 55));
  clearTimeout(bubbleTimer);
  bubbleTimer = setTimeout(() => el.bubble.classList.add("hidden"), ms);
}

// One complete utterance: canned lines, errors, proactive intent text.
function say(text, holdMs) {
  streaming = false; // a full reply supersedes anything mid-stream
  el.bubble.textContent = text;
  showBubble();
  dismissAfter(text, holdMs);
  Character.talk(Math.min(4, text.length / 22));
}

// `reply_chunk`: append. First chunk opens a fresh bubble.
function streamChunk(text) {
  if (!streaming) {
    streaming = true;
    el.bubble.textContent = "";
    showBubble();
  }
  el.bubble.textContent += text;
  el.bubble.scrollTop = el.bubble.scrollHeight; // follow the newest text
  Character.talk(0.8); // keep the mouth moving as long as tokens keep arriving
}

// `reply_end`: now it's safe to start the dismiss clock.
function streamEnd() {
  if (!streaming) return; // end without chunks, or already superseded by say()
  streaming = false;
  dismissAfter(el.bubble.textContent);
}

function setStateDot(value) {
  el.dot.className = value;
  el.dot.title = value;
}

// ---------------------------------------------------------------- frame loop --

let last = performance.now();
let lastRot = 0;

function frame(now) {
  // Clamp dt: after the machine sleeps or the window is occluded, a huge dt
  // would teleport the avatar and shoot it off-screen on the next fall.
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;

  const { x, y, rot } = Behavior.update(dt);
  el.avatar.style.transform =
    `translate(${Math.round(x)}px, ${Math.round(y)}px)` + (rot ? ` rotate(${rot}deg)` : "");

  // Undo the surface rotation for the speech bubble only — a wall-crawler should
  // still have readable dialogue.
  if (rot !== lastRot) {
    el.panel.style.transform = `translateX(-50%) rotate(${-rot}deg)`;
    lastRot = rot;
  }

  requestAnimationFrame(frame);
}

// ------------------------------------------------- click-through arbitration --

let interactive = false;
let dragging = false;

function setInteractive(next) {
  if (next === interactive) return; // don't spam IPC every mousemove
  interactive = next;
  el.avatar.classList.toggle("hot", next);
  window.desk.setInteractive(next);
}

// Is the pointer over the character (or over the open chat panel)?
// Uses Behavior.hitbox() rather than pos+size: on a wall the character is
// rotated 90°, so its on-screen box has width and height swapped.
function pointerIsOnUs(cx, cy) {
  const pad = 6;
  const b = Behavior.hitbox();
  if (cx >= b.x - pad && cx <= b.x + b.w + pad && cy >= b.y - pad && cy <= b.y + b.h + pad) {
    return true;
  }

  if (!el.chat.classList.contains("hidden")) {
    const r = el.chat.getBoundingClientRect();
    if (cx >= r.left - pad && cx <= r.right + pad && cy >= r.top - pad && cy <= r.bottom + pad) {
      return true;
    }
  }
  return false;
}

window.addEventListener("mousemove", (e) => {
  if (dragging) {
    Behavior.grabMove(e.clientX - grabOff.x, e.clientY - grabOff.y);
    return;
  }
  // Keep the window interactive while the chat input has focus, or a single
  // stray mousemove would yank the window out from under the user's typing.
  setInteractive(pointerIsOnUs(e.clientX, e.clientY) || document.activeElement === el.input);
});

// --------------------------------------------------------------- drag & poke --

const grabOff = { x: 0, y: 0 };
let pressAt = null;

document.getElementById("char").addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  dragging = true;
  pressAt = { x: e.clientX, y: e.clientY };
  el.avatar.classList.add("dragging");
  // grab() first: it drops any surface rotation and re-anchors to keep the
  // character where it visually was. Reading pos before that would compute the
  // offset against the rotated placement and yank it on the first mousemove.
  Behavior.grab();
  grabOff.x = e.clientX - Behavior.pos.x;
  grabOff.y = e.clientY - Behavior.pos.y;
  e.preventDefault();
});

window.addEventListener("mouseup", (e) => {
  if (!dragging) return;
  dragging = false;
  el.avatar.classList.remove("dragging");
  Behavior.release();

  // A press that barely moved is a click, not a drag: poke + toggle the chat.
  const moved = Math.hypot(e.clientX - pressAt.x, e.clientY - pressAt.y);
  if (moved < 4) {
    Behavior.poke();
    const opening = el.chat.classList.contains("hidden");
    el.chat.classList.toggle("hidden", !opening);
    if (opening) el.input.focus();
  }
  // We may have been released far from the character — recompute hover.
  setInteractive(pointerIsOnUs(e.clientX, e.clientY));
});

// ------------------------------------------------------------------ chat I/O --

function submit() {
  const text = el.input.value.trim();
  if (!text) return;
  el.input.value = "";
  if (!sendQuery(text)) say("i can't reach my backend right now.");
}

el.send.addEventListener("click", submit);
el.quit.addEventListener("click", () => window.desk.quit());
el.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submit();
  if (e.key === "Escape") {
    el.chat.classList.add("hidden");
    el.input.blur();
  }
});

// ---------------------------------------------------------------- websocket --

let ws = null;
let retry = 500; // ms, backs off to 10s
let pendingContext = null; // latest focused app, sent once we're connected

function connect() {
  ws = new WebSocket(WS_URL);

  ws.addEventListener("open", () => {
    retry = 500;
    console.log("[avatar] backend connected");
    setStateDot("idle");
    if (pendingContext) sendContext(pendingContext);
  });

  ws.addEventListener("message", (e) => {
    let msg;
    try {
      msg = JSON.parse(e.data);
    } catch {
      return; // a malformed frame shouldn't take down the avatar
    }
    switch (msg.type) {
      case "reply":
        say(msg.text);
        break;
      case "reply_chunk":
        streamChunk(msg.text);
        break;
      case "reply_end":
        streamEnd();
        break;
      case "state":
        setStateDot(msg.value);
        break;
      case "intent":
        // The nudge. Behavior queues it for the next transition — it never
        // interrupts a stride or a fall mid-flight.
        Behavior.setIntent({ action: msg.action, text: msg.text });
        break;
    }
  });

  ws.addEventListener("close", () => {
    setStateDot("offline");
    ws = null;
    setTimeout(connect, retry);
    retry = Math.min(10000, retry * 2);
  });

  // 'error' always precedes 'close', so reconnect is handled above.
  ws.addEventListener("error", () => {});
}

function socketReady() {
  return ws && ws.readyState === WebSocket.OPEN;
}

function sendQuery(text) {
  if (!socketReady()) return false;
  ws.send(JSON.stringify({ type: "query", agent: AGENT, text }));
  return true;
}

function sendContext(info) {
  if (!socketReady()) {
    pendingContext = info;
    return false;
  }
  ws.send(JSON.stringify({ type: "context", app: info.app || "", title: info.title || "" }));
  return true;
}

// ---------------------------------------------------------------------- boot --

// Load the rig first: behavior needs its size and capabilities before it can
// decide where the floor is or whether walls are even an option.
const character = Character.load(CHARACTER);
Behavior.init({ size: character.size, capabilities: character.capabilities });
el.avatar.style.width = `${character.size.w}px`;
el.avatar.style.height = `${character.size.h}px`;

window.desk.onWorldLayout((layout) => Behavior.setWorld(layout));

window.desk.onFocusChanged((info) => {
  Behavior.setFocusedApp(info.app);
  pendingContext = info;
  sendContext(info);
});

Behavior.on("say", (text) => say(text));

setStateDot("offline");
connect();
requestAnimationFrame((t) => {
  last = t;
  requestAnimationFrame(frame);
});
