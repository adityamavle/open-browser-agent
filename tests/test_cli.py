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
    code = cli.handle_run("wiki summary", str(tmp_path))
    output = capsys.readouterr().out
    trace = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))

    assert code == 0
    assert "Resolved example task 'wikipedia-summary'" in output
    assert trace["events"][0]["event"] == "task_resolved"
    assert trace["verification"]["success"] is False


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
