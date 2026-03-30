# Architecture

`open-browser-agent` is a small browser-use kernel built around a strict loop:

- observe
- plan
- act
- verify

The project is intentionally narrow. It is not trying to be a fully general autonomous web agent yet. The current focus is on making a few real web tasks reliable, inspectable, and replayable.

## Current Shape

The runtime is split into a few explicit layers:

1. Browser
- owns Playwright session lifecycle
- exposes a single active page to higher layers
- isolates browser-launch and teardown details

2. Action API
- supports deterministic step types:
  - `goto` / `navigate`
  - `click`
  - `type`
  - `press`
  - `wait_for`
  - `extract`
- returns structured `ActionResult` objects instead of raw Playwright handles

3. Observer
- captures compact page state after actions
- current observation includes:
  - URL
  - title
  - visible text
  - compact DOM summary
  - form state
  - optional screenshot path

4. Planner
- converts a goal into the shared step schema
- currently supports:
  - deterministic task-registry planning
  - Anthropic planning through Claude Sonnet
- planner output is validated back into the same step contract regardless of provider

5. Executor
- runs validated steps through the action API
- records pre/post observations for traceability
- supports bounded fallback strategies for known workflows

6. Verifier
- evaluates task success using explicit rules
- supports page-state and artifact-based verification
- records per-rule results in trace output

7. Trace
- records:
  - run metadata
  - planned steps
  - per-step events
  - final verification
  - artifacts
- intended to support diagnosis and replay, not just logging

8. Replay
- summarizes and replays trace data deterministically where possible

## Step Contract

All planning and execution revolves around a simple shared step schema:

- `id`
- `type`
- `args`
- `expected`
- `timeout_ms`

This keeps the LLM planner constrained. It can suggest steps, but it cannot bypass the executor.

## Artifacts

Runs can emit structured artifacts alongside the trace.

Current important artifact types:

- `extracts`
- `extract_sequence`
- `research_brief`
- `comparison`

The comparison artifact is especially important for the current Wikipedia demo. It now distinguishes between:

- `raw_rows`: directly extracted evidence
- `rows`: user-facing rows after LLM reprocessing

## LLM Usage

The project now uses LLMs in two separate places:

1. Planning
- Claude can plan bounded multi-page workflows
- planner output is validated into the shared deterministic step schema

2. Reprocessing
- some tasks need more than raw extraction
- a flag named `isLLMReProcessingRequired` marks those cases
- the current `wikipedia-comparison` flow uses a Claude-based row synthesizer to rewrite raw section text into concise CSV-ready cells

This separation matters:

- the browser and executor remain deterministic
- the LLM is used where reasoning adds value
- raw evidence stays preserved in trace artifacts

## Current Strong Demo

The strongest current demo is Wikipedia comparison.

Example flow:

1. User gives a comparison query.
2. Planner chooses a bounded set of Wikipedia pages and extraction targets.
3. Browser visits each page and extracts raw evidence.
4. Runtime groups evidence into comparison rows.
5. Claude reprocesses those rows into concise, column-appropriate values.
6. OBA prints a comparison summary and optionally writes CSV.
7. Trace preserves both the raw and synthesized outputs.

## Why This Architecture Works

- deterministic core keeps behavior inspectable
- planner and reprocessor are provider-swappable layers
- traces preserve debugging value
- artifacts provide user-facing outputs
- bounded tasks are realistic enough to demo while still testable

## Open Work

The architecture is functional, but still evolving.

Important remaining work:

- stronger comparison-specific verification beyond row-count/file checks
- cleaner section extraction on messy Wikipedia pages
- generalized post-processing for non-Wikipedia tasks
- explicit site adapters for domains like `bestbuy.com`
- more browser-native workflows where actions trigger feedback and the next step depends on updated state

## Near-Term Direction

The project is still open and actively evolving.

The next major shift is from extraction-heavy demos toward more complex web-use tasks that require:

- actions
- environment feedback
- adaptation
- bounded retries

Examples:

- validation-heavy form workflows
- dynamic controls
- richer site-specific extractors
- comparison workflows across more live sites
