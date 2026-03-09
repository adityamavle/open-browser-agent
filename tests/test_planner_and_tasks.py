from __future__ import annotations

from open_browser_agent.planner import Planner
from open_browser_agent.tasks.form_fill import FORM_FILL_TASK
from open_browser_agent.tasks.table_scrape import TABLE_SCRAPE_TASK
from open_browser_agent.tasks.wikipedia_summary import WIKIPEDIA_SUMMARY_TASK


def test_planner_returns_task_steps() -> None:
    planner = Planner()
    steps = planner.plan("wiki summary")

    assert len(steps) == len(WIKIPEDIA_SUMMARY_TASK.steps)
    assert steps[0].type == "navigate"


def test_planner_raises_for_missing_goal() -> None:
    planner = Planner()

    try:
        planner.plan("missing goal")
    except ValueError as exc:
        assert "No task found" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError")


def test_task_modules_export_expected_specs() -> None:
    assert FORM_FILL_TASK.task_id == "form-fill"
    assert TABLE_SCRAPE_TASK.task_id == "table-scrape"
    assert WIKIPEDIA_SUMMARY_TASK.task_id == "wikipedia-summary"
