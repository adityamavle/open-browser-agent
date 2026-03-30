# commands.md

Commands validated against the current repo state.

## Environment

```powershell
powershell -NoProfile
conda activate cua_env
cd C:\Users\adity\Computer_Use_agents
pip install -e .
```

## Planner Smoke Tests

```powershell
oba plan "wikipedia-summary" --planner anthropic
```

```powershell
oba plan "Compare endangered birds in South America by population, habitat, and conservation initiatives and export to csv" --planner anthropic
```

## Passing Run Commands

```powershell
oba run "wiki summary" --trace-dir traces_e2e --artifacts summary
```

```powershell
oba run "table-scrape" --trace-dir traces_e2e --artifacts summary
```

```powershell
oba run "form-fill" --trace-dir traces_e2e --artifacts summary
```

```powershell
oba run "extract the filmography section for Leonardo DiCaprio from Wikipedia" --planner anthropic --trace-dir traces_e2e --artifacts summary
```

```powershell
oba run "Compare endangered birds in South America by population, habitat, and conservation initiatives and export to csv" --planner anthropic --trace-dir traces_e2e --artifacts summary
```

## Reliability and Tests

```powershell
pytest -q
```
