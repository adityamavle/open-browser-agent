from __future__ import annotations

from dataclasses import dataclass, field

from open_browser_agent.schemas.step import Step
from open_browser_agent.verifier import VerificationRule


@dataclass(slots=True)
class TaskSpec:
    task_id: str
    summary: str
    aliases: tuple[str, ...] = ()
    steps: list[Step] = field(default_factory=list)
    verifier_hint: str = ""
    verification_rules: list[VerificationRule] = field(default_factory=list)


def fixture_url(name: str) -> str:
    return f"fixture://{name}"


TASKS: list[TaskSpec] = [
    TaskSpec(
        task_id="form-fill",
        summary="Fill and submit a sandbox form.",
        aliases=("form", "fill form", "sandbox form"),
        steps=[
            Step(id="goto-form", type="navigate", args={"url": fixture_url("form_fill.html")}),
            Step(id="wait-form", type="wait_for", args={"selector": "form"}),
            Step(id="type-name", type="type", args={"selector": "#name", "text": "Ada Lovelace"}),
            Step(id="click-submit", type="click", args={"selector": "#submit"}),
            Step(id="wait-success", type="wait_for", args={"selector": "#success"}),
        ],
        verifier_hint="Confirmation page or success message is visible.",
        verification_rules=[
            VerificationRule(kind="text_contains", value="Thanks, Ada Lovelace!", label="success message"),
            VerificationRule(kind="dom_contains", value="main:Submission complete", label="completion state"),
        ],
    ),
    TaskSpec(
        task_id="table-scrape",
        summary="Scrape an HTML table and output JSON.",
        aliases=("table", "scrape table"),
        steps=[
            Step(id="goto-table", type="navigate", args={"url": fixture_url("table_scrape.html")}),
            Step(id="wait-table", type="wait_for", args={"selector": "table"}),
            Step(id="extract-table", type="extract", args={"target": "table"}),
        ],
        verifier_hint="Extracted JSON contains expected rows and columns.",
        verification_rules=[
            VerificationRule(kind="dom_contains", value="table:Language Creator", label="table visible"),
            VerificationRule(kind="text_contains", value="Ada Lovelace", label="expected row text"),
        ],
    ),
    TaskSpec(
        task_id="wikipedia-summary",
        summary="Extract a Wikipedia summary and cited links.",
        aliases=("wikipedia", "wiki summary", "extract wikipedia summary"),
        steps=[
            Step(id="goto-wikipedia", type="navigate", args={"url": fixture_url("wikipedia_summary.html")}),
            Step(id="wait-summary", type="wait_for", args={"selector": "main"}),
            Step(id="extract-summary", type="extract", args={"target": "summary"}),
        ],
        verifier_hint="Summary text is non-empty and at least one cited link is present.",
        verification_rules=[
            VerificationRule(kind="text_contains", value="Ada Lovelace was an English mathematician", label="summary text"),
            VerificationRule(kind="dom_contains", value="a:[1]", label="citation link"),
        ],
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
