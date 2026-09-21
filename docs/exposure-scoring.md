# Exposure scoring (v2.4 “Correlation”)

CyberMirror’s overall scan score is a **heuristic exposure indicator**, not a probability.

## Algorithm (`evidence_aware_v1`)

1. **Filter** — drop negative / system / inconclusive outcomes and blocked / possible / not_found verification.
2. **Deduplicate** — keep the strongest weight per URL (or platform+title).
3. **Weight** — `risk_weight × verification_factor × confidence_factor`.
4. **Aggregate (peak-dominated)** — ~72% top item + smaller shares for 2nd/3rd + tiny remainder; optional bonus for independent platforms.
5. **Explain** — `ScanDetail.risk_explanation` lists reasons and contributing items.

## Examples

| Profile | Expected behavior |
|---------|-------------------|
| 1× Critical credential leak + 20× informational negatives | Score stays high (critical not diluted) |
| 3× duplicate copies of the same URL | Counts once |
| Only blocked/possible checks | Score ≈ 0 |

## UI

Scan detail shows the explanation + disclaimer. Dashboard/history continue to show the numeric score.
