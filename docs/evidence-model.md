# Evidence & provenance model (v2.3 “Evidence”)

CyberMirror findings carry three independent axes:

| Axis | Field | Meaning |
|------|--------|---------|
| **Risk** | `risk_level` | How severe the exposure is if true |
| **Outcome** | `outcome` | Exposure semantic used by risk gating (`confirmed_exposure`, `negative`, `inconclusive`, `system`) |
| **Verification** | `verification` | Scanner certainty (`verified`, `likely`, `possible`, `not_found`, `blocked`, …) |

## EvidenceObservation

Stored on `Finding.evidence` and mirrored into `raw_json.evidence` for persistence.

Key fields:

- `kind` — `observation` (remote), `derived` (correlator), `seed` (investigator input; not public proof)
- `method` — `http`, `playwright`, `api`, `correlator`, …
- `queried_identifier` / `identifier_type` — what was searched
- `source_url` / `platform` / `http_status` / `collected_at`
- `positive_markers` / `negative_markers` — detection strings matched
- `blocked_reason` — captcha / login wall marker when applicable
- `confidence_reason` — human-readable why confidence was assigned
- `corroborating_finding_ids` — links for derived conclusions

## Backward compatibility

- Pre-2.3 rows lack these fields; loaders default `verification=unknown` and empty evidence.
- `outcome` continues to be merged into `raw_json` as before.
- Risk scoring uses `outcome` first; when `verification` is set, scanners also set a matching `outcome`.

## Reference scanners

Username (`username_scan`) and Social Browser (`social_browser`) populate verification + evidence as of v2.3.
