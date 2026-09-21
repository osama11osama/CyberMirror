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

One active budget is registered per running scan/investigation. Cancellation marks that budget cancelled before the job is stopped, and completion/failure/cancellation removes it from the active registry after retaining summary counters in the job or intelligence payload. The former `allowed_seed_identifiers` field was removed because it was not an enforced security boundary; investigation scope comes from the explicit profile and operational work is bounded by the budget.

## Public-target / SSRF protection

Automatic page acquisition accepts only public `http` and `https` targets. Before each direct request, redirect, and Playwright request, CyberMirror resolves the hostname and rejects localhost, private/ULA, loopback, link-local, multicast, unspecified, reserved, metadata-style, mixed public/private DNS answers, user-info URLs, and non-HTTP schemes. Rejections become structured blocked/unsupported artifacts with an explanation.

Direct responses are streamed under one absolute acquisition deadline and stopped at the configured extracted-content byte cap, so an untrusted large or indefinitely streaming response is never fully buffered. Only one registered investigation may operate on a scan at a time; overlapping intelligence refreshes return a conflict instead of sharing or clearing another operation's budget.

DNS validation cannot completely remove the time-of-check/time-of-use window if a hostile DNS server changes its answer before the HTTP client connects. Deployments needing a stronger boundary should also enforce network-level egress rules. Redirects are followed manually and revalidated rather than delegated to an unrestricted client.

## Data minimization

- Prefer bounded excerpts and structured facts over full page copies
- Deep artifacts live under `data/cache/deep_artifacts/` and can be listed/deleted via API
- Never log secrets or unrelated sensitive page content
