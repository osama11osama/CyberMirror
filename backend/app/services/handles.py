"""Safe profile-handle extraction from known social/profile URL shapes."""

from __future__ import annotations

from urllib.parse import urlparse

# Host → path prefixes that precede the username segment.
_PROFILE_HOST_PREFIXES: dict[str, tuple[str, ...]] = {
    "github.com": (),
    "www.github.com": (),
    "gitlab.com": (),
    "www.gitlab.com": (),
    "bitbucket.org": (),
    "twitter.com": (),
    "www.twitter.com": (),
    "x.com": (),
    "www.x.com": (),
    "instagram.com": (),
    "www.instagram.com": (),
    "tiktok.com": ("@",),
    "www.tiktok.com": ("@",),
    "reddit.com": ("u", "user"),
    "www.reddit.com": ("u", "user"),
    "linkedin.com": ("in",),
    "www.linkedin.com": ("in",),
    "facebook.com": (),
    "www.facebook.com": (),
    "pinterest.com": (),
    "www.pinterest.com": (),
    "medium.com": ("@",),
    "www.medium.com": ("@",),
    "dev.to": (),
    "keybase.io": (),
}


_SKIP_SEGMENTS = {
    "search", "watch", "p", "posts", "status", "articles", "article",
    "blog", "news", "tag", "tags", "category", "explore", "about",
    "login", "signup", "share", "hashtag", "reel", "reels", "stories",
    "groups", "group", "company", "jobs", "feed", "events", "marketplace",
    "pages", "photo", "photos", "video", "videos", "channel", "c",
}


def extract_profile_handle(url: str, *, expected_username: str | None = None) -> str | None:
    """Return a profile handle only for recognized URL patterns.

    When ``expected_username`` is provided, also accept a first-path-segment match
    against that username (case-insensitive) on unknown hosts — still avoiding
    generic segments like ``articles``.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = (parsed.netloc or "").lower().split(":")[0]
    path = (parsed.path or "").strip("/")
    if not path:
        return None
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None

    prefixes = _PROFILE_HOST_PREFIXES.get(host)
    if prefixes is None and host.startswith("www."):
        prefixes = _PROFILE_HOST_PREFIXES.get(host[4:])

    if prefixes is not None:
        # Known profile host: strip configured prefixes then take next segment.
        if prefixes:
            head = parts[0].lstrip("@").lower()
            prefix_set = {p.lstrip("@").lower() for p in prefixes}
            # TikTok / Medium style /@user when "@" is a configured prefix.
            if parts[0].startswith("@") and "@" in prefixes:
                handle = parts[0].lstrip("@")
            elif head in prefix_set:
                if len(parts) < 2:
                    return None
                handle = parts[1].lstrip("@")
            else:
                # Required profile prefix missing (e.g. linkedin.com/groups/…).
                return None
        else:
            handle = parts[0].lstrip("@")
        if handle and len(handle) >= 2 and handle.lower() not in _SKIP_SEGMENTS:
            # Facebook profile.php?id=… is not a handle path.
            if handle.lower() == "profile.php":
                return None
            return handle.lower()
        return None

    # Unknown host: only accept if the segment equals the seed username.
    expected = (expected_username or "").strip().lstrip("@").lower()
    if not expected:
        return None
    candidate = parts[0].lstrip("@").lower()
    if candidate == expected and candidate not in _SKIP_SEGMENTS:
        return candidate
    # /u/username or /user/username on unknown hosts
    if len(parts) >= 2 and parts[0].lower() in ("u", "user", "in") and parts[1].lstrip("@").lower() == expected:
        return expected
    return None
