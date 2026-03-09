# open-browser-agent

A small browser-use agent with a clear `observe -> plan -> act -> verify` loop, JSON traces, and deterministic replay.

## Status

The repo now has a deterministic core: task registry, CLI, trace recorder, replay summary, action layer, observer, executor, verifier, and unit tests built around fake browser objects.
Current test status: `37 passed`, `98%` coverage on `src/open_browser_agent`.

## Install

```powershell
pip install -r requirements.txt
pip install -e .
playwright install chromium
```
## CLI

```powershell
oba --help
oba examples list
oba run "wiki summary"
oba replay traces\<trace-id>.json
```

## What Works

- task lookup and dry-run trace creation
- deterministic executor over structured steps
- fake-friendly browser abstractions for unit testing
- replay summaries from saved traces

## Next

- wire CLI to a live Playwright session
- add real example sites and verifiers
- enforce the current coverage target in CI
