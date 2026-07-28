// Launcher for `npm start`.
//
// Exists for one reason: VS Code's extension host sets ELECTRON_RUN_AS_NODE=1,
// and that variable is inherited by anything you launch from its integrated
// terminal. With it set, the electron binary runs as plain Node — so
// `require("electron")` hands back the path to the executable (a string)
// instead of the API, and main.js dies on `ipcMain.on` of undefined.
//
// So: strip the variable, then spawn electron for real.

const { spawn } = require("child_process");
const path = require("path");

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

const electron = require("electron"); // the npm shim: resolves to the binary path
const root = path.join(__dirname, "..");

const child = spawn(electron, [root, ...process.argv.slice(2)], {
  env,
  stdio: "inherit",
});

child.on("close", (code) => process.exit(code ?? 0));
