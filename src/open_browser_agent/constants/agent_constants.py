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
    "artifact_text_min_length",
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
    "navigate_extracted_result": {"source_target", "index", "url_field"},
}

REQUIRED_STEP_ARGS: dict[str, set[str]] = {
    "navigate": {"url"},
    "goto": {"url"},
    "click": {"selector"},
    "type": {"selector", "text"},
    "press": {"keys"},
    "wait_for": {"selector"},
    "extract": {"target"},
    "navigate_extracted_result": {"source_target", "index"},
}

ANTHROPIC_PLANNER_SYSTEM_PROMPT = (
    "You are a planner for a deterministic browser agent. "
    "Return JSON only. "
    "You may only use the step types: navigate, goto, click, type, press, wait_for, extract, navigate_extracted_result. "
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
    "extract => {target}; "
    "navigate_extracted_result => {source_target, index, url_field}. "
    "For extract you must use target, never selector, attribute, artifact_name, schema, fields, or limit. "
    "Valid extract targets are either a supported logical target such as 'summary' or 'table', or an explicit CSS selector string already implied by the task. "
    "If the goal matches a known bundled task, preserve the bundled task intent and do not substitute a different topic, destination URL, or extract target. "
    "Do not turn target into a natural-language instruction. target must be a short literal value. "
    "Keep the plan short and complete. "
    "Do not emit explanations outside JSON."
)

ANTHROPIC_PLANNER_USER_PROMPT_LINES = (
    "Allowed step types: navigate, goto, click, type, press, wait_for, extract, navigate_extracted_result",
    "Return a JSON object with keys: task_id, verifier_hint, verification_rules, metadata, steps.",
    "verification_rules is optional and should be a list of objects with keys: kind, value, label. Use [] if unsure.",
    "expected must always be an object, never a string.",
    "Do not invent new args. Use exact args by type only.",
    "extract steps must use args.target only.",
    "args.target must be a short literal such as 'summary', 'table', or an explicit selector string. Never use a sentence as target.",
    "Prefer short plans of 3 to 6 steps.",
    "Do not browse outside the goal unnecessarily.",
)

COMPARISON_SYNTHESIS_SYSTEM_PROMPT = (
    "You rewrite raw extracted web evidence into compact comparison rows. "
    "Return JSON only. "
    "Do not add commentary outside JSON. "
    "Preserve entity_name and article_url exactly. "
    "For each requested comparison column, produce a concise value suitable for a CSV cell. "
    "Prefer short factual phrases over copied paragraphs. "
    "Do not invent facts not grounded in the provided evidence. "
    "If evidence is weak, keep the cell brief and conservative."
)

COMPARISON_SYNTHESIS_USER_PROMPT_LINES = (
    "Return a JSON object with keys: rows.",
    "rows must be a JSON array of objects.",
    "Each row must contain entity_name, article_url, and the requested comparison columns only.",
    "Keep each synthesized cell concise, ideally under 25 words.",
    "Do not include citations or long reference dumps inside the main cell values.",
)

WIKIPEDIA_PLANNER_HINTS = (
    "Wikipedia article URLs normally use the format https://en.wikipedia.org/wiki/Title_With_Underscores.",
    "When the topic is clear, prefer direct navigation to the article URL instead of searching first.",
    "If the direct article flow fails, the bounded fallback is: navigate to https://en.wikipedia.org/wiki/Main_Page, type the topic into input[name='search'], press Enter, wait_for main, then extract target='summary'.",
    "For Wikipedia summary tasks, keep extract target exactly 'summary'.",
    "For Wikipedia section tasks, valid logical extract targets include 'section_headings' and 'section:<Section Name>'.",
    "Do not invent alternative sites or search engines for Wikipedia tasks.",
)

WIKIPEDIA_COMPARISON_PLANNER_HINTS = (
    "For Wikipedia comparison tasks, prefer exactly 3 entity pages unless the user explicitly asks for more. Never exceed 5 pages.",
    "If the user explicitly names comparison columns, preserve them when feasible.",
    "If columns are underspecified, infer at most 5 topic-specific, comparison-relevant columns.",
    "Do not invent filler columns such as notes, misc, or other.",
    "Default to text comparison output unless the user explicitly asks for CSV, export, spreadsheet, or file output.",
    "For comparison tasks, prefer task_id 'wikipedia-comparison' and include metadata.output_mode plus metadata.columns when known.",
    "Only use existing Wikipedia extract targets that the runtime already supports: summary, citation_links, section_headings, and section:<Section Name>.",
    "Choose section targets that are likely to exist across the selected Wikipedia pages.",
    "Do not use extract target 'table' for Wikipedia comparison tasks. The comparison table is a synthesized output artifact, not a page-level extract target.",
    "For each selected entity page, extract summary and any section targets needed for the requested comparison columns.",
    "Keep comparison plans compact: avoid redundant expected fields, avoid citation extraction unless required, and keep the total step count as small as possible.",
)

BESTBUY_COMPARISON_PLANNER_HINTS = (
    "For Best Buy comparison tasks, stay within Best Buy search results and product detail pages only.",
    "Use the existing Best Buy extract targets that the runtime supports: bestbuy_search_results, bestbuy_product_facts, and bestbuy_price.",
    "For live Best Buy search, use navigate_extracted_result with source_target='bestbuy_search_results', index starting at 0, and url_field='href' to visit products discovered at runtime.",
    "Prefer a compact plan: open search results, extract result URLs, visit a capped number of product pages, extract product facts, and synthesize the comparison artifact after execution.",
    "Do not add cart, sign-in, shipping, store-selection, or checkout steps.",
    "For Best Buy comparison tasks, prefer task_id 'bestbuy-laptop-comparison' when the goal is a bounded laptop comparison demo.",
)
