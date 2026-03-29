from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def replay_trace(trace_path: Path) -> dict[str, Any]:
    if not trace_path.exists():
        return {"ok": False, "error": f"Trace not found: {trace_path}"}

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    verification = payload.get("verification") or {}
    artifacts = payload.get("artifacts") or {}
    checks = verification.get("checks") or []
    passed_checks = [check for check in checks if check.get("passed")]
    failed_checks = [check for check in checks if not check.get("passed")]
    return {
        "ok": True,
        "mode": "dry-run",
        "trace_path": str(trace_path),
        "task": payload.get("task"),
        "goal": payload.get("goal"),
        "events": len(events),
        "step_ids": [event.get("step_id") for event in events],
        "artifact_keys": sorted(artifacts.keys()),
        "verification": verification,
        "verification_summary": {
            "checks_total": len(checks),
            "checks_passed": len(passed_checks),
            "checks_failed": len(failed_checks),
            "failed_labels": [str(check.get("label") or check.get("kind") or "unknown") for check in failed_checks],
        },
    }
