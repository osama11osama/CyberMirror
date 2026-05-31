"""Native OSINT modules — CyberMirror proprietary engine."""

from abc import ABC, abstractmethod

from app.models.schemas import Finding, IdentityProfile


class NativeModule(ABC):
    id: str = "base"
    name: str = "Base Module"
    description: str = ""
    category: str = "general"

    @abstractmethod
    async def scan(self, profile: IdentityProfile, scan_id: str = "") -> list[Finding]:
        ...
