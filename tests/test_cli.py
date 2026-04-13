from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

from open_browser_agent import cli
from open_browser_agent.schemas.observation import Observation
from open_browser_agent.schemas.step import Step
from open_browser_agent.strategies import get_fallback_plan
from open_browser_agent.strategies.wikipedia import (
    build_wikipedia_search_fallback_steps,
    extract_wikipedia_topic_from_steps,
)
from open_browser_agent.tasks.registry import FORM_FILL_URL, TABLE_SCRAPE_URL, WIKIPEDIA_SUMMARY_URL


def test_build_parser_accepts_examples_list() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["examples", "list"])
    assert args.command == "examples"
    assert args.examples_command == "list"


def test_build_parser_accepts_reliability() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["reliability", "form-fill", "--runs", "3", "--stop-on-failure", "--planner", "task-registry"])

    assert args.command == "reliability"
    assert args.goal == "form-fill"
    assert args.runs == 3
    assert args.stop_on_failure is True
    assert args.planner == "task-registry"


def test_build_parser_accepts_plan() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["plan", "wiki summary", "--planner", "task-registry"])

    assert args.command == "plan"
    assert args.goal == "wiki summary"
    assert args.planner == "task-registry"


def test_build_parser_accepts_run_artifacts_mode() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["run", "wiki summary", "--artifacts", "detailed"])

    assert args.command == "run"
    assert args.goal == "wiki summary"
    assert args.artifacts == "detailed"


def test_build_parser_accepts_eval() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["eval", "--runs", "4", "--planner", "task-registry"])

    assert args.command == "eval"
    assert args.goal is None
    assert args.runs == 4
    assert args.planner == "task-registry"


def test_handle_examples_list(capsys) -> None:
    code = cli.handle_examples_list()
    output = capsys.readouterr().out

    assert code == 0
    assert "wikipedia-summary" in output


def test_handle_run_for_unknown_goal(tmp_path: Path, capsys) -> None:
    code = cli.handle_run("missing goal", str(tmp_path))
    output = capsys.readouterr().out

    traces = list(tmp_path.glob("*.json"))
    assert code == 1
    assert "No example task matched" in output
    assert len(traces) == 1


def test_handle_run_failure_prints_run_summary(tmp_path: Path, capsys) -> None:
    class FakeBrowserSession:
        def __init__(self) -> None:
            self.page = None

        def __enter__(self):
            raise cli.BrowserSessionError("Playwright missing")

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    cli.BrowserSession = FakeBrowserSession

    code = cli.handle_run("wiki summary", str(tmp_path))
    output = capsys.readouterr().out

    assert code == 1
    assert "Browser session error: Playwright missing." in output
    assert "Run summary:" in output
    assert "- status: failure" in output
    assert "- planner: task-registry" in output


def test_handle_run_known_goal_suppresses_artifacts_when_disabled(tmp_path: Path, capsys) -> None:
    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector

        def inner_text(self) -> str:
            if self.selector == "body":
                return self.page.body_text
            if self.selector == "p":
                return self.page.summary_text
            if self.selector == "table":
                return self.page.table_text
            raise KeyError(self.selector)

    class FakePage:
        def __init__(self) -> None:
            self.url = "about:blank"
            self.title_value = "Blank"
            self.body_text = ""
            self.summary_text = ""
            self.table_text = ""
            self.keyboard = type("Keyboard", (), {"press": lambda self, keys: None})()
            self.citation_links = [{"text": "Citation 1", "href": "https://example.com/citation-1"}]

        def goto(self, url: str) -> None:
            self.url = url
            if "Ada_Lovelace" in url:
                self.title_value = "Ada Lovelace - Summary"
                self.body_text = "Ada Lovelace was an English mathematician and writer. [1]"
                self.summary_text = "Ada Lovelace was an English mathematician and writer.[1]"

        def click(self, selector: str) -> None:
            self.last_click = selector

        def fill(self, selector: str, text: str) -> None:
            self.last_fill = (selector, text)

        def wait_for_selector(self, selector: str) -> None:
            self.last_wait = selector

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        def evaluate(self, script: str):
            if "querySelectorAll('main p, article p, p')" in script:
                return self.summary_text
            if "reference a[href]" in script:
                return self.citation_links
            raise AssertionError("Unexpected evaluate call")

        def title(self) -> str:
            return self.title_value

        def screenshot(self, path: str) -> None:
            self.screenshot_path = path

        def snapshot_dom_summary(self) -> list[str]:
            return ["main:Ada Lovelace", "a:[1]"]

    class FakeBrowserSession:
        def __init__(self) -> None:
            self.page = FakePage()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    cli.BrowserSession = FakeBrowserSession

    code = cli.handle_run("wiki summary", str(tmp_path), artifacts_mode="none")
    output = capsys.readouterr().out

    assert code == 0
    assert "Run summary:" in output
    assert "- artifacts:" not in output


def test_handle_run_for_known_goal(tmp_path: Path, capsys) -> None:
    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector

        def inner_text(self) -> str:
            if self.selector == "body":
                return self.page.body_text
            if self.selector == "p":
                return self.page.summary_text
            if self.selector == "table":
                return self.page.table_text
            raise KeyError(self.selector)

    class FakePage:
        def __init__(self) -> None:
            self.url = "about:blank"
            self.title_value = "Blank"
            self.body_text = ""
            self.summary_text = ""
            self.table_text = "Last Name First Name Email Due Web Site Action Smith John jdoe@hotmail.com $50.00 http://www.jsmith.com edit delete"
            self.keyboard = type("Keyboard", (), {"press": lambda self, keys: None})()
            self.citation_links = [{"text": "Citation 1", "href": "https://example.com/citation-1"}]

        def goto(self, url: str) -> None:
            self.url = url
            if "Ada_Lovelace" in url:
                self.title_value = "Ada Lovelace - Summary"
                self.body_text = (
                    "Ada Lovelace was an English mathematician and writer known for her work "
                    "on Charles Babbage's early mechanical general-purpose computer. [1]"
                )
                self.summary_text = (
                    "Ada Lovelace was an English mathematician and writer known for her work "
                    "on Charles Babbage's early mechanical general-purpose computer.[1]"
                )

        def click(self, selector: str) -> None:
            self.last_click = selector

        def fill(self, selector: str, text: str) -> None:
            self.last_fill = (selector, text)

        def wait_for_selector(self, selector: str) -> None:
            self.last_wait = selector

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        def evaluate(self, script: str):
            if "querySelectorAll('main p, article p, p')" in script:
                return self.summary_text
            if "reference a[href]" in script:
                return self.citation_links
            raise AssertionError("Unexpected evaluate call")

        def title(self) -> str:
            return self.title_value

        def screenshot(self, path: str) -> None:
            self.screenshot_path = path

        def snapshot_dom_summary(self) -> list[str]:
            return ["main:Ada Lovelace", "a:[1]"]

    class FakeBrowserSession:
        def __init__(self) -> None:
            self.page = FakePage()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    cli.BrowserSession = FakeBrowserSession

    code = cli.handle_run("wiki summary", str(tmp_path))
    output = capsys.readouterr().out
    trace = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))

    assert code == 0
    assert "Task 'wikipedia-summary' completed with success=True" in output
    assert "Run summary:" in output
    assert "- planner: task-registry" in output
    assert "1. navigate https://en.wikipedia.org/wiki/Ada_Lovelace" in output
    assert "3. extract summary" in output
    assert "4. extract citation_links" in output
    assert "- research_brief:" in output
    assert "  - topic: Ada Lovelace - Summary" in output
    assert "- artifacts:" in output
    assert "- summary: Ada Lovelace was an English mathematician and writer known for her work" in output
    assert "Verification checks: total=3 passed=3 failed=0" in output
    assert trace["steps"][0]["id"] == "goto-wikipedia"
    assert trace["steps"][0]["args"]["url"] == WIKIPEDIA_SUMMARY_URL
    assert trace["events"][0]["event"] == "plan_generated"
    assert trace["verification"]["success"] is True
    assert len(trace["verification"]["checks"]) == 3
    assert all(check["passed"] for check in trace["verification"]["checks"])
    assert trace["events"][0]["provider"] == "task-registry"


def test_print_run_report_detailed_artifacts(capsys) -> None:
    outcome = cli.RunOutcome(
        success=True,
        reason="All verification rules passed.",
        trace_path=Path("trace.json"),
        task_id="wikipedia-summary",
        duration_ms=123,
        planner_provider="anthropic",
        planner_model="claude-sonnet-4-6",
        steps=[
            {
                "id": "1",
                "type": "extract",
                "args": {"target": "summary"},
                "expected": {"non_empty": True},
                "timeout_ms": 1000,
            }
        ],
        artifacts={"extracts": {"summary": "Line one.\nLine two."}},
    )

    cli._print_run_report("wiki summary", outcome, artifacts_mode="detailed")
    output = capsys.readouterr().out

    assert "- artifacts:" in output
    assert "Line one.\nLine two." in output


def test_build_run_artifacts_includes_wikipedia_research_brief() -> None:
    observation = Observation(
        url="https://en.wikipedia.org/wiki/Grace_Hopper",
        title="Grace Hopper - Wikipedia",
        visible_text="Visible text",
        dom_summary=[],
        form_state=[],
        screenshot_path=None,
    )

    artifacts = cli._build_run_artifacts(
        task_id="wikipedia-summary",
        goal="summarize Grace Hopper from Wikipedia",
        observation=observation,
        extract_artifacts={
            "summary": "Grace Hopper summary",
            "citation_links": [{"text": "[1]", "href": "#cite_note-1"}],
            "section_headings": ["Career", "Legacy"],
            "section:Legacy": "Legacy text",
        },
    )

    assert artifacts["isLLMReProcessingRequired"] is False
    assert artifacts["research_brief"]["topic"] == "Grace Hopper"
    assert artifacts["research_brief"]["summary"] == "Grace Hopper summary"
    assert artifacts["research_brief"]["sections"]["Legacy"] == "Legacy text"


def test_print_run_report_shows_research_brief(capsys) -> None:
    outcome = cli.RunOutcome(
        success=True,
        reason="All verification rules passed.",
        trace_path=Path("trace.json"),
        task_id="wikipedia-section",
        duration_ms=321,
        planner_provider="task-registry",
        steps=[],
        artifacts={
            "research_brief": {
                "topic": "Leonardo DiCaprio",
                "article_url": "https://en.wikipedia.org/wiki/Leonardo_DiCaprio",
                "sections": {"Filmography": "Main articles: Leonardo DiCaprio filmography"},
            },
            "extracts": {"section:Filmography": "Main articles: Leonardo DiCaprio filmography"},
        },
    )

    cli._print_run_report("extract the filmography section for Leonardo DiCaprio from Wikipedia", outcome, artifacts_mode="summary")
    output = capsys.readouterr().out

    assert "- research_brief:" in output
    assert "  - topic: Leonardo DiCaprio" in output
    assert "  - section[Filmography]: Main articles: Leonardo DiCaprio filmography" in output


def test_extract_wikipedia_topic_from_steps() -> None:
    steps = [
        Step(
            id="1",
            type="navigate",
            args={"url": "https://en.wikipedia.org/wiki/Grace_Hopper"},
            expected={},
            timeout_ms=1000,
        )
    ]

    topic = extract_wikipedia_topic_from_steps(steps)

    assert topic == "Grace Hopper"


def test_build_wikipedia_search_fallback_steps() -> None:
    steps = build_wikipedia_search_fallback_steps("Grace Hopper")

    assert [step.type for step in steps] == ["navigate", "wait_for", "type", "press", "wait_for", "extract", "extract"]
    assert steps[0].args["url"] == "https://en.wikipedia.org/wiki/Main_Page"
    assert steps[2].args["text"] == "Grace Hopper"
    assert steps[-2].args["target"] == "summary"
    assert steps[-1].args["target"] == "citation_links"


def test_get_fallback_plan_returns_wikipedia_strategy() -> None:
    plan_result = SimpleNamespace(
        task_id="wikipedia-summary",
        steps=[
            Step(
                id="1",
                type="navigate",
                args={"url": "https://en.wikipedia.org/wiki/Grace_Hopper"},
                expected={},
                timeout_ms=1000,
            )
        ],
    )

    fallback = get_fallback_plan(plan_result, "Verification failed")

    assert fallback is not None
    assert fallback.strategy_name == "wikipedia-search-press"
    assert fallback.steps[2].args["text"] == "Grace Hopper"


def test_handle_replay(tmp_path: Path, capsys) -> None:
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps({"goal": "goal", "task": "task", "events": [], "artifacts": {}, "verification": None}),
        encoding="utf-8",
    )

    code = cli.handle_replay(str(trace_path))
    output = capsys.readouterr().out

    assert code == 0
    assert '"mode": "dry-run"' in output


def test_main_dispatches_examples_list(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["oba", "examples", "list"])
    assert cli.main() == 0


def test_bundled_tasks_use_public_urls() -> None:
    urls = {FORM_FILL_URL, TABLE_SCRAPE_URL, WIKIPEDIA_SUMMARY_URL}
    assert all(url.startswith("https://") for url in urls)


def test_handle_reliability_reports_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    outcomes = [
        cli.RunOutcome(
            success=True,
            reason="All verification rules passed.",
            trace_path=tmp_path / "r1.json",
            task_id="form-fill",
            duration_ms=100,
            action_stats={"goto": {"ok": 1, "failed": 0}, "type": {"ok": 2, "failed": 0}},
        ),
        cli.RunOutcome(
            success=False,
            reason="Step failed: wait timeout",
            trace_path=tmp_path / "r2.json",
            task_id="form-fill",
            duration_ms=200,
            failure_kind="execution",
            action_stats={"goto": {"ok": 1, "failed": 0}, "wait_for": {"ok": 0, "failed": 1}},
        ),
        cli.RunOutcome(
            success=True,
            reason="All verification rules passed.",
            trace_path=tmp_path / "r3.json",
            task_id="form-fill",
            duration_ms=300,
            action_stats={"goto": {"ok": 1, "failed": 0}, "click": {"ok": 1, "failed": 0}},
        ),
    ]

    state = SimpleNamespace(index=0)

    def fake_run_goal(goal: str, trace_dir: str, planner_name: str = "task-registry") -> cli.RunOutcome:
        _ = goal, trace_dir, planner_name
        outcome = outcomes[state.index]
        state.index += 1
        return outcome

    monkeypatch.setattr(cli, "run_goal", fake_run_goal)

    code = cli.handle_reliability("form-fill", runs=3, trace_dir=str(tmp_path))
    output = capsys.readouterr().out

    assert code == 1
    assert "[1/3] PASS" in output
    assert "[2/3] FAIL" in output
    assert '"successes": 2' in output
    assert '"failures": 1' in output
    assert '"success_rate": 0.667' in output
    assert '"action_coverage"' in output
    assert '"goto"' in output


def test_handle_reliability_stops_on_unknown_task(monkeypatch, tmp_path: Path, capsys) -> None:
    outcome = cli.RunOutcome(
        success=False,
        reason="No matching task found. Planner/executor implementation pending.",
        trace_path=tmp_path / "missing.json",
        task_id=None,
        duration_ms=10,
        failure_kind="task_lookup",
    )
    monkeypatch.setattr(cli, "run_goal", lambda goal, trace_dir, planner_name="task-registry": outcome)

    code = cli.handle_reliability("unknown", runs=5, trace_dir=str(tmp_path))
    output = capsys.readouterr().out

    assert code == 1
    assert '"runs_executed": 1' in output


def test_handle_plan_prints_structured_steps(capsys) -> None:
    code = cli.handle_plan("wiki summary")
    output = capsys.readouterr().out

    assert code == 0
    assert '"ok": true' in output.lower()
    assert '"provider": "task-registry"' in output
    assert '"task": "wikipedia-summary"' in output


def test_handle_eval_reports_task_summaries(monkeypatch, tmp_path: Path, capsys) -> None:
    single_outcomes = {
        "form-fill": cli.RunOutcome(
            success=True,
            reason="All verification rules passed.",
            trace_path=tmp_path / "single1.json",
            task_id="form-fill",
            duration_ms=100,
        ),
        "table-scrape": cli.RunOutcome(
            success=False,
            reason="Step failed: extract failed",
            trace_path=tmp_path / "single2.json",
            task_id="table-scrape",
            duration_ms=120,
            failure_kind="execution",
        ),
    }

    def fake_run_goal(goal: str, trace_dir: str, planner_name: str = "task-registry") -> cli.RunOutcome:
        _ = trace_dir, planner_name
        return single_outcomes[goal]

    def fake_reliability(
        goal: str,
        runs: int,
        trace_dir: str,
        planner_name: str = "task-registry",
        stop_on_failure: bool = False,
        emit_progress: bool = True,
    ):
        _ = trace_dir, planner_name, stop_on_failure, emit_progress
        if goal == "form-fill":
            return {
                "goal": goal,
                "task": "form-fill",
                "runs_requested": runs,
                "runs_executed": runs,
                "successes": runs,
                "failures": 0,
                "success_rate": 1.0,
                "avg_duration_ms": 100,
                "failure_reasons": {},
                "action_coverage": {},
            }
        return {
            "goal": goal,
            "task": "table-scrape",
            "runs_requested": runs,
            "runs_executed": runs,
            "successes": runs - 1,
            "failures": 1,
            "success_rate": round((runs - 1) / runs, 3),
            "avg_duration_ms": 120,
            "failure_reasons": {"Step failed: extract failed": 1},
            "action_coverage": {},
        }

    monkeypatch.setattr(cli, "run_goal", fake_run_goal)
    monkeypatch.setattr(cli, "_run_reliability_series", fake_reliability)

    code = cli.handle_eval("form-fill", runs=2, trace_dir=str(tmp_path))
    output = capsys.readouterr().out

    assert code == 0
    assert "EVAL PASS task=form-fill" in output
    assert '"all_passed": true' in output.lower()


def test_handle_eval_defaults_to_all_tasks(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "run_goal",
        lambda goal, trace_dir, planner_name="task-registry": cli.RunOutcome(
            success=True,
            reason="ok",
            trace_path=tmp_path / f"{goal}.json",
            task_id=goal,
            duration_ms=10,
        ),
    )
    monkeypatch.setattr(
        cli,
        "_run_reliability_series",
        lambda goal, runs, trace_dir, planner_name="task-registry", stop_on_failure=False, emit_progress=True: {
            "goal": goal,
            "task": goal,
            "runs_requested": runs,
            "runs_executed": runs,
            "successes": runs,
            "failures": 0,
            "success_rate": 1.0,
            "avg_duration_ms": 10,
            "failure_reasons": {},
            "action_coverage": {},
        },
    )

    code = cli.handle_eval(None, runs=1, trace_dir=str(tmp_path))
    output = capsys.readouterr().out

    assert code == 0
    assert '"task": "form-fill"' in output
    assert '"task": "table-scrape"' in output


def test_build_comparison_artifact_uses_extract_sequence() -> None:
    observation = SimpleNamespace(url="https://en.wikipedia.org/wiki/Andean_condor", title="Andean condor - Wikipedia")
    artifact = cli._build_comparison_artifact(
        task_id="wikipedia-comparison",
        goal="Compare endangered birds in South America by habitat and conservation initiatives and export to csv",
        observation=observation,
        extract_sequence=[
            {
                "step_id": "condor-habitat",
                "target": "section:Habitat",
                "value": "Andean mountains and open grasslands.",
                "current_url": "https://en.wikipedia.org/wiki/Andean_condor",
                "page_title": "Andean condor - Wikipedia",
            },
            {
                "step_id": "condor-conservation",
                "target": "section:Conservation initiatives",
                "value": "Protected habitat and breeding programs.",
                "current_url": "https://en.wikipedia.org/wiki/Andean_condor",
                "page_title": "Andean condor - Wikipedia",
            },
            {
                "step_id": "macaw-habitat",
                "target": "section:Habitat",
                "value": "Tropical forests in northern South America.",
                "current_url": "https://en.wikipedia.org/wiki/Spix%27s_macaw",
                "page_title": "Spix's macaw - Wikipedia",
            },
        ],
        plan_metadata={"mode": "llm", "model": "claude-sonnet-4-6"},
    )

    assert artifact is not None
    assert artifact["output_mode"] == "csv"
    assert artifact["isLLMReProcessingRequired"] is True
    assert artifact["columns"] == ["habitat", "conservation initiatives"]
    assert artifact["raw_rows"][0]["habitat"] == "Andean mountains and open grasslands."
    assert len(artifact["rows"]) == 2
    assert artifact["rows"][0]["entity_name"] == "Andean condor"
    assert artifact["rows"][0]["habitat"] == "Andean mountains and open grasslands."


def test_build_comparison_artifact_supports_bestbuy_product_facts() -> None:
    observation = SimpleNamespace(
        url="file:///bestbuy_surface_laptop_13.html",
        title="Microsoft Surface Laptop 13-inch - Best Buy",
    )
    artifact = cli._build_comparison_artifact(
        task_id="bestbuy-laptop-comparison",
        goal="Compare Best Buy laptops by price, display size, RAM, and storage and export to csv",
        observation=observation,
        extract_sequence=[
            {
                "step_id": "macbook-facts",
                "target": "bestbuy_product_facts",
                "value": {
                    "entity_name": "Apple MacBook Air 13-inch Laptop - M4 chip - 16GB Memory - 512GB SSD",
                    "product_name": "Apple MacBook Air 13-inch Laptop - M4 chip - 16GB Memory - 512GB SSD",
                    "product_url": "file:///bestbuy_macbook_air_13.html",
                    "sku": "6530001",
                    "price": "$1,099.00",
                    "facts": {
                        "model name": "Apple MacBook Air 13-inch Laptop - M4 chip - 16GB Memory - 512GB SSD",
                        "display size": "13.6 inches",
                        "ram": "16 gigabytes",
                        "storage": "512 gigabytes",
                    },
                    "specifications": {
                        "Screen Size": "13.6 inches",
                        "System Memory (RAM)": "16 gigabytes",
                        "Solid State Drive Capacity": "512 gigabytes",
                    },
                },
                "current_url": "file:///bestbuy_macbook_air_13.html",
                "page_title": "Apple MacBook Air 13-inch Laptop - Best Buy",
            },
            {
                "step_id": "macbook-price",
                "target": "bestbuy_price",
                "value": "$1,099.00",
                "current_url": "file:///bestbuy_macbook_air_13.html",
                "page_title": "Apple MacBook Air 13-inch Laptop - Best Buy",
            },
            {
                "step_id": "surface-facts",
                "target": "bestbuy_product_facts",
                "value": {
                    "entity_name": "Microsoft Surface Laptop 13-inch - Snapdragon X Plus - 16GB Memory - 512GB SSD",
                    "product_name": "Microsoft Surface Laptop 13-inch - Snapdragon X Plus - 16GB Memory - 512GB SSD",
                    "product_url": "file:///bestbuy_surface_laptop_13.html",
                    "sku": "6540002",
                    "price": "$999.00",
                    "facts": {
                        "model name": "Microsoft Surface Laptop 13-inch - Snapdragon X Plus - 16GB Memory - 512GB SSD",
                        "display size": "13 inches",
                        "ram": "16 gigabytes",
                        "storage": "512 gigabytes",
                    },
                    "specifications": {
                        "Display Size": "13 inches",
                        "System Memory (RAM)": "16 gigabytes",
                        "Solid State Drive Capacity": "512 gigabytes",
                    },
                },
                "current_url": "file:///bestbuy_surface_laptop_13.html",
                "page_title": "Microsoft Surface Laptop 13-inch - Best Buy",
            },
            {
                "step_id": "surface-price",
                "target": "bestbuy_price",
                "value": "$999.00",
                "current_url": "file:///bestbuy_surface_laptop_13.html",
                "page_title": "Microsoft Surface Laptop 13-inch - Best Buy",
            },
        ],
        plan_metadata={"mode": "task_lookup"},
    )

    assert artifact is not None
    assert artifact["output_mode"] == "csv"
    assert artifact["isLLMReProcessingRequired"] is False
    assert artifact["columns"] == ["price", "display size", "RAM", "storage"]
    assert artifact["rows"][0]["entity_name"].startswith("Apple MacBook Air")
    assert artifact["rows"][0]["price"] == "$1,099.00"
    assert artifact["rows"][0]["display size"] == "13.6 inches"
    assert artifact["rows"][1]["RAM"] == "16 gigabytes"


def test_build_run_artifacts_writes_csv_for_comparison_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    observation = SimpleNamespace(url="https://en.wikipedia.org/wiki/Andean_condor", title="Andean condor - Wikipedia")

    artifacts = cli._build_run_artifacts(
        task_id="wikipedia-comparison",
        goal="Compare endangered birds in South America by habitat and conservation initiatives and export to csv",
        observation=observation,
        extract_artifacts={},
        extract_sequence=[
            {
                "step_id": "condor-habitat",
                "target": "section:Habitat",
                "value": "Andean mountains and open grasslands.",
                "current_url": "https://en.wikipedia.org/wiki/Andean_condor",
                "page_title": "Andean condor - Wikipedia",
            },
            {
                "step_id": "condor-conservation",
                "target": "section:Conservation initiatives",
                "value": "Protected habitat and breeding programs.",
                "current_url": "https://en.wikipedia.org/wiki/Andean_condor",
                "page_title": "Andean condor - Wikipedia",
            },
        ],
        plan_metadata={"mode": "llm", "model": "claude-sonnet-4-6"},
        run_id="run123",
    )

    comparison = artifacts["comparison"]
    assert isinstance(comparison, dict)
    csv_path = Path(str(comparison["csv_path"]))
    assert csv_path.exists()
    assert csv_path == tmp_path / "artifacts" / "comparisons" / "endangered_birds_in_south_america_run123.csv"

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["entity_name"] == "Andean condor"
    assert rows[0]["habitat"] == "Andean mountains and open grasslands."
    assert rows[0]["conservation initiatives"] == "Protected habitat and breeding programs."


def test_build_run_artifacts_does_not_write_csv_for_text_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    observation = SimpleNamespace(url="https://en.wikipedia.org/wiki/Andean_condor", title="Andean condor - Wikipedia")

    artifacts = cli._build_run_artifacts(
        task_id="wikipedia-comparison",
        goal="Compare endangered birds in South America by habitat and conservation initiatives",
        observation=observation,
        extract_artifacts={},
        extract_sequence=[
            {
                "step_id": "condor-habitat",
                "target": "section:Habitat",
                "value": "Andean mountains and open grasslands.",
                "current_url": "https://en.wikipedia.org/wiki/Andean_condor",
                "page_title": "Andean condor - Wikipedia",
            }
        ],
        plan_metadata={"mode": "llm", "model": "claude-sonnet-4-6"},
        run_id="run124",
    )

    comparison = artifacts["comparison"]
    assert isinstance(comparison, dict)
    assert "csv_path" not in comparison
    assert not (tmp_path / "artifacts" / "comparisons").exists()


def test_artifact_lines_include_extract_sequence_count() -> None:
    lines = cli._artifact_lines(
        {
            "extracts": {"summary": "Short summary"},
            "extract_sequence": [{"step_id": "s1"}, {"step_id": "s2"}],
        },
        mode="summary",
    )

    assert any("extract_sequence: 2 extract events" in line for line in lines)


def test_effective_verification_rules_for_wikipedia_comparison_use_artifacts() -> None:
    rules = cli._effective_verification_rules(
        task_id="wikipedia-comparison",
        plan_rules=[],
        plan_metadata={"entities": ["Spix's macaw", "Blue-throated macaw", "Lear's macaw"]},
        artifacts={
            "comparison": {
                "output_mode": "csv",
                "rows": [{}, {}, {}],
                "csv_path": "C:/tmp/example.csv",
            }
        },
    )

    assert [rule.kind for rule in rules] == [
        "artifact_exists",
        "artifact_list_min_length",
        "artifact_exists",
    ]
    assert rules[1].value == {"path": "comparison.rows", "min": 3}
    assert rules[2].value == "comparison.csv_path"


def test_effective_verification_rules_for_bestbuy_comparison_use_artifacts() -> None:
    rules = cli._effective_verification_rules(
        task_id="bestbuy-laptop-comparison",
        plan_rules=[],
        plan_metadata={},
        artifacts={
            "comparison": {
                "output_mode": "csv",
                "rows": [{}, {}],
                "csv_path": "C:/tmp/bestbuy.csv",
            }
        },
    )

    assert [rule.kind for rule in rules] == [
        "artifact_exists",
        "artifact_list_min_length",
        "artifact_exists",
    ]
    assert rules[1].value == {"path": "comparison.rows", "min": 2}


def test_is_llm_reprocessing_required_is_true_for_comparison_goal() -> None:
    assert (
        cli._is_llm_reprocessing_required(
            task_id="wikipedia-comparison",
            goal="Compare endangered birds in South America by habitat",
            plan_metadata={},
        )
        is True
    )


def test_build_comparison_artifact_applies_llm_reprocessing(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "_maybe_synthesize_comparison_rows",
        lambda subject, columns, raw_rows, plan_metadata: {
            "rows": [
                {
                    "entity_name": "Andean condor",
                    "article_url": "https://en.wikipedia.org/wiki/Andean_condor",
                    "habitat": "High Andes grasslands",
                    "conservation initiatives": "Protected areas and anti-poisoning work",
                }
            ],
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
        },
    )
    observation = SimpleNamespace(url="https://en.wikipedia.org/wiki/Andean_condor", title="Andean condor - Wikipedia")

    artifact = cli._build_comparison_artifact(
        task_id="wikipedia-comparison",
        goal="Compare endangered birds in South America by habitat and conservation initiatives and export to csv",
        observation=observation,
        extract_sequence=[
            {
                "step_id": "condor-habitat",
                "target": "section:Habitat",
                "value": "Andean mountains and open grasslands.",
                "current_url": "https://en.wikipedia.org/wiki/Andean_condor",
                "page_title": "Andean condor - Wikipedia",
            },
            {
                "step_id": "condor-conservation",
                "target": "section:Conservation initiatives",
                "value": "Protected habitat and breeding programs.",
                "current_url": "https://en.wikipedia.org/wiki/Andean_condor",
                "page_title": "Andean condor - Wikipedia",
            },
        ],
        plan_metadata={"mode": "llm", "model": "claude-sonnet-4-6"},
    )

    assert artifact is not None
    assert artifact["rows"][0]["habitat"] == "High Andes grasslands"
    assert artifact["raw_rows"][0]["habitat"] == "Andean mountains and open grasslands."
    assert artifact["metadata"]["llm_reprocessing_applied"] is True
    assert artifact["metadata"]["llm_reprocessing_provider"] == "anthropic"
