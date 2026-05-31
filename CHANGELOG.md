# Changelog

## [2.0.0] - 2026-05-31

Major performance and UX release.

### Added
- **Parallel module execution** — independent scanners run concurrently via `asyncio.gather`
- **Live findings** — results stream during scan (`GET /api/scans/{id}/findings/live`)
- **Cancel scan** — stop a running job (`POST /api/scans/{id}/cancel`)
- **Recommendations column** — risk reason + actionable advice in Evidence Center
- **History pagination** — page through scans, delete individual entries
- **Export download** — browser download via `/export/{format}/download`
- **Consent modal** — legal/ethical use acknowledgment before first scan
- **WMN health warning** — Settings shows alert when WhatsMyName data is missing
- **Email service probes** — Spotify, Twitter/X, Adobe registration signals
- **Real correlator** — cross-platform linkage after all modules finish
- **Launcher auto-setup** — first run installs pip/npm deps + Playwright
- **Production mode default** — `CyberMirror.bat` uses `--prod` by default

### Changed
- Default app version → **2.0.0**
- Removed unused legacy `adapters/` stubs

### Tests
- Added `test_job_store.py`, `test_correlator.py`

---

## [1.0.0] - 2026-05-31

First public release.

### Added
- Native OSINT engine with 8 modules (web search, username scan, social browser, email, phone, breach, domain, correlator)
- Angular 19 web UI: Dashboard, Investigation, History, Graph, Settings, Reports
- Async scans with progress polling
- SQLite persistence — view saved scans without re-scanning
- Relationship graph with node click (details) and double-click (open URL)
- Scan comparison (2 selected history entries)
- Risk scoring and recommendations engine
- Export HTML, JSON, CSV
- Windows launcher (`CyberMirror.exe`, `.bat`, `--prod` mode)
- Settings UI for scan limits, Playwright, HIBP, scheduled rescans
- WMN data integration (600+ platforms)
- Playwright browser checks for Facebook, Instagram, LinkedIn, TikTok

### Requirements
- Python 3.10+
- Node.js LTS
- Optional: WhatsMyName JSON for full platform coverage
