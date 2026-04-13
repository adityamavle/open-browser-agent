from open_browser_agent.tasks.registry import TASKS

BESTBUY_COMPARISON_TASK = next(task for task in TASKS if task.task_id == "bestbuy-laptop-comparison")
