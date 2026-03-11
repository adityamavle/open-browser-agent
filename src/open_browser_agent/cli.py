from __future__ import annotations

import argparse
import json
from pathlib import Path

from open_browser_agent.actions import ActionAPI
from open_browser_agent.browser import BrowserSession, BrowserSessionError
from open_browser_agent.executor import Executor
from open_browser_agent.observer import Observer
from open_browser_agent.replay import replay_trace
from open_browser_agent.tasks.registry import TASKS, find_task_by_goal
from open_browser_agent.trace import TraceRecorder
from open_browser_agent.verifier import Verifier


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


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

    replay_parser = subparsers.add_parser("replay", help="Replay a saved trace.")
    replay_parser.add_argument("trace_path", help="Path to a trace JSON file.")

    examples_parser = subparsers.add_parser("examples", help="Inspect bundled example tasks.")
    examples_subparsers = examples_parser.add_subparsers(dest="examples_command", required=True)
    examples_subparsers.add_parser("list", help="List example tasks.")

    return parser


def handle_run(goal: str, trace_dir: str) -> int:
    task = find_task_by_goal(goal)
    recorder = TraceRecorder(Path(trace_dir))
    trace = recorder.start_run(goal=goal, task_id=task.task_id if task else None)

    if task is None:
        recorder.finish_run(
            trace,
            success=False,
            reason="No matching task found. Planner/executor implementation pending.",
        )
        print(
            f"No example task matched {goal!r}. "
            f"Initialized trace at {trace.trace_path}."
        )
        return 1

    recorder.set_steps(trace, task.steps)
    recorder.append_event(
        trace,
        {
            "event": "task_resolved",
            "task_id": task.task_id,
            "step_count": len(task.steps),
            "verifier_hint": task.verifier_hint,
        },
    )

    try:
        with BrowserSession() as session:
            actions = ActionAPI(lambda: session.page, url_resolver=_resolve_url)
            observer = Observer(lambda: session.page)
            executor = Executor(actions=actions, observer=observer, trace_recorder=recorder, trace=trace)

            results = executor.run_steps(task.steps)
            first_failure = next((result for result in results if not result.success), None)
            if first_failure is not None:
                recorder.finish_run(trace, success=False, reason=first_failure.message)
                print(
                    f"Task '{task.task_id}' failed during execution. "
                    f"Trace written to {trace.trace_path}."
                )
                return 1

            verification = Verifier(task.verification_rules).verify(observer.capture())
            recorder.finish_run(trace, success=verification.success, reason=verification.reason)
            print(
                f"Task '{task.task_id}' completed with success={verification.success}. "
                f"Trace written to {trace.trace_path}."
            )
            return 0 if verification.success else 1
    except BrowserSessionError as exc:
        recorder.finish_run(trace, success=False, reason=str(exc))
        print(f"Browser session error: {exc}. Trace written to {trace.trace_path}.")
        return 1


def _resolve_url(url: str) -> str:
    if not url.startswith("fixture://"):
        return url

    fixture_name = url.removeprefix("fixture://")
    fixture_path = FIXTURE_DIR / fixture_name
    return fixture_path.resolve().as_uri()


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
        return handle_run(args.goal, args.trace_dir)
    if args.command == "replay":
        return handle_replay(args.trace_path)
    if args.command == "examples" and args.examples_command == "list":
        return handle_examples_list()

    parser.error("Unsupported command.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
