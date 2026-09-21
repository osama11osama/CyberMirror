"""Parse authoritative page structure before free-text heuristics (#61).

Prefers JSON-LD and Open Graph / meta tags.  Never invents entities from
generic capitalized words.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_META_RE = re.compile(
    r'<meta\b[^>]*(?:property|name)=["\']([^"\']+)["\'][^>]*content=["\']([^"\']*)["\'][^>]*>',
    re.I,
)
_META_RE_ALT = re.compile(
    r'<meta\b[^>]*content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']([^"\']+)["\'][^>]*>',
    re.I,
)


@dataclass
class StructuredSignals:
    organizations: list[dict[str, Any]] = field(default_factory=list)
    products: list[dict[str, Any]] = field(default_factory=list)
    locations: list[dict[str, Any]] = field(default_factory=list)
    authors: list[dict[str, Any]] = field(default_factory=list)
    social_profiles: list[dict[str, Any]] = field(default_factory=list)
    vehicles: list[dict[str, Any]] = field(default_factory=list)
    open_graph: dict[str, str] = field(default_factory=dict)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _walk_jsonld(node: Any, out: StructuredSignals, *, depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(node, list):
        for item in node:
            _walk_jsonld(item, out, depth=depth + 1)
        return
    if not isinstance(node, dict):
        return

    types = {str(t).lower() for t in _as_list(node.get("@type"))}
    name = str(node.get("name") or node.get("legalName") or "").strip()

    if types & {"organization", "corporation", "localbusiness", "hotel"}:
        if name and len(name) >= 2:
            out.organizations.append(
                {"name": name, "source": "jsonld", "raw_type": sorted(types)}
            )
    if types & {"product", "softwareapplication"}:
        if name and len(name) >= 2:
            out.products.append({"name": name, "source": "jsonld", "raw_type": sorted(types)})
    if types & {"place", "city", "administrativearea", "country"}:
        if name and len(name) >= 2:
            out.locations.append({"name": name, "source": "jsonld", "raw_type": sorted(types)})
    if types & {"person"}:
        author_name = str(node.get("name") or "").strip()
        url = str(node.get("url") or "").strip()
        if isinstance(node.get("sameAs"), list):
            for item in node["sameAs"]:
                out.social_profiles.append({"url": str(item), "source": "jsonld_sameAs"})
        elif isinstance(node.get("sameAs"), str):
            out.social_profiles.append({"url": str(node["sameAs"]), "source": "jsonld_sameAs"})
        if author_name:
            out.authors.append({"name": author_name, "url": url, "source": "jsonld_person"})
    if types & {"vehicle", "car"}:
        if name:
            out.vehicles.append({"name": name, "source": "jsonld"})

    for key in ("author", "creator", "reviewer"):
        for item in _as_list(node.get(key)):
            if isinstance(item, str) and item.strip():
                out.authors.append({"name": item.strip(), "source": f"jsonld_{key}"})
            else:
                _walk_jsonld(item, out, depth=depth + 1)
    for key in ("location", "contentLocation", "address", "itemReviewed", "brand", "manufacturer", "provider", "publisher"):
        for item in _as_list(node.get(key)):
            if isinstance(item, str) and item.strip():
                if key in ("location", "contentLocation", "address"):
                    out.locations.append({"name": item.strip(), "source": f"jsonld_{key}"})
                elif key in ("brand", "manufacturer", "provider", "publisher"):
                    out.organizations.append({"name": item.strip(), "source": f"jsonld_{key}"})
            elif isinstance(item, dict):
                addr = item.get("addressLocality") or item.get("name") or item.get("addressRegion")
                if addr and key in ("location", "contentLocation", "address", "itemReviewed"):
                    # Prefer locality when present on nested address objects.
                    locality = item.get("addressLocality")
                    if isinstance(item.get("address"), dict):
                        locality = locality or item["address"].get("addressLocality")
                    out.locations.append(
                        {
                            "name": str(locality or addr).strip(),
                            "source": f"jsonld_{key}",
                        }
                    )
                _walk_jsonld(item, out, depth=depth + 1)

    if "@graph" in node:
        _walk_jsonld(node["@graph"], out, depth=depth + 1)
    # Walk remaining nested objects for completeness without infinite loops.
    for key, value in node.items():
        if key.startswith("@") or key in {
            "author",
            "creator",
            "reviewer",
            "location",
            "contentLocation",
            "address",
            "itemReviewed",
            "brand",
            "manufacturer",
            "provider",
            "publisher",
        }:
            continue
        if isinstance(value, (dict, list)):
            _walk_jsonld(value, out, depth=depth + 1)


def _parse_meta(html: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for m in _META_RE.finditer(html or ""):
        meta[m.group(1).lower()] = m.group(2).strip()
    for m in _META_RE_ALT.finditer(html or ""):
        meta.setdefault(m.group(2).lower(), m.group(1).strip())
    return meta


_SOCIAL_HOSTS = {
    "twitter.com": "twitter",
    "x.com": "twitter",
    "github.com": "github",
    "linkedin.com": "linkedin",
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "reddit.com": "reddit",
}


def social_profile_from_url(url: str) -> dict[str, str] | None:
    try:
        parts = urlparse(url)
    except Exception:
        return None
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    platform = _SOCIAL_HOSTS.get(host)
    if not platform:
        return None
    path = (parts.path or "").strip("/")
    if not path or "/" in path.split("/")[0] and path.count("/") > 2:
        # Keep first path segment as handle for simple profile URLs.
        pass
    segment = path.split("/")[0] if path else ""
    if platform == "linkedin" and path.startswith("in/"):
        segment = path.split("/")[1] if "/" in path else ""
    if platform == "reddit" and path.startswith("user/"):
        segment = path.split("/")[1] if "/" in path else ""
    if not segment or segment in {"login", "signup", "explore", "search", "settings"}:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{2,40}", segment):
        return None
    return {"platform": platform, "handle": segment, "url": url}


def parse_structured_signals(html_or_text: str) -> StructuredSignals:
    """Extract structured signals from HTML; plain text yields empty structure."""
    out = StructuredSignals()
    raw = html_or_text or ""
    for block in _JSONLD_RE.finditer(raw):
        body = block.group(1).strip()
        if not body:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        _walk_jsonld(data, out)

    meta = _parse_meta(raw)
    out.open_graph = {
        k: v for k, v in meta.items() if k.startswith("og:") or k.startswith("article:")
    }
    if meta.get("og:site_name"):
        out.organizations.append({"name": meta["og:site_name"], "source": "og:site_name"})
    for key in ("og:locality", "geo.placename", "og:country-name"):
        if meta.get(key):
            out.locations.append({"name": meta[key], "source": key})
    if meta.get("article:author"):
        author = meta["article:author"]
        if author.startswith("http"):
            profile = social_profile_from_url(author)
            if profile:
                out.social_profiles.append({**profile, "source": "article:author"})
            out.authors.append({"name": author, "url": author, "source": "article:author"})
        else:
            out.authors.append({"name": author, "source": "article:author"})

    return out
