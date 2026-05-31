const { app, BrowserWindow, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

const BACKEND_PORT = 8787;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
let backendProcess = null;

function startBackend() {
  const backendDir = path.join(__dirname, "..", "backend");
  const isWin = process.platform === "win32";
  const python = isWin ? "python" : "python3";

  backendProcess = spawn(python, ["main.py"], {
    cwd: backendDir,
    stdio: "inherit",
    shell: isWin,
  });

  backendProcess.on("error", (err) => {
    console.error("Failed to start backend:", err);
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: "#0d1117",
    title: "CyberMirror",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const devMode = process.argv.includes("--dev");
  if (devMode) {
    win.loadURL("http://localhost:4200");
  } else {
    const fs = require("fs");
    const candidates = [
      path.join(__dirname, "..", "frontend", "dist", "cybermirror", "browser", "index.html"),
      path.join(__dirname, "..", "frontend", "dist", "cybermirror", "index.html"),
    ];
    const indexPath = candidates.find((p) => fs.existsSync(p)) || candidates[0];
    win.loadFile(indexPath);
  }

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

app.whenReady().then(() => {
  startBackend();
  setTimeout(createWindow, 2000);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (backendProcess) backendProcess.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backendProcess) backendProcess.kill();
});
