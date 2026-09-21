# Intelligence entity & event model (v2.5 / #36)

CyberMirror findings answer *what source/result was observed*.  
**Entities** and **Events** answer *what structured facts were extracted*, always linked to evidence IDs.

## Origins

| Origin | Meaning |
|--------|---------|
| `seed` | Investigator-supplied input — **not** public evidence |
| `observed` | Extracted from acquired public content |
| `derived` | Inferred conclusion that must cite supporting evidence IDs |

## Date precision

`FuzzyDate.precision`: `exact_datetime` | `exact_day` | `month` | `year` | `unknown`

Never invent finer precision. Stay date and publication date are separate fields on `Event`.

## Persistence

Intelligence payloads are stored per scan as JSON (additive). Pre-v2.5 scans simply have empty bundles.

## Example

A forum finding URL → PageArtifact → Entity(handle) + Event(forum_post) both referencing the same evidence observation ID.
