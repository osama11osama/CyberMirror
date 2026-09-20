# CyberMirror

CyberMirror is a local-first OSINT self-audit application for reviewing a person's public digital footprint. It combines a FastAPI backend, an Angular frontend, local SQLite history, and a set of built-in scanners for public web, username, email, phone, domain, breach, and social-profile checks.

> Use CyberMirror only for your own identifiers or for subjects who have explicitly authorized the investigation.

## What it does

CyberMirror can:

- run multiple scan modules concurrently;
- search the public web for identity-related results;
- check public username profile URLs across a built-in catalog;
- optionally extend username coverage with the WhatsMyName dataset;
- inspect selected social profile URLs with Playwright;
- look for public email and phone exposure;
- query Have I Been Pwned when the user supplies an API key;
- inspect public WHOIS/domain information;
- correlate findings into a relationship graph;
- store scan history locally;
- compare scans and export reports.

The project does **not** vendor or execute third-party OSINT applications. Optional external data and services are documented below.

## Architecture

```text
Angular UI
   |
   v
FastAPI REST API
   |
   v
Scan Engine
   |-- Web Search
   |-- Username Scanner
   |-- Social Browser
   |-- Email Scanner
   |-- Phone Scanner
   |-- Breach Scanner
   |-- Domain Scanner
   `-- Identity Correlator
   |
   +--> Risk analysis
   +--> SQLite history
   +--> Graph / reports
```

A more detailed description is available in [docs/architecture.md](docs/architecture.md).

## Privacy model

CyberMirror stores its scan database, logs, cache, generated reports, runtime settings, API token, and encryption material under local runtime directories that are excluded from version control.

Local storage does **not** mean that scanning is offline. Network-based modules send the identifiers needed for a check to external websites or services. For example:

- web-search modules send search queries to the configured search provider;
- username and social checks request public profile URLs;
- the optional HIBP integration sends the queried email address to the HIBP API;
- some email checks query public account-registration endpoints.

Use only identifiers you are authorized to investigate, and review the terms and privacy policies of external services before enabling or distributing integrations.

## Quick start

### Requirements

- Python 3.10+
- Node.js 20+ recommended
- Chromium installed through Playwright for browser-based checks

### Backend

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r backend/requirements.txt
playwright install chromium
```

### Frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### Run

On Windows:

```text
CyberMirror.bat
```

Or run the services manually:

```bash
# terminal 1
cd backend
python main.py

# terminal 2
cd frontend
npm start
```

Backend API: `http://127.0.0.1:8787/api`  
Frontend: `http://localhost:4200`

### Local API authentication

The normal launcher and Electron wrapper generate a fresh API token for each run. The token is passed to the backend and injected into the local UI without exposing it through `/api/health`. Browser sessions keep the credential in `sessionStorage`, and authenticated downloads send it in the `X-CyberMirror-Token` header.

The health endpoint remains public so launchers can check readiness, but it does not return API credentials.

For manual frontend/backend development, either:

- keep authentication enabled, set the same `API_TOKEN` for the backend, and open the frontend once with `#api_token=<token>`; the UI immediately removes the fragment after importing the token; or
- set `API_AUTH_ENABLED=false` only for a localhost-bound development session.

Do not expose the backend beyond localhost when authentication is disabled.

## Optional WhatsMyName dataset

CyberMirror includes a small fallback username catalog. For broader coverage, it can load the community-maintained [WhatsMyName](https://github.com/WebBreacher/WhatsMyName) dataset at runtime.

Place `wmn-data.json` at:

```text
data/wmn-data.json
```

or set `WMN_DATA_PATH` in your local `.env`.

The upstream dataset is **not** committed to this repository. Its license and attribution requirements remain in effect. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [backend/app/modules/username/ATTRIBUTION.md](backend/app/modules/username/ATTRIBUTION.md).

## Configuration

Copy `.env.example` to `.env` and change only the values you need.

Important local/runtime files are intentionally ignored by Git:

- `.env`
- `data/wmn-data.json`
- `data/runtime_settings.json`
- `data/secrets.json`
- `data/.api_token`
- `data/.encryption_key`
- SQLite databases, cache, logs, and exports

Do not commit API keys, personal scan data, generated reports, or machine-specific paths.

## Project structure

```text
CyberMirror/
├── backend/             FastAPI application and scan engine
│   ├── app/
│   │   ├── api/         REST routes
│   │   ├── engine/      scan orchestration and job state
│   │   ├── modules/     built-in scan modules
│   │   ├── services/    risk, graph, auth, crypto, reporting
│   │   └── storage/     SQLite persistence
│   └── tests/
├── frontend/            Angular application
├── launcher/            Windows launcher and build helpers
├── desktop/             optional Electron wrapper
├── docs/                architecture documentation
├── data/                local runtime data (ignored except .gitkeep)
└── exports/             generated reports (ignored except .gitkeep)
```

## Development

Backend tests:

```bash
cd backend
python -m pytest tests/ -q
```

Frontend build:

```bash
cd frontend
npm ci
npm run build
```

GitHub Actions runs both checks for pushes and pull requests targeting `main`.

## Third-party software and data

CyberMirror uses normal Python and JavaScript dependencies installed through package managers and can interact with external data/services. Those projects retain their own licenses and terms.

The username fallback catalog has a separate attribution/licensing notice because some detection definitions are adapted from or cross-checked against WhatsMyName data. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Responsible use

CyberMirror is intended for defensive self-audit, education, and authorized research. It is not designed for credential theft, unauthorized account access, harassment, or intrusive surveillance.

Public information can still be personal data. Users are responsible for complying with applicable law, platform terms, and authorization requirements.

## License

CyberMirror-authored source code is copyright © 2026 osama11osama. All rights reserved unless a file explicitly states otherwise.

Third-party data and dependencies are governed by their respective licenses. In particular, the username catalog attribution is documented separately.
