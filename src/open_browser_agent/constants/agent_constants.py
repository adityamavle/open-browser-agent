from __future__ import annotations

ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-6"
ANTHROPIC_DEFAULT_VERSION = "2023-06-01"
ANTHROPIC_DEFAULT_MAX_TOKENS = 1200

SUPPORTED_VERIFICATION_KINDS = {
    "url_contains",
    "text_contains",
    "dom_contains",
    "artifact_exists",
    "artifact_text_contains",
    "artifact_list_min_length",
}

ALLOWED_STEP_ARGS: dict[str, set[str]] = {
    "navigate": {"url"},
    "goto": {"url"},
    "click": {"selector"},
    "type": {"selector", "text"},
    "press": {"keys"},
    "wait_for": {"selector"},
    "extract": {"target"},
}

REQUIRED_STEP_ARGS: dict[str, set[str]] = {
    "navigate": {"url"},
    "goto": {"url"},
    "click": {"selector"},
    "type": {"selector", "text"},
    "press": {"keys"},
    "wait_for": {"selector"},
    "extract": {"target"},
}

ANTHROPIC_PLANNER_SYSTEM_PROMPT = (
    "You are a planner for a deterministic browser agent. "
    "Return JSON only. "
    "You may only use the step types: navigate, goto, click, type, press, wait_for, extract. "
    "Each step must contain id, type, args, expected, timeout_ms. "
    "args must be a JSON object. "
    "expected must be a JSON object; use {} if you do not need it. "
    "verification_rules must be a JSON array; use [] if unsure. "
    "Only use supported verification kinds: url_contains, text_contains, dom_contains, artifact_exists, artifact_text_contains, artifact_list_min_length. "
    "Allowed args by step type are exact: "
    "navigate/goto => {url}; "
    "click => {selector}; "
    "type => {selector, text}; "
    "press => {keys}; "
    "wait_for => {selector}; "
    "extract => {target}. "
    "For extract you must use target, never selector, attribute, artifact_name, schema, fields, or limit. "
    "Valid extract targets are either a supported logical target such as 'summary' or 'table', or an explicit CSS selector string already implied by the task. "
    "If the goal matches a known bundled task, preserve the bundled task intent and do not substitute a different topic, destination URL, or extract target. "
    "Do not turn target into a natural-language instruction. target must be a short literal value. "
    "Keep the plan short and complete. "
    "Do not emit explanations outside JSON."
)

ANTHROPIC_PLANNER_USER_PROMPT_LINES = (
    "Allowed step types: navigate, goto, click, type, press, wait_for, extract",
    "Return a JSON object with keys: task_id, verifier_hint, verification_rules, metadata, steps.",
    "verification_rules is optional and should be a list of objects with keys: kind, value, label. Use [] if unsure.",
    "expected must always be an object, never a string.",
    "Do not invent new args. Use exact args by type only.",
    "extract steps must use args.target only.",
    "args.target must be a short literal such as 'summary', 'table', or an explicit selector string. Never use a sentence as target.",
    "Prefer short plans of 3 to 6 steps.",
    "Do not browse outside the goal unnecessarily.",
)
