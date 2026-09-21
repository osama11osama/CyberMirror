"""Scheduler integration: module selection without wall-clock waits."""

from app.services import scheduler


def test_scheduled_modules_respect_enabled_list(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "get_enabled_modules",
        lambda: ["web_search", "username_scan"],
    )
    mods = scheduler.modules_for_scheduled_scan()
    assert mods == ["web_search", "username_scan"]
    assert "ahmia_search" not in mods
