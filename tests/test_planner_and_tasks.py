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


def test_planner_builds_dynamic_wikipedia_steps_for_topic_prompt() -> None:
    planner = Planner()
    plan = planner.plan("summarize Grace Hopper from Wikipedia")

    assert plan.task_id == "wikipedia-summary"
    assert plan.steps[0].args["url"] == "https://en.wikipedia.org/wiki/Grace_Hopper"
    assert plan.steps[3].args["target"] == "citation_links"
    assert plan.verification_rules[0].value == "Grace_Hopper"
    assert plan.verification_rules[1].kind == "artifact_exists"


def test_planner_builds_wikipedia_section_steps() -> None:
    planner = Planner()
    plan = planner.plan("extract the filmography section for Leonardo DiCaprio from Wikipedia")

    assert plan.task_id == "wikipedia-section"
    assert plan.steps[0].args["url"] == "https://en.wikipedia.org/wiki/Leonardo_DiCaprio"
    assert plan.steps[2].args["target"] == "section_headings"
    assert plan.steps[3].args["target"] == "section:Filmography"


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
    assert "extract(target=citation_links)" in prompt
    assert "Wikipedia article URLs normally use the format https://en.wikipedia.org/wiki/Title_With_Underscores." in prompt
    assert "bounded fallback is: navigate to https://en.wikipedia.org/wiki/Main_Page" in prompt


def test_anthropic_prompt_includes_dynamic_wikipedia_grounding() -> None:
    provider = AnthropicPlannerProvider(api_key="test-key", model="claude-sonnet-4-6")

    prompt = provider._build_user_prompt(
        type("Req", (), {"goal": "summarize Grace Hopper from Wikipedia", "site": None, "observation_summary": {}})()
    )

    assert "Bundled task match: wikipedia-summary" in prompt
    assert "https://en.wikipedia.org/wiki/Grace_Hopper" in prompt
    assert "Extract a Wikipedia summary for Grace Hopper." in prompt
    assert "prefer direct navigation to the article URL instead of searching first." in prompt


def test_anthropic_prompt_includes_wikipedia_section_target_guidance() -> None:
    provider = AnthropicPlannerProvider(api_key="test-key", model="claude-sonnet-4-6")

    prompt = provider._build_user_prompt(
        type(
            "Req",
            (),
            {"goal": "extract the filmography section for Leonardo DiCaprio from Wikipedia", "site": None, "observation_summary": {}},
        )()
    )

    assert "Bundled task match: wikipedia-section" in prompt
    assert "extract(target=section_headings)" in prompt
    assert "extract(target=section:Filmography)" in prompt
    assert "valid logical extract targets include 'section_headings' and 'section:<Section Name>'." in prompt


def test_anthropic_prompt_includes_wikipedia_comparison_constraints() -> None:
    provider = AnthropicPlannerProvider(api_key="test-key", model="claude-sonnet-4-6")

    prompt = provider._build_user_prompt(
        type(
            "Req",
            (),
            {
                "goal": "Compare endangered birds in South America by population, habitat, and conservation initiatives and export to csv",
                "site": None,
                "observation_summary": {},
            },
        )()
    )

    assert "Comparison intent detected." in prompt
    assert "Comparison subject: endangered birds in South America" in prompt
    assert 'Requested columns (bounded): ["population", "habitat", "conservation initiatives"]' in prompt
    assert "Requested output mode: csv" in prompt
    assert "prefer exactly 3 entity pages unless the user explicitly asks for more." in prompt
    assert "Default to text comparison output unless the user explicitly asks for CSV" in prompt
    assert "prefer task_id 'wikipedia-comparison'" in prompt
    assert "Do not use extract target 'table'" in prompt
    assert "Only use existing Wikipedia extract targets that the runtime already supports" in prompt


def test_planner_rejects_wikipedia_comparison_plan_with_table_extract() -> None:
    class InvalidComparisonProvider:
        name = "invalid-comparison-provider"

        def plan(self, request) -> ProviderPlan:
            _ = request
            return ProviderPlan(
                steps=[
                    {"id": "1", "type": "goto", "args": {"url": "https://en.wikipedia.org/wiki/Spix%27s_macaw"}},
                    {"id": "2", "type": "extract", "args": {"target": "summary"}},
                    {"id": "3", "type": "goto", "args": {"url": "https://en.wikipedia.org/wiki/Lear%27s_macaw"}},
                    {"id": "4", "type": "extract", "args": {"target": "summary"}},
                    {"id": "5", "type": "extract", "args": {"target": "table"}},
                ],
                metadata={"columns": ["species", "population"]},
            )

    try:
        Planner(provider=InvalidComparisonProvider()).plan(
            "Compare endangered birds in South America by population and habitat"
        )
    except PlannerError as exc:
        assert "must not use extract target 'table'" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected PlannerError")


def test_planner_rejects_wikipedia_comparison_plan_when_no_section_target_can_be_inferred() -> None:
    class MissingSectionProvider:
        name = "missing-section-provider"

        def plan(self, request) -> ProviderPlan:
            _ = request
            return ProviderPlan(
                steps=[
                    {"id": "1", "type": "goto", "args": {"url": "https://en.wikipedia.org/wiki/Spix%27s_macaw"}},
                    {"id": "2", "type": "extract", "args": {"target": "summary"}},
                    {"id": "3", "type": "goto", "args": {"url": "https://en.wikipedia.org/wiki/Lear%27s_macaw"}},
                    {"id": "4", "type": "extract", "args": {"target": "summary"}},
                ],
                metadata={"columns": ["population"]},
            )

    try:
        Planner(provider=MissingSectionProvider()).plan(
            "Compare endangered birds in South America by population"
        )
    except PlannerError as exc:
        assert "must extract at least one section target" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected PlannerError")


def test_planner_normalizes_wikipedia_comparison_plan_by_inserting_section_extracts() -> None:
    class SummaryOnlyComparisonProvider:
        name = "summary-only-comparison-provider"

        def plan(self, request) -> ProviderPlan:
            _ = request
            return ProviderPlan(
                steps=[
                    {"id": "1", "type": "goto", "args": {"url": "https://en.wikipedia.org/wiki/Spix%27s_macaw"}},
                    {"id": "2", "type": "extract", "args": {"target": "summary"}},
                    {"id": "3", "type": "goto", "args": {"url": "https://en.wikipedia.org/wiki/Lear%27s_macaw"}},
                    {"id": "4", "type": "extract", "args": {"target": "summary"}},
                ],
                metadata={"columns": ["population", "habitat"]},
            )

    plan = Planner(provider=SummaryOnlyComparisonProvider()).plan(
        "Compare endangered birds in South America by population and habitat"
    )

    targets = [step.args["target"] for step in plan.steps if step.type == "extract"]
    assert targets == ["summary", "section:Habitat", "summary", "section:Habitat"]


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


def test_anthropic_provider_parses_python_literal_plan() -> None:
    class FakeTransport:
        def post_json(self, url, headers, payload, timeout_s):
            _ = url, headers, payload, timeout_s
            return {
                "id": "resp_456",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "{'task_id': 'wiki-brief', 'verifier_hint': 'brief ready', "
                            "'verification_rules': [{'kind': 'artifact_exists', 'value': 'extracts.summary', 'label': 'summary'}], "
                            "'steps': [{'id': 's1', 'type': 'navigate', 'args': {'url': 'https://en.wikipedia.org/wiki/Ada_Lovelace'}, "
                            "'expected': {}, 'timeout_ms': 10000}]}"
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


def test_anthropic_provider_reports_max_tokens_truncation_clearly() -> None:
    class FakeTransport:
        def post_json(self, url, headers, payload, timeout_s):
            _ = url, headers, payload, timeout_s
            return {
                "id": "resp_789",
                "stop_reason": "max_tokens",
                "content": [{"type": "text", "text": '{"task_id":"wikipedia-comparison","steps":[{"id":1'}],
            }

    provider = AnthropicPlannerProvider(
        api_key="test-key",
        model="claude-sonnet-4-20250514",
        transport=FakeTransport(),
    )

    try:
        provider.plan(
            request=type(
                "Req",
                (),
                {
                    "goal": "Compare endangered birds in South America by population and habitat",
                    "site": None,
                    "observation_summary": {},
                },
            )()
        )
    except PlannerError as exc:
        assert "truncated at max_tokens" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected PlannerError")


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
