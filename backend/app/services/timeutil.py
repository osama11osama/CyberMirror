"""UTC helpers — always persist timezone-aware timestamps."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    """ISO-8601 UTC with trailing Z so browsers treat the instant correctly."""
    return to_iso(utc_now())


def parse_iso_datetime(value: str) -> datetime:
    """Parse stored timestamps; naive values are treated as UTC."""
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
