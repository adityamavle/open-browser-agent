from __future__ import annotations

from open_browser_agent.planner import (
    AnthropicPlannerProvider,
    Planner,
    PlannerError,
    ProviderPlan,
    build_planner,
)
from open_browser_agent.tasks.form_fill import FORM_FILL_TASK
from open_browser_agent.tasks.table_scrape import TABLE_SCRAPE_TASK
from open_browser_agent.tasks.wikipedia_summary import WIKIPEDIA_SUMMARY_TASK


def test_planner_returns_task_steps() -> None:
    planner = Planner()
    plan = planner.plan("wiki summary")

    assert len(plan.steps) == len(WIKIPEDIA_SUMMARY_TASK.steps)
    assert plan.steps[0].type == "navigate"
    assert plan.provider_name == "task-registry"
    assert plan.task_id == "wikipedia-summary"


def test_planner_raises_for_missing_goal() -> None:
    planner = Planner()

    try:
        planner.plan("missing goal")
    except PlannerError as exc:
        assert "No matching task found" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected PlannerError")


def test_planner_validates_provider_steps() -> None:
    class DictProvider:
        name = "dict-provider"

        def plan(self, request) -> ProviderPlan:
            _ = request
            return ProviderPlan(
                steps=[{"id": "s1", "type": "navigate", "args": {"url": "https://example.test"}, "timeout_ms": 2222}],
                task_id="custom",
            )

    plan = Planner(provider=DictProvider()).plan("custom goal")

    assert plan.provider_name == "dict-provider"
    assert plan.steps[0].id == "s1"
    assert plan.steps[0].timeout_ms == 2222


def test_planner_rejects_invalid_provider_steps() -> None:
    class InvalidProvider:
        name = "invalid-provider"

        def plan(self, request) -> ProviderPlan:
            _ = request
            return ProviderPlan(steps=[{"type": "navigate"}])

    try:
        Planner(provider=InvalidProvider()).plan("bad goal")
    except PlannerError as exc:
        assert "missing required keys" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected PlannerError")


def test_planner_rejects_unsupported_extract_args() -> None:
    class InvalidExtractProvider:
        name = "invalid-extract-provider"

        def plan(self, request) -> ProviderPlan:
            _ = request
            return ProviderPlan(
                steps=[
                    {
                        "id": "s1",
                        "type": "extract",
                        "args": {"selector": "#id", "attribute": "innerText"},
                        "expected": {},
                        "timeout_ms": 1000,
                    }
                ]
            )

    try:
        Planner(provider=InvalidExtractProvider()).plan("bad extract")
    except PlannerError as exc:
        assert "extract" in str(exc)
        assert "target" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected PlannerError")


def test_planner_coerces_string_expected_to_description_dict() -> None:
    class StringExpectedProvider:
        name = "string-expected-provider"

        def plan(self, request) -> ProviderPlan:
            _ = request
            return ProviderPlan(
                steps=[
                    {
                        "id": "s1",
                        "type": "wait_for",
                        "args": {"selector": "main"},
                        "expected": "main content is visible",
                        "timeout_ms": 1000,
                    }
                ]
            )

    plan = Planner(provider=StringExpectedProvider()).plan("coerce expected")

    assert plan.steps[0].expected == {"description": "main content is visible"}


def test_anthropic_prompt_includes_bundled_task_grounding() -> None:
    provider = AnthropicPlannerProvider(api_key="test-key", model="claude-sonnet-4-6")

    prompt = provider._build_user_prompt(type("Req", (), {"goal": "wikipedia-summary", "site": None, "observation_summary": {}})())

    assert "Bundled task match: wikipedia-summary" in prompt
    assert "https://en.wikipedia.org/wiki/Ada_Lovelace" in prompt
    assert "extract(target=summary)" in prompt


def test_planner_rejects_overlong_extract_target() -> None:
    class LongTargetProvider:
        name = "long-target-provider"

        def plan(self, request) -> ProviderPlan:
            _ = request
            return ProviderPlan(
                steps=[
                    {
                        "id": "s1",
                        "type": "extract",
                        "args": {
                            "target": "Extract the first 3-5 paragraphs of the article introduction and include title, summary, and citations in a single target"
                        },
                        "expected": {},
                        "timeout_ms": 1000,
                    }
                ]
            )

    try:
        Planner(provider=LongTargetProvider()).plan("bad long target")
    except PlannerError as exc:
        assert "target is too long" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected PlannerError")


def test_anthropic_provider_parses_json_plan() -> None:
    class FakeTransport:
        def post_json(self, url, headers, payload, timeout_s):
            assert url == "https://api.anthropic.com/v1/messages"
            assert headers["x-api-key"] == "test-key"
            assert headers["anthropic-version"] == "2023-06-01"
            assert payload["model"] == "claude-sonnet-4-20250514"
            assert payload["max_tokens"] == 1200
            _ = timeout_s
            return {
                "id": "resp_123",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"task_id":"wiki-brief","verifier_hint":"brief ready",'
                            '"verification_rules":[{"kind":"artifact_exists","value":"extracts.summary","label":"summary"}],'
                            '"steps":[{"id":"s1","type":"navigate","args":{"url":"https://en.wikipedia.org/wiki/Ada_Lovelace"},'
                            '"expected":{},"timeout_ms":10000}]}'
                        ),
                    }
                ],
            }

    provider = AnthropicPlannerProvider(
        api_key="test-key",
        model="claude-sonnet-4-20250514",
        transport=FakeTransport(),
    )

    plan = provider.plan(request=type("Req", (), {"goal": "research Ada Lovelace", "site": None, "observation_summary": {}})())

    assert plan.task_id == "wiki-brief"
    assert plan.steps[0]["type"] == "navigate"
    assert plan.verification_rules[0].kind == "artifact_exists"
    assert plan.metadata["model"] == "claude-sonnet-4-20250514"


def test_build_planner_supports_anthropic(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    monkeypatch.setenv("OBA_ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    planner = build_planner("anthropic")

    assert planner.provider.name == "anthropic"


def test_build_planner_reads_anthropic_key_from_dotenv(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OBA_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OBA_ANTHROPIC_MODEL", raising=False)
    (tmp_path / ".env").write_text(
        "ANTHROPIC_API_KEY=dotenv-key\nOBA_ANTHROPIC_MODEL=claude-sonnet-4-20250514\n",
        encoding="utf-8",
    )

    planner = build_planner("anthropic")

    assert planner.provider.name == "anthropic"
    assert planner.provider.api_key == "dotenv-key"


def test_task_modules_export_expected_specs() -> None:
    assert FORM_FILL_TASK.task_id == "form-fill"
    assert TABLE_SCRAPE_TASK.task_id == "table-scrape"
    assert WIKIPEDIA_SUMMARY_TASK.task_id == "wikipedia-summary"
