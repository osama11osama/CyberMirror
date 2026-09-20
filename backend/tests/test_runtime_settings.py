"""Runtime settings persistence tests."""

import json

from app.services import runtime_settings as rs


def test_disabled_modules_are_preserved(tmp_path, monkeypatch):
    runtime_file = tmp_path / "runtime_settings.json"
    monkeypatch.setattr(rs, "RUNTIME_FILE", runtime_file)

    runtime_file.write_text(json.dumps({
        "enabled_modules": ["web_search", "email_scan"],
        "module_catalog": list(rs._ALL_MODULES),
    }), encoding="utf-8")

    loaded = rs.load_runtime()
    assert loaded["enabled_modules"] == ["web_search", "email_scan"]
    assert "ahmia_search" not in loaded["enabled_modules"]
    assert "credential_leaks" not in loaded["enabled_modules"]


def test_new_catalog_modules_are_opted_in_once(tmp_path, monkeypatch):
    runtime_file = tmp_path / "runtime_settings.json"
    monkeypatch.setattr(rs, "RUNTIME_FILE", runtime_file)

    old_catalog = [m for m in rs._ALL_MODULES if m != "ahmia_search"]
    runtime_file.write_text(json.dumps({
        "enabled_modules": ["web_search"],
        "module_catalog": old_catalog,
    }), encoding="utf-8")

    loaded = rs.load_runtime()
    assert "web_search" in loaded["enabled_modules"]
    assert "ahmia_search" in loaded["enabled_modules"]
    assert loaded["enabled_modules"].count("ahmia_search") == 1


def test_save_runtime_stamps_module_catalog(tmp_path, monkeypatch):
    runtime_file = tmp_path / "runtime_settings.json"
    monkeypatch.setattr(rs, "RUNTIME_FILE", runtime_file)
    monkeypatch.setattr(rs, "apply_runtime", lambda data=None: None)

    rs.save_runtime({"enabled_modules": ["domain_scan"]})
    saved = json.loads(runtime_file.read_text(encoding="utf-8"))
    assert saved["enabled_modules"] == ["domain_scan"]
    assert saved["module_catalog"] == list(rs._ALL_MODULES)
