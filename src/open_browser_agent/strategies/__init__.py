from __future__ import annotations

from open_browser_agent.strategies.base import FallbackPlan, FallbackStrategy
from open_browser_agent.strategies.wikipedia import WikipediaFallbackStrategy

_FALLBACK_STRATEGIES: list[FallbackStrategy] = [
    WikipediaFallbackStrategy(),
]


def get_fallback_plan(plan_result, trigger: str) -> FallbackPlan | None:
    for strategy in _FALLBACK_STRATEGIES:
        fallback = strategy.build_fallback(plan_result, trigger)
        if fallback is not None:
            return fallback
    return None


__all__ = ["FallbackPlan", "FallbackStrategy", "WikipediaFallbackStrategy", "get_fallback_plan"]
