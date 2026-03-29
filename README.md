# open-browser-agent

A small browser-use agent with a clear `observe -> plan -> act -> verify` loop, JSON traces, and deterministic replay.

## Status

The repo now has a working deterministic core plus a browser-backed CLI path for bundled public tasks. Current implementation includes:

- task registry with structured steps
- browser session wrapper over Playwright
- action layer, observer, executor, verifier, trace recorder, and replay summary
- deterministic public web tasks for end-to-end smoke testing
- provider-based planner interface with bundled-task and Anthropic planner support
- human-readable `oba run` summaries layered on top of replayable JSON traces
- unit coverage around the deterministic modules

## Install

### Conda

```powershell
conda create -n cua_env python=3.11 -y
conda activate cua_env
pip install -r requirements.txt
pip install -e .
python -m playwright install chromium
```

### Without Conda

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python -m playwright install chromium
```

## Planner Setup

The default planner is `task-registry`, which maps supported goals onto bundled task plans.

To enable the Anthropic planner, create a local `.env` from `.env.example` and set your real key:

```powershell
copy .env.example .env
```

Then edit `.env` locally:

```env
ANTHROPIC_API_KEY=your_real_key_here
OBA_ANTHROPIC_MODEL=claude-sonnet-4-6
```

Keep `.env` local. It is gitignored. `.env.example` is the committed template.

## CLI

```powershell
oba --help
oba examples list
oba run "wiki summary" --trace-dir traces_e2e
oba run "wiki summary" --planner anthropic --artifacts detailed --trace-dir traces_e2e
oba run "form" --trace-dir traces_e2e
oba reliability "form-fill" --runs 5 --trace-dir traces_e2e
oba plan "wiki summary" --planner anthropic
oba replay traces_e2e\<trace-id>.json
```

`oba run` prints a compact summary by default and always writes the full JSON trace. Use `--artifacts none|summary|detailed` to control how much extracted content is printed at the end of the run.

## What Works

- browser-backed execution for bundled public demo tasks
- deterministic executor over structured steps
- Anthropic planner integration for constrained step-schema generation
- pre/post observations recorded in JSON traces, including compact form-state snapshots
- rule-based verification on final page state
- per-rule verification checks recorded in trace JSON for easier failure diagnosis
- extracted artifacts captured in trace JSON and surfaced in CLI run summaries
- repeated-run reliability checks via `oba reliability`
- replay summaries from saved traces
- fake-friendly browser abstractions for unit testing

## Next

- expand the Wikipedia flow from a fixed article into a dynamic research-brief demo
- preserve stronger bundled verification when the Anthropic planner is used
- add citation-link extraction and richer result artifacts
- define the common interface for future site-specific extractors such as Best Buy
