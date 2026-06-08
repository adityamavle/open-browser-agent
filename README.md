# open-browser-agent

`open-browser-agent` is a lightweight browser agent kernel for traceable web task execution.

It is built around a simple loop:

```text
observe -> plan -> act -> verify
```

Every run moves through structured steps, captures browser observations, verifies the result, and writes a JSON trace that can be inspected or replayed after the run.

## Utility

Browser-agent runs are much easier to trust when the plan, actions, browser state, artifacts, and verification result are visible. `open-browser-agent` keeps those pieces explicit.

Use it when you want:

- a CUA kernel that is easy to inspect and extend
- structured browser actions instead of ad hoc automation scripts
- task-specific verification rules, for example explicit success checks for each workflow
- replayable traces for debugging
- CSV and artifact output from browser workflows
- a CLI that can run, plan, replay, and repeatedly test tasks

## Capabilities

- Task registry for bundled browser workflows.
- Playwright browser session wrapper.
- Structured action API: `goto`, `click`, `type`, `press`, `wait_for`, `extract`.
- Observer that records URL, title, visible text, compact DOM summaries, form state, and optional screenshots.
- Deterministic executor over a small step schema.
- Verification rules for URLs, visible text, DOM snippets, and extracted artifacts.
- JSON trace recorder with pre/post observations around each step.
- Replay summaries from saved traces.
- Reliability runner for repeated task execution.
- Planner interface with a deterministic task-registry planner and optional Anthropic planner.
- Artifact summaries for research briefs, comparison rows, and CSV exports.

## Install
### Virtualenv

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python -m playwright install chromium
```

Create a local environment file from the template:

```bash
cp .env.example .env
```

The default task-registry planner does not require an API key. To use the Anthropic planner, open `.env` and replace the value after `ANTHROPIC_API_KEY=` with your Anthropic API key:

```env
ANTHROPIC_API_KEY=your_real_key_here
```

Keep the variable name exactly as `ANTHROPIC_API_KEY`; only replace `your_real_key_here`.

## Quickstart

List the bundled examples:

```bash
oba examples list
```

Run a deterministic task:

```bash
oba run "wiki summary" --trace-dir traces_e2e
```

Replay the generated trace:

```bash
oba replay traces_e2e/<trace-id>.json
```

Run a repeated reliability check:

```bash
oba reliability "wiki summary" --runs 3 --trace-dir traces_e2e
```

## Example Utility

The examples utility shows the task IDs and summaries that the default task-registry planner can run without an LLM:

```bash
oba examples list
```

Example output shape:

```text
form-fill: Fill and submit a public sandbox form.
table-scrape: Scrape a public HTML table and output JSON.
wikipedia-search-press: Search Wikipedia by typing a query and pressing Enter.
wikipedia-summary: Extract a public Wikipedia summary and cited links.
bestbuy-laptop-comparison: Compare two fixture-backed Best Buy laptop product pages and export a CSV-ready artifact.
```

You can pass either a task ID or a supported alias/prompt to `oba run`:

```bash
oba run "form-fill" --trace-dir traces_e2e
oba run "table" --trace-dir traces_e2e
oba run "wiki summary" --trace-dir traces_e2e
oba run "Compare Best Buy laptops by price, display size, RAM, and storage and export to csv" --trace-dir traces_e2e
```

## Bundled Workflows

### Form Fill

Runs a public sandbox form workflow, fills known fields, submits the page, and verifies the submitted values appear in the result.

```bash
oba run "form" --trace-dir traces_e2e
```

### Table Scrape

Opens a public HTML table demo and extracts table text through the structured action API.

```bash
oba run "table-scrape" --trace-dir traces_e2e
```

### Wikipedia Summary

Navigates to a Wikipedia article, extracts the article summary and citation links, and emits a research brief artifact.

```bash
oba run "wiki summary" --trace-dir traces_e2e --artifacts summary
```

Dynamic Wikipedia prompts are also supported for direct article-style summary requests:

```bash
oba run "summarize Grace Hopper from Wikipedia" --trace-dir traces_e2e
oba run "extract the filmography section for Leonardo DiCaprio from Wikipedia" --trace-dir traces_e2e
```

### Best Buy Comparison

Runs a product-comparison workflow that extracts product facts, normalizes comparison rows, prints a CSV preview, and writes CSV exports.

```bash
oba run "Compare Best Buy laptops by price, display size, RAM, and storage and export to csv" --trace-dir traces_e2e --artifacts summary
```

You can also opt into live Best Buy search-result comparison by including `live` in the goal:

```bash
oba run "Compare live Best Buy top 5 gaming monitors by display size, refresh rate, resolution, and model name and export to csv" --trace-dir traces_e2e --artifacts summary
```

## CLI Reference

### `oba run`

Run a goal or bundled example task.

```bash
oba run <goal-or-task> [--planner task-registry|anthropic] [--trace-dir traces] [--artifacts none|summary|detailed]
```

Examples:

```bash
oba run "wiki summary" --trace-dir traces_e2e
oba run "wiki summary" --planner anthropic --artifacts detailed --trace-dir traces_e2e
oba run "Compare Best Buy laptops by price, display size, RAM, and storage and export to csv" --trace-dir traces_e2e
```

### `oba plan`

Generate and print structured steps without running the browser.

```bash
oba plan "wiki summary"
oba plan "wiki summary" --planner anthropic
```

### `oba replay`

Read a saved JSON trace and print a replay summary.

```bash
oba replay traces_e2e/<trace-id>.json
```

### `oba reliability`

Run the same task repeatedly and report pass/fail reliability, failure reasons, duration, and action coverage.

```bash
oba reliability "form-fill" --runs 5 --trace-dir traces_e2e
oba reliability "wiki summary" --runs 3 --trace-dir traces_e2e --stop-on-failure
```

### `oba eval`

Run the bundled evaluation loop for one task or all tasks.

```bash
oba eval --runs 3 --trace-dir traces_e2e
oba eval "wiki summary" --runs 3 --trace-dir traces_e2e
```

### `oba examples list`

Print the bundled example tasks.

```bash
oba examples list
```

## Traces And Artifacts

Every `oba run` writes a JSON trace to the selected trace directory.

The trace captures:

- run metadata
- goal and task ID
- generated steps
- action events
- pre/post observations
- action results and errors
- extracted artifacts
- verification checks
- final success or failure reason

Artifacts may include:

- `extracts`: raw values from `extract` steps
- `extract_sequence`: ordered extract events with page context
- `research_brief`: normalized Wikipedia summary output
- `comparison`: normalized comparison rows and CSV metadata

CSV comparison exports are written under:

```text
artifacts/comparisons/
```

## Planner Setup

The default planner is `task-registry`. It maps supported goals onto bundled deterministic plans and does not require an API key.

The `.env.example` file includes the Anthropic planner settings:

```env
ANTHROPIC_API_KEY=your_real_key_here
OBA_ANTHROPIC_MODEL=claude-sonnet-4-6
OBA_ANTHROPIC_BASE_URL=https://api.anthropic.com/v1/messages
OBA_ANTHROPIC_VERSION=2023-06-01
OBA_ANTHROPIC_MAX_TOKENS=1200
```

In your local `.env`, keep `ANTHROPIC_API_KEY` as the variable name and put your real key in place of `your_real_key_here`.

Run with:

```bash
oba plan "wiki summary" --planner anthropic
oba run "wiki summary" --planner anthropic --trace-dir traces_e2e
```

Keep `.env` local. It is gitignored.

## Architecture

The codebase is split into a few small modules:

- `browser.py`: Playwright lifecycle and page creation.
- `actions.py`: structured browser action API.
- `observer.py`: URL, title, visible text, DOM summary, form state, screenshot paths.
- `executor.py`: step dispatcher and execution loop.
- `planner.py`: task-registry and Anthropic planner providers.
- `verifier.py`: explicit success rules.
- `trace.py`: JSON trace writing.
- `replay.py`: trace replay summaries.
- `comparison.py`: comparison intent parsing and optional row synthesis.
- `tasks/registry.py`: bundled task specs and dynamic task matching.

## Development

Run tests:

```bash
source .venv/bin/activate
pytest
```

Run coverage:

```bash
source .venv/bin/activate
pytest --cov=src/open_browser_agent
```

Before treating a workflow as complete, run the task directly and then run reliability:

```bash
oba run "wiki summary" --trace-dir traces_e2e
oba reliability "wiki summary" --runs 3 --trace-dir traces_e2e
```

## Project Direction

The project direction is to keep the kernel reliable and expand through focused vertical slices:

1. Make deterministic bundled workflows excellent.
2. Keep traces useful enough to debug failures.
3. Add site-specific extractors behind explicit interfaces.
4. Use LLM planning only when it emits the same validated step schema.
5. Preserve replayability and verification as workflows get richer.
