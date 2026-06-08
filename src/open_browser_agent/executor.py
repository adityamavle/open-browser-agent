from __future__ import annotations

from dataclasses import dataclass

from open_browser_agent.actions import ActionAPI, ActionResult
from open_browser_agent.observer import Observer
from open_browser_agent.schemas.step import Step
from open_browser_agent.trace import RunTrace, TraceRecorder


@dataclass(slots=True)
class ExecutionResult:
    step_id: str
    success: bool
    message: str
    action_result: ActionResult | None = None


class ExecutorError(RuntimeError):
    """Raised when an unsupported step is dispatched."""


class Executor:
    """Runs structured steps against the browser backend."""

    def __init__(
        self,
        actions: ActionAPI,
        observer: Observer | None = None,
        trace_recorder: TraceRecorder | None = None,
        trace: RunTrace | None = None,
    ) -> None:
        self.actions = actions
        self.observer = observer
        self.trace_recorder = trace_recorder
        self.trace = trace
        self._history: list[ExecutionResult] = []

    def run_step(self, step: Step) -> ExecutionResult:
        pre_observation = self.observer.capture() if self.observer else None
        action_result = self._dispatch(step)
        post_observation = self.observer.capture() if self.observer else None

        if self.trace_recorder and self.trace:
            self.trace_recorder.append_event(
                self.trace,
                {
                    "step_id": step.id,
                    "action": action_result.action,
                    "status": "ok" if action_result.ok else "error",
                    "details": action_result.details,
                    "error": action_result.error,
                    "error_code": action_result.error_code,
                    "pre_observation": pre_observation.to_dict() if pre_observation else None,
                    "post_observation": post_observation.to_dict() if post_observation else None,
                },
            )

        message = "Step completed." if action_result.ok else f"Step failed: {action_result.error}"
        result = ExecutionResult(step_id=step.id, success=action_result.ok, message=message, action_result=action_result)
        self._history.append(result)
        return result

    def run_steps(self, steps: list[Step]) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        for step in steps:
            result = self.run_step(step)
            results.append(result)
            if not result.success:
                break
        return results

    def _dispatch(self, step: Step) -> ActionResult:
        timeout_ms = step.timeout_ms
        if step.type in {"navigate", "goto"}:
            return self.actions.goto(step.args["url"], timeout_ms=timeout_ms)
        if step.type == "click":
            return self.actions.click(step.args["selector"], timeout_ms=timeout_ms)
        if step.type == "type":
            return self.actions.type(step.args["selector"], step.args["text"], timeout_ms=timeout_ms)
        if step.type == "press":
            return self.actions.press(step.args["keys"], timeout_ms=timeout_ms)
        if step.type == "wait_for":
            return self.actions.wait_for(step.args["selector"], timeout_ms=timeout_ms)
        if step.type == "extract":
            return self.actions.extract(step.args["target"], timeout_ms=timeout_ms)
        if step.type == "navigate_extracted_result":
            return self._navigate_extracted_result(step, timeout_ms=timeout_ms)
        raise ExecutorError(f"Unsupported step type: {step.type}")

    def _navigate_extracted_result(self, step: Step, timeout_ms: int | None = None) -> ActionResult:
        source_target = str(step.args["source_target"])
        index = int(step.args["index"])
        url_field = str(step.args.get("url_field") or "href")
        source_value = self._latest_extract_value(source_target)
        details = {
            "source_target": source_target,
            "index": index,
            "url_field": url_field,
            "timeout_ms": timeout_ms,
        }
        if not isinstance(source_value, list):
            return ActionResult(
                ok=False,
                action="navigate_extracted_result",
                error=f"No list extract found for target: {source_target}",
                error_code="missing_extract",
                details=details,
            )
        if index < 0 or index >= len(source_value):
            return ActionResult(
                ok=False,
                action="navigate_extracted_result",
                error=f"Extract target {source_target!r} does not include result index {index}.",
                error_code="missing_extract_result",
                details={**details, "available_results": len(source_value)},
            )
        result = source_value[index]
        if not isinstance(result, dict):
            return ActionResult(
                ok=False,
                action="navigate_extracted_result",
                error=f"Extract result index {index} is not an object.",
                error_code="invalid_extract_result",
                details=details,
            )
        url = str(result.get(url_field) or "").strip()
        if not url:
            return ActionResult(
                ok=False,
                action="navigate_extracted_result",
                error=f"Extract result index {index} does not include URL field {url_field!r}.",
                error_code="missing_extract_url",
                details={**details, "result": result},
            )
        action_result = self.actions.goto(url, timeout_ms=timeout_ms)
        action_result.details.update(details)
        return action_result

    def _latest_extract_value(self, target: str):
        for result in reversed(self._history):
            action_result = result.action_result
            if action_result is None or action_result.action != "extract" or not action_result.ok:
                continue
            if str(action_result.details.get("target") or "") == target:
                return action_result.details.get("value")
        return None
