## Current Focus

Best Buy demo workflow.

The Wikipedia demo is in a usable state. The next vertical slice should prove that the agent can handle a bounded ecommerce research workflow on a real public site without expanding the action surface unnecessarily.

## Goal

Build a deterministic Best Buy product-comparison demo that:

- navigates to Best Buy search or product pages
- extracts a compact set of product facts
- compares multiple products on requested attributes
- exports the result to CSV
- records enough trace data to debug selector drift and extraction failures

This should stay scoped to read-only research. Do not add cart, account, checkout, or auth flows.

## First Demo Shape

Target user flow:

`oba run "Compare Best Buy laptops by price, display size, RAM, and storage and export to csv" --planner anthropic --trace-dir traces_e2e --artifacts summary`

Expected output:

- comparison artifact with normalized rows
- CSV written to `artifacts/comparisons/`
- trace containing extracted raw page artifacts and final synthesized rows

## Implementation Order

### 1. Lock the demo contract

- add a dedicated Best Buy comparison task shape instead of relying on Wikipedia-specific extraction assumptions
- define the minimum supported attributes for v1:
  - price
  - screen size / display size
  - RAM / memory
  - storage
  - model name
- define the verification contract:
  - at least 2 comparison rows
  - CSV path exists when output mode is csv
  - each row includes `entity_name` and `article_url` or product URL

### 2. Add Best Buy extraction primitives

- extend `extract` targets with bounded Best Buy-specific extractors
- prefer structured extraction from product detail sections over broad visible-text parsing
- keep extractor outputs JSON-first and compact

Initial extractor targets:

- `bestbuy_search_results`
- `bestbuy_product_facts`
- `bestbuy_price`

### 3. Add planner grounding for Best Buy

- add planner guidance that recognizes Best Buy comparison goals
- constrain plans so they stay inside:
  - Best Buy search results
  - product detail pages
  - extraction steps only
- avoid unconstrained browsing or generic ecommerce navigation

### 4. Add artifact normalization

- convert raw Best Buy extracts into normalized comparison rows
- map site-specific labels into stable output columns
- preserve both raw and normalized artifacts in the trace

### 5. Add bundled reliability task(s)

- one fixed, deterministic Best Buy demo query for repeated runs
- one dynamic planner-driven comparison prompt
- run `oba reliability` for each before calling the slice done

## Engineering Notes

- keep the existing comparison artifact pipeline, but generalize naming away from Wikipedia assumptions where needed
- introduce site-specific extractor code behind an obvious interface instead of mixing Best Buy selectors into generic CLI logic
- preserve lazy browser imports and fake-friendly testing
- if Best Buy becomes unstable, keep a fallback public ecommerce demo site available rather than broadening the architecture

## Definition Of Done

- a Best Buy comparison prompt produces a non-empty comparison artifact
- CSV export works end-to-end
- traces clearly show raw extraction inputs and normalized output rows
- unit coverage stays above the current threshold for touched deterministic modules
- the new workflow passes repeated reliability runs individually

## Immediate Next Task

Implement the bounded extractor interface for Best Buy product pages, then wire a fixed task through planner, artifact normalization, and verification before attempting a broader dynamic comparison prompt.
