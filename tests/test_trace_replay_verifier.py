from __future__ import annotations

import json
from pathlib import Path

from open_browser_agent.replay import replay_trace
from open_browser_agent.schemas.observation import Observation
from open_browser_agent.schemas.trace import TraceEvent, TraceVerification
from open_browser_agent.trace import TraceRecorder
from open_browser_agent.verifier import VerificationRule, Verifier


def test_trace_recorder_round_trip(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    trace = recorder.start_run(goal="goal", task_id="task")
    recorder.append_event(trace, {"step_id": "s1", "action": "click"})
    recorder.finish_run(trace, success=True, reason="done")

    payload = recorder.load_trace(trace.trace_path)

    assert payload["goal"] == "goal"
    assert payload["events"][0]["step_id"] == "s1"
    assert payload["verification"]["success"] is True


def test_replay_trace_reports_missing_file(tmp_path: Path) -> None:
    result = replay_trace(tmp_path / "missing.json")
    assert result["ok"] is False


def test_replay_trace_reports_summary(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps(
            {
                "goal": "goal",
                "task": "task",
                "events": [{"step_id": "s1"}, {"step_id": "s2"}],
                "verification": {"success": True},
            }
        ),
        encoding="utf-8",
    )

    result = replay_trace(trace_path)

    assert result["ok"] is True
    assert result["events"] == 2
    assert result["step_ids"] == ["s1", "s2"]


def test_verifier_accepts_passing_rules() -> None:
    observation = Observation(
        url="https://example.test/success",
        title="Title",
        visible_text="Summary complete",
        dom_summary=["main:Summary", "button:Done"],
        screenshot_path=None,
    )
    verifier = Verifier(
        [
            VerificationRule(kind="url_contains", value="success"),
            VerificationRule(kind="text_contains", value="Summary"),
            VerificationRule(kind="dom_contains", value="button:Done"),
        ]
    )

    result = verifier.verify(observation)

    assert result.success is True


def test_verifier_rejects_failing_rule() -> None:
    observation = Observation(
        url="https://example.test/failure",
        title="Title",
        visible_text="Summary complete",
        dom_summary=["main:Summary"],
        screenshot_path=None,
    )
    verifier = Verifier([VerificationRule(kind="dom_contains", value="button:Done", label="done button")])

    result = verifier.verify(observation)

    assert result.success is False
    assert "done button" in result.reason


def test_verifier_rejects_unknown_rule() -> None:
    verifier = Verifier([VerificationRule(kind="unknown", value="x")])
    observation = Observation(
        url="u",
        title="t",
        visible_text="v",
        dom_summary=[],
        screenshot_path=None,
    )

    try:
        verifier.verify(observation)
    except ValueError as exc:
        assert "Unsupported verification rule" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError")


def test_trace_schema_to_dict_helpers() -> None:
    event = TraceEvent(step_id="s1", action="click", status="ok", details={"selector": "#id"})
    verification = TraceVerification(success=True, reason="done", completed_at="2026-03-09T00:00:00Z")

    assert event.to_dict()["action"] == "click"
    assert verification.to_dict()["success"] is True
