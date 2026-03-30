from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, unquote

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
WIKIPEDIA_MAIN_URL = "https://en.wikipedia.org/wiki/Main_Page"
WIKIPEDIA_URL_PATTERN = re.compile(r"https?://en\.wikipedia\.org/wiki/(?P<slug>[^?#\s]+)", re.IGNORECASE)


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
        task_id="wikipedia-search-press",
        summary="Search Wikipedia by typing a query and pressing Enter.",
        aliases=("wiki press", "wikipedia press", "search with enter"),
        steps=[
            Step(id="goto-wikipedia-main", type="navigate", args={"url": WIKIPEDIA_MAIN_URL}),
            Step(id="wait-wikipedia-search", type="wait_for", args={"selector": "input[name='search']"}),
            Step(
                id="type-search-query",
                type="type",
                args={"selector": "input[name='search']", "text": "Ada Lovelace"},
            ),
            Step(id="press-enter-search", type="press", args={"keys": "Enter"}),
        ],
        verifier_hint="Keyboard Enter triggers navigation to the target article.",
        verification_rules=[
            VerificationRule(kind="url_contains", value="Ada_Lovelace", label="article URL"),
            VerificationRule(
                kind="text_contains",
                value="English mathematician and writer",
                label="summary text",
            ),
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
            Step(id="extract-citation-links", type="extract", args={"target": "citation_links"}),
        ],
        verifier_hint="Summary text is non-empty and at least one cited link is present.",
        verification_rules=[
            VerificationRule(kind="url_contains", value="Ada_Lovelace", label="article URL"),
            VerificationRule(kind="artifact_exists", value="extracts.summary", label="summary extracted"),
            VerificationRule(kind="artifact_list_min_length", value={"path": "extracts.citation_links", "min": 1}, label="citation links"),
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
    dynamic_wikipedia_section_task = _build_dynamic_wikipedia_section_task(goal)
    if dynamic_wikipedia_section_task is not None:
        return dynamic_wikipedia_section_task
    dynamic_wikipedia_task = _build_dynamic_wikipedia_summary_task(goal)
    if dynamic_wikipedia_task is not None:
        return dynamic_wikipedia_task
    return None


def _build_dynamic_wikipedia_section_task(goal: str) -> TaskSpec | None:
    request = _extract_wikipedia_section_request(goal)
    if request is None:
        return None

    article = request["article"]
    if request["kind"] == "section_headings":
        return TaskSpec(
            task_id="wikipedia-section-headings",
            summary=f"Extract section headings for {article['display_title']} from Wikipedia.",
            steps=[
                Step(id="goto-wikipedia", type="navigate", args={"url": article["url"]}),
                Step(id="wait-summary", type="wait_for", args={"selector": "main"}),
                Step(id="extract-section-headings", type="extract", args={"target": "section_headings"}),
            ],
            verifier_hint="Section headings are extracted from the article.",
            verification_rules=[
                VerificationRule(kind="url_contains", value=article["slug"], label="article URL"),
                VerificationRule(
                    kind="artifact_list_min_length",
                    value={"path": "extracts.section_headings", "min": 1},
                    label="section headings",
                ),
            ],
        )

    section_name = request["section_name"]
    section_target = f"section:{section_name}"
    return TaskSpec(
        task_id="wikipedia-section",
        summary=f"Extract the {section_name} section for {article['display_title']} from Wikipedia.",
        steps=[
            Step(id="goto-wikipedia", type="navigate", args={"url": article["url"]}),
            Step(id="wait-summary", type="wait_for", args={"selector": "main"}),
            Step(id="extract-section-headings", type="extract", args={"target": "section_headings"}),
            Step(id="extract-section", type="extract", args={"target": section_target}),
        ],
        verifier_hint="Requested article section is extracted from the page.",
        verification_rules=[
            VerificationRule(kind="url_contains", value=article["slug"], label="article URL"),
            VerificationRule(
                kind="artifact_list_min_length",
                value={"path": "extracts.section_headings", "min": 1},
                label="section headings",
            ),
            VerificationRule(
                kind="artifact_text_min_length",
                value={"path": f"extracts.{section_target}", "min_chars": 20},
                label="section extracted",
            ),
        ],
    )


def _build_dynamic_wikipedia_summary_task(goal: str) -> TaskSpec | None:
    stripped = goal.strip()
    lowered = stripped.lower()
    if not stripped:
        return None
    if lowered in {"wikipedia-summary", "wiki summary", "wikipedia", "extract wikipedia summary"}:
        return None

    article = _extract_wikipedia_article(goal)
    if article is None:
        return None

    return TaskSpec(
        task_id="wikipedia-summary",
        summary=f"Extract a Wikipedia summary for {article['display_title']}.",
        aliases=("wikipedia", "wiki summary", "extract wikipedia summary"),
        steps=[
            Step(id="goto-wikipedia", type="navigate", args={"url": article["url"]}),
            Step(id="wait-summary", type="wait_for", args={"selector": "main"}),
            Step(id="extract-summary", type="extract", args={"target": "summary"}),
            Step(id="extract-citation-links", type="extract", args={"target": "citation_links"}),
        ],
        verifier_hint="Summary text is non-empty and at least one cited link is present.",
        verification_rules=[
            VerificationRule(kind="url_contains", value=article["slug"], label="article URL"),
            VerificationRule(kind="artifact_exists", value="extracts.summary", label="summary extracted"),
            VerificationRule(kind="artifact_list_min_length", value={"path": "extracts.citation_links", "min": 1}, label="citation links"),
        ],
    )


def _extract_wikipedia_article(goal: str) -> dict[str, str] | None:
    goal = goal.strip()
    url_match = WIKIPEDIA_URL_PATTERN.search(goal)
    if url_match:
        slug = url_match.group("slug")
        return _article_from_slug(slug)

    lowered = goal.lower()
    if "wikipedia" not in lowered and "wiki" not in lowered:
        return None

    patterns = (
        r"^(?:wikipedia-summary|wiki summary|wikipedia summary)\s*:?\s+(?P<topic>.+)$",
        r"^(?:summarize|get|extract|research|brief)\s+(?P<topic>.+?)\s+from\s+(?:the\s+)?wikipedia$",
        r"^(?:get\s+)?(?:a\s+)?(?:short\s+)?wikipedia summary for\s+(?P<topic>.+)$",
        r"^(?:get\s+)?(?:a\s+)?(?:short\s+)?wiki summary for\s+(?P<topic>.+)$",
        r"^open (?:the )?(?P<topic>.+?) wikipedia page and extract (?:the )?summary$",
        r"^(?P<topic>.+?) wikipedia summary$",
    )
    for pattern in patterns:
        match = re.match(pattern, goal, flags=re.IGNORECASE)
        if not match:
            continue
        topic = _clean_topic(match.group("topic"))
        if topic:
            return _article_from_topic(topic)
    return None


def _extract_wikipedia_section_request(goal: str) -> dict[str, object] | None:
    goal = goal.strip()
    if not goal:
        return None
    patterns = (
        (
            r"^(?:show|get|extract|list)\s+(?:the\s+)?section headings for\s+(?P<topic>.+?)\s+from\s+(?:the\s+)?wikipedia$",
            "section_headings",
        ),
        (
            r"^(?:show|get|extract)\s+(?:the\s+)?(?P<section>.+?)\s+section for\s+(?P<topic>.+?)\s+from\s+(?:the\s+)?wikipedia$",
            "section",
        ),
    )
    for pattern, kind in patterns:
        match = re.match(pattern, goal, flags=re.IGNORECASE)
        if not match:
            continue
        article = _article_from_topic(_clean_topic(match.group("topic")))
        if kind == "section_headings":
            return {"kind": kind, "article": article}
        return {
            "kind": kind,
            "article": article,
            "section_name": _normalize_section_name(match.group("section")),
        }
    return None


def _article_from_topic(topic: str) -> dict[str, str]:
    display_title = topic.strip().replace("_", " ")
    slug = quote(display_title.replace(" ", "_"), safe="()")
    return {
        "display_title": display_title,
        "slug": slug,
        "url": f"https://en.wikipedia.org/wiki/{slug}",
    }


def _article_from_slug(slug: str) -> dict[str, str]:
    normalized_slug = slug.strip()
    decoded_slug = unquote(normalized_slug)
    display_title = decoded_slug.replace("_", " ")
    return {
        "display_title": display_title,
        "slug": normalized_slug,
        "url": f"https://en.wikipedia.org/wiki/{normalized_slug}",
    }


def _clean_topic(topic: str) -> str:
    cleaned = topic.strip().strip("\"'").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _normalize_section_name(section_name: str) -> str:
    cleaned = _clean_topic(section_name)
    return " ".join(part.capitalize() if not part.isupper() else part for part in cleaned.split(" "))
