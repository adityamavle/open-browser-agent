from __future__ import annotations

import argparse
import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from open_browser_agent.actions import ActionAPI
from open_browser_agent.browser import BrowserSession, BrowserSessionError
from open_browser_agent.comparison import (
    AnthropicComparisonRowSynthesizer,
    ComparisonSynthesisError,
    parse_comparison_intent,
)
from open_browser_agent.executor import Executor
from open_browser_agent.observer import Observer
from open_browser_agent.planner import Planner, PlannerError, build_planner
from open_browser_agent.replay import replay_trace
from open_browser_agent.strategies import get_fallback_plan
from open_browser_agent.strategies.wikipedia import collect_extract_artifacts, collect_extract_sequence
from open_browser_agent.tasks.registry import TASKS
from open_browser_agent.trace import TraceRecorder
from open_browser_agent.verifier import VerificationInput, VerificationRule, Verifier


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
    fallback_used: bool = False
    fallback_strategy: str | None = None
    fallback_trigger: str | None = None


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
            all_results = list(results)
            first_failure = next((result for result in results if not result.success), None)
            extract_artifacts = collect_extract_artifacts(results)
            extract_sequence = collect_extract_sequence(results)
            if extract_artifacts:
                recorder.set_artifact(trace, "extracts", extract_artifacts)
            if extract_sequence:
                recorder.set_artifact(trace, "extract_sequence", extract_sequence)
            fallback_used = False
            fallback_strategy: str | None = None
            fallback_trigger: str | None = None
            if first_failure is not None:
                fallback_attempt = _attempt_fallback(
                    plan_result=plan_result,
                    recorder=recorder,
                    trace=trace,
                    executor=executor,
                    trigger=first_failure.message,
                )
                if fallback_attempt is not None:
                    fallback_used = True
                    fallback_strategy = fallback_attempt["strategy"]
                    fallback_trigger = first_failure.message
                    results = fallback_attempt["results"]
                    all_results.extend(results)
                    extract_artifacts = fallback_attempt["extract_artifacts"]
                    extract_sequence = fallback_attempt["extract_sequence"]
                    if extract_artifacts:
                        recorder.set_artifact(trace, "extracts", extract_artifacts)
                    if extract_sequence:
                        recorder.set_artifact(trace, "extract_sequence", extract_sequence)
                    first_failure = next((result for result in results if not result.success), None)
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
                    action_stats=_build_action_stats(all_results),
                    planner_provider=plan_result.provider_name,
                    planner_model=_planner_model(plan_result.metadata),
                    steps=_steps_to_dict(plan_result.steps),
                    artifacts=_build_run_artifacts(
                        task_id=plan_result.task_id,
                        goal=goal,
                        observation=observer.capture(),
                        extract_artifacts=extract_artifacts,
                        extract_sequence=extract_sequence,
                        plan_metadata=plan_result.metadata,
                        run_id=trace.run_id,
                    ),
                    fallback_used=fallback_used,
                    fallback_strategy=fallback_strategy,
                    fallback_trigger=fallback_trigger,
                )

            current_observation = observer.capture()
            artifacts = _build_run_artifacts(
                task_id=plan_result.task_id,
                goal=goal,
                observation=current_observation,
                extract_artifacts=extract_artifacts,
                extract_sequence=extract_sequence,
                plan_metadata=plan_result.metadata,
                run_id=trace.run_id,
            )
            verification_rules = _effective_verification_rules(
                task_id=plan_result.task_id,
                plan_rules=plan_result.verification_rules,
                plan_metadata=plan_result.metadata,
                artifacts=artifacts,
            )
            verification = Verifier(verification_rules).verify(
                VerificationInput(
                    observation=current_observation,
                    artifacts=artifacts,
                )
            )
            if not verification.success and not fallback_used:
                fallback_attempt = _attempt_fallback(
                    plan_result=plan_result,
                    recorder=recorder,
                    trace=trace,
                    executor=executor,
                    trigger=verification.reason,
                )
                if fallback_attempt is not None:
                    fallback_used = True
                    fallback_strategy = fallback_attempt["strategy"]
                    fallback_trigger = verification.reason
                    results = fallback_attempt["results"]
                    all_results.extend(results)
                    extract_artifacts = fallback_attempt["extract_artifacts"]
                    extract_sequence = fallback_attempt["extract_sequence"]
                    if extract_artifacts:
                        recorder.set_artifact(trace, "extracts", extract_artifacts)
                    if extract_sequence:
                        recorder.set_artifact(trace, "extract_sequence", extract_sequence)
                    fallback_observation = observer.capture()
                    artifacts = _build_run_artifacts(
                        task_id=plan_result.task_id,
                        goal=goal,
                        observation=fallback_observation,
                        extract_artifacts=extract_artifacts,
                        extract_sequence=extract_sequence,
                        plan_metadata=plan_result.metadata,
                        run_id=trace.run_id,
                    )
                    verification_rules = _effective_verification_rules(
                        task_id=plan_result.task_id,
                        plan_rules=plan_result.verification_rules,
                        plan_metadata=plan_result.metadata,
                        artifacts=artifacts,
                    )
                    fallback_verification = Verifier(verification_rules).verify(
                        VerificationInput(
                            observation=fallback_observation,
                            artifacts=artifacts,
                        )
                    )
                    if fallback_verification.success or next((result for result in results if not result.success), None) is None:
                        verification = fallback_verification
            final_observation = observer.capture()
            artifacts = _build_run_artifacts(
                task_id=plan_result.task_id,
                goal=goal,
                observation=final_observation,
                extract_artifacts=extract_artifacts,
                extract_sequence=extract_sequence,
                plan_metadata=plan_result.metadata,
                run_id=trace.run_id,
            )
            if artifacts:
                for artifact_key, artifact_value in artifacts.items():
                    recorder.set_artifact(trace, artifact_key, artifact_value)
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
                action_stats=_build_action_stats(all_results),
                planner_provider=plan_result.provider_name,
                planner_model=_planner_model(plan_result.metadata),
                steps=_steps_to_dict(plan_result.steps),
                artifacts=artifacts,
                fallback_used=fallback_used,
                fallback_strategy=fallback_strategy,
                fallback_trigger=fallback_trigger,
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
    if isinstance(extracts, dict):
        for key, value in extracts.items():
            if isinstance(value, str):
                compact = " ".join(value.split()) if mode == "summary" else value
                preview = compact[:240] + ("..." if mode == "summary" and len(compact) > 240 else "")
                lines.append(f"- {key}: {preview}")
            else:
                lines.append(f"- {key}: {json.dumps(value)}")
    extract_sequence = artifacts.get("extract_sequence") if isinstance(artifacts, dict) else None
    if isinstance(extract_sequence, list) and extract_sequence:
        sequence_count = len(extract_sequence)
        if mode == "summary":
            lines.append(f"- extract_sequence: {sequence_count} extract events")
        else:
            lines.append(f"- extract_sequence: {json.dumps(extract_sequence, ensure_ascii=False)}")
    return lines


def _build_run_artifacts(
    task_id: str | None,
    goal: str,
    observation,
    extract_artifacts: dict[str, Any],
    extract_sequence: list[dict[str, Any]] | None = None,
    plan_metadata: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    artifacts: dict[str, object] = {}
    extract_sequence = extract_sequence or []
    plan_metadata = plan_metadata or {}
    artifacts["isLLMReProcessingRequired"] = _is_llm_reprocessing_required(
        task_id=task_id,
        goal=goal,
        plan_metadata=plan_metadata,
    )
    if extract_artifacts:
        artifacts["extracts"] = extract_artifacts
    if extract_sequence:
        artifacts["extract_sequence"] = extract_sequence

    research_brief = _build_research_brief(task_id=task_id, goal=goal, observation=observation, extract_artifacts=extract_artifacts)
    if research_brief is not None:
        artifacts["research_brief"] = research_brief
    comparison_artifact = _build_comparison_artifact(
        task_id=task_id,
        goal=goal,
        observation=observation,
        extract_sequence=extract_sequence,
        plan_metadata=plan_metadata,
    )
    if comparison_artifact is not None:
        comparison_artifact["isLLMReProcessingRequired"] = bool(artifacts["isLLMReProcessingRequired"])
        csv_path = _maybe_write_comparison_csv(comparison_artifact, run_id=run_id)
        if csv_path is not None:
            comparison_artifact["csv_path"] = str(csv_path)
        artifacts["comparison"] = comparison_artifact
    return artifacts


def _build_research_brief(task_id: str | None, goal: str, observation, extract_artifacts: dict[str, Any]) -> dict[str, object] | None:
    if task_id not in {"wikipedia-summary", "wikipedia-section", "wikipedia-section-headings"}:
        return None
    summary = extract_artifacts.get("summary")
    citation_links = extract_artifacts.get("citation_links")
    section_headings = extract_artifacts.get("section_headings")
    section_extracts = {
        key.removeprefix("section:"): value
        for key, value in extract_artifacts.items()
        if key.startswith("section:")
    }
    topic = observation.title.replace(" - Wikipedia", "").strip() if getattr(observation, "title", "") else goal
    brief: dict[str, object] = {
        "topic": topic,
        "article_url": getattr(observation, "url", ""),
        "article_title": getattr(observation, "title", ""),
    }
    if isinstance(summary, str) and summary.strip():
        brief["summary"] = summary
    if isinstance(citation_links, list) and citation_links:
        brief["citation_links"] = citation_links
    if isinstance(section_headings, list) and section_headings:
        brief["section_headings"] = section_headings
    if section_extracts:
        brief["sections"] = section_extracts
    return brief


def _is_llm_reprocessing_required(
    task_id: str | None,
    goal: str,
    plan_metadata: dict[str, Any],
) -> bool:
    metadata_flag = plan_metadata.get("isLLMReProcessingRequired")
    if isinstance(metadata_flag, bool):
        return metadata_flag
    if task_id == "wikipedia-comparison":
        return True
    if parse_comparison_intent(goal) is not None and plan_metadata.get("mode") == "llm":
        return True
    return False


def _maybe_synthesize_comparison_rows(
    subject: str,
    columns: list[str],
    raw_rows: list[dict[str, object]],
    plan_metadata: dict[str, Any],
) -> dict[str, object] | None:
    if not raw_rows:
        return None
    if plan_metadata.get("mode") != "llm":
        return None
    try:
        synthesizer = AnthropicComparisonRowSynthesizer.from_env()
    except ComparisonSynthesisError:
        return None
    try:
        result = synthesizer.synthesize(subject=subject, columns=columns, raw_rows=raw_rows)
    except Exception:
        return None
    return {
        "rows": result.rows,
        "provider": result.provider,
        "model": result.model,
    }


def _build_comparison_artifact(
    task_id: str | None,
    goal: str,
    observation,
    extract_sequence: list[dict[str, Any]],
    plan_metadata: dict[str, Any],
) -> dict[str, object] | None:
    comparison_intent = parse_comparison_intent(goal)
    if comparison_intent is None:
        return None

    raw_rows = _build_comparison_rows(extract_sequence, requested_columns=comparison_intent.requested_columns)
    if not raw_rows and task_id == "bestbuy-live-comparison":
        raw_rows = _build_bestbuy_search_result_rows(
            extract_sequence=extract_sequence,
            requested_columns=comparison_intent.requested_columns,
            goal=goal,
        )
    if not raw_rows:
        return None

    columns = comparison_intent.requested_columns or _infer_comparison_columns_from_rows(raw_rows)
    if len(columns) > 5:
        columns = columns[:5]

    synthesized_rows = raw_rows
    synthesis_metadata = {
        "llm_reprocessing_applied": False,
        "llm_reprocessing_provider": None,
        "llm_reprocessing_model": None,
        "llm_reprocessing_error": None,
    }
    synthesis_result = _maybe_synthesize_comparison_rows(
        subject=comparison_intent.subject,
        columns=columns,
        raw_rows=raw_rows,
        plan_metadata=plan_metadata,
    )
    if synthesis_result is not None:
        synthesized_rows = synthesis_result["rows"]
        synthesis_metadata = {
            "llm_reprocessing_applied": True,
            "llm_reprocessing_provider": synthesis_result["provider"],
            "llm_reprocessing_model": synthesis_result["model"],
            "llm_reprocessing_error": None,
        }
    elif _is_llm_reprocessing_required(task_id=task_id, goal=goal, plan_metadata=plan_metadata):
        synthesis_metadata["llm_reprocessing_error"] = "llm_reprocessing_unavailable"

    return {
        "query": goal,
        "subject": comparison_intent.subject,
        "output_mode": comparison_intent.output_mode,
        "isLLMReProcessingRequired": _is_llm_reprocessing_required(
            task_id=task_id,
            goal=goal,
            plan_metadata=plan_metadata,
        ),
        "task_id": task_id,
        "article_url": getattr(observation, "url", ""),
        "columns": columns,
        "raw_rows": raw_rows,
        "rows": synthesized_rows,
        "entity_count": len(synthesized_rows),
        "metadata": {
            "planner_mode": plan_metadata.get("mode"),
            "model": plan_metadata.get("model"),
            **synthesis_metadata,
        },
    }


def _effective_verification_rules(
    task_id: str | None,
    plan_rules: list,
    plan_metadata: dict[str, Any],
    artifacts: dict[str, object],
) -> list:
    if not task_id or not task_id.endswith("comparison"):
        return list(plan_rules)

    comparison = artifacts.get("comparison")
    if not isinstance(comparison, dict):
        return list(plan_rules)

    expected_rows = 0
    entities = plan_metadata.get("entities")
    if isinstance(entities, list):
        expected_rows = len(entities)
    minimum_rows = max(2, expected_rows or 0)

    rules = [
        VerificationRule(kind="artifact_exists", value="comparison", label="comparison artifact"),
        VerificationRule(
            kind="artifact_list_min_length",
            value={"path": "comparison.rows", "min": minimum_rows},
            label="comparison rows",
        ),
    ]
    if str(comparison.get("output_mode") or "").lower() == "csv":
        rules.append(VerificationRule(kind="artifact_exists", value="comparison.csv_path", label="comparison csv"))
    return rules


def _maybe_write_comparison_csv(comparison: dict[str, object], run_id: str | None = None) -> Path | None:
    if str(comparison.get("output_mode") or "").lower() != "csv":
        return None
    rows = comparison.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    columns = comparison.get("columns")
    if not isinstance(columns, list) or not columns:
        return None

    output_dir = Path("artifacts") / "comparisons"
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify_comparison_subject(str(comparison.get("subject") or "comparison"))
    suffix = run_id or "manual"
    path = output_dir / f"{slug}_{suffix}.csv"

    fieldnames = ["entity_name", *[str(column) for column in columns], "article_url"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            if not isinstance(row, dict):
                continue
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    return path.resolve()


def _build_comparison_rows(
    extract_sequence: list[dict[str, Any]],
    requested_columns: list[str],
) -> list[dict[str, object]]:
    page_rows: dict[str, dict[str, object]] = {}
    page_order: list[str] = []
    for item in extract_sequence:
        url = str(item.get("current_url") or "").strip()
        if not url:
            continue
        if url not in page_rows:
            page_order.append(url)
            page_rows[url] = {
                "entity_name": _entity_name_from_page_title(str(item.get("page_title") or ""), url),
                "article_url": url,
            }
        row = page_rows[url]
        target = str(item.get("target") or "").strip()
        value = item.get("value")
        if target == "summary" and isinstance(value, str) and value.strip():
            row["summary"] = value
        elif target == "citation_links" and isinstance(value, list) and value:
            row["citation_links"] = value
        elif target.startswith("section:") and isinstance(value, str) and value.strip():
            row[target.removeprefix("section:")] = value
        elif target == "section_headings" and isinstance(value, list) and value:
            row["section_headings"] = value
        elif target == "bestbuy_price" and isinstance(value, str) and value.strip():
            row["price"] = value
        elif target == "bestbuy_product_facts" and isinstance(value, dict) and value:
            _merge_bestbuy_product_facts(row, value)
        elif target == "bestbuy_search_results" and isinstance(value, list) and value:
            row["search_results"] = value

    normalized_requested = {_normalize_column_name(column): column for column in requested_columns}
    rows: list[dict[str, object]] = []
    for url in page_order:
        raw_row = page_rows[url]
        if _is_search_results_only_row(raw_row):
            continue
        row: dict[str, object] = {
            "entity_name": raw_row["entity_name"],
            "article_url": raw_row["article_url"],
        }
        if requested_columns:
            for normalized, original in normalized_requested.items():
                matched = _match_requested_column(raw_row, normalized)
                if matched is not None:
                    row[original] = matched
        else:
            for key in ("summary",):
                if key in raw_row:
                    row[key] = raw_row[key]
        rows.append(row)
    return rows


def _is_search_results_only_row(row: dict[str, object]) -> bool:
    comparison_data_keys = set(row) - {"entity_name", "article_url", "search_results"}
    return "search_results" in row and not comparison_data_keys


def _build_bestbuy_search_result_rows(
    extract_sequence: list[dict[str, Any]],
    requested_columns: list[str],
    goal: str,
) -> list[dict[str, object]]:
    search_results = _latest_search_results(extract_sequence)
    if not search_results:
        return []
    limit = _bestbuy_live_result_limit(goal)
    normalized_requested = {_normalize_column_name(column): column for column in requested_columns}
    ranked_rows: list[dict[str, object]] = []
    for item in search_results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        href = str(item.get("href") or "").strip()
        if not title or not href:
            continue
        ranked_rows.append(_bestbuy_search_result_facts(title=title, href=href, price=str(item.get("price") or "").strip()))
    ranked_rows.sort(
        key=lambda row: _bestbuy_search_row_score(row=row, requested_columns=requested_columns, goal=goal),
        reverse=True,
    )

    rows: list[dict[str, object]] = []
    for raw_row in ranked_rows[:limit]:
        row: dict[str, object] = {
            "entity_name": raw_row["entity_name"],
            "article_url": raw_row["article_url"],
        }
        if requested_columns:
            for normalized, original in normalized_requested.items():
                matched = _match_requested_column(raw_row, normalized)
                if matched is not None:
                    row[original] = matched
        else:
            for key in ("price", "model name", "display size", "ram", "storage", "gpu"):
                if key in raw_row:
                    row[key] = raw_row[key]
        rows.append(row)
    return rows


def _latest_search_results(extract_sequence: list[dict[str, Any]]) -> list[dict[str, object]]:
    for item in reversed(extract_sequence):
        if str(item.get("target") or "") != "bestbuy_search_results":
            continue
        value = item.get("value")
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, dict)]
    return []


def _bestbuy_live_result_limit(goal: str) -> int:
    match = re.search(r"\b(?:top|first)\s+(\d+)\b", goal.lower())
    if match is None:
        return 3
    return max(2, min(int(match.group(1)), 5))


def _bestbuy_search_result_facts(title: str, href: str, price: str = "") -> dict[str, object]:
    row: dict[str, object] = {
        "entity_name": title,
        "article_url": href,
        "model name": title,
    }
    if price:
        row["price"] = price
    display_size = _first_match(title, r"(\d+(?:\.\d+)?)\s*(?:\"|inch|in\b)")
    if display_size:
        row["display size"] = f"{display_size} inches"
    ram = _first_match(title, r"(\d+)\s*(?:GB|gigabytes)\s*(?:RAM|Memory|DDR\d?)")
    if ram:
        row["ram"] = f"{ram}GB"
    storage = _first_match(title, r"(\d+(?:\.\d+)?)\s*(TB|GB|gigabytes)\s*(?:SSD|Storage)")
    if storage:
        row["storage"] = _normalize_capacity(storage)
    refresh_rate = _first_match(title, r"(\d+(?:\.\d+)?)\s*Hz")
    if refresh_rate:
        row["refresh rate"] = f"{refresh_rate}Hz"
    resolution = _bestbuy_resolution_from_title(title)
    if resolution:
        row["resolution"] = resolution
    gpu = _first_match(
        title,
        r"((?:NVIDIA|GeForce|RTX|GTX|AMD Radeon|Radeon)[A-Za-z0-9\s\-]+?)(?:\s+-|\s+\d+(?:GB|TB)|$)",
    )
    if gpu:
        row["gpu"] = " ".join(gpu.split())
    return row


def _bestbuy_search_row_score(row: dict[str, object], requested_columns: list[str], goal: str) -> int:
    score = 0
    for column in requested_columns:
        if _match_requested_column(row, _normalize_column_name(column)) not in (None, ""):
            score += 10
    title = str(row.get("entity_name") or "").lower()
    if "gaming" in goal.lower() and "gaming" in title:
        score += 5
    if "laptop" in title:
        score += 1
    return score


def _first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return ""
    return " ".join(part for part in match.groups() if part).strip()


def _normalize_capacity(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    normalized = re.sub(r"\bGB\b", "GB", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bTB\b", "TB", normalized, flags=re.IGNORECASE)
    return normalized


def _bestbuy_resolution_from_title(title: str) -> str:
    explicit = _first_match(title, r"(\d{3,4}\s*x\s*\d{3,4})")
    if explicit:
        return explicit.replace(" ", "")
    normalized = title.lower()
    resolution_terms = (
        ("ultra-wqhd", "Ultra-WQHD"),
        ("wqhd", "WQHD"),
        ("qhd", "QHD"),
        ("uhd", "UHD"),
        ("4k", "4K"),
        ("2k", "2K"),
        ("fhd", "FHD"),
        ("full hd", "Full HD"),
    )
    for needle, label in resolution_terms:
        if needle in normalized:
            return label
    return ""


def _entity_name_from_page_title(page_title: str, url: str) -> str:
    cleaned = page_title.replace(" - Wikipedia", "").replace(" - Best Buy", "").strip()
    if cleaned:
        return cleaned
    return url.rstrip("/").rsplit("/", 1)[-1].replace("_", " ")


def _normalize_column_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _match_requested_column(raw_row: dict[str, object], normalized_column: str) -> object | None:
    aliases = _comparison_column_aliases(normalized_column)
    for key, value in raw_row.items():
        normalized_key = _normalize_column_name(str(key))
        if normalized_key == normalized_column:
            return value
        if normalized_key.startswith(normalized_column) or normalized_column.startswith(normalized_key):
            return value
        if normalized_key in aliases:
            return value
    return None


def _infer_comparison_columns_from_rows(rows: list[dict[str, object]]) -> list[str]:
    inferred: list[str] = []
    for row in rows:
        for key in row.keys():
            if key in {"entity_name", "article_url"}:
                continue
            if key not in inferred:
                inferred.append(key)
            if len(inferred) >= 5:
                return inferred
    return inferred


def _slugify_comparison_subject(subject: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", subject.lower()).strip("_")
    return normalized or "comparison"


def _merge_bestbuy_product_facts(row: dict[str, object], value: dict[str, object]) -> None:
    entity_name = value.get("entity_name") or value.get("product_name")
    if isinstance(entity_name, str) and entity_name.strip():
        row["entity_name"] = entity_name
        row["model name"] = entity_name
    product_url = value.get("product_url")
    if isinstance(product_url, str) and product_url.strip():
        row["article_url"] = product_url
    sku = value.get("sku")
    if isinstance(sku, str) and sku.strip():
        row["sku"] = sku
    price = value.get("price")
    if isinstance(price, str) and price.strip():
        row["price"] = price
    facts = value.get("facts")
    if isinstance(facts, dict):
        for key, fact_value in facts.items():
            if isinstance(key, str) and fact_value not in (None, ""):
                row[key] = fact_value
    specifications = value.get("specifications")
    if isinstance(specifications, dict):
        for key, spec_value in specifications.items():
            if not isinstance(key, str) or spec_value in (None, ""):
                continue
            normalized_key = _normalize_column_name(key)
            if normalized_key.startswith("screen size"):
                row.setdefault("display size", spec_value)
            elif normalized_key.startswith("display size"):
                row.setdefault("display size", spec_value)
            elif normalized_key.startswith("system memory") or normalized_key == "ram":
                row.setdefault("ram", spec_value)
            elif (
                normalized_key.startswith("solid state drive capacity")
                or normalized_key.startswith("ssd capacity")
                or normalized_key.startswith("storage capacity")
            ):
                row["storage"] = spec_value
            elif "storage" in normalized_key or "ssd" in normalized_key:
                row.setdefault("storage", spec_value)


def _comparison_column_aliases(normalized_column: str) -> set[str]:
    aliases = {normalized_column}
    alias_map = {
        "price": {"current price"},
        "display size": {"screen size"},
        "screen size": {"display size"},
        "ram": {"memory", "system memory"},
        "memory": {"ram", "system memory"},
        "storage": {"storage type", "storage capacity", "solid state drive capacity", "ssd capacity"},
        "model name": {"entity name", "product name"},
    }
    aliases.update(alias_map.get(normalized_column, set()))
    return aliases


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
    if outcome.fallback_used:
        print(f"- fallback: {outcome.fallback_strategy or 'unknown'}")
        if outcome.fallback_trigger:
            print(f"- fallback_trigger: {outcome.fallback_trigger}")
    print("- plan:")
    if outcome.steps:
        for index, step in enumerate(outcome.steps, start=1):
            print(f"  {index}. {_format_step_summary(step)}")
    else:
        print("  none")
    research_brief = outcome.artifacts.get("research_brief") if isinstance(outcome.artifacts, dict) else None
    if isinstance(research_brief, dict):
        _print_research_brief(research_brief, mode=artifacts_mode)
    comparison_artifact = outcome.artifacts.get("comparison") if isinstance(outcome.artifacts, dict) else None
    if isinstance(comparison_artifact, dict):
        _print_comparison_artifact(comparison_artifact, mode=artifacts_mode)
    artifact_lines = _artifact_lines(outcome.artifacts, mode=artifacts_mode)
    if artifact_lines:
        print("- artifacts:")
        for line in artifact_lines:
            print(f"  {line}")
    print(f"- trace: {outcome.trace_path}")


def _print_research_brief(brief: dict[str, object], mode: str = "summary") -> None:
    if mode == "none":
        return
    print("- research_brief:")
    topic = brief.get("topic")
    if topic:
        print(f"  - topic: {topic}")
    article_url = brief.get("article_url")
    if article_url:
        print(f"  - article_url: {article_url}")
    summary = brief.get("summary")
    if isinstance(summary, str) and summary.strip():
        summary_text = summary if mode == "detailed" else summary[:280] + ("..." if len(summary) > 280 else "")
        print(f"  - summary: {summary_text}")
    section_headings = brief.get("section_headings")
    if isinstance(section_headings, list) and section_headings:
        headings_preview = section_headings if mode == "detailed" else section_headings[:8]
        print(f"  - section_headings: {json.dumps(headings_preview, ensure_ascii=False)}")
    sections = brief.get("sections")
    if isinstance(sections, dict) and sections:
        for name, value in sections.items():
            if not isinstance(value, str) or not value.strip():
                continue
            section_preview = value if mode == "detailed" else value[:220] + ("..." if len(value) > 220 else "")
            print(f"  - section[{name}]: {section_preview}")
    citation_links = brief.get("citation_links")
    if isinstance(citation_links, list) and citation_links:
        citation_preview = citation_links if mode == "detailed" else citation_links[:3]
        print(f"  - citation_links: {json.dumps(citation_preview, ensure_ascii=False)}")


def _print_comparison_artifact(comparison: dict[str, object], mode: str = "summary") -> None:
    if mode == "none":
        return
    print("- comparison:")
    subject = comparison.get("subject")
    if subject:
        print(f"  - subject: {subject}")
    output_mode = comparison.get("output_mode")
    if output_mode:
        print(f"  - output_mode: {output_mode}")
    llm_reprocessing = comparison.get("isLLMReProcessingRequired")
    if isinstance(llm_reprocessing, bool):
        print(f"  - isLLMReProcessingRequired: {str(llm_reprocessing).lower()}")
    metadata = comparison.get("metadata")
    if isinstance(metadata, dict):
        if metadata.get("llm_reprocessing_applied") is not None:
            print(f"  - llm_reprocessing_applied: {str(bool(metadata.get('llm_reprocessing_applied'))).lower()}")
        if metadata.get("llm_reprocessing_provider"):
            print(f"  - llm_reprocessing_provider: {metadata.get('llm_reprocessing_provider')}")
    columns = comparison.get("columns")
    if isinstance(columns, list) and columns:
        print(f"  - columns: {json.dumps(columns, ensure_ascii=False)}")
    rows = comparison.get("rows")
    if isinstance(rows, list) and rows:
        row_preview = rows if mode == "detailed" else rows[:3]
        print(f"  - rows: {json.dumps(row_preview, ensure_ascii=False)}")
        csv_preview = _comparison_csv_preview(comparison, max_rows=10)
        if csv_preview:
            print("  - csv_preview:")
            for line in csv_preview.splitlines():
                print(f"    {line}")
    csv_path = comparison.get("csv_path")
    if csv_path:
        print(f"  - csv_path: {csv_path}")


def _comparison_csv_preview(comparison: dict[str, object], max_rows: int = 10) -> str:
    rows = comparison.get("rows")
    columns = comparison.get("columns")
    if not isinstance(rows, list) or not rows:
        return ""
    if not isinstance(columns, list) or not columns:
        return ""
    fieldnames = ["entity_name", *[str(column) for column in columns], "article_url"]
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    written = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        writer.writerow({name: row.get(name, "") for name in fieldnames})
        written += 1
        if written >= max_rows:
            break
    return handle.getvalue().strip()


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


def _attempt_fallback(
    plan_result,
    recorder: TraceRecorder,
    trace,
    executor: Executor,
    trigger: str,
) -> dict[str, Any] | None:
    fallback_plan = get_fallback_plan(plan_result, trigger)
    if fallback_plan is None:
        return None
    recorder.append_event(
        trace,
        {
            "event": "fallback_plan_generated",
            "strategy": fallback_plan.strategy_name,
            "trigger": fallback_plan.trigger,
            "step_count": len(fallback_plan.steps),
        },
    )
    fallback_results = executor.run_steps(fallback_plan.steps)
    return {
        "strategy": fallback_plan.strategy_name,
        "steps": fallback_plan.steps,
        "results": fallback_results,
        "extract_artifacts": collect_extract_artifacts(fallback_results),
        "extract_sequence": collect_extract_sequence(fallback_results),
    }


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
