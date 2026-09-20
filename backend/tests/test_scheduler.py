"""Scheduler module-selection tests (no real timer loop)."""

from app.services import scheduler


def test_scheduled_scans_use_enabled_modules(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "get_enabled_modules",
        lambda: ["web_search", "email_scan"],
    )
    assert scheduler.modules_for_scheduled_scan() == ["web_search", "email_scan"]


def test_disabling_module_removes_it_from_scheduled_selection(monkeypatch):
    enabled = ["username_scan", "domain_scan"]

    def _enabled():
        return list(enabled)

    monkeypatch.setattr(scheduler, "get_enabled_modules", _enabled)
    assert "ahmia_search" not in scheduler.modules_for_scheduled_scan()

    enabled.append("ahmia_search")
    assert "ahmia_search" in scheduler.modules_for_scheduled_scan()
