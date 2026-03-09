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

    def goto(self, url: str) -> None:
        self.url = url

    def click(self, selector: str) -> None:
        self.last_click = selector

    def fill(self, selector: str, text: str) -> None:
        self.last_fill = (selector, text)

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
