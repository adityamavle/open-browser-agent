from __future__ import annotations

from dataclasses import dataclass, field

from open_browser_agent.schemas.step import Step


@dataclass(slots=True)
class TaskSpec:
    task_id: str
    summary: str
    aliases: tuple[str, ...] = ()
    steps: list[Step] = field(default_factory=list)
    verifier_hint: str = ""


TASKS: list[TaskSpec] = [
    TaskSpec(
        task_id="form-fill",
        summary="Fill and submit a sandbox form.",
        aliases=("form", "fill form", "sandbox form"),
        steps=[
            Step(id="goto-form", type="navigate", args={"url": "https://example.com/form"}),
            Step(id="wait-form", type="wait_for", args={"selector": "form"}),
        ],
        verifier_hint="Confirmation page or success message is visible.",
    ),
    TaskSpec(
        task_id="table-scrape",
        summary="Scrape an HTML table and output JSON.",
        aliases=("table", "scrape table"),
        steps=[
            Step(id="goto-table", type="navigate", args={"url": "https://example.com/table"}),
            Step(id="extract-table", type="extract", args={"target": "table"}),
        ],
        verifier_hint="Extracted JSON contains expected rows and columns.",
    ),
    TaskSpec(
        task_id="wikipedia-summary",
        summary="Extract a Wikipedia summary and cited links.",
        aliases=("wikipedia", "wiki summary", "extract wikipedia summary"),
        steps=[
            Step(id="goto-wikipedia", type="navigate", args={"url": "https://wikipedia.org"}),
            Step(id="extract-summary", type="extract", args={"target": "summary"}),
        ],
        verifier_hint="Summary text is non-empty and at least one cited link is present.",
    ),
]


def find_task_by_goal(goal: str) -> TaskSpec | None:
    lowered = goal.strip().lower()
    for task in TASKS:
        if lowered == task.task_id or lowered in task.aliases:
            return task
        if lowered and lowered in task.summary.lower():
            return task
    return None
