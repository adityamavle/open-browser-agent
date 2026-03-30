from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from open_browser_agent.schemas.step import Step


@dataclass(slots=True)
class FallbackPlan:
    strategy_name: str
    trigger: str
    steps: list[Step]


class FallbackStrategy(Protocol):
    name: str

    def build_fallback(self, plan_result, trigger: str) -> FallbackPlan | None:
        """Return a bounded fallback plan for a known task, or None if unsupported."""
