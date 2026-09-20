"""
CyberMirror launcher — kills old runs, starts backend + frontend, shows live progress.
Usage:
  CyberMirror.exe           Dev mode (ng serve + browser)
  CyberMirror.exe --prod    Production (ng build + static serve) — faster startup
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BACKEND_PORT = 8787
FRONTEND_PORT = 4200
BACKEND_HEALTH = f"http://127.0.0.1:{BACKEND_PORT}/api/health"
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}"
PID_FILE_NAME = ".cybermirror-pids.json"

# Angular first compile can take several minutes
BACKEND_TIMEOUT = 90
FRONTEND_DEV_TIMEOUT = 600   # 10 min
FRONTEND_PROD_TIMEOUT = 300  # 5 min (includes build)

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_procs: dict[str, subprocess.Popen | None] = {"backend": None, "frontend": None}
_log_threads: list[threading.Thread] = []


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def pid_file() -> Path:
    return project_root() / PID_FILE_NAME


def logs_dir() -> Path:
    d = project_root() / "data" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(msg: str) -> None:
    safe = msg.encode("ascii", errors="replace").decode()
    print(f"[CyberMirror] {safe}", flush=True)


def _configure_console() -> None:
    if sys.platform != "win32":
        return
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def load_pids() -> dict:
    path = pid_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_pids(data: dict) -> None:
    pid_file().write_text(json.dumps(data, indent=2), encoding="utf-8")


def kill_pid(pid: int) -> None:
    if pid <= 0 or pid == os.getpid():
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
        )
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def kill_port(port: int) -> None:
    if sys.platform != "win32":
        return
    try:
        out = subprocess.check_output(
            f'netstat -ano | findstr ":{port}"',
            shell=True,
            text=True,
            errors="ignore",
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.CalledProcessError:
        return
    for line in out.splitlines():
        if "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if parts and parts[-1].isdigit():
            kill_pid(int(parts[-1]))


def stop_all() -> None:
    log("Stopping CyberMirror...")
    for key in ("backend", "frontend", "launcher"):
        pid = load_pids().get(key)
        if pid:
            kill_pid(int(pid))
    kill_port(BACKEND_PORT)
    kill_port(FRONTEND_PORT)
    for p in _procs.values():
        if p and p.poll() is None:
            kill_pid(p.pid)
    save_pids({})
    time.sleep(1)


def _url_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _format_elapsed(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def _progress_bar(ratio: float, width: int = 30) -> str:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(width * ratio)
    return "[" + "=" * filled + ">" + " " * (width - filled - 1) + "]"


def wait_for_service(
    url: str,
    timeout: float,
    label: str,
    proc: subprocess.Popen | None = None,
    hints: list[str] | None = None,
) -> bool:
    """Wait for URL with live progress bar and process health check."""
    hints = hints or []
    start = time.time()
    hint_idx = 0
    last_hint_at = 0

    log(f"Waiting for {label} (timeout {_format_elapsed(int(timeout))})...")
    if hints:
        log(f"  Tip: {hints[0]}")

    while time.time() - start < timeout:
        elapsed = int(time.time() - start)

        if proc is not None and proc.poll() is not None:
            print()
            log(f"ERROR: {label} process exited early (code {proc.returncode})")
            log(f"  Check log: {logs_dir() / f'{label.lower().replace(' ', '_')}.log'}")
            return False

        if _url_ok(url):
            print()
            log(f"{label} ready in {_format_elapsed(elapsed)} OK")
            return True

        ratio = elapsed / timeout
        bar = _progress_bar(ratio)
        status = f"\r[CyberMirror] {label} {bar} {_format_elapsed(elapsed)}"
        print(status, end="", flush=True)

        # Rotate hints every 20 seconds
        if hints and elapsed - last_hint_at >= 20:
            hint_idx = (hint_idx + 1) % len(hints)
            print()
            log(f"  Still working... {hints[hint_idx]}")
            last_hint_at = elapsed

        time.sleep(2)

    print()
    log(f"ERROR: {label} did not respond on {url} within {_format_elapsed(int(timeout))}")
    return False


def _pipe_reader(proc: subprocess.Popen, log_path: Path, prefix: str) -> None:
    """Stream subprocess output to log file and print important lines."""
    keywords = (
        "error", "Error", "ERROR", "failed", "Failed",
        "Compiled", "compiled", "Application bundle", "listening",
        "ready", "Ready", "Local:", "warning", "WARN",
        "Building", "Generating", "chunk", "npm ERR",
    )
    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as f:
            if proc.stdout is None:
                return
            for line in proc.stdout:
                f.write(line)
                f.flush()
                stripped = line.rstrip()
                if any(k in stripped for k in keywords):
                    log(f"  [{prefix}] {stripped[:120]}")
    except Exception:
        pass


def spawn_logged(
    cmd: list[str],
    cwd: Path,
    name: str,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.Popen:
    log_path = logs_dir() / f"{name}.log"
    log(f"Starting {name}... (log: {log_path.name})")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["FORCE_COLOR"] = "0"
    if env_overrides:
        env.update(env_overrides)

    kwargs: dict = {
        "cwd": str(cwd),
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW

    proc = subprocess.Popen(cmd, **kwargs)
    t = threading.Thread(target=_pipe_reader, args=(proc, log_path, name), daemon=True)
    t.start()
    _log_threads.append(t)
    return proc


def resolve_frontend_dist(frontend_dir: Path) -> Path | None:
    """Angular 19+ outputs to dist/cybermirror/browser/; older builds use dist/cybermirror/."""
    for sub in ("browser", ""):
        d = frontend_dir / "dist" / "cybermirror" / sub if sub else frontend_dir / "dist" / "cybermirror"
        if (d / "index.html").exists():
            return d
    return None


def spawn_build(cmd: list[str], cwd: Path, name: str) -> int:
    """Run a blocking command with live output."""
    log_path = logs_dir() / f"{name}.log"
    log(f"Running {name}... (log: {log_path.name})")
    with open(log_path, "w", encoding="utf-8", errors="replace") as f:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if proc.stdout:
            for line in proc.stdout:
                f.write(line)
                f.flush()
                stripped = line.rstrip()
                if stripped and any(k in stripped for k in ("error", "Error", "Building", "complete", "Application")):
                    log(f"  [build] {stripped[:100]}")
        return proc.wait()


def find_python() -> str:
    for name in ("python", "python3", "py"):
        try:
            subprocess.run(
                [name, "--version"],
                capture_output=True,
                check=True,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return name
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    raise RuntimeError("Python not found — install from https://python.org")


def find_npm() -> str:
    for name in ("npm.cmd", "npm"):
        try:
            subprocess.run(
                ["where", name],
                capture_output=True,
                check=True,
                shell=True,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return name
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError("Node.js/npm not found — install from https://nodejs.org")


def check_dependencies(root: Path) -> list[str]:
    issues: list[str] = []
    if not (root / "backend" / "main.py").exists():
        issues.append("Backend folder missing")
    if not (root / "frontend" / "package.json").exists():
        issues.append("Frontend folder missing")
    try:
        find_python()
    except RuntimeError as e:
        issues.append(str(e))
    try:
        find_npm()
    except RuntimeError as e:
        issues.append(str(e))
    return issues


def auto_setup(root: Path, python: str, npm: str) -> None:
    """Install Python/npm deps and Playwright on first run."""
    backend = root / "backend"
    frontend = root / "frontend"
    marker = root / "data" / ".setup_complete"

    if not marker.exists():
        log("First run - installing dependencies (one-time)...")

        req = backend / "requirements.txt"
        if req.exists():
            log("  pip install -r requirements.txt ...")
            subprocess.run(
                [python, "-m", "pip", "install", "-r", str(req)],
                cwd=str(backend),
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            log("  playwright install chromium ...")
            subprocess.run(
                [python, "-m", "playwright", "install", "chromium"],
                cwd=str(backend),
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )

        if (frontend / "package.json").exists() and not (frontend / "node_modules").exists():
            log("  npm install ...")
            subprocess.run(
                [npm, "install"],
                cwd=str(frontend),
                shell=True,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )

        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok", encoding="utf-8")
        log("Setup complete.")
    elif not (frontend / "node_modules").exists():
        log("node_modules missing - running npm install ...")
        subprocess.run(
            [npm, "install"],
            cwd=str(frontend),
            shell=True,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )


def tail_log_errors(name: str, lines: int = 20) -> None:
    path = logs_dir() / f"{name}.log"
    if not path.exists():
        return
    log(f"--- Last {lines} lines of {path.name} ---")
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in content[-lines:]:
            print(f"  | {line[:100]}")
    except Exception:
        pass
    log("--- end log ---")


def start_tray(on_stop, on_open) -> None:
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return

    def make_icon():
        img = Image.new("RGB", (64, 64), color=(13, 17, 23))
        d = ImageDraw.Draw(img)
        d.ellipse((8, 8, 56, 56), fill=(56, 139, 253))
        return img

    def stop(icon, _item):
        icon.stop()
        on_stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open CyberMirror", lambda i, _: on_open()),
        pystray.MenuItem("Stop", stop),
    )
    icon = pystray.Icon("CyberMirror", make_icon(), "CyberMirror", menu)
    threading.Thread(target=icon.run, daemon=True).start()


def main() -> int:
    _configure_console()
    parser = argparse.ArgumentParser(description="CyberMirror Launcher")
    parser.add_argument("--prod", action="store_true", default=True, help="Production mode (default)")
    parser.add_argument("--dev", action="store_true", help="Dev mode — ng serve (slow first compile)")
    args = parser.parse_args()
    use_prod = not args.dev

    root = project_root()
    log("CyberMirror v2 launcher")
    log(f"Project: {root}")

    issues = check_dependencies(root)
    for i in issues:
        log(f"WARNING: {i}")
    if any("missing" in i.lower() or "not found" in i.lower() for i in issues):
        input("Press Enter to exit...")
        return 1

    python = find_python()
    npm = find_npm()
    auto_setup(root, python, npm)

    stop_all()
    backend_dir = root / "backend"
    frontend_dir = root / "frontend"

    # --- Backend ---
    # Use a fresh per-run token and pass it to the UI through the URL fragment.
    # Fragments are not sent to the HTTP server and the frontend removes it
    # immediately after storing the token in sessionStorage.
    api_token = secrets.token_urlsafe(32)
    launch_url = f"{FRONTEND_URL}#api_token={api_token}"
    _procs["backend"] = spawn_logged(
        [python, "main.py"],
        backend_dir,
        "backend",
        env_overrides={"API_TOKEN": api_token},
    )
    if not wait_for_service(BACKEND_HEALTH, BACKEND_TIMEOUT, "Backend", _procs["backend"]):
        tail_log_errors("backend")
        stop_all()
        input("Press Enter to exit...")
        return 1

    # --- Frontend ---
    if use_prod:
        dist = resolve_frontend_dist(frontend_dir)
        if dist is None:
            log("No production build found - building Angular (one-time, ~2-5 min)...")
            code = spawn_build([npm, "run", "build"], frontend_dir, "frontend_build")
            dist = resolve_frontend_dist(frontend_dir)
            if dist is None:
                log(f"ERROR: Frontend build failed (npm exit code {code})")
                tail_log_errors("frontend_build")
                stop_all()
                input("Press Enter to exit...")
                return 1
            if code != 0:
                log(f"Build finished with warnings (exit {code}) - output found, continuing.")
        log(f"Serving production frontend from {dist.name}/...")
        _procs["frontend"] = spawn_logged(
            [python, "-m", "http.server", str(FRONTEND_PORT), "--directory", str(dist)],
            frontend_dir,
            "frontend",
        )
        fe_timeout = 60
        fe_hints = ["Static files - should be quick"]
    else:
        log("")
        log("Starting Angular dev server (ng serve)...")
        log("  First compile often takes 3-10 minutes - progress bar below is normal.")
        log("  Tip: next time use production mode (CyberMirror.bat) for faster startup.")
        log("")
        _procs["frontend"] = spawn_logged([npm, "run", "start"], frontend_dir, "frontend")
        fe_timeout = FRONTEND_DEV_TIMEOUT
        fe_hints = [
            "Angular is compiling TypeScript - first run is slow",
            "Watch for [frontend] Compiled successfully in the log above",
            "Still compiling... large projects need several minutes",
            "If this is your first run, npm install may still be caching",
            "Port 4200 opens only after compile finishes",
        ]

    if not wait_for_service(FRONTEND_URL, fe_timeout, "Frontend", _procs["frontend"], fe_hints):
        tail_log_errors("frontend")
        log("")
        log("Troubleshooting:")
        log("  1. Run: cd frontend && npm install")
        log("  2. Try production mode: CyberMirror.exe --prod")
        log("  3. Or manually: cd frontend && npm start")
        stop_all()
        input("Press Enter to exit...")
        return 1

    save_pids({
        "launcher": os.getpid(),
        "backend": _procs["backend"].pid if _procs["backend"] else 0,
        "frontend": _procs["frontend"].pid if _procs["frontend"] else 0,
    })

    webbrowser.open(launch_url)
    log("")
    log("=" * 50)
    log(f"  CyberMirror is running -> {FRONTEND_URL}")
    log(f"  Backend API          -> http://127.0.0.1:{BACKEND_PORT}")
    log("  Keep this window open. Ctrl+C or tray icon to stop.")
    log("=" * 50)

    start_tray(on_stop=stop_all, on_open=lambda: webbrowser.open(launch_url))

    try:
        while True:
            for name, proc in _procs.items():
                if proc and proc.poll() is not None:
                    log(f"ERROR: {name} stopped unexpectedly (code {proc.returncode})")
                    tail_log_errors(name)
                    stop_all()
                    input("Press Enter to exit...")
                    return 1
            time.sleep(2)
    except KeyboardInterrupt:
        log("Shutting down...")
        stop_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
