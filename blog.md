# From Browser Automation to Traceable Research Workflows

`open-browser-agent` is an ongoing open-source project to build a small, reliable computer-use kernel for the web.

The goal is not to claim general autonomous browsing. The goal is to make a few tightly scoped workflows work well end to end with:

- explicit planning
- deterministic browser actions
- observable state
- strong traces
- verification

This post covers the current state of the project and the strongest demo path so far: Wikipedia comparison research.

## What The Project Is Trying To Prove

Most browser-use demos stop at one of two extremes:

- raw browser automation with weak reasoning
- pure LLM prompting with weak grounding

This project is trying to sit in the middle:

- use the browser to gather real evidence
- keep the action space deterministic
- use an LLM only where reasoning genuinely helps

That means the system should be able to:

1. plan a bounded workflow from a natural-language goal
2. execute it on live public pages
3. capture enough evidence for debugging and verification
4. produce a user-facing artifact, not just a trace file

## Use Case 1: Wikipedia Research Brief

The first Wikipedia use case is a research brief flow.

Example:

```powershell
oba run "summarize Grace Hopper from Wikipedia" --planner anthropic --trace-dir traces_e2e --artifacts detailed
```

What happens:

- the planner resolves the article
- the browser opens the page
- the executor extracts summary and citation-related evidence
- the run emits a `research_brief` artifact
- the trace preserves the full action and observation history

This is intentionally simple, but it proves the full kernel:

- real page
- structured planning
- deterministic execution
- artifact-aware verification

## Use Case 2: Wikipedia Comparison Research

The stronger demo is comparison research across multiple Wikipedia pages.

Example:

```powershell
oba run "Compare endangered birds in South America by population, habitat, and conservation initiatives and export to csv" --planner anthropic --trace-dir traces_e2e --artifacts summary
```

What happens:

1. Claude plans a bounded comparison workflow.
2. OBA visits multiple relevant Wikipedia pages.
3. It extracts raw evidence such as:
   - summary
   - selected sections
4. The runtime groups the evidence per entity.
5. A second Claude pass rewrites raw evidence into concise CSV-ready rows.
6. OBA writes the final comparison sheet and preserves the raw evidence in trace artifacts.

This second pass matters. Without it, comparison cells become long copied article chunks. With it, the output starts to look like a real research product rather than a dump of scraped text.

## End-To-End Architecture

The current demo follows a compact end-to-end architecture.

1. Planning
- a natural-language goal is converted into a bounded structured plan
- the plan stays within the existing browser step schema

2. Browser execution
- OBA visits the selected live pages
- it runs deterministic actions such as:
  - `goto`
  - `wait_for`
  - `extract`

3. Observation and trace
- every run records:
  - planned steps
  - action events
  - extracted artifacts
  - verification results

4. Evidence grouping
- extracted values are grouped per entity/page
- raw evidence is preserved for debugging and replay

5. Output shaping
- the final comparison rows are normalized into concise table-ready values
- when requested, those rows are written to CSV

6. Verification
- the run checks that the expected artifact exists and that the comparison rows were actually produced

This is the main design idea behind the project:
- keep browser actions deterministic
- keep outputs inspectable
- add reasoning where it improves the final result

## Example Output Shape

For the endangered-birds comparison, the final output now looks like:

- `population`
- `habitat`
- `conservation initiatives`

And the values are synthesized into concise forms such as:

- `Approximately 350-400 individuals in the wild; critically endangered`
- `Caatinga of northeastern Brazil`
- `Captive breeding, reserve expansion, nest monitoring`

That is much better than writing raw section dumps directly into CSV.

## Current Limitations

The project is still ongoing, and there are clear gaps.

Some Wikipedia sections are still noisy.
Reference-heavy pages can contaminate extracted section content before the LLM reprocessing layer cleans it up.

Verification for comparison tasks is still relatively shallow.
The current checks are enough to prove the pipeline runs, but not enough to fully guarantee semantic quality.

The system is also still not a general open-ended agent by default. Outside of bundled or supported workflows, users must explicitly opt into LLM planning.

## What Comes Next

The current Wikipedia comparison path is strong enough to demo, but the broader direction is toward more complex web-use tasks that require actions plus feedback from the environment.

That means moving beyond “visit and extract” into workflows such as:

- validation-heavy forms
- dynamic controls
- filtered/sorted interactive pages
- tasks where the next action depends on what the page just changed to

This is the next important step. Extraction demos prove grounding, but interactive workflows prove real computer use.

## Conclusion

The current version of `open-browser-agent` sits between a browser script and a broader autonomous agent.

It currently provides:

- deterministic browser actions
- constrained planning
- useful traces
- explicit verification
- LLM post-processing where representation quality matters

The Wikipedia brief and Wikipedia comparison demos are the clearest proof points today.

The project is still open and evolving, and the next step is clear: more complex web tasks where actions cause state changes and the agent must read the environment and adapt.
