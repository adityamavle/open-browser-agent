from __future__ import annotations

import json
from pathlib import Path

from open_browser_agent.replay import replay_trace
from open_browser_agent.schemas.observation import Observation
from open_browser_agent.schemas.step import Step
from open_browser_agent.schemas.trace import TraceEvent, TraceVerification
from open_browser_agent.trace import TraceRecorder
from open_browser_agent.verifier import VerificationInput, VerificationRule, Verifier


def test_trace_recorder_round_trip(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    trace = recorder.start_run(goal="goal", task_id="task")
    recorder.set_artifact(trace, "extracts", {"summary": "Summary text"})
    recorder.set_steps(trace, [Step(id="s1", type="click", args={"selector": "#go"})])
    recorder.append_event(trace, {"step_id": "s1", "action": "click"})
    recorder.finish_run(
        trace,
        success=True,
        reason="done",
        checks=[{"kind": "text_contains", "label": "summary", "value": "ok", "passed": True, "evidence": "ok"}],
    )

    payload = recorder.load_trace(trace.trace_path)

    assert payload["goal"] == "goal"
    assert payload["steps"][0]["id"] == "s1"
    assert payload["events"][0]["step_id"] == "s1"
    assert payload["artifacts"]["extracts"]["summary"] == "Summary text"
    assert payload["verification"]["success"] is True
    assert payload["verification"]["checks"][0]["label"] == "summary"


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
                "artifacts": {"extracts": {"table": "row1"}},
                "verification": {
                    "success": False,
                    "checks": [
                        {"kind": "text_contains", "label": "summary", "passed": True},
                        {"kind": "dom_contains", "label": "done button", "passed": False},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    result = replay_trace(trace_path)

    assert result["ok"] is True
    assert result["events"] == 2
    assert result["step_ids"] == ["s1", "s2"]
    assert result["artifact_keys"] == ["extracts"]
    assert result["verification_summary"]["checks_total"] == 2
    assert result["verification_summary"]["checks_passed"] == 1
    assert result["verification_summary"]["checks_failed"] == 1
    assert result["verification_summary"]["failed_labels"] == ["done button"]


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
    assert len(result.checks) == 3
    assert all(check["passed"] for check in result.checks)


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
    assert result.checks[-1]["passed"] is False
    assert result.checks[-1]["label"] == "done button"


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


def test_verifier_accepts_artifact_rules() -> None:
    observation = Observation(
        url="https://example.test/items",
        title="Items",
        visible_text="Visible text",
        dom_summary=[],
        screenshot_path=None,
    )
    verifier = Verifier(
        [
            VerificationRule(kind="artifact_exists", value="extracts.table", label="table extract"),
            VerificationRule(
                kind="artifact_text_contains",
                value={"path": "extracts.summary", "contains": "Ada"},
                label="summary extract",
            ),
            VerificationRule(
                kind="artifact_list_min_length",
                value={"path": "extracts.rows", "min": 2},
                label="row count",
            ),
        ]
    )

    result = verifier.verify(
        VerificationInput(
            observation=observation,
            artifacts={"extracts": {"table": "table text", "summary": "Ada summary", "rows": [1, 2]}},
        )
    )

    assert result.success is True
    assert len(result.checks) == 3


def test_trace_schema_to_dict_helpers() -> None:
    event = TraceEvent(step_id="s1", action="click", status="ok", details={"selector": "#id"})
    verification = TraceVerification(
        success=True,
        reason="done",
        completed_at="2026-03-09T00:00:00Z",
        checks=[{"kind": "url_contains", "label": "url", "value": "success", "passed": True, "evidence": "url"}],
    )

    assert event.to_dict()["action"] == "click"
    assert verification.to_dict()["success"] is True
    assert verification.to_dict()["checks"][0]["kind"] == "url_contains"
