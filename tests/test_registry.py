from __future__ import annotations

from open_browser_agent.tasks.registry import find_task_by_goal


def test_find_task_by_goal_matches_alias() -> None:
    task = find_task_by_goal("wiki summary")
    assert task is not None
    assert task.task_id == "wikipedia-summary"


def test_find_task_by_goal_matches_summary_substring() -> None:
    task = find_task_by_goal("html table")
    assert task is not None
    assert task.task_id == "table-scrape"


def test_find_task_by_goal_returns_none_for_empty_input() -> None:
    assert find_task_by_goal("") is None
