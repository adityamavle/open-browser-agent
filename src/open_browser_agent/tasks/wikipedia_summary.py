from open_browser_agent.tasks.registry import TASKS

WIKIPEDIA_SUMMARY_TASK = next(task for task in TASKS if task.task_id == "wikipedia-summary")
