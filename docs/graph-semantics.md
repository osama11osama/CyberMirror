# Identity graph semantics (v2.4)

## Node roles

| `data.role` | Meaning |
|-------------|---------|
| `seed` | Investigator-supplied search input (not public proof) |
| `discovered` | Observed remote evidence |
| `derived` | Correlator / multi-platform handle conclusion |

## Edge labels

| Label | Meaning |
|-------|---------|
| `search input` | Person → seed attribute |
| `observed` / module id | Seed or person → observed finding |
| `weak / unverified` | Attached but not strong (blocked/possible/…) |
| `corroborates` | Correlation node → supporting profile findings |
| `supported by` | Derived correlator finding → supporting finding nodes |
| `matches seed username` | Seed username → handle correlation |

## Filters (UI)

Risk, verification (`verified`/`likely`/…/`derived`), and source module.

Weak observations do not create multi-platform corroboration nodes.
