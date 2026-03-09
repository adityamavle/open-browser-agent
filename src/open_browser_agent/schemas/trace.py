from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TraceEvent:
    step_id: str
    action: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TraceVerification:
    success: bool
    reason: str
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
