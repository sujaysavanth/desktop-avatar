// Renderer: runs in the window. Phase 0 (this pass) has NO websocket — it echoes
// locally so you can verify the character, bubble, input, and state dot in
// isolation. The wiring pass swaps `fakeReply()` for real websocket calls.

// ---- where a Live2D model would live ----
// Drop a model at avatar/assets/model/<name>.model3.json and set this path.
// If it fails to load (or isn't there), we fall back to the SVG placeholder.
const LIVE2D_MODEL_PATH = "../assets/model/model.model3.json";

const stateDot = document.getElementById("state-dot");
const bubble = document.getElementById("bubble");
const input = document.getElementById("msg");
const sendBtn = document.getElementById("send");
const placeholder = document.getElementById("placeholder");
const canvas = document.getElementById("live2d");

// ---------- state indicator ----------
function setState(value) {
  stateDot.className = value; // idle | thinking | needs-you
  stateDot.title = value;
}

// ---------- speech bubble ----------
let bubbleTimer = null;
function say(text) {
  bubble.textContent = text;
  bubble.classList.remove("hidden");
  clearTimeout(bubbleTimer);
  bubbleTimer = setTimeout(() => bubble.classList.add("hidden"), 6000);
}

// ---------- Live2D (optional, graceful fallback) ----------
async function tryLoadLive2D() {
  try {
    if (!window.PIXI || !PIXI.live2d) throw new Error("pixi-live2d not available");

    const app = new PIXI.Application({
      view: canvas,
      autoStart: true,
      resizeTo: document.getElementById("stage"),
      backgroundAlpha: 0, // transparent
    });

    const model = await PIXI.live2d.Live2DModel.from(LIVE2D_MODEL_PATH);
    app.stage.addChild(model);

    // fit model to stage
    const scale = Math.min(
      app.renderer.width / model.width,
      app.renderer.height / model.height
    );
    model.scale.set(scale);
    model.x = (app.renderer.width - model.width) / 2;
    model.y = app.renderer.height - model.height;

    placeholder.classList.add("hidden"); // real model loaded, hide SVG
    console.log("[avatar] Live2D model loaded");
    return true;
  } catch (err) {
    console.log("[avatar] Live2D not loaded, using placeholder:", err.message);
    return false; // placeholder stays visible
  }
}

// ---------- Phase 0 local echo (stands in for the backend) ----------
// Mirrors the stub server's behavior: thinking -> reply -> idle.
function fakeReply(text) {
  setState("thinking");
  setTimeout(() => {
    say(`you said: ${text}`);
    setState("idle");
  }, 800);
}

// ---------- input handling ----------
function submit() {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  fakeReply(text); // wiring pass replaces this with window.desk.send(...)
}

sendBtn.addEventListener("click", submit);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submit();
});

// ---------- boot ----------
setState("idle");
tryLoadLive2D();
say("hi! i'm your placeholder avatar 👋");
