from __future__ import annotations

from dataclasses import dataclass

from open_browser_agent.actions import ActionAPI, ActionResult
from open_browser_agent.observer import Observer
from open_browser_agent.schemas.step import Step
from open_browser_agent.trace import RunTrace, TraceRecorder


@dataclass(slots=True)
class ExecutionResult:
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
                    "pre_observation": pre_observation.to_dict() if pre_observation else None,
                    "post_observation": post_observation.to_dict() if post_observation else None,
                },
            )

        message = "Step completed." if action_result.ok else f"Step failed: {action_result.error}"
        return ExecutionResult(success=action_result.ok, message=message, action_result=action_result)

    def run_steps(self, steps: list[Step]) -> list[ExecutionResult]:
        return [self.run_step(step) for step in steps]

    def _dispatch(self, step: Step) -> ActionResult:
        if step.type in {"navigate", "goto"}:
            return self.actions.goto(step.args["url"])
        if step.type == "click":
            return self.actions.click(step.args["selector"])
        if step.type == "type":
            return self.actions.type(step.args["selector"], step.args["text"])
        if step.type == "press":
            return self.actions.press(step.args["keys"])
        if step.type == "wait_for":
            return self.actions.wait_for(step.args["selector"])
        if step.type == "extract":
            return self.actions.extract(step.args["target"])
        raise ExecutorError(f"Unsupported step type: {step.type}")
