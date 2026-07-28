// Preload: the only bridge between the sandboxed renderer and the main process.
// Phase 0 exposes just window controls. Phase 0-wiring will add a `send`/`onMessage`
// pair here for the websocket — kept in one place so the renderer stays clean.

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desk", {
  quit: () => ipcRenderer.send("app:quit"),
  moveBy: (dx, dy) => ipcRenderer.send("window:move", { dx, dy }),
});
