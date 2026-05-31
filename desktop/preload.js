const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("cyberMirror", {
  apiBase: "http://127.0.0.1:8787/api",
  slogan: "See Yourself as the Internet Sees You",
});
