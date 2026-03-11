from __future__ import annotations

import json
from pathlib import Path

from open_browser_agent import cli


def test_build_parser_accepts_examples_list() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["examples", "list"])
    assert args.command == "examples"
    assert args.examples_command == "list"


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
            self.table_text = "Language Creator Python Guido van Rossum Analytical Engine Notes Ada Lovelace"
            self.keyboard = type("Keyboard", (), {"press": lambda self, keys: None})()

        def goto(self, url: str) -> None:
            self.url = url
            if url.endswith("wikipedia_summary.html"):
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
    assert trace["steps"][0]["id"] == "goto-wikipedia"
    assert trace["events"][0]["event"] == "task_resolved"
    assert trace["verification"]["success"] is True


def test_handle_replay(tmp_path: Path, capsys) -> None:
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps({"goal": "goal", "task": "task", "events": [], "verification": None}),
        encoding="utf-8",
    )

    code = cli.handle_replay(str(trace_path))
    output = capsys.readouterr().out

    assert code == 0
    assert '"mode": "dry-run"' in output


def test_main_dispatches_examples_list(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["oba", "examples", "list"])
    assert cli.main() == 0
