# CyberMirror — Architecture Document

**Slogan:** See Yourself as the Internet Sees You  
**Version:** 0.1.0 (Phase 1)  
**Date:** 2026-05-31

---

## 1. Executive Summary

CyberMirror is a desktop OSINT **self-audit** platform that unifies multiple open-source intelligence tools behind a single FastAPI backend, Angular frontend, and Electron shell. It does **not** copy third-party code. Each tool is invoked through a **license-respecting adapter** (subprocess CLI or documented public API), with normalized output stored in SQLite and visualized in a SOC-style dashboard.

**Scope constraint:** Personal audit or explicit permission only. Passive collection. No intrusive scanning, credential abuse, or dark-web modules.

**Local tool paths (discovered):** Tools live under `C:\استخبارات\OSINT_tools\`, not directly under `C:\استخبارات\`. CyberMirror defaults point to `../OSINT_tools/{tool}` relative to the project root.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Electron Desktop Shell                       │
│  desktop/main.js  →  loads Angular SPA  →  spawns FastAPI       │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP (localhost:8787)
┌────────────────────────────▼────────────────────────────────────┐
│                      FastAPI Backend                               │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ REST API     │  │ Scan Engine  │  │ Risk + Recommendations │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬────────────┘ │
│         │                 │                       │              │
│  ┌──────▼─────────────────▼───────────────────────▼────────────┐ │
│  │              Provider Adapter Layer (BaseAdapter)            │ │
│  └──────┬──────┬──────┬──────┬──────┬──────┬──────┬───────────┘ │
└─────────┼──────┼──────┼──────┼──────┼──────┼──────┼─────────────┘
          │      │      │      │      │      │      │
     Maigret Sherlock Blackbird Holehe Social  Spider Recon GHunt
                              WMN*   Analyzer Foot    -ng
                              (via Blackbird/Maigret data)
```

### Data Flow

1. User submits **Identity Profile** (name, username, email, phone, location, website, company).
2. **Scan Engine** selects enabled providers from settings.
3. Each **Adapter** runs tool → parses output → returns `Finding[]`.
4. **Risk Engine** scores each finding (Critical → Info).
5. **Recommendations Engine** attaches actionable advice.
6. **Graph Builder** creates Cytoscape nodes/edges for relationship view.
7. Results persisted to **SQLite**; reports exported to `exports/`.

---

## 3. Tool Inspection Matrix

### 3.1 Maigret

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Username dossier across 3,000+ sites; extracts profile metadata |
| **License** | MIT |
| **Location** | `OSINT_tools/maigret` |
| **Run** | `maigret USERNAME` or `pip install maigret` |
| **CLI output** | `--json simple`, `--json ndjson`, `--html`, `--pdf` |
| **Python API** | `import maigret` — embeddable (see docs) |
| **Entry** | `pyproject.toml` → console script `maigret` |
| **Strengths** | Largest site DB, recursive search, rich reports, no API keys |
| **Weaknesses** | Slow full scan (`-a`), CAPTCHA/rate limits, commercial license for SaaS resale |
| **Integration** | **Subprocess adapter** (Phase 2): `maigret {user} --json simple -fo {tmpdir}` |
| **Ethics** | Username-only OSINT; educational / authorized use |

### 3.2 Sherlock

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Hunt usernames across 400+ social networks |
| **License** | MIT |
| **Location** | `OSINT_tools/sherlock` |
| **Run** | `sherlock user123` or `pipx install sherlock-project` |
| **CLI output** | `--json FILE`, `--csv`, `--xlsx`, text files |
| **Entry** | `sherlock_project/sherlock.py` |
| **Strengths** | Fast, mature, low false positives, JSON export |
| **Weaknesses** | Username only; fewer sites than Maigret |
| **Integration** | **Subprocess**: `sherlock {user} --json {path} --print-found` |
| **Ethics** | Public profile enumeration only |

### 3.3 Blackbird

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Username + email search on 600+ platforms; integrates WhatsMyName data |
| **License** | Check repo (educational disclaimer; MIT-style usage) |
| **Location** | `OSINT_tools/blackbird` |
| **Run** | `python blackbird.py --username X` / `--email X` |
| **CLI output** | `--csv`, `--pdf`, JSON via `saveToJson` |
| **Entry** | `blackbird.py` → `src/modules/` |
| **Strengths** | Dual username/email, WMN integration, optional AI profiling |
| **Weaknesses** | Python deps + optional AI key; heavier than Sherlock |
| **Integration** | **Subprocess** from configured `BLACKBIRD_PATH` |
| **Ethics** | Educational disclaimer in README |

### 3.4 WhatsMyName

| Attribute | Detail |
|-----------|--------|
| **Purpose** | **Data project** — JSON detection rules for username checkers |
| **License** | CC BY-SA 4.0 |
| **Location** | `OSINT_tools/WhatsMyName` |
| **Run** | No standalone checker (removed 2023); use `wmn-data.json` |
| **Data file** | `wmn-data.json` |
| **Strengths** | Community-maintained site list, low FP when used correctly |
| **Weaknesses** | Not a runnable tool alone; needs a checker (Blackbird, Naminter, etc.) |
| **Integration** | **Indirect** via Blackbird/Maigret/Sherlock; optional **WMN adapter** reads JSON + lightweight HTTP checks (Phase 2+) |
| **Ethics** | Share-alike license — attribute WMN if distributing derived data |

### 3.5 Holehe

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Email → registered accounts on 120+ sites (password reset flow) |
| **License** | GPL-3.0 |
| **Location** | `OSINT_tools/holehe` |
| **Run** | `holehe email@example.com` |
| **Python API** | Async modules: `from holehe.modules... import ...` |
| **Output** | Per-module dict: `{name, exists, rateLimit, emailrecovery, phoneNumber}` |
| **Strengths** | Best-in-class email footprint; does not alert target |
| **Weaknesses** | GPL — **linking/copying code requires GPL compliance**; use subprocess isolation |
| **Integration** | **Subprocess only** (keeps CyberMirror backend separate from GPL code) |
| **Ethics** | Self-audit / authorized email only |

### 3.6 Social Analyzer

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Profile discovery + metadata across 1000+ sites; confidence scoring 0–100 |
| **License** | AGPL-3.0 (verify repo LICENSE) |
| **Location** | `OSINT_tools/social-analyzer` |
| **Run** | `npm start` (web :9005), `nodejs app.js --username X`, `python3 app.py --username X` |
| **Output** | JSON analysis files, screenshots optional |
| **Strengths** | Rich detection modules, metadata graph, multi-technique |
| **Weaknesses** | Node + Python deps, Firefox/Chrome for full features, AGPL obligations |
| **Integration** | **Subprocess** CLI with `--output json`; avoid embedding AGPL code |
| **Ethics** | Law-enforcement oriented; restrict to self-audit in CyberMirror |

### 3.7 SpiderFoot

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Full OSINT automation — 200+ modules, web UI, correlation engine |
| **License** | MIT |
| **Location** | `OSINT_tools/spiderfoot` |
| **Run** | `python sf.py -l 127.0.0.1:5001` |
| **API** | Built-in web UI + scan API on local server |
| **Output** | SQLite, CSV, JSON, GEXF |
| **Strengths** | Most comprehensive; module ecosystem; correlation rules |
| **Weaknesses** | Heavy; many modules are aggressive — **must whitelist passive modules only** |
| **Integration** | **Phase 4**: subprocess + REST to local SpiderFoot; module allowlist |
| **Passive modules** | `sfp_accounts`, `sfp_google`, `sfp_email`, `sfp_wikipedia`, etc. |
| **Blocked modules** | Port scan, intrusive crawl, dark web, breach dumps without consent |

### 3.8 Recon-ng

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Modular recon framework (Metasploit-like CLI) |
| **License** | Free software (see repo; historically GPL-style) |
| **Location** | `OSINT_tools/recon-ng` |
| **Run** | `./recon-ng` interactive CLI |
| **Output** | Workspace SQLite, module JSON |
| **Strengths** | Professional workflow, many passive modules |
| **Weaknesses** | CLI-first, steep learning curve, not GUI-native |
| **Integration** | **Phase 4**: subprocess with scripted module chains; passive modules only |

### 3.9 GHunt

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Google account / email OSINT (Gaia ID, Drive, etc.) |
| **License** | AGPL-3.0 |
| **Location** | `OSINT_tools/GHunt` |
| **Run** | `pipx install ghunt` → `ghunt email X --json out.json` |
| **Requirements** | **Google login** via companion browser extension |
| **Strengths** | Deep Google-specific intelligence |
| **Weaknesses** | Requires authenticated session; AGPL; offensive framing |
| **Integration** | **Optional Phase 4** — subprocess after user completes `ghunt login`; disabled by default |
| **CyberMirror policy** | Opt-in only; warn user about Google ToS |

---

## 4. License Compliance Strategy

| Tool | License | CyberMirror approach |
|------|---------|---------------------|
| Maigret, Sherlock, SpiderFoot | MIT | Subprocess or documented API — no copy required |
| Holehe | GPL-3.0 | **Subprocess only** — no import of holehe modules into proprietary code |
| Social Analyzer, GHunt | AGPL-3.0 | **Subprocess only**; disclose if user enables; no code merging |
| WhatsMyName | CC BY-SA 4.0 | Attribute source; do not republish modified JSON without SA |
| Blackbird | Educational/MIT-like | Subprocess; respect disclaimer |

CyberMirror backend code: **MIT** (recommended). GPL/AGPL tools run as **external processes**.

---

## 5. Unified Data Model

### IdentityProfile
```json
{
  "full_name": "Jane Doe",
  "username": "janedoe",
  "email": "jane@example.com",
  "phone": "+15550100",
  "location": "New York, US",
  "website": "https://example.com",
  "company": "Acme Corp"
}
```

### Finding (Evidence Center)
```json
{
  "id": "uuid",
  "scan_id": "uuid",
  "source": "maigret",
  "provider": "MaigretAdapter",
  "category": "username_discovery",
  "platform": "GitHub",
  "title": "Profile found",
  "url": "https://github.com/janedoe",
  "description": "Public profile with repos",
  "snippet": "...",
  "confidence": 0.92,
  "risk_level": "Medium",
  "risk_reason": "Username linked to public repos",
  "recommendation": "Review public repository visibility",
  "timestamp": "2026-05-31T12:00:00Z",
  "raw": {}
}
```

### Graph Node Types
`Person | Email | Username | Phone | Website | SocialAccount | PublicProfile | Location | Company`

---

## 6. Risk Engine

| Level | Criteria |
|-------|----------|
| **Critical** | Phone + name + location together in one public artifact |
| **High** | Email + real identity; recovery phone/email exposed |
| **Medium** | Social profile connected to real name/location |
| **Low** | Generic username match, weak linkage |
| **Info** | Informational mention, no PII |
| **Unknown** | Insufficient context |

---

## 7. Module Mapping

| CyberMirror Module | Providers |
|--------------------|-----------|
| Identity Search | Query builder + optional SerpAPI/DuckDuckGo (future) |
| Username Discovery | Maigret, Sherlock, Blackbird, WMN (via Blackbird) |
| Email Exposure | Holehe |
| Social Discovery | Social Analyzer |
| Advanced Intelligence | SpiderFoot (passive), Recon-ng (passive), GHunt (opt-in) |
| Relationship Graph | Internal graph builder from findings |
| Reports | HTML, JSON, CSV generators |
| Dashboard | Aggregations from SQLite |

---

## 8. Technology Stack

| Layer | Stack |
|-------|-------|
| Desktop | Electron + electron-builder |
| Frontend | Angular 19, Angular Material, PrimeNG, ECharts, Cytoscape.js |
| Backend | Python 3.11+, FastAPI, Pydantic v2, Uvicorn, SQLite |
| Config | `.env` — tool paths, SERPAPI_KEY |

---

## 9. API Endpoints (Phase 1)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/settings` | Current configuration (masked secrets) |
| PUT | `/api/settings` | Update tool paths |
| POST | `/api/scans` | Start scan |
| GET | `/api/scans` | List scans |
| GET | `/api/scans/{id}` | Scan detail + findings |
| GET | `/api/scans/{id}/graph` | Cytoscape graph JSON |
| GET | `/api/scans/{id}/dashboard` | Dashboard stats |
| POST | `/api/scans/{id}/export` | Export HTML/JSON/CSV |
| GET | `/api/providers` | Available providers + status |

---

## 10. Development Phases

### Phase 1 ✅ (this delivery)
- Tool inspection + architecture doc
- FastAPI backend skeleton
- Provider abstraction + stub adapters
- SQLite schema
- Angular + Electron scaffold
- Dark SOC theme shell

### Phase 2
- Wire Maigret, Sherlock, Blackbird, Holehe adapters (subprocess)
- Real scan execution + finding normalization

### Phase 3
- Dashboard charts (ECharts)
- Risk + recommendations engines (full rules)
- Cytoscape relationship graph
- HTML/JSON/CSV reports

### Phase 4
- SpiderFoot passive integration
- Recon-ng passive modules
- GHunt opt-in module
- Advanced analytics

### Future Roadmap
- Breach monitoring (HIBP API)
- PDF export
- AI recommendations
- Screenshot capture
- Timeline analysis
- Enterprise multi-user

---

## 11. Security & Ethics

1. **Consent banner** on first launch — self-audit or authorized subjects only.
2. **Local-only storage** — `data/` and `exports/` gitignored.
3. **No hardcoded paths or API keys.**
4. **Provider allowlists** — disable aggressive SpiderFoot/Recon-ng modules.
5. **Audit log** — every scan records timestamp, profile hash, providers used.
6. **GHunt disabled by default** — requires explicit opt-in + Google authentication.

---

## 12. Directory Structure

```
CyberMirror/
├── desktop/           # Electron main process
├── frontend/          # Angular SPA
├── backend/           # FastAPI application
│   ├── app/
│   │   ├── adapters/  # Tool wrappers
│   │   ├── api/       # Routes
│   │   ├── engine/    # Scan orchestration
│   │   ├── models/    # Pydantic schemas
│   │   ├── services/  # Risk, graph, reports
│   │   └── storage/   # SQLite
│   └── requirements.txt
├── tools/             # Symlinks or path refs to OSINT_tools/*
├── data/              # SQLite DB
├── exports/           # Generated reports
└── docs/              # This document
```

---

*CyberMirror — See Yourself as the Internet Sees You.*
