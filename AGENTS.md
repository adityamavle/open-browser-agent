# AGENTS.md

## Setup Instructions

- Always start a fresh shell with `powershell -NoProfile` so PowerShell does not try to load profile scripts that are blocked by execution policy.
- Always run `conda activate cua_env` before any Python command, test command, package command, or Playwright-related command because each new terminal session starts fresh and requires re-activating the environment.
- Always run `pip install -e .` inside `cua_env` for this repo so `open_browser_agent` and the `oba` CLI are available without relying on `PYTHONPATH`.

## Northstar

Build a small, reliable browser-use agent that can complete tightly scoped web tasks end-to-end with a clear `observe -> plan -> act -> verify` loop, strong traces, and deterministic replay.

This repo is not trying to be a general autonomous agent at first. It is trying to become a clean agent kernel that can later swap the browser backend for other environments such as Windows desktop automation.

Success looks like:

- a new contributor can install and run one example quickly
- each task execution produces a useful trace
- replay is reliable enough to debug failures
- the codebase is small enough to understand in one sitting

## Scope

Initial target:

- browser-only agent on Playwright
- structured action API
- lightweight observation layer
- deterministic executor
- task verifier
- JSON trace and replay
- simple CLI

Out of scope for the first iteration:

- broad autonomous browsing
- multi-agent orchestration
- long-horizon planning
- desktop automation
- fine-tuning, memory systems, or complex retrieval

## Steering

Keep the project tight.

- Prefer reliability over breadth.
- Prefer deterministic execution before LLM-driven planning.
- Keep APIs small and explicit.
- Every run should emit a replayable trace.
- Every example task should have a clear verification rule.
- Before concluding a change is complete, run each bundled task individually and run `oba reliability` for each task, then inspect the resulting traces.
- Avoid adding abstractions that are not needed by the first 3-5 tasks.
- Use public sandbox or demo sites for examples whenever possible.
- Use `next.md` at the repo root as the rolling source of truth for upcoming features, implementation priorities, and newly identified pain points to address as the project evolves.

## Current Status

Implemented in the repo:

- Python package scaffold and CLI
- task registry with structured steps
- trace creation and replay summary
- deterministic executor over the action API
- observer and verifier primitives
- unit tests built around fake browser objects
- current local test baseline: `37 passed`, `98%` coverage on `src/open_browser_agent`

Current blocker:

- Windows `cua_env` exists at `C:\Users\adity\anaconda3\envs\cua_env` but does not contain its own `python.exe`, so package installation currently falls back to the global Python interpreter

Near-term implementation rule:

- keep the core importable and testable even before Playwright/browser binaries are present by using lazy imports and dependency injection at the browser boundary
- keep unit coverage above 95% for implemented deterministic modules before expanding scope

## Current Repository State

Last summarized: June 4, 2026.

The repo has moved from a scaffold into a small working browser-agent kernel with product-facing documentation, bundled tasks, traceable execution, replay, reliability tooling, and a bounded Best Buy comparison slice.

Current product shape:

- package name: `open-browser-agent`
- CLI entrypoint: `oba`
- primary user path: install locally, run bundled workflows, inspect JSON traces, replay runs, and measure reliability
- default planner: deterministic task registry
- optional planner: Anthropic planner that must emit the same validated step schema
- project stance: deterministic browser workflows first, LLM planning second

Current CLI commands:

- `oba run <goal-or-task>` runs a bundled task or supported dynamic goal
- `oba plan <goal-or-task>` prints the structured step plan without launching the browser
- `oba replay <trace.json>` prints a replay summary from a saved trace
- `oba reliability <goal-or-task>` repeats one task and reports pass/fail reliability, duration, failure reasons, and action coverage
- `oba eval [goal-or-task]` runs the bundled evaluation loop for one task or all tasks
- `oba examples list` prints registered example task IDs and summaries

Current bundled workflows:

- `form-fill`: fills and submits a public sandbox form, then verifies submitted values
- `table-scrape`: opens a public HTML table demo and extracts table content
- `wikipedia-search-press`: searches Wikipedia by typing a query and pressing Enter
- `wikipedia-summary`: extracts a Wikipedia summary plus citation links and produces a research brief artifact
- dynamic Wikipedia summary prompts, such as `summarize Grace Hopper from Wikipedia`
- dynamic Wikipedia section prompts, such as `extract the filmography section for Leonardo DiCaprio from Wikipedia`
- `bestbuy-laptop-comparison`: fixture-backed Best Buy laptop comparison that extracts search results, product facts, prices, normalized comparison rows, and CSV-ready output

Current Best Buy state:

- Best Buy work is intentionally read-only and bounded to product research
- fixture-backed product pages exist for deterministic local execution
- supported Best Buy extract targets are `bestbuy_search_results`, `bestbuy_product_facts`, and `bestbuy_price`
- comparison artifacts normalize product facts into rows with columns such as price, display size, RAM, storage, and model name
- CSV exports are written under `artifacts/comparisons/`
- cart, checkout, sign-in, store-selection, and account mutation flows remain out of scope

Current trace and artifact behavior:

- every `oba run` writes a JSON trace under the selected trace directory
- traces include run metadata, goal, task ID, steps, events, pre/post observations, action results, errors, artifacts, verification checks, and final status
- extract artifacts are stored as `extracts`
- ordered extraction context is stored as `extract_sequence`
- Wikipedia runs can produce `research_brief`
- comparison runs can produce `comparison` artifacts plus CSV paths when requested

Current code organization:

- `browser.py`: Playwright lifecycle and page creation
- `actions.py`: structured browser actions and logical extract targets
- `observer.py`: page observations for planning, verification, and traces
- `executor.py`: deterministic step dispatch
- `planner.py`: task-registry planner, Anthropic planner, step validation, and goal-specific constraints
- `verifier.py`: explicit verification rules
- `trace.py`: JSON trace writing
- `replay.py`: trace replay summaries
- `comparison.py`: comparison intent parsing and optional row synthesis
- `tasks/registry.py`: bundled tasks and dynamic task matching
- `strategies/`: fallback strategies, currently focused on Wikipedia search fallback
- `fixtures/`: deterministic local fixtures for tests and bounded demos

Current documentation state:

- `README.md` has been expanded into a product-style README
- README now includes product positioning, install instructions, quickstart, example utility docs, bundled workflow docs, CLI reference, traces/artifacts, planner setup, architecture, development commands, scope, and project direction
- `next.md` exists as the rolling source of truth for near-term work, currently centered on the Best Buy workflow

Current test state:

- last completed full local test run in this session: `117 passed`
- focused touched-module run also passed: `82 passed`
- tests cover actions, browser wrapper, CLI behavior, comparison parsing/synthesis, executor, observer, planner/tasks, registry, trace, replay, and verifier
- Playwright browser-backed end-to-end runs may require unsandboxed execution on Windows because launching Chromium can be blocked by sandbox subprocess restrictions

Known environment caveats:

- follow the setup rule to start fresh shells with `powershell -NoProfile`
- activate `cua_env` before Python, package, test, or Playwright commands
- run `pip install -e .` inside `cua_env` for this repo
- the existing `cua_env` issue may still cause Python/package commands to fall back to the global Python interpreter
- networked planner calls and Playwright browser launch may require approval outside the sandbox depending on the current environment

## Running The Package On macOS

Use these steps when setting up or running the whole package on macOS.

### 1. Clone and enter the repo

```bash
git clone https://github.com/adityamavle/open-browser-agent.git
cd open-browser-agent
```

### 2. Create and activate a Python environment

Recommended with `venv`:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Alternative with Conda:

```bash
conda create -n cua_env python=3.11 -y
conda activate cua_env
python -m pip install --upgrade pip
```

### 3. Install dependencies and the local package

```bash
pip install -r requirements.txt
pip install -e .
```

The editable install is important because it exposes the `oba` CLI while still running against the local source tree.

### 4. Install Playwright browser binaries

```bash
python -m playwright install chromium
```

If macOS prompts for browser or automation permissions, approve them. Browser-backed workflows need Chromium to launch successfully.

### 5. Verify the CLI is available

```bash
oba --help
oba examples list
```

Expected examples include:

```text
form-fill
table-scrape
wikipedia-search-press
wikipedia-summary
bestbuy-laptop-comparison
```

### 6. Run bundled workflows

Run the Wikipedia demo:

```bash
oba run "wiki summary" --trace-dir traces_e2e --artifacts summary
```

Run a dynamic Wikipedia summary:

```bash
oba run "summarize Grace Hopper from Wikipedia" --trace-dir traces_e2e --artifacts summary
```

Run the Best Buy fixture-backed comparison demo:

```bash
oba run "Compare Best Buy laptops by price, display size, RAM, and storage and export to csv" --trace-dir traces_e2e --artifacts summary
```

Run reliability for a task:

```bash
oba reliability "wiki summary" --runs 3 --trace-dir traces_e2e
```

Replay a trace:

```bash
oba replay traces_e2e/<trace-id>.json
```

### 7. Run tests

```bash
pytest
```

For coverage:

```bash
pytest --cov=src/open_browser_agent
```

### 8. Optional Anthropic planner setup

The default planner is `task-registry` and does not require API keys. To use the Anthropic planner on macOS:

```bash
cp .env.example .env
```

Edit `.env`:

```env
ANTHROPIC_API_KEY=your_real_key_here
OBA_ANTHROPIC_MODEL=claude-sonnet-4-6
```

Then run:

```bash
oba plan "wiki summary" --planner anthropic
oba run "wiki summary" --planner anthropic --trace-dir traces_e2e
```

### 9. Expected outputs

Successful runs should produce:

- terminal run summary
- JSON trace files under the selected trace directory, usually `traces_e2e/`
- extracted artifacts inside the trace JSON
- comparison CSV files under `artifacts/comparisons/` when the goal requests CSV output

### 10. Common macOS issues

- If `oba` is not found, confirm the virtual environment is active and rerun `pip install -e .`.
- If Chromium fails to launch, rerun `python -m playwright install chromium`.
- If Python is too old, install Python 3.11 and recreate the environment.
- If `pytest` is missing, install dev dependencies with `pip install -e ".[dev]"`.
- If planner API calls fail, confirm `.env` exists and contains a valid `ANTHROPIC_API_KEY`.

## Product Shape

Repo name:

- `open-browser-agent`

Core user experience:

- `pip install open-browser-agent`
- `oba run "task"`
- `oba replay trace.json`

Primary outcome:

- a small OSS package that demonstrates the full CUA stack in a controlled environment

## Architecture

Keep the system split into a few obvious modules.

### 1. Browser

Responsibility:

- own Playwright lifecycle
- create pages/contexts
- expose safe primitives to higher layers

Likely contents:

- browser launch config
- context/page setup
- navigation helpers
- timeout handling

### 2. Actions

Responsibility:

- define the action surface the executor can use

Initial action API:

- `click(selector)`
- `type(selector, text)`
- `press(keys)`
- `wait_for(selector)`
- `extract(selector | schema)`
- `goto(url)`
- `scroll(direction | amount)`

Notes:

- selectors should be explicit and logged
- actions should return structured results, not raw Playwright objects

### 3. Observer

Responsibility:

- collect the state needed for planning, verification, and debugging

Initial observation payload:

- current URL
- page title
- visible text snapshot
- simplified DOM snapshot
- optional screenshot path

Notes:

- keep the DOM snapshot compact and stable
- do not dump the full page unless needed for debugging

### 4. Executor

Responsibility:

- execute structured steps against the browser backend

Initial approach:

- deterministic executor over a small step schema
- no LLM required for first milestone

Example step types:

- navigate
- click
- type
- press
- wait_for
- extract
- verify

Notes:

- separate step execution from planning
- make failures explicit and typed

### 5. Planner

Responsibility:

- convert a goal plus observations into structured steps

Milestone order:

- milestone 1: hand-authored plans per example task
- milestone 2: optional LLM planner that outputs the same step schema

Notes:

- planner output should be inspectable JSON
- planner should not bypass the executor API

### 6. Verifier

Responsibility:

- decide whether the task succeeded

Examples:

- result table exists
- confirmation page shown
- extracted summary is non-empty
- target fields present in JSON output

Notes:

- each task must define its own success criteria
- verification should be simple and testable

### 7. Trace

Responsibility:

- record each run in a replayable, debuggable format

Trace should capture:

- run id
- timestamp
- goal
- task id
- step index
- action type
- action input
- observation summary
- URL
- selector, if any
- result
- error, if any
- screenshot path, if any
- final verification result

### 8. Replay

Responsibility:

- re-run a prior trace or step sequence deterministically where possible

Notes:

- replay should prefer stored structured steps over regenerated plans
- mismatch handling should be explicit in logs

### 9. CLI

Responsibility:

- give users one-command entry points

Initial commands:

- `oba run <goal or task>`
- `oba replay <trace.json>`
- `oba examples list`

## Data Contracts

Use simple JSON-first contracts.

### Step schema

Each step should include:

- `id`
- `type`
- `args`
- `expected`
- `timeout_ms`

### Observation schema

Each observation should include:

- `url`
- `title`
- `visible_text`
- `dom_summary`
- `form_state`
- `screenshot_path`

### Trace schema

Each trace should include:

- `meta`
- `goal`
- `task`
- `steps`
- `events`
- `verification`
- `artifacts`

## MVP Examples

Start with tasks that are easy to verify and not auth-fragile.

Recommended first 4:

1. Fill and submit a sandbox form.
2. Scrape an HTML table and output JSON.
3. Extract a Wikipedia summary and cited links.
4. Navigate a demo site and verify a result page.

Avoid at first:

- login flows
- CAPTCHAs
- account mutations
- rate-limited or anti-bot-heavy sites

## Definition Of Done

The first usable release is done when:

- package installs locally
- `oba run` can execute at least 3 example tasks
- each run emits a JSON trace
- `oba replay` can replay those traces with useful logging
- each example has an explicit verifier
- README shows install, run, replay, and examples

## Implementation Plan

Build in thin vertical slices.

### Phase 1: Repo skeleton

Deliver:

- Python package scaffold
- CLI entrypoint
- basic config
- trace directory layout

Target output:

- `oba --help` works

### Phase 2: Browser backend

Deliver:

- Playwright wrapper
- browser/page lifecycle
- navigation helper
- timeout/error handling

Target output:

- can launch a page and visit a URL from CLI

### Phase 3: Action API

Deliver:

- `goto`
- `click`
- `type`
- `press`
- `wait_for`
- `extract`

Target output:

- action calls return structured results and append to trace

### Phase 4: Observer

Deliver:

- URL/title capture
- visible text extraction
- simplified DOM summary
- optional screenshot capture

Target output:

- each executed step records a pre/post observation summary

### Phase 5: Deterministic executor

Deliver:

- step schema
- step dispatcher
- error handling and retries
- task runner for hand-authored plans

Target output:

- example tasks can run without an LLM

### Phase 6: Verifier

Deliver:

- verifier interface
- task-specific success checks
- final run status

Target output:

- each example ends with `success` or `failure` plus reason

### Phase 7: Trace and replay

Deliver:

- trace writer
- trace loader
- replay command

Target output:

- prior runs can be replayed from stored step data

### Phase 8: Example tasks

Deliver:

- 3-5 stable tasks
- task metadata
- task-specific verifiers

Target output:

- examples provide the first evaluation set

### Phase 9: Optional LLM planner

Deliver:

- planner interface
- prompt/template
- planner output validation into step schema

Target output:

- LLM can generate the same structured steps already supported by executor

## Suggested Folder Layout

```text
open-browser-agent/
  AGENTS.md
  README.md
  pyproject.toml
  src/open_browser_agent/
    cli.py
    browser.py
    actions.py
    observer.py
    executor.py
    verifier.py
    trace.py
    replay.py
    planner.py
    tasks/
      registry.py
      form_fill.py
      table_scrape.py
      wikipedia_summary.py
      demo_nav.py
    schemas/
      step.py
      observation.py
      trace.py
  examples/
  tests/
```

## One-Week Build Sequence

Use this if the goal is fast momentum.

### Day 1

- scaffold package
- wire CLI
- launch Playwright

### Day 2

- implement browser wrapper
- implement `goto`, `click`, `type`, `wait_for`

### Day 3

- add observer
- add trace writer

### Day 4

- implement deterministic executor
- add first example task

### Day 5

- add verifier layer
- add second and third example tasks

### Day 6

- implement replay
- tighten logs and error messages

### Day 7

- write README
- run through install and example flows from scratch

## Evaluation Plan

Keep evaluation simple at the start.

For each example task, define:

- input
- expected end state
- verification rule
- failure classes

Track:

- task success rate
- mean steps to completion
- retry count
- replay success rate

The examples folder is the first eval suite.

## Non-Goals For Now

Do not spend early time on:

- generalized agent memory
- prompt optimization
- multi-tab orchestration
- complex caching layers
- remote browser infra
- dashboards

## Immediate Next Step

Start with a deterministic, no-LLM milestone that proves:

- the browser backend works
- the action API is usable
- the observer records enough state
- traces are worth keeping

Once that works on 3 stable tasks, add an LLM planner that emits the same step schema rather than redesigning the system.
