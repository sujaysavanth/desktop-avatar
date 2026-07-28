// Preload: the only bridge between the sandboxed renderer and the main process.
//
// Deliberate deviation from the original Phase 0 note here: the websocket lives
// in the RENDERER, not main. The renderer gets a native WebSocket for free,
// which keeps the avatar zero-dependency; putting it in main would have meant
// adding `ws` just to re-bridge every frame of conversation back across IPC.
// So this bridge carries only what main genuinely owns: window click-through,
// screen geometry, the focused app, and quit.

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desk", {
  quit: () => ipcRenderer.send("app:quit"),

  // true  = clicks land on our window (pointer is over the character)
  // false = clicks pass through to whatever is really underneath
  setInteractive: (interactive) => ipcRenderer.send("avatar:interactive", !!interactive),

  // { origin, size, displays[] } — where the floor is, per monitor.
  onWorldLayout: (fn) => ipcRenderer.on("world:layout", (_e, layout) => fn(layout)),

  // { app, title } — fires only when the foreground window actually changes.
  onFocusChanged: (fn) => ipcRenderer.on("focus:changed", (_e, info) => fn(info)),
});
