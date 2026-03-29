from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from open_browser_agent.actions import ActionAPI
from open_browser_agent.browser import BrowserSession, BrowserSessionError
from open_browser_agent.executor import Executor
from open_browser_agent.observer import Observer
from open_browser_agent.planner import Planner, PlannerError, build_planner
from open_browser_agent.replay import replay_trace
from open_browser_agent.tasks.registry import TASKS
from open_browser_agent.trace import TraceRecorder
from open_browser_agent.verifier import VerificationInput, Verifier


@dataclass(slots=True)
class RunOutcome:
    success: bool
    reason: str
    trace_path: Path
    task_id: str | None
    duration_ms: int
    failure_kind: str | None = None
    verification_checks: list[dict[str, object]] = field(default_factory=list)
    action_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    planner_provider: str | None = None
    planner_model: str | None = None
    steps: list[dict[str, object]] = field(default_factory=list)
    artifacts: dict[str, object] = field(default_factory=dict)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oba",
        description="A small browser-use agent with tracing and replay.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a goal or named example task.")
    run_parser.add_argument("goal", help="Natural language goal or example task name.")
    run_parser.add_argument(
        "--trace-dir",
        default="traces",
        help="Directory where run traces will be written.",
    )
    run_parser.add_argument(
        "--planner",
        default="task-registry",
        help="Planner provider to use: task-registry or anthropic.",
    )
    run_parser.add_argument(
        "--artifacts",
        choices=("none", "summary", "detailed"),
        default="summary",
        help="Artifact display mode for oba run output.",
    )
    plan_parser = subparsers.add_parser("plan", help="Generate and print structured steps for a goal.")
    plan_parser.add_argument("goal", help="Natural language goal or example task name.")
    plan_parser.add_argument(
        "--planner",
        default="task-registry",
        help="Planner provider to use: task-registry or anthropic.",
    )
    reliability_parser = subparsers.add_parser(
        "reliability",
        help="Run the same goal multiple times and report pass/fail reliability.",
    )
    reliability_parser.add_argument("goal", help="Natural language goal or example task name.")
    reliability_parser.add_argument("--runs", type=int, default=5, help="Number of repeated runs.")
    reliability_parser.add_argument(
        "--trace-dir",
        default="traces",
        help="Directory where run traces will be written.",
    )
    reliability_parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop the loop immediately when a run fails.",
    )
    reliability_parser.add_argument(
        "--planner",
        default="task-registry",
        help="Planner provider to use: task-registry or anthropic.",
    )
    eval_parser = subparsers.add_parser(
        "eval",
        help="Run the bundled evaluation loop for one task or all example tasks.",
    )
    eval_parser.add_argument("goal", nargs="?", help="Optional example task name or goal. Defaults to all tasks.")
    eval_parser.add_argument("--runs", type=int, default=3, help="Number of reliability runs per task.")
    eval_parser.add_argument(
        "--trace-dir",
        default="traces",
        help="Directory where evaluation traces will be written.",
    )
    eval_parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop the evaluation loop immediately when a run fails.",
    )
    eval_parser.add_argument(
        "--planner",
        default="task-registry",
        help="Planner provider to use: task-registry or anthropic.",
    )

    replay_parser = subparsers.add_parser("replay", help="Replay a saved trace.")
    replay_parser.add_argument("trace_path", help="Path to a trace JSON file.")

    examples_parser = subparsers.add_parser("examples", help="Inspect bundled example tasks.")
    examples_subparsers = examples_parser.add_subparsers(dest="examples_command", required=True)
    examples_subparsers.add_parser("list", help="List example tasks.")

    return parser


def run_goal(goal: str, trace_dir: str, planner_name: str = "task-registry") -> RunOutcome:
    started = perf_counter()
    recorder = TraceRecorder(Path(trace_dir))
    trace = recorder.start_run(goal=goal, task_id=None)

    try:
        planner = build_planner(planner_name)
    except PlannerError as exc:
        reason = str(exc)
        recorder.append_event(
            trace,
            {
                "event": "planning_failed",
                "provider": planner_name,
                "reason": reason,
            },
        )
        recorder.finish_run(trace, success=False, reason=reason, checks=[])
        return RunOutcome(
            success=False,
            reason=reason,
            trace_path=trace.trace_path,
            task_id=None,
            duration_ms=int((perf_counter() - started) * 1000),
            failure_kind="planning",
            verification_checks=[],
            action_stats={},
            planner_provider=planner_name,
        )

    try:
        plan_result = planner.plan(goal)
    except PlannerError as exc:
        reason = str(exc)
        recorder.append_event(
            trace,
            {
                "event": "planning_failed",
                "provider": planner.provider.name,
                "reason": reason,
            },
        )
        recorder.finish_run(
            trace,
            success=False,
            reason=reason,
            checks=[],
        )
        return RunOutcome(
            success=False,
            reason=reason,
            trace_path=trace.trace_path,
            task_id=None,
            duration_ms=int((perf_counter() - started) * 1000),
            failure_kind="planning",
            verification_checks=[],
            action_stats={},
            planner_provider=planner.provider.name,
        )

    recorder.set_task(trace, plan_result.task_id)
    recorder.set_steps(trace, plan_result.steps)
    recorder.append_event(
        trace,
        {
            "event": "plan_generated",
            "provider": plan_result.provider_name,
            "task_id": plan_result.task_id,
            "step_count": len(plan_result.steps),
            "verifier_hint": plan_result.verifier_hint,
            "metadata": plan_result.metadata,
        },
    )

    try:
        with BrowserSession() as session:
            actions = ActionAPI(lambda: session.page)
            observer = Observer(lambda: session.page)
            executor = Executor(actions=actions, observer=observer, trace_recorder=recorder, trace=trace)

            results = executor.run_steps(plan_result.steps)
            first_failure = next((result for result in results if not result.success), None)
            extract_artifacts = _collect_extract_artifacts(results)
            if extract_artifacts:
                recorder.set_artifact(trace, "extracts", extract_artifacts)
            if first_failure is not None:
                reason = first_failure.message
                recorder.finish_run(trace, success=False, reason=reason, checks=[])
                return RunOutcome(
                    success=False,
                    reason=reason,
                    trace_path=trace.trace_path,
                    task_id=plan_result.task_id,
                    duration_ms=int((perf_counter() - started) * 1000),
                    failure_kind="execution",
                    verification_checks=[],
                    action_stats=_build_action_stats(results),
                    planner_provider=plan_result.provider_name,
                    planner_model=_planner_model(plan_result.metadata),
                    steps=_steps_to_dict(plan_result.steps),
                    artifacts={"extracts": extract_artifacts} if extract_artifacts else {},
                )

            verification = Verifier(plan_result.verification_rules).verify(
                VerificationInput(
                    observation=observer.capture(),
                    artifacts={"extracts": extract_artifacts},
                )
            )
            recorder.finish_run(
                trace,
                success=verification.success,
                reason=verification.reason,
                checks=verification.checks,
            )
            return RunOutcome(
                success=verification.success,
                reason=verification.reason,
                trace_path=trace.trace_path,
                task_id=plan_result.task_id,
                duration_ms=int((perf_counter() - started) * 1000),
                failure_kind=None if verification.success else "verification",
                verification_checks=verification.checks,
                action_stats=_build_action_stats(results),
                planner_provider=plan_result.provider_name,
                planner_model=_planner_model(plan_result.metadata),
                steps=_steps_to_dict(plan_result.steps),
                artifacts={"extracts": extract_artifacts} if extract_artifacts else {},
            )
    except BrowserSessionError as exc:
        reason = str(exc)
        recorder.finish_run(trace, success=False, reason=reason, checks=[])
        return RunOutcome(
            success=False,
            reason=reason,
            trace_path=trace.trace_path,
            task_id=plan_result.task_id,
            duration_ms=int((perf_counter() - started) * 1000),
            failure_kind="browser",
            verification_checks=[],
            action_stats={},
            planner_provider=plan_result.provider_name,
            planner_model=_planner_model(plan_result.metadata),
            steps=_steps_to_dict(plan_result.steps),
        )


def handle_run(
    goal: str,
    trace_dir: str,
    planner_name: str = "task-registry",
    artifacts_mode: str = "summary",
) -> int:
    outcome = run_goal(goal=goal, trace_dir=trace_dir, planner_name=planner_name)
    if outcome.failure_kind == "planning" and outcome.task_id is None:
        print(
            f"No example task matched {goal!r}. "
            f"Initialized trace at {outcome.trace_path}."
        )
        return 1

    label = outcome.task_id or goal
    label_prefix = "Task" if outcome.task_id else "Goal"

    if not outcome.success:
        if outcome.failure_kind == "browser":
            print(f"Browser session error: {outcome.reason}. Trace written to {outcome.trace_path}.")
            _print_run_report(goal=goal, outcome=outcome, artifacts_mode=artifacts_mode)
            return 1
        print(
            f"{label_prefix} '{label}' failed during execution. "
            f"Trace written to {outcome.trace_path}."
        )
        _print_run_report(goal=goal, outcome=outcome, artifacts_mode=artifacts_mode)
        _print_verification_summary(outcome.verification_checks)
        return 1

    print(
        f"{label_prefix} '{label}' completed with success={outcome.success}. "
        f"Trace written to {outcome.trace_path}."
    )
    _print_run_report(goal=goal, outcome=outcome, artifacts_mode=artifacts_mode)
    _print_verification_summary(outcome.verification_checks)
    return 0


def handle_plan(goal: str, planner_name: str = "task-registry") -> int:
    try:
        planner = build_planner(planner_name)
        plan_result = planner.plan(goal)
    except PlannerError as exc:
        print(json.dumps({"ok": False, "goal": goal, "error": str(exc), "provider": planner_name}, indent=2))
        return 1
    print(json.dumps({"ok": True, "goal": goal, **plan_result.to_dict()}, indent=2))
    return 0


def _print_verification_summary(checks: list[dict[str, object]]) -> None:
    if not checks:
        return
    passed = sum(1 for check in checks if bool(check.get("passed")))
    failed = len(checks) - passed
    failed_labels = [str(check.get("label") or check.get("kind") or "unknown") for check in checks if not bool(check.get("passed"))]
    label_suffix = f" failed_labels={failed_labels}" if failed_labels else ""
    print(f"Verification checks: total={len(checks)} passed={passed} failed={failed}{label_suffix}")


def _steps_to_dict(steps: list) -> list[dict[str, object]]:
    return [
        {
            "id": step.id,
            "type": step.type,
            "args": dict(step.args),
            "expected": dict(step.expected),
            "timeout_ms": step.timeout_ms,
        }
        for step in steps
    ]


def _planner_model(metadata: dict[str, object] | None) -> str | None:
    if not metadata:
        return None
    model = metadata.get("model")
    return str(model) if model else None


def _format_step_summary(step: dict[str, object]) -> str:
    step_type = str(step.get("type") or "unknown")
    args = step.get("args") or {}
    if not isinstance(args, dict):
        return step_type
    if step_type in {"navigate", "goto"} and args.get("url"):
        return f"{step_type} {args['url']}"
    if step_type in {"click", "wait_for"} and args.get("selector"):
        return f"{step_type} {args['selector']}"
    if step_type == "type" and args.get("selector"):
        text = str(args.get("text") or "")
        preview = f" text={text[:40]!r}" if text else ""
        return f"type {args['selector']}{preview}"
    if step_type == "press" and args.get("keys"):
        return f"press {args['keys']}"
    if step_type == "extract" and args.get("target"):
        return f"extract {args['target']}"
    return step_type


def _artifact_lines(artifacts: dict[str, object], mode: str = "summary") -> list[str]:
    if mode == "none":
        return []
    lines: list[str] = []
    extracts = artifacts.get("extracts") if isinstance(artifacts, dict) else None
    if not isinstance(extracts, dict):
        return lines
    for key, value in extracts.items():
        if isinstance(value, str):
            compact = " ".join(value.split()) if mode == "summary" else value
            preview = compact[:240] + ("..." if mode == "summary" and len(compact) > 240 else "")
            lines.append(f"- {key}: {preview}")
        else:
            lines.append(f"- {key}: {json.dumps(value)}")
    return lines


def _print_run_report(goal: str, outcome: RunOutcome, artifacts_mode: str = "summary") -> None:
    print("Run summary:")
    print(f"- goal: {goal}")
    if outcome.task_id:
        print(f"- task: {outcome.task_id}")
    print(f"- planner: {outcome.planner_provider or 'unknown'}")
    if outcome.planner_model:
        print(f"- model: {outcome.planner_model}")
    print(f"- status: {'success' if outcome.success else 'failure'}")
    print(f"- reason: {outcome.reason}")
    print(f"- duration_ms: {outcome.duration_ms}")
    print("- plan:")
    if outcome.steps:
        for index, step in enumerate(outcome.steps, start=1):
            print(f"  {index}. {_format_step_summary(step)}")
    else:
        print("  none")
    artifact_lines = _artifact_lines(outcome.artifacts, mode=artifacts_mode)
    if artifact_lines:
        print("- artifacts:")
        for line in artifact_lines:
            print(f"  {line}")
    print(f"- trace: {outcome.trace_path}")


def _build_action_stats(results: list) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for result in results:
        action_result = result.action_result
        if action_result is None:
            continue
        bucket = stats.setdefault(action_result.action, {"ok": 0, "failed": 0})
        if action_result.ok:
            bucket["ok"] += 1
        else:
            bucket["failed"] += 1
    return stats


def _collect_extract_artifacts(results: list) -> dict[str, Any]:
    extracts: dict[str, Any] = {}
    for result in results:
        action_result = result.action_result
        if action_result is None or action_result.action != "extract" or not action_result.ok:
            continue
        target = str(action_result.details.get("target") or "unknown")
        extracts[target] = action_result.details.get("value")
    return extracts


def _run_reliability_series(
    goal: str,
    runs: int,
    trace_dir: str,
    planner_name: str = "task-registry",
    stop_on_failure: bool = False,
    emit_progress: bool = True,
) -> dict[str, Any]:
    if runs <= 0:
        return {
            "goal": goal,
            "task": None,
            "runs_requested": runs,
            "runs_executed": 0,
            "successes": 0,
            "failures": 0,
            "success_rate": 0.0,
            "avg_duration_ms": 0,
            "failure_reasons": {"Reliability runs must be >= 1.": 1},
            "action_coverage": {},
        }

    successes = 0
    failures = 0
    durations_ms: list[int] = []
    failure_reasons: dict[str, int] = {}
    action_coverage: dict[str, dict[str, int]] = {}
    task_id: str | None = None

    for run_index in range(1, runs + 1):
        outcome = run_goal(goal=goal, trace_dir=trace_dir, planner_name=planner_name)
        task_id = task_id or outcome.task_id
        durations_ms.append(outcome.duration_ms)
        status = "PASS" if outcome.success else "FAIL"
        if emit_progress:
            print(
                f"[{run_index}/{runs}] {status} "
                f"task={outcome.task_id or 'n/a'} duration_ms={outcome.duration_ms} "
                f"trace={outcome.trace_path}"
            )
        if outcome.success:
            successes += 1
        else:
            failures += 1
            failure_reasons[outcome.reason] = failure_reasons.get(outcome.reason, 0) + 1
            if stop_on_failure:
                break
            if outcome.task_id is None:
                break

        for action, counts in outcome.action_stats.items():
            bucket = action_coverage.setdefault(action, {"ok": 0, "failed": 0, "runs_seen": 0})
            bucket["ok"] += counts.get("ok", 0)
            bucket["failed"] += counts.get("failed", 0)
            bucket["runs_seen"] += 1

    executed_runs = successes + failures
    return {
        "goal": goal,
        "task": task_id,
        "runs_requested": runs,
        "runs_executed": executed_runs,
        "successes": successes,
        "failures": failures,
        "success_rate": round(successes / executed_runs, 3) if executed_runs else 0.0,
        "avg_duration_ms": int(sum(durations_ms) / executed_runs) if executed_runs else 0,
        "failure_reasons": failure_reasons,
        "action_coverage": action_coverage,
    }


def handle_reliability(
    goal: str,
    runs: int,
    trace_dir: str,
    planner_name: str = "task-registry",
    stop_on_failure: bool = False,
) -> int:
    if runs <= 0:
        print("Reliability runs must be >= 1.")
        return 2

    summary = _run_reliability_series(
        goal=goal,
        runs=runs,
        trace_dir=trace_dir,
        planner_name=planner_name,
        stop_on_failure=stop_on_failure,
        emit_progress=True,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["failures"] == 0 and summary["runs_executed"] == runs else 1


def handle_eval(
    goal: str | None,
    runs: int,
    trace_dir: str,
    planner_name: str = "task-registry",
    stop_on_failure: bool = False,
) -> int:
    goals = [goal] if goal else [task.task_id for task in TASKS]
    task_summaries: list[dict[str, Any]] = []
    all_passed = True

    for task_goal in goals:
        single_outcome = run_goal(goal=task_goal, trace_dir=trace_dir, planner_name=planner_name)
        reliability = _run_reliability_series(
            goal=task_goal,
            runs=runs,
            trace_dir=trace_dir,
            planner_name=planner_name,
            stop_on_failure=stop_on_failure,
            emit_progress=False,
        )
        single_passed = bool(single_outcome.success)
        reliability_passed = bool(reliability["failures"] == 0 and reliability["runs_executed"] == runs)
        all_passed = all_passed and single_passed and reliability_passed
        task_summary = {
            "goal": task_goal,
            "task": single_outcome.task_id or reliability["task"],
            "single_run_success": single_passed,
            "single_run_trace": str(single_outcome.trace_path),
            "single_run_failure_kind": single_outcome.failure_kind,
            "reliability": reliability,
        }
        task_summaries.append(task_summary)
        status = "PASS" if single_passed and reliability_passed else "FAIL"
        print(
            f"EVAL {status} task={task_summary['task'] or task_goal} "
            f"single={single_passed} reliability={reliability['successes']}/{reliability['runs_executed']}"
        )
        if stop_on_failure and status == "FAIL":
            break

    print(json.dumps({"tasks": task_summaries, "all_passed": all_passed}, indent=2))
    return 0 if all_passed else 1


def handle_replay(trace_path: str) -> int:
    result = replay_trace(Path(trace_path))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def handle_examples_list() -> int:
    for task in TASKS:
        print(f"{task.task_id}: {task.summary}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        return handle_run(args.goal, args.trace_dir, planner_name=args.planner, artifacts_mode=args.artifacts)
    if args.command == "plan":
        return handle_plan(args.goal, planner_name=args.planner)
    if args.command == "reliability":
        return handle_reliability(
            goal=args.goal,
            runs=args.runs,
            trace_dir=args.trace_dir,
            planner_name=args.planner,
            stop_on_failure=args.stop_on_failure,
        )
    if args.command == "eval":
        return handle_eval(
            goal=args.goal,
            runs=args.runs,
            trace_dir=args.trace_dir,
            planner_name=args.planner,
            stop_on_failure=args.stop_on_failure,
        )
    if args.command == "replay":
        return handle_replay(args.trace_path)
    if args.command == "examples" and args.examples_command == "list":
        return handle_examples_list()

    parser.error("Unsupported command.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
