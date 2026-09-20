# Changelog

## Unreleased

### Changed
- Removed machine-specific paths and stale references to local OSINT tool folders.
- Made the optional WhatsMyName dataset path portable and project-relative by default.
- Replaced the historical adapter-oriented architecture document with documentation of the current native module architecture.
- Added explicit third-party attribution and licensing notes for external data and services.
- Clarified that scan history is stored locally while network-based modules necessarily send queries to external services.
- Removed the obsolete `tools/` reference document.

### Privacy
- Local configuration, external datasets, runtime secrets, tokens, logs, and generated data remain excluded from version control.
- Public documentation no longer includes developer workstation paths.

## [2.1.0] - 2026-05-31

### Added
- Real PDF export (xhtml2pdf)
- Cooperative scan cancel (batched modules abort)
- Module error display in UI
- 8 email registration probes + Gravatar MD5 fix
- Facebook name search + id URL via Playwright
- URL handle correlator
- API token auth (X-CyberMirror-Token)
- Encrypted profile storage + encrypted secrets file
- Dashboard risk trend + scan picker
- Graph scan selector + risk filter
- Profile/module persistence in Investigation
- Settings: enable/disable modules, clear cache, Arabic UI
- GitHub Actions CI + Docker
- Electron health-check wait

### Security
- HIBP key moved to encrypted `data/secrets.json`
- `runtime_settings.json` secrets gitignored

## [2.0.0] - 2026-05-31

### Added
- Parallel module execution with `asyncio`
- Live findings during a scan
- Cooperative scan cancellation
- Risk reasons and recommendations in Evidence Center
- History pagination and deletion
- Export downloads
- Consent modal before first investigation
- WhatsMyName dataset health check
- Email registration-signal probes
- Finding correlation
- First-run dependency setup in the launcher
- Production-mode launcher

### Changed
- Default app version to 2.0.0
- Removed unused legacy adapter stubs

### Tests
- Added job-store and correlator tests

## [1.0.0] - 2026-05-31

### Added
- Native scan engine with web, username, social, email, phone, breach, domain, and correlation modules
- Angular web UI with Dashboard, Investigation, History, Graph, Settings, and Reports
- Async scans with progress polling
- SQLite persistence
- Relationship graph
- Scan comparison
- Risk scoring and recommendations
- HTML, JSON, and CSV export
- Windows launcher
- Runtime settings
- Optional WhatsMyName dataset support
- Playwright browser checks
