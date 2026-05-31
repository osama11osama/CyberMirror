# Changelog

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
