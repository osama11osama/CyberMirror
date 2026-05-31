# CyberMirror v1.0.0

**See Yourself as the Internet Sees You**

CyberMirror is a **local OSINT self-audit platform**. Enter a name, username, email, or phone — the native engine searches the public web and hundreds of platforms, scores risk, and saves everything locally.

> **Legal use only:** self-audit or with explicit permission. Public data only.

---

## Version 1.0.0 — What's Included

| Feature | Description |
|---------|-------------|
| **8 native modules** | Web search, username scan (600+ sites), Playwright social browser, email, phone, breach check, domain/WHOIS, identity correlator |
| **Investigation workspace** | Enter profile → async scan with progress bar |
| **Evidence Center** | Filterable results: where, what, source, risk |
| **Relationship graph** | Cytoscape graph — click node for details, double-click to open URL |
| **Scan history** | All scans saved in SQLite — click row to view without re-scanning |
| **Compare scans** | Select 2 history entries → see new/removed findings |
| **Dashboard** | Risk score, charts, latest scan stats |
| **Export** | HTML, JSON, CSV reports |
| **Settings** | Scan limits, Playwright toggle, HIBP key, scheduled rescans |
| **One-click launcher** | `CyberMirror.exe` / `.bat` — kills old processes, starts backend + frontend |

---

## Quick Start

### First-time setup

```powershell
cd backend
pip install -r requirements.txt
playwright install chromium

cd ..\frontend
npm install
```

### Run (recommended — production mode)

```powershell
# Double-click or run:
CyberMirror-Prod.bat
```

Or build the exe once:

```powershell
cd launcher
.\build-exe.bat
# Then double-click CyberMirror.exe --prod
```

### What the launcher does

1. Stops any previous backend (port **8787**) and frontend (port **4200**)
2. Starts Python FastAPI backend
3. Serves the Angular UI (prod build) or `ng serve` (dev)
4. Opens **http://localhost:4200** in your browser
5. Shows progress bar while starting

---

## Manual start (developers)

```powershell
# Terminal 1 — Backend
cd backend
python main.py

# Terminal 2 — Frontend
cd frontend
npm start
```

Backend API: `http://127.0.0.1:8787/api`  
Frontend: `http://localhost:4200`

---

## How It Works

```
You enter profile (name, username, email, phone…)
        ↓
POST /api/scans  →  background scan job
        ↓
Modules run (web search, 600+ username checks, Playwright, …)
        ↓
Findings deduplicated → risk analyzed → saved to SQLite
        ↓
View in Evidence Center / Graph / History / Export
```

### Native engine modules

| ID | Module | What it does |
|----|--------|--------------|
| `web_search` | Web Search | DuckDuckGo with site-specific queries (facebook.com, instagram.com, …) |
| `username_scan` | Username Scanner | 600+ platforms via WMN detection patterns |
| `social_browser` | Social Browser | Playwright headless checks for Facebook, Instagram, LinkedIn, TikTok |
| `email_scan` | Email Scanner | Public email exposure on the web |
| `phone_scan` | Phone Scanner | Phone number web search |
| `breach_scan` | Breach Scanner | Have I Been Pwned (optional API key) |
| `domain_scan` | Domain Scanner | WHOIS + site mentions for personal websites |
| `identity_correlator` | Identity Correlator | Risk linkage across profile fields |

### Data storage (all local)

| Path | Contents |
|------|----------|
| `data/cybermirror.sqlite3` | Scans, findings, profiles |
| `data/logs/` | Backend + launcher logs |
| `data/cache/` | Web search result cache |
| `exports/` | Exported HTML/JSON/CSV reports |

---

## Project structure

```
CyberMirror/
├── backend/           FastAPI + native OSINT engine
│   └── app/modules/   web_search, username, social, email, phone, breach, domain
├── frontend/          Angular 19 UI
├── launcher/          One-click Windows launcher + exe builder
├── desktop/           Optional Electron wrapper
├── data/              SQLite + logs (created at runtime)
└── exports/           Report exports
```

---

## Configuration

Edit in **Settings** UI or `data/runtime_settings.json`:

- `username_scan_limit` — max WMN platforms (default 600)
- `web_search_max_queries` — DuckDuckGo query count
- `wmn_data_path` — path to WhatsMyName JSON (data only)
- `playwright_enabled` — browser checks for social platforms
- `hibp_api_key` — optional breach API key
- `schedule_enabled` — automatic weekly rescan

---

## API overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Backend status |
| `/api/modules` | GET | Available scan modules |
| `/api/scans` | POST | Start scan (async) |
| `/api/scans/{id}/status` | GET | Scan progress |
| `/api/scans/{id}` | GET | Full scan + findings |
| `/api/scans/compare/{a}/{b}` | GET | Compare two scans |
| `/api/scans/{id}/graph` | GET | Graph data |
| `/api/scans/{id}/export` | POST | Export report |

---

## Tags & releases

| Tag | Description |
|-----|-------------|
| **v1.0.0** | First stable release — native engine, history, graph, launcher |

---

## License & ethics

For **personal self-audit** or authorized investigations only.  
Do not use against others without consent.  
All data stays on your machine.

---

## Extending

1. Create a class in `backend/app/modules/` extending `NativeModule`
2. Register in `backend/app/modules/registry.py`
3. Module appears automatically in the UI
