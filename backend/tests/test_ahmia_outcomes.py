"""Ahmia NEGATIVE requires every identity query to complete successfully."""

import pytest

from app.models.schemas import FindingOutcome, IdentityProfile
from app.modules.ahmia.scanner import AhmiaSearchModule


@pytest.mark.asyncio
async def test_partial_query_success_is_inconclusive(monkeypatch):
    module = AhmiaSearchModule()
    profile = IdentityProfile(
        email="alice@example.com",
        username="alice",
        full_name="Alice Example",
    )

    async def fake_pw(query, label, scan_id, seen):
        # First query succeeds with no hits; later queries fail.
        if label == "email":
            return [], True
        return [], False

    async def fake_ddgs(queries, scan_id, seen):
        # Fallback only completes the email query again — username/name still missing.
        return [], {queries[0][0]} if queries else set()

    monkeypatch.setattr("app.modules.ahmia.scanner.settings.playwright_enabled", True)
    monkeypatch.setattr(module, "_playwright_search", fake_pw)
    monkeypatch.setattr(module, "_ddgs_fallback", fake_ddgs)

    findings = await module.scan(profile, scan_id="t1")
    assert len(findings) == 1
    assert findings[0].outcome == FindingOutcome.INCONCLUSIVE


@pytest.mark.asyncio
async def test_all_queries_ok_with_no_hits_is_negative(monkeypatch):
    module = AhmiaSearchModule()
    profile = IdentityProfile(email="bob@example.com", username="bobuser")

    async def fake_pw(query, label, scan_id, seen):
        return [], True

    async def fake_ddgs(queries, scan_id, seen):
        return [], set()

    monkeypatch.setattr("app.modules.ahmia.scanner.settings.playwright_enabled", True)
    monkeypatch.setattr(module, "_playwright_search", fake_pw)
    monkeypatch.setattr(module, "_ddgs_fallback", fake_ddgs)

    findings = await module.scan(profile, scan_id="t2")
    assert len(findings) == 1
    assert findings[0].outcome == FindingOutcome.NEGATIVE
