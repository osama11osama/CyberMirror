"""Public HTTP(S) target validation for automatic page acquisition.

Search results are untrusted.  This module is the single SSRF boundary used by
both direct HTTP and browser-backed acquisition.  DNS is checked before every
navigation/redirect.  There is still an unavoidable DNS rebinding window when
the HTTP client resolves the name again; callers therefore must not disable
redirect validation and should keep this service on an egress-restricted host
when a stronger network boundary is required.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Callable, Iterable
from urllib.parse import urlsplit


Resolver = Callable[[str, int], Iterable[tuple]]


@dataclass(frozen=True)
class TargetValidation:
    allowed: bool
    url: str
    reason: str | None = None
    host: str = ""
    resolved_addresses: tuple[str, ...] = field(default_factory=tuple)


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    # is_global excludes loopback, RFC1918/ULA, link-local, multicast,
    # unspecified, reserved, documentation, and metadata-style destinations.
    return address.is_global


def validate_public_target(
    url: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> TargetValidation:
    """Resolve and allow only unambiguously public HTTP(S) destinations."""
    value = (url or "").strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        return TargetValidation(False, value, "invalid_url")

    if parsed.scheme.lower() not in {"http", "https"}:
        return TargetValidation(False, value, "unsupported_scheme")
    if parsed.username is not None or parsed.password is not None:
        return TargetValidation(False, value, "userinfo_not_allowed")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        return TargetValidation(False, value, "missing_host")
    if host == "localhost" or host.endswith(".localhost"):
        return TargetValidation(False, value, "localhost_not_allowed", host=host)

    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError:
        return TargetValidation(False, value, "invalid_port", host=host)

    # Literal addresses do not require DNS and avoid platform-specific
    # getaddrinfo behavior for bracketed IPv6 values.
    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        literal = None
    if literal is not None:
        text = str(literal)
        if not _is_public_address(text):
            return TargetValidation(False, value, "non_public_address", host, (text,))
        return TargetValidation(True, value, host=host, resolved_addresses=(text,))

    try:
        records = resolver(host, port)
        addresses = tuple(sorted({str(item[4][0]).split("%", 1)[0] for item in records}))
    except (OSError, socket.gaierror, UnicodeError, ValueError):
        return TargetValidation(False, value, "dns_resolution_failed", host=host)
    if not addresses:
        return TargetValidation(False, value, "dns_no_addresses", host=host)
    forbidden = tuple(address for address in addresses if not _is_public_address(address))
    if forbidden:
        return TargetValidation(
            False,
            value,
            "dns_resolved_non_public_address",
            host,
            addresses,
        )
    return TargetValidation(True, value, host=host, resolved_addresses=addresses)


async def validate_public_target_async(url: str) -> TargetValidation:
    """Async wrapper so DNS resolution cannot block the event loop."""
    return await asyncio.to_thread(validate_public_target, url)
