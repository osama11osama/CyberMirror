"""Investigation Journal — explainable investigation steps (#48)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.services.timeutil import utc_now


class JournalStepType(str, Enum):
    SEED = "investigation_seed"
    QUERY = "generated_query"
    SEARCH_RESULT = "search_result"
    ACQUISITION = "page_acquisition"
    BLOCKED = "blocked_or_error"
    ENTITY_EXTRACTION = "entity_extraction"
    ACTIVITY_EXTRACTION = "activity_extraction"
    CLUSTER = "evidence_cluster"
    IDENTITY = "identity_hypothesis"
    PIVOT = "pivot_generation"
    EVENT = "event_creation"
    CONCLUSION = "conclusion"


class JournalStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    parent_ids: list[str] = Field(default_factory=list)
    step_type: JournalStepType
    timestamp: datetime = Field(default_factory=utc_now)
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    reason: str = ""
    status: str = "ok"
    metadata: dict = Field(default_factory=dict)
    scan_id: str = ""


class InvestigationJournal(BaseModel):
    scan_id: str = ""
    steps: list[JournalStep] = Field(default_factory=list)

    def add(self, step: JournalStep) -> JournalStep:
        step.scan_id = step.scan_id or self.scan_id
        self.steps.append(step)
        return step

    def ordered(self) -> list[JournalStep]:
        return sorted(self.steps, key=lambda s: s.timestamp.isoformat())

    def trail_for(self, ref_id: str) -> list[JournalStep]:
        """Return steps that produced or reference a conclusion/entity/event."""
        hits = [
            s
            for s in self.steps
            if ref_id in s.output_refs or ref_id in s.input_refs
        ]
        # Walk parents.
        seen = {s.id for s in hits}
        queue = list(hits)
        while queue:
            s = queue.pop()
            for pid in s.parent_ids:
                parents = [x for x in self.steps if x.id == pid and x.id not in seen]
                for p in parents:
                    seen.add(p.id)
                    hits.append(p)
                    queue.append(p)
        return sorted(hits, key=lambda s: s.timestamp.isoformat())
