"""Pydantic models for CyberMirror."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"
    UNKNOWN = "Unknown"


class FindingCategory(str, Enum):
    USERNAME = "username_discovery"
    EMAIL = "email_exposure"
    SOCIAL = "social_discovery"
    IDENTITY = "identity_search"
    ADVANCED = "advanced_intelligence"
    OTHER = "other"


class IdentityProfile(BaseModel):
    full_name: str = ""
    username: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    website: str = ""
    company: str = ""


class ScanRequest(BaseModel):
    profile: IdentityProfile
    providers: list[str] = Field(default_factory=list)
    async_mode: bool = True


class ScanStartResponse(BaseModel):
    id: str
    status: str = "running"
    message: str = ""
    providers: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    scan_id: str = ""
    source: str = ""
    provider: str = ""
    category: FindingCategory = FindingCategory.OTHER
    platform: str = ""
    title: str = ""
    url: str = ""
    description: str = ""
    snippet: str = ""
    confidence: float = 0.0
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    risk_reason: str = ""
    recommendation: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw: dict[str, Any] = Field(default_factory=dict)


class ScanSummary(BaseModel):
    id: str
    created_at: datetime
    profile: IdentityProfile
    status: str
    providers: list[str]
    finding_count: int = 0
    risk_score: float = 0.0


class ScanDetail(ScanSummary):
    findings: list[Finding] = Field(default_factory=list)


class DashboardStats(BaseModel):
    total_findings: int = 0
    risk_score: float = 0.0
    by_source: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_risk: dict[str, int] = Field(default_factory=dict)
    high_risk_count: int = 0
    recent_scans: list[ScanSummary] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str = ""


class GraphData(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class ProviderStatus(BaseModel):
    id: str
    name: str
    available: bool
    path: str
    license: str
    category: str
    description: str
    enabled: bool = True


class SettingsUpdate(BaseModel):
    serpapi_key: str | None = None
    hibp_api_key: str | None = None
    username_scan_limit: int | None = None
    web_search_max_queries: int | None = None
    web_search_results_per_query: int | None = None
    wmn_data_path: str | None = None
    playwright_enabled: bool | None = None
    schedule_enabled: bool | None = None
    schedule_interval_hours: int | None = None
    cache_ttl_seconds: int | None = None
    enabled_modules: list[str] | None = None
    locale: str | None = None


class ScanCompareResult(BaseModel):
    scan_a: str
    scan_b: str
    new_findings: list[Finding] = Field(default_factory=list)
    removed_findings: list[Finding] = Field(default_factory=list)
    unchanged_count: int = 0


class ExportRequest(BaseModel):
    format: str = "json"  # json | csv | html
