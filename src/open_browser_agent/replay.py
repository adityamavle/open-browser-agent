from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def replay_trace(trace_path: Path) -> dict[str, Any]:
    if not trace_path.exists():
        return {"ok": False, "error": f"Trace not found: {trace_path}"}

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    return {
        "ok": True,
        "mode": "dry-run",
        "trace_path": str(trace_path),
        "task": payload.get("task"),
        "goal": payload.get("goal"),
        "events": len(events),
        "step_ids": [event.get("step_id") for event in events],
        "verification": payload.get("verification"),
    }
