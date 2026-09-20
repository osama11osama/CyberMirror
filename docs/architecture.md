# CyberMirror Architecture

## Overview

CyberMirror is a local-first self-audit application with three main layers:

1. **Angular frontend** for investigations, evidence review, history, graphs, settings, and exports.
2. **FastAPI backend** for API routing, scan orchestration, storage, and report generation.
3. **Built-in scan modules** that perform focused checks and normalize results into a shared `Finding` model.

The current implementation is a native CyberMirror engine. It does not depend on external OSINT command-line applications being installed next to the repository.

## Runtime flow

```text
Identity profile
      |
      v
POST /api/scans
      |
      v
ScanEngine
      |
      +---------------- parallel ----------------+
      |                                          |
      v                                          v
independent scan modules                    live job state
      |                                          |
      +---------------- findings ----------------+
                         |
                         v
                  deduplication
                         |
                         v
                    risk analysis
                         |
                         v
               identity correlation
                         |
                         v
                 SQLite persistence
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
          History      Graph       Export
```

Most independent modules are started concurrently. The identity correlator runs after the first-stage findings are available so it can reason over relationships between results.

## Backend components

### API

`backend/app/api/routes.py` exposes the REST endpoints used by the frontend. The API supports:

- starting and cancelling scans;
- polling scan progress;
- retrieving live and persisted findings;
- listing and deleting historical scans;
- comparing two scans;
- graph generation;
- report export;
- runtime settings.

A local API token protects non-public API routes by default.

### Scan engine

`backend/app/engine/scan_engine.py` is responsible for:

- selecting enabled modules;
- running independent modules concurrently;
- collecting live findings and module errors;
- cooperative cancellation;
- deduplicating results;
- applying risk analysis;
- running post-scan correlation;
- persisting completed findings.

### Built-in modules

| Module | Purpose | Network dependency |
| --- | --- | --- |
| Web Search | Searches public indexed pages for supplied identifiers | DDGS/search provider |
| Username Scanner | Checks public username profile URLs | Public websites; optional WMN dataset |
| Social Browser | Browser-based checks for selected social profiles | Public social websites via Playwright |
| Email Scanner | Public web exposure and registration-signal checks | Public web and selected external endpoints |
| Phone Scanner | Searches indexed public references to a phone number | DDGS/search provider |
| Breach Scanner | Queries breach exposure | HIBP API when configured; limited search fallback |
| Domain Scanner | WHOIS and indexed references for a supplied website | WHOIS and web search |
| Identity Correlator | Relates findings and profile identifiers | No external network requirement |

All modules return the same `Finding` schema so the rest of the application can process results consistently.

## Username data

CyberMirror has two sources for username site definitions:

1. a small fallback catalog committed as `backend/app/modules/username/sites.json`;
2. an optional external `wmn-data.json` supplied by the user.

The external WhatsMyName dataset is loaded at runtime and is not vendored in this repository. The fallback catalog has its own attribution notice because some definitions are adapted from or cross-checked against WhatsMyName. See `backend/app/modules/username/ATTRIBUTION.md`.

The default external dataset location is project-local:

```text
data/wmn-data.json
```

This file is ignored by Git.

## Storage and privacy

Local runtime state is stored under `data/` and `exports/`.

Important files include:

- `data/cybermirror.sqlite3` — scan and finding history;
- `data/runtime_settings.json` — UI-configurable runtime settings;
- `data/secrets.json` — encrypted application secrets;
- `data/.api_token` — local API authentication token;
- `data/.encryption_key` — local encryption key;
- `data/cache/` — temporary network result cache;
- `data/logs/` — application logs;
- `exports/` — generated reports.

These paths are excluded from version control.

Sensitive profile JSON stored in SQLite is encrypted when encryption is enabled. This protects local-at-rest data from casual inspection, but it is not a substitute for operating-system access controls or full-disk encryption.

## Network boundary

CyberMirror is local-first, not offline-only. A scan can make outbound requests containing the identifier being checked.

Examples include:

- public search queries;
- username profile URL requests;
- Playwright visits to public social pages;
- HIBP API requests;
- selected account-registration signal checks.

The frontend and scan history remain local by default, but external sites can still observe normal network requests made during a scan.

## Frontend

The Angular application provides:

- dashboard and risk trends;
- investigation form and module selection;
- live scan progress;
- evidence/scan detail;
- relationship graph visualization;
- scan history and comparison;
- settings;
- report generation/download.

Cytoscape.js is used for relationship visualization and ECharts for dashboard charts.

## Configuration

Static defaults live in `backend/app/config.py`. User-editable settings are persisted separately under `data/runtime_settings.json`.

Machine-specific absolute paths are intentionally not part of repository defaults. Relative paths are resolved from the repository root.

The example environment file documents supported environment overrides without embedding workstation-specific values.

## Security boundaries

CyberMirror applies several local safeguards:

- API token authentication for local API requests;
- encrypted profile storage when cryptography support is available;
- separate encrypted secret storage;
- Git ignores for runtime secrets and personal scan data;
- module-level rate limiting and caching;
- explicit cancellation checks in long-running modules.

The application should still be treated as a research/self-audit tool. External services, websites, and page structures can change without notice.

## Third-party boundary

CyberMirror does not vendor third-party OSINT applications. Python and JavaScript libraries are installed from their normal package ecosystems.

External datasets and services keep their own licenses and terms. See [../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
