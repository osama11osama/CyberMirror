from datetime import timezone

from app.services.timeutil import parse_iso_datetime, to_iso, utc_now, utc_now_iso


def test_utc_now_iso_has_z_suffix():
    assert utc_now_iso().endswith("Z")
    assert to_iso(utc_now()).endswith("Z")


def test_naive_iso_is_parsed_as_utc():
    dt = parse_iso_datetime("2026-09-20T23:54:29.617466")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 23


def test_zulu_iso_roundtrip():
    dt = parse_iso_datetime("2026-09-20T23:54:29.617466Z")
    assert dt.tzinfo is not None
    assert to_iso(dt).startswith("2026-09-20T23:54:29")
