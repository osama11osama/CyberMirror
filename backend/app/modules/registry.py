"""Native module registry — CyberMirror proprietary engine only."""

from app.modules.base import NativeModule
from app.modules.breach.scanner import BreachScanModule
from app.modules.domain.scanner import DomainScanModule
from app.modules.email.scanner import EmailScanModule
from app.modules.identity.correlator import IdentityCorrelatorModule
from app.modules.identity.web_search import WebSearchModule
from app.modules.phone.scanner import PhoneScanModule
from app.modules.social.playwright_scan import SocialBrowserModule
from app.modules.username.scanner import UsernameScanModule

NATIVE_MODULES: dict[str, type[NativeModule]] = {
    "web_search": WebSearchModule,
    "username_scan": UsernameScanModule,
    "social_browser": SocialBrowserModule,
    "email_scan": EmailScanModule,
    "phone_scan": PhoneScanModule,
    "breach_scan": BreachScanModule,
    "domain_scan": DomainScanModule,
    "identity_correlator": IdentityCorrelatorModule,
}

DEFAULT_MODULES = [
    "web_search",
    "username_scan",
    "social_browser",
    "email_scan",
    "phone_scan",
    "breach_scan",
    "domain_scan",
    "identity_correlator",
]


def get_module(module_id: str) -> NativeModule:
    cls = NATIVE_MODULES.get(module_id)
    if not cls:
        raise ValueError(f"Unknown module: {module_id}")
    return cls()


def list_modules() -> list[dict]:
    result = []
    for mid, cls in NATIVE_MODULES.items():
        mod = cls()
        result.append({
            "id": mid,
            "name": mod.name,
            "description": mod.description,
            "category": mod.category,
            "available": True,
            "builtin": True,
            "license": "CyberMirror Proprietary",
        })
    return result
