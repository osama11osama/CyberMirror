"""Smart search query generation — native CyberMirror logic."""

# Major platforms — site-specific searches find accounts web scanners miss.
SITE_PLATFORMS = (
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "tiktok.com",
    "reddit.com",
    "github.com",
    "youtube.com",
    "pinterest.com",
    "snapchat.com",
    "telegram.org",
    "t.me",
    "threads.net",
    "medium.com",
    "twitch.tv",
)


def build_queries(profile: dict) -> list[str]:
    name = (profile.get("full_name") or profile.get("name") or "").strip()
    email = (profile.get("email") or "").strip()
    phone = (profile.get("phone") or "").strip()
    username = (profile.get("username") or "").strip()
    location = (profile.get("location") or "").strip()
    company = (profile.get("company") or "").strip()
    website = (profile.get("website") or "").strip()

    queries: list[str] = []

    def add(*parts: str) -> None:
        q = " ".join(p for p in parts if p)
        if q:
            queries.append(q)

    # Direct identity searches
    if name:
        add(f'"{name}"')
        add(name)
    if email:
        add(f'"{email}"')
        add(email)
    if phone:
        add(f'"{phone}"')
        add(phone)
    if username:
        add(f'"{username}"')
        add(username)

    # Combinations
    add(name, email)
    add(name, phone)
    add(name, username)
    add(name, location)
    add(name, company)
    add(username, location)
    add(email, "contact")
    add(phone, "whatsapp")
    add(phone, "telegram")

    # Site-specific username searches (critical for Facebook/Instagram)
    if username:
        for domain in SITE_PLATFORMS:
            add(f"site:{domain} {username}")
            add(f'site:{domain} "{username}"')

    # Name on major social sites
    if name:
        for domain in ("facebook.com", "linkedin.com", "instagram.com"):
            add(f'site:{domain} "{name}"')

    if website:
        add(name, website)

    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique
