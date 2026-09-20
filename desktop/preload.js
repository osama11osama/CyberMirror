const { contextBridge, ipcRenderer } = require("electron");

const apiToken = ipcRenderer.sendSync("cybermirror:get-api-token");

contextBridge.exposeInMainWorld("cyberMirror", {
  apiBase: "http://127.0.0.1:8787/api",
  apiToken,
  slogan: "See Yourself as the Internet Sees You",
});
