"""Deterministic SSRF-boundary and acquisition tests (#56)."""

import asyncio

import httpx
import pytest

from app.services.investigation_budget import InvestigationBudget
from app.services.page_analyzer import AcquisitionMethod, acquire_page, artifact_from_http
from app.services.public_target import TargetValidation, validate_public_target


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "data:text/plain,hello",
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[fc00::1]/",
        "http://[fe80::1]/",
    ],
)
def test_rejects_non_public_targets(url):
    outcome = validate_public_target(url)
    assert not outcome.allowed
    assert outcome.reason


def test_dns_resolution_rejects_any_non_public_answer():
    def resolver(_host, _port):
        return [
            (2, 1, 6, "", ("93.184.216.34", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]

    outcome = validate_public_target("https://public.example/path", resolver=resolver)
    assert not outcome.allowed
    assert outcome.reason == "dns_resolved_non_public_address"


def test_public_dns_answer_is_allowed():
    def resolver(_host, _port):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    outcome = validate_public_target("https://public.example/path", resolver=resolver)
    assert outcome.allowed
    assert outcome.resolved_addresses == ("93.184.216.34",)


def test_http_artifact_preserves_relative_canonical_url():
    artifact = artifact_from_http(
        source_url="https://public.example/result?id=1",
        final_url="https://public.example/result?id=1",
        body='<link href="/canonical/1" rel="canonical"><p>Public text</p>',
        status=200,
    )
    assert artifact.canonical_url == "https://public.example/canonical/1"


@pytest.mark.asyncio
async def test_redirect_to_private_target_is_blocked_without_request(monkeypatch):
    async def validation(url):
        if url.startswith("https://public.example"):
            return TargetValidation(True, url, host="public.example", resolved_addresses=("93.184.216.34",))
        return validate_public_target(url)

    monkeypatch.setattr("app.services.page_analyzer.validate_public_target_async", validation)
    requested = []

    async def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    artifact = await acquire_page(
        "https://public.example/start",
        budget=InvestigationBudget(scan_id="redirect"),
        transport=httpx.MockTransport(handler),
    )
    assert requested == ["https://public.example/start"]
    assert artifact.acquisition_method == AcquisitionMethod.UNSUPPORTED
    assert artifact.blocked_reason == "unsafe_target:non_public_address"
    assert artifact.evidence_id


@pytest.mark.asyncio
async def test_rendered_challenge_remains_blocked(monkeypatch):
    async def validation(url):
        return TargetValidation(True, url, host="public.example", resolved_addresses=("93.184.216.34",))

    async def rendered(_url, timeout=20.0):
        return "<html>Please log in to continue</html>", "https://public.example/login"

    async def handler(_request):
        return httpx.Response(200, text="<html><script>app()</script></html>")

    monkeypatch.setattr("app.services.page_analyzer.validate_public_target_async", validation)
    monkeypatch.setattr("app.services.page_analyzer._try_playwright", rendered)
    artifact = await acquire_page(
        "https://public.example/app",
        prefer_playwright=True,
        budget=InvestigationBudget(scan_id="render"),
        transport=httpx.MockTransport(handler),
    )
    assert artifact.acquisition_method == AcquisitionMethod.BLOCKED
    assert artifact.blocked_reason.startswith(("login_wall:", "challenge:"))


@pytest.mark.asyncio
async def test_snippet_fallback_preserves_destination_failure(monkeypatch):
    async def validation(url):
        return TargetValidation(True, url, host="public.example", resolved_addresses=("93.184.216.34",))

    async def handler(_request):
        return httpx.Response(403, text="Access denied")

    monkeypatch.setattr("app.services.page_analyzer.validate_public_target_async", validation)
    artifact = await acquire_page(
        "https://public.example/blocked",
        snippet_fallback="Indexed public excerpt",
        budget=InvestigationBudget(scan_id="fallback"),
        transport=httpx.MockTransport(handler),
    )
    assert artifact.acquisition_method == AcquisitionMethod.SEARCH_SNIPPET
    assert artifact.main_text == "Indexed public excerpt"
    assert artifact.metadata["destination_failure_reason"] == "http_403"


@pytest.mark.asyncio
async def test_response_body_is_streamed_and_capped(monkeypatch):
    async def validation(url):
        return TargetValidation(True, url, host="public.example", resolved_addresses=("93.184.216.34",))

    class LargeStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 10_000

    async def handler(_request):
        return httpx.Response(200, stream=LargeStream())

    monkeypatch.setattr("app.services.page_analyzer.validate_public_target_async", validation)
    budget = InvestigationBudget(scan_id="bounded", max_extracted_content_bytes=64)
    artifact = await acquire_page(
        "https://public.example/large",
        budget=budget,
        transport=httpx.MockTransport(handler),
    )
    assert len(artifact.main_text.encode()) == 64
    assert artifact.metadata["content_truncated"] is True


@pytest.mark.asyncio
async def test_streaming_read_obeys_absolute_deadline(monkeypatch):
    async def validation(url):
        return TargetValidation(True, url, host="public.example", resolved_addresses=("93.184.216.34",))

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(1)
            yield b"late"

    async def handler(_request):
        return httpx.Response(200, stream=SlowStream())

    monkeypatch.setattr("app.services.page_analyzer.validate_public_target_async", validation)
    budget = InvestigationBudget(scan_id="deadline", page_timeout_seconds=0.01)
    artifact = await acquire_page(
        "https://public.example/slow",
        budget=budget,
        transport=httpx.MockTransport(handler),
    )
    assert artifact.acquisition_method == AcquisitionMethod.ERROR
    assert artifact.blocked_reason == "request_error:TimeoutError"


@pytest.mark.asyncio
async def test_non_success_http_rejects_extraction_and_uses_snippet(monkeypatch):
    async def validation(url):
        return TargetValidation(True, url, host="public.example", resolved_addresses=("93.184.216.34",))

    async def handler(_request):
        return httpx.Response(404, text="Not found")

    monkeypatch.setattr("app.services.page_analyzer.validate_public_target_async", validation)
    artifact = await acquire_page(
        "https://public.example/missing",
        snippet_fallback="@RareHandle99 public snippet",
        budget=InvestigationBudget(scan_id="http404"),
        transport=httpx.MockTransport(handler),
    )
    assert artifact.acquisition_method == AcquisitionMethod.SEARCH_SNIPPET
    assert artifact.metadata["destination_failure_reason"] == "http_404"
    assert "RareHandle99" in artifact.main_text


@pytest.mark.asyncio
async def test_target_rejection_falls_back_to_snippet(monkeypatch):
    async def validation(url):
        return TargetValidation(False, url, reason="dns_resolution_failed")

    monkeypatch.setattr("app.services.page_analyzer.validate_public_target_async", validation)
    artifact = await acquire_page(
        "https://gone.example/page",
        snippet_fallback="Indexed excerpt about RareHandle99",
        budget=InvestigationBudget(scan_id="dnsfail"),
    )
    assert artifact.acquisition_method == AcquisitionMethod.SEARCH_SNIPPET
    assert artifact.metadata["destination_failure_reason"] == "dns_resolution_failed"
    assert "RareHandle99" in artifact.main_text
