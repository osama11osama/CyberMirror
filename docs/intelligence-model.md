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

## Evidence lineage and identifiers

Artifact, evidence, entity, event, cluster, hypothesis, and Journal identifiers are separate namespaces. The production pipeline uses an explicit `EvidenceLineageIndex` to translate:

`EvidenceObservation.id -> PageArtifact.id -> EvidenceCluster.id`

Identity corroboration and timeline counts are calculated through that mapping. Identical mirror artifacts share one cluster and therefore remain one independent observation. Travel events are derived only after author hypotheses and mirror lineage are available; mirror copies do not create duplicate travel conclusions.

## Acquisition flow

URL findings without embedded content are passed to the Deep Page Analyzer. Eligible public pages are fetched directly, optionally rendered when enabled by the caller, and normalized into `PageArtifact`. A stored search snippet is a weaker fallback when normal acquisition fails or is blocked. Unsafe destinations remain structured unsupported evidence and are never requested.

## Example

A forum finding URL → PageArtifact → Entity(handle) + Event(forum_post) both referencing the same evidence observation ID.
