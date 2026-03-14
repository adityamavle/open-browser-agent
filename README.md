# open-browser-agent

A small browser-use agent with a clear `observe -> plan -> act -> verify` loop, JSON traces, and deterministic replay.

## Status

The repo now has a working deterministic core plus a browser-backed CLI path for bundled public demo-site tasks. Current implementation includes:

- task registry with structured steps
- browser session wrapper over Playwright
- action layer, observer, executor, verifier, trace recorder, and replay summary
- deterministic public demo-site tasks for end-to-end smoke testing
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

## CLI

```powershell
oba --help
oba examples list
oba run "wiki summary" --trace-dir traces_e2e
oba run "form" --trace-dir traces_e2e
oba replay traces_e2e\<trace-id>.json
```

## What Works

- browser-backed execution for bundled public demo tasks
- deterministic executor over structured steps
- pre/post observations recorded in JSON traces, including compact form-state snapshots
- rule-based verification on final page state
- replay summaries from saved traces
- fake-friendly browser abstractions for unit testing

## Next

- strengthen replay into deterministic re-execution
- add more explicit per-step expected outcomes
- strengthen the real-page task set and verifiers
- enforce the current coverage target in CI
