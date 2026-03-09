from __future__ import annotations

from open_browser_agent.schemas.step import Step
from open_browser_agent.tasks.registry import find_task_by_goal


class Planner:
    """Optional planner that emits structured steps for the executor."""

    def plan(self, goal: str) -> list[Step]:
        task = find_task_by_goal(goal)
        if task is None:
            raise ValueError(f"No task found for goal: {goal}")
        return list(task.steps)
