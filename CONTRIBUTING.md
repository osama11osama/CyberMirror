# Contributing to CyberMirror

Thanks for helping improve CyberMirror. This guide covers local setup, Docker, tests, pull requests, scanners, and privacy rules.

## Principles

- Prefer **small, focused pull requests** linked to an issue.
- Match existing code style; keep diffs minimal.
- Never commit secrets, scan databases, personal identifiers, or machine-specific absolute paths.
- Use CyberMirror only for authorized self-audit / research (see README responsible-use notes).

## Local setup

### Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements.txt
playwright install chromium
```

### Frontend

```bash
cd frontend
npm ci
npm run build   # required for CyberMirror.bat / Docker-style static UI
# npm start     # optional Angular dev server on :4200
```

### Run

- Windows: double-click `CyberMirror.bat` (keep the console open).
- Manual: backend `python backend/main.py`, frontend `npm start` or serve `frontend/dist`.
- API health: `http://127.0.0.1:8787/api/health`
- UI (dev): `http://localhost:4200`

Copy `.env.example` to `.env` only when you need overrides. Defaults bind the API to `127.0.0.1`.

## Docker

```bash
docker compose up --build
```

- App / API: `http://localhost:8787` (UI served from the image when built; API under `/api`)
- Health: `http://localhost:8787/api/health`
- Bundled UI uses same-origin `/api`. Unlock with the in-app token form or `#api_token=<token>` after reading `data/.api_token` — HTTP endpoints never return the API token.
- Compose sets `HOST=0.0.0.0` so the published port works; local non-Docker defaults remain localhost.
- Volumes `cm-data` and `cm-exports` persist SQLite, token, logs, and exports.
- Optional: set `API_TOKEN` in Compose to pin a stable credential.
- Playwright/Chromium install is **fail-closed** in the Dockerfile (build fails if browser deps cannot install).

## Tests

```bash
cd backend && python -m pytest tests/ -q
cd frontend && npm ci && npm run build
```

Integration coverage lives in `backend/tests/integration/` (temp DB, mocked scanners, export/auth/encryption). Do not add uncontrolled live OSINT calls to CI tests.

Evidence/provenance model: [docs/evidence-model.md](docs/evidence-model.md).

## Code map

| Area | Path |
|------|------|
| API routes | `backend/app/api/routes.py` |
| Scan orchestration | `backend/app/engine/scan_engine.py` |
| Module registry | `backend/app/modules/registry.py` |
| Scanners | `backend/app/modules/*/scanner.py` |
| Angular UI | `frontend/src/app/` |

## Adding or changing a scanner

1. Implement a `NativeModule` under `backend/app/modules/<id>/`.
2. Register it in `backend/app/modules/registry.py` (`NATIVE_MODULES`).
3. Use `FindingOutcome` correctly (confirmed / negative / inconclusive / system).
4. Add or update tests under `backend/tests/`.
5. Do **not** copy incompatible third-party OSINT tools or licensed datasets into the repo. Prefer documented optional runtime data (e.g. WhatsMyName via `data/wmn-data.json`) and keep attribution in `THIRD_PARTY_NOTICES.md` / module `ATTRIBUTION.md`.
6. Avoid committing detection lists that violate upstream licenses.

## Branch and PR expectations

- Branch from `main` with a short prefix: `fix/`, `feat/`, `chore/`, `docs/`.
- One concern per PR when practical.
- Fill out the pull request template (summary, linked issue, testing, privacy/third-party impact).
- CI must be green before merge.

## Privacy and hygiene

Do **not** commit or paste into public issues/PRs:

- `.env`, API tokens, HIBP keys, encryption keys
- `data/*.sqlite3`, `data/secrets.json`, `data/.api_token`, scan exports
- Real personal identifiers used in scans
- Machine-specific absolute paths (Windows user-profile paths, POSIX home directories)

CI rejects tracked private runtime files and machine paths in tracked text.

## Security reports

Do not open a public issue with exploitable details or private data. Prefer a private channel to the maintainer when reporting security-sensitive problems. Use the security issue template only for high-level, non-exploitable descriptions.

## License / attribution

Respect upstream licenses for dependencies and optional datasets. Document new third-party data sources before merging.
