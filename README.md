# open-browser-agent

`open-browser-agent` is a small browser-use agent kernel for deterministic web tasks.

It is built around a simple loop:

```text
observe -> plan -> act -> verify
```

The project is intentionally narrow. It is not trying to be a general autonomous browser on day one. The goal is to provide a clean, inspectable foundation for browser automation where every task runs through structured steps, emits a JSON trace, and can be replayed or debugged after failure.

## Why This Exists

Most browser-agent demos are hard to debug because the browser state, plan, actions, and verification result are scattered across logs or hidden inside an LLM loop. `open-browser-agent` keeps those pieces explicit.

Use it when you want:

- a small Computer Use Agent kernel that is easy to read
- deterministic browser execution before broad autonomy
- structured browser actions instead of ad hoc scripts
- task-specific verification rules
- replayable traces for debugging and reliability checks
- a CLI that can run, inspect, replay, and repeatedly test example tasks

## Current Capabilities

- Task registry for bundled demo workflows.
- Playwright-backed browser session wrapper.
- Structured action API: `goto`, `click`, `type`, `press`, `wait_for`, `extract`.
- Observer that records URL, title, visible text, compact DOM summaries, form state, and optional screenshots.
- Deterministic executor over a small step schema.
- Verification rules for URLs, visible text, DOM snippets, and extracted artifacts.
- JSON trace recorder with pre/post observations around each step.
- Replay summaries from saved traces.
- Reliability runner for repeated task execution.
- Planner interface with the default task registry planner and optional Anthropic planner.
- Artifact summaries for research briefs, comparison rows, and CSV exports.

## Install

### Conda

```powershell
conda create -n cua_env python=3.11 -y
conda activate cua_env
pip install -r requirements.txt
pip install -e .
python -m playwright install chromium
```

### Virtualenv

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python -m playwright install chromium
```

## Quickstart

List the bundled examples:

```powershell
oba examples list
```

Run a deterministic task:

```powershell
oba run "wiki summary" --trace-dir traces_e2e
```

Replay the generated trace:

```powershell
oba replay traces_e2e\<trace-id>.json
```

Run a repeated reliability check:

```powershell
oba reliability "wiki summary" --runs 3 --trace-dir traces_e2e
```

## Example Utility

The examples utility shows the task IDs and summaries that the default task-registry planner can run without an LLM:

```powershell
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

```powershell
oba run "form-fill" --trace-dir traces_e2e
oba run "table" --trace-dir traces_e2e
oba run "wiki summary" --trace-dir traces_e2e
oba run "Compare Best Buy laptops by price, display size, RAM, and storage and export to csv" --trace-dir traces_e2e
```

## Bundled Workflows

### Form Fill

Runs a public sandbox form workflow, fills known fields, submits the page, and verifies the submitted values appear in the result.

```powershell
oba run "form" --trace-dir traces_e2e
```

### Table Scrape

Opens a public HTML table demo and extracts table text through the structured action API.

```powershell
oba run "table-scrape" --trace-dir traces_e2e
```

### Wikipedia Summary

Navigates to a Wikipedia article, extracts the article summary and citation links, and emits a research brief artifact.

```powershell
oba run "wiki summary" --trace-dir traces_e2e --artifacts summary
```

Dynamic Wikipedia prompts are also supported for direct article-style summary requests:

```powershell
oba run "summarize Grace Hopper from Wikipedia" --trace-dir traces_e2e
oba run "extract the filmography section for Leonardo DiCaprio from Wikipedia" --trace-dir traces_e2e
```

### Best Buy Comparison

Runs a bounded, fixture-backed product-comparison workflow. The first slice focuses on read-only product research: product facts, normalized comparison rows, and CSV export.

```powershell
oba run "Compare Best Buy laptops by price, display size, RAM, and storage and export to csv" --trace-dir traces_e2e --artifacts summary
```

This workflow is intentionally scoped to extraction and comparison. It does not add items to cart, sign in, choose stores, or enter checkout flows.

## CLI Reference

### `oba run`

Run a goal or bundled example task.

```powershell
oba run <goal-or-task> [--planner task-registry|anthropic] [--trace-dir traces] [--artifacts none|summary|detailed]
```

Examples:

```powershell
oba run "wiki summary" --trace-dir traces_e2e
oba run "wiki summary" --planner anthropic --artifacts detailed --trace-dir traces_e2e
oba run "Compare Best Buy laptops by price, display size, RAM, and storage and export to csv" --trace-dir traces_e2e
```

### `oba plan`

Generate and print structured steps without running the browser.

```powershell
oba plan "wiki summary"
oba plan "wiki summary" --planner anthropic
```

### `oba replay`

Read a saved JSON trace and print a replay summary.

```powershell
oba replay traces_e2e\<trace-id>.json
```

### `oba reliability`

Run the same task repeatedly and report pass/fail reliability, failure reasons, duration, and action coverage.

```powershell
oba reliability "form-fill" --runs 5 --trace-dir traces_e2e
oba reliability "wiki summary" --runs 3 --trace-dir traces_e2e --stop-on-failure
```

### `oba eval`

Run the bundled evaluation loop for one task or all tasks.

```powershell
oba eval --runs 3 --trace-dir traces_e2e
oba eval "wiki summary" --runs 3 --trace-dir traces_e2e
```

### `oba examples list`

Print the bundled example tasks.

```powershell
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

To enable the Anthropic planner, create a local `.env`:

```powershell
copy .env.example .env
```

Then set:

```env
ANTHROPIC_API_KEY=your_real_key_here
OBA_ANTHROPIC_MODEL=claude-sonnet-4-6
```

Run with:

```powershell
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

```powershell
conda activate cua_env
pytest
```

Run coverage:

```powershell
conda activate cua_env
pytest --cov=src/open_browser_agent
```

Before treating a workflow as complete, run the task directly and then run reliability:

```powershell
oba run "wiki summary" --trace-dir traces_e2e
oba reliability "wiki summary" --runs 3 --trace-dir traces_e2e
```

## Scope

In scope:

- browser-only automation on Playwright
- deterministic task plans
- small structured action API
- compact observations
- JSON traces
- task-specific verification
- replay and reliability tooling
- bounded demo workflows

Out of scope for the first iteration:

- broad autonomous browsing
- login flows
- CAPTCHAs
- checkout/account mutation flows
- long-horizon planning
- multi-agent orchestration
- desktop automation
- memory systems or retrieval-heavy agents

## Project Direction

The current product direction is to keep the kernel small and reliable, then expand through thin vertical slices:

1. Make deterministic bundled workflows excellent.
2. Keep traces useful enough to debug failures.
3. Add site-specific extractors behind explicit interfaces.
4. Use LLM planning only when it emits the same validated step schema.
5. Preserve replayability and verification as workflows get richer.
