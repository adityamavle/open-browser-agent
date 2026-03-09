from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class RunTrace:
    run_id: str
    started_at: str
    goal: str
    task_id: str | None
    trace_path: Path
    events: list[dict[str, Any]] = field(default_factory=list)


class TraceRecorder:
    def __init__(self, trace_dir: Path) -> None:
        self.trace_dir = trace_dir
        self.trace_dir.mkdir(parents=True, exist_ok=True)

    def start_run(self, goal: str, task_id: str | None) -> RunTrace:
        run_id = uuid4().hex
        trace_path = self.trace_dir / f"{run_id}.json"
        trace = RunTrace(
            run_id=run_id,
            started_at=datetime.now(UTC).isoformat(),
            goal=goal,
            task_id=task_id,
            trace_path=trace_path,
        )
        self._write(
            trace,
            {
                "meta": {
                    "run_id": trace.run_id,
                    "started_at": trace.started_at,
                },
                "goal": trace.goal,
                "task": trace.task_id,
                "steps": [],
                "events": [],
                "verification": None,
                "artifacts": {},
            },
        )
        return trace

    def append_event(self, trace: RunTrace, event: dict[str, Any]) -> None:
        payload = self._load(trace.trace_path)
        payload.setdefault("events", []).append(event)
        trace.events.append(event)
        self._write(trace, payload)

    def finish_run(self, trace: RunTrace, success: bool, reason: str) -> None:
        payload = self._load(trace.trace_path)
        payload["verification"] = {
            "success": success,
            "reason": reason,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        self._write(trace, payload)

    def load_trace(self, path: Path) -> dict[str, Any]:
        return self._load(path)

    def _load(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, trace: RunTrace, payload: dict[str, Any]) -> None:
        trace.trace_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
