from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from open_browser_agent.schemas.step import Step
from open_browser_agent.strategies.base import FallbackPlan
from open_browser_agent.tasks.registry import WIKIPEDIA_MAIN_URL


class WikipediaFallbackStrategy:
    name = "wikipedia-search-press"

    def build_fallback(self, plan_result, trigger: str) -> FallbackPlan | None:
        if getattr(plan_result, "task_id", None) != "wikipedia-summary":
            return None
        topic = extract_wikipedia_topic_from_steps(getattr(plan_result, "steps", []))
        if not topic:
            return None
        return FallbackPlan(
            strategy_name=self.name,
            trigger=trigger,
            steps=build_wikipedia_search_fallback_steps(topic),
        )


def extract_wikipedia_topic_from_steps(steps: list[Step]) -> str | None:
    if not steps:
        return None
    first_step = steps[0]
    if first_step.type not in {"navigate", "goto"}:
        return None
    url = str(first_step.args.get("url") or "")
    marker = "https://en.wikipedia.org/wiki/"
    if not url.startswith(marker):
        return None
    slug = url[len(marker) :].split("?", 1)[0].split("#", 1)[0].strip()
    if not slug or slug == "Main_Page":
        return None
    return unquote(slug).replace("_", " ")


def build_wikipedia_search_fallback_steps(topic: str) -> list[Step]:
    return [
        Step(id="fallback-goto-wikipedia-main", type="navigate", args={"url": WIKIPEDIA_MAIN_URL}),
        Step(id="fallback-wait-search", type="wait_for", args={"selector": "input[name='search']"}),
        Step(id="fallback-type-topic", type="type", args={"selector": "input[name='search']", "text": topic}),
        Step(id="fallback-press-enter", type="press", args={"keys": "Enter"}),
        Step(id="fallback-wait-main", type="wait_for", args={"selector": "main"}),
        Step(id="fallback-extract-summary", type="extract", args={"target": "summary"}),
        Step(id="fallback-extract-citation-links", type="extract", args={"target": "citation_links"}),
    ]


def collect_extract_artifacts(results: list[Any]) -> dict[str, Any]:
    extracts: dict[str, Any] = {}
    for result in results:
        action_result = getattr(result, "action_result", None)
        if action_result is None or action_result.action != "extract" or not action_result.ok:
            continue
        target = str(action_result.details.get("target") or "unknown")
        extracts[target] = action_result.details.get("value")
    return extracts


def collect_extract_sequence(results: list[Any]) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    for result in results:
        action_result = getattr(result, "action_result", None)
        if action_result is None or action_result.action != "extract" or not action_result.ok:
            continue
        sequence.append(
            {
                "step_id": getattr(result, "step_id", ""),
                "target": str(action_result.details.get("target") or "unknown"),
                "value": action_result.details.get("value"),
                "current_url": str(action_result.details.get("current_url") or ""),
                "page_title": str(action_result.details.get("page_title") or ""),
            }
        )
    return sequence
