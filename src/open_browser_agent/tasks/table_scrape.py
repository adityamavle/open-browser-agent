from open_browser_agent.tasks.registry import TASKS

TABLE_SCRAPE_TASK = next(task for task in TASKS if task.task_id == "table-scrape")
