from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderSource:
    provider: str
    source_url: str
    source_timestamp: str | None
    fetched_at: str
    is_stale: bool = False


@dataclass(frozen=True)
class ProviderResult:
    data: dict[str, Any] | None
    sources: list[ProviderSource] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
