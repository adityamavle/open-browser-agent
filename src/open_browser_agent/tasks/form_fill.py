from open_browser_agent.tasks.registry import TASKS

FORM_FILL_TASK = next(task for task in TASKS if task.task_id == "form-fill")
