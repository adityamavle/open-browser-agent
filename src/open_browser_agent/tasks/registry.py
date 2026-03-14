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


FORM_FILL_URL = "https://testpages.eviltester.com/pages/forms/html-form/"
TABLE_SCRAPE_URL = "https://the-internet.herokuapp.com/tables"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/wiki/Ada_Lovelace"


TASKS: list[TaskSpec] = [
    TaskSpec(
        task_id="form-fill",
        summary="Fill and submit a public sandbox form.",
        aliases=("form", "fill form", "sandbox form"),
        steps=[
            Step(id="goto-form", type="navigate", args={"url": FORM_FILL_URL}),
            Step(id="wait-form", type="wait_for", args={"selector": "input[name='username']"}),
            Step(
                id="type-name",
                type="type",
                args={"selector": "input[name='username']", "text": "Ada Lovelace"},
            ),
            Step(
                id="type-comments",
                type="type",
                args={"selector": "textarea[name='comments']", "text": "Open Browser Agent public demo run."},
            ),
            Step(id="click-submit", type="click", args={"selector": "input[type='submit']"}),
        ],
        verifier_hint="Submitted values are visible on the processed form page.",
        verification_rules=[
            VerificationRule(kind="text_contains", value="Ada Lovelace", label="submitted username"),
            VerificationRule(
                kind="text_contains",
                value="Open Browser Agent public demo run.",
                label="submitted comments",
            ),
        ],
    ),
    TaskSpec(
        task_id="table-scrape",
        summary="Scrape a public HTML table and output JSON.",
        aliases=("table", "scrape table"),
        steps=[
            Step(id="goto-table", type="navigate", args={"url": TABLE_SCRAPE_URL}),
            Step(id="wait-table", type="wait_for", args={"selector": "#table1"}),
            Step(id="extract-table", type="extract", args={"target": "#table1"}),
        ],
        verifier_hint="Extracted JSON contains expected rows and columns.",
        verification_rules=[
            VerificationRule(kind="url_contains", value="/tables", label="tables page"),
            VerificationRule(kind="text_contains", value="Smith", label="expected row text"),
        ],
    ),
    TaskSpec(
        task_id="wikipedia-summary",
        summary="Extract a public Wikipedia summary and cited links.",
        aliases=("wikipedia", "wiki summary", "extract wikipedia summary"),
        steps=[
            Step(id="goto-wikipedia", type="navigate", args={"url": WIKIPEDIA_SUMMARY_URL}),
            Step(id="wait-summary", type="wait_for", args={"selector": "main"}),
            Step(id="extract-summary", type="extract", args={"target": "summary"}),
        ],
        verifier_hint="Summary text is non-empty and at least one cited link is present.",
        verification_rules=[
            VerificationRule(kind="url_contains", value="Ada_Lovelace", label="article URL"),
            VerificationRule(
                kind="text_contains",
                value="English mathematician and writer",
                label="summary text",
            ),
            VerificationRule(kind="text_contains", value="[1]", label="citation link"),
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
