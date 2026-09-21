# Responsible investigation boundary (v2.5 / #44)

CyberMirror is a **local self-audit / authorized OSINT** tool. Deep analysis must stay bounded.

## Forbidden (explicitly out of scope)

- Authentication bypass
- CAPTCHA bypass
- Paywall / access-control bypass
- Credential stuffing
- Scraping private / non-public account areas
- Aggressive retry against blocked services

Blocked sources become structured blocked/inconclusive evidence — never defeated protections.

## Investigation budgets

Central `InvestigationBudget` enforces:

- max pivot depth
- max generated queries
- max pages total / per domain
- page timeout and content size caps
- optional allow/block domain lists
- cancellation
- blocked-hit backoff

Every search, acquisition, and pivot module must consult this budget.

## Data minimization

- Prefer bounded excerpts and structured facts over full page copies
- Deep artifacts live under `data/cache/deep_artifacts/` and can be listed/deleted via API
- Never log secrets or unrelated sensitive page content
