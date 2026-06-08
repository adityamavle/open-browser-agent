from __future__ import annotations

from pathlib import Path

from open_browser_agent.actions import ActionAPI
from open_browser_agent.executor import Executor, ExecutorError
from open_browser_agent.observer import Observer
from open_browser_agent.schemas.step import Step
from open_browser_agent.trace import TraceRecorder


class FakeLocator:
    def __init__(self, text: str) -> None:
        self._text = text

    def inner_text(self) -> str:
        return self._text


class FakeKeyboard:
    def press(self, keys: str) -> None:
        self.keys = keys


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.test/start"
        self.keyboard = FakeKeyboard()
        self.title_value = "Start"
        self.body_text = "Visible page text"
        self.dom_summary = ["main:Home", "form:Search"]
        self.form_values = {"#name": "<empty>"}

    def goto(self, url: str) -> None:
        self.url = url

    def click(self, selector: str) -> None:
        self.last_click = selector

    def fill(self, selector: str, text: str) -> None:
        self.last_fill = (selector, text)
        self.form_values[selector] = text

    def wait_for_selector(self, selector: str) -> None:
        self.last_wait = selector

    def locator(self, selector: str) -> FakeLocator:
        values = {"body": self.body_text, "table": "a b", "p": "summary", "#item": "item text"}
        return FakeLocator(values[selector])

    def title(self) -> str:
        return self.title_value

    def screenshot(self, path: str) -> None:
        self.screenshot_path = path

    def snapshot_dom_summary(self) -> list[str]:
        return self.dom_summary

    def snapshot_form_state(self) -> list[str]:
        return [f"input:text:name={self.form_values['#name']}"]


def test_executor_runs_supported_steps_and_traces(tmp_path: Path) -> None:
    page = FakePage()
    actions = ActionAPI(lambda: page)
    observer = Observer(lambda: page)
    recorder = TraceRecorder(tmp_path)
    trace = recorder.start_run(goal="goal", task_id="task")
    executor = Executor(actions=actions, observer=observer, trace_recorder=recorder, trace=trace)

    result = executor.run_step(Step(id="s1", type="navigate", args={"url": "https://example.test/next"}))

    assert result.success is True
    payload = recorder.load_trace(trace.trace_path)
    assert payload["events"][0]["step_id"] == "s1"
    assert payload["events"][0]["pre_observation"]["title"] == "Start"
    assert payload["events"][0]["post_observation"]["url"] == "https://example.test/next"
    assert payload["events"][0]["pre_observation"]["form_state"] == ["input:text:name=<empty>"]


def test_executor_run_steps_returns_all_results() -> None:
    page = FakePage()
    executor = Executor(actions=ActionAPI(lambda: page))

    results = executor.run_steps(
        [
            Step(id="s1", type="click", args={"selector": "#submit"}),
            Step(id="s2", type="extract", args={"target": "#item"}),
        ]
    )

    assert [result.success for result in results] == [True, True]
    assert results[1].action_result.details["value"] == "item text"


def test_executor_navigates_to_extracted_result() -> None:
    class SearchPage(FakePage):
        def locator(self, selector: str) -> FakeLocator:
            if selector == "body":
                return FakeLocator(self.body_text)
            return super().locator(selector)

        def evaluate(self, script: str):
            if "document.querySelectorAll('[data-testid=\"sku-card\"], .sku-item, li.sku-item')" in script:
                return [
                    {"title": "Laptop One", "href": "https://www.bestbuy.com/site/laptop-one/111.p"},
                    {"title": "Laptop Two", "href": "https://www.bestbuy.com/site/laptop-two/222.p"},
                ]
            return []

    page = SearchPage()
    executor = Executor(actions=ActionAPI(lambda: page))

    results = executor.run_steps(
        [
            Step(id="extract-results", type="extract", args={"target": "bestbuy_search_results"}),
            Step(
                id="goto-second-result",
                type="navigate_extracted_result",
                args={"source_target": "bestbuy_search_results", "index": 1, "url_field": "href"},
            ),
        ]
    )

    assert [result.success for result in results] == [True, True]
    assert page.url == "https://www.bestbuy.com/site/laptop-two/222.p"
    assert results[1].action_result is not None
    assert results[1].action_result.details["source_target"] == "bestbuy_search_results"


def test_executor_reports_missing_extracted_result() -> None:
    executor = Executor(actions=ActionAPI(lambda: FakePage()))

    result = executor.run_step(
        Step(
            id="goto-missing-result",
            type="navigate_extracted_result",
            args={"source_target": "bestbuy_search_results", "index": 0},
        )
    )

    assert result.success is False
    assert result.action_result is not None
    assert result.action_result.error_code == "missing_extract"


def test_executor_run_steps_stops_after_first_failure() -> None:
    class BrokenPage(FakePage):
        def click(self, selector: str) -> None:
            raise RuntimeError("click failed")

        def locator(self, selector: str) -> FakeLocator:
            if selector == "#should-not-run":
                raise AssertionError("extract step should not run after failure")
            return super().locator(selector)

    page = BrokenPage()
    executor = Executor(actions=ActionAPI(lambda: page))

    results = executor.run_steps(
        [
            Step(id="s1", type="click", args={"selector": "#submit"}),
            Step(id="s2", type="extract", args={"target": "#should-not-run"}),
        ]
    )

    assert len(results) == 1
    assert results[0].success is False


def test_executor_raises_on_unsupported_step() -> None:
    executor = Executor(actions=ActionAPI(lambda: FakePage()))

    try:
        executor.run_step(Step(id="s1", type="scroll", args={"amount": 10}))
    except ExecutorError as exc:
        assert "Unsupported step type" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ExecutorError")


def test_executor_dispatches_all_supported_step_types() -> None:
    page = FakePage()
    executor = Executor(actions=ActionAPI(lambda: page))

    assert executor.run_step(Step(id="s1", type="type", args={"selector": "#name", "text": "Ada"})).success
    assert executor.run_step(Step(id="s2", type="press", args={"keys": "Enter"})).success
    assert executor.run_step(Step(id="s3", type="wait_for", args={"selector": "form"})).success


def test_executor_trace_records_form_state_changes(tmp_path: Path) -> None:
    page = FakePage()
    observer = Observer(lambda: page)
    recorder = TraceRecorder(tmp_path)
    trace = recorder.start_run(goal="goal", task_id="task")
    executor = Executor(actions=ActionAPI(lambda: page), observer=observer, trace_recorder=recorder, trace=trace)

    result = executor.run_step(Step(id="s1", type="type", args={"selector": "#name", "text": "Ada"}))

    assert result.success is True
    payload = recorder.load_trace(trace.trace_path)
    assert payload["events"][0]["pre_observation"]["form_state"] == ["input:text:name=<empty>"]
    assert payload["events"][0]["post_observation"]["form_state"] == ["input:text:name=Ada"]


def test_executor_dispatches_step_timeout_to_actions() -> None:
    class SpyActions:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int | None]] = []

        def goto(self, url: str, timeout_ms: int | None = None):
            _ = url
            self.calls.append(("goto", timeout_ms))
            return ActionAPI(lambda: FakePage()).goto("https://example.test")

        def click(self, selector: str, timeout_ms: int | None = None):
            _ = selector
            self.calls.append(("click", timeout_ms))
            return ActionAPI(lambda: FakePage()).click("#submit")

        def type(self, selector: str, text: str, timeout_ms: int | None = None):
            _ = selector, text
            self.calls.append(("type", timeout_ms))
            return ActionAPI(lambda: FakePage()).type("#name", "Ada")

        def press(self, keys: str, timeout_ms: int | None = None):
            _ = keys
            self.calls.append(("press", timeout_ms))
            return ActionAPI(lambda: FakePage()).press("Enter")

        def wait_for(self, selector: str, timeout_ms: int | None = None):
            _ = selector
            self.calls.append(("wait_for", timeout_ms))
            return ActionAPI(lambda: FakePage()).wait_for("form")

        def extract(self, target: str, timeout_ms: int | None = None):
            _ = target
            self.calls.append(("extract", timeout_ms))
            return ActionAPI(lambda: FakePage()).extract("#item")

    actions = SpyActions()
    executor = Executor(actions=actions)  # type: ignore[arg-type]

    steps = [
        Step(id="s1", type="navigate", args={"url": "https://example.test"}, timeout_ms=111),
        Step(id="s2", type="click", args={"selector": "#submit"}, timeout_ms=222),
        Step(id="s3", type="type", args={"selector": "#name", "text": "Ada"}, timeout_ms=333),
        Step(id="s4", type="press", args={"keys": "Enter"}, timeout_ms=444),
        Step(id="s5", type="wait_for", args={"selector": "form"}, timeout_ms=555),
        Step(id="s6", type="extract", args={"target": "#item"}, timeout_ms=666),
    ]

    results = executor.run_steps(steps)

    assert all(result.success for result in results)
    assert actions.calls == [
        ("goto", 111),
        ("click", 222),
        ("type", 333),
        ("press", 444),
        ("wait_for", 555),
        ("extract", 666),
    ]
