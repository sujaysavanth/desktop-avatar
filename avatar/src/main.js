// Electron main process.
// Creates a transparent, frameless, always-on-top window that holds the avatar.
// Phase 0: no websocket yet — this just proves the window + character render.

const { app, BrowserWindow, ipcMain, screen } = require("electron");
const path = require("path");

let win;

function createWindow() {
  const { width } = screen.getPrimaryDisplay().workAreaSize;

  win = new BrowserWindow({
    width: 360,
    height: 520,
    // sit in the bottom-right corner by default
    x: width - 380,
    y: 120,
    frame: false, // no title bar / chrome
    transparent: true, // see-through background
    alwaysOnTop: true, // floats above other windows
    resizable: false,
    skipTaskbar: true, // don't show in the taskbar
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // keep it above full-screen apps too
  win.setAlwaysOnTop(true, "screen-saver");
  win.loadFile(path.join(__dirname, "index.html"));

  // Uncomment to debug rendering:
  // win.webContents.openDevTools({ mode: "detach" });
}

// --- window control from the renderer (drag handle, quit button) ---
ipcMain.on("app:quit", () => app.quit());

ipcMain.on("window:move", (_e, { dx, dy }) => {
  if (!win) return;
  const [x, y] = win.getPosition();
  win.setPosition(x + Math.round(dx), y + Math.round(dy));
});

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
