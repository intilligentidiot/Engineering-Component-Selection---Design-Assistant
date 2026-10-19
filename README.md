# Tesla Mechanical Designs — Engineering Calculation Assistant

An engineering calculation tool: an engineer describes a machine, a project or an engineering question in plain words, and the tool works out which calculations are needed, asks only for what is missing, and calculates every result itself with the full working shown.

**What it covers**

- Motor + gearbox sizing for conveyors, lifts, turntables, screw and rack & pinion axes and winders, with matching motor + gearbox combinations (verified local database + internet search)
- Whole-project calculation plans — built-in bulk belt conveyor (ISO 5048) and shredder plans; any other machine when the AI is switched on
- Bearing life (ISO 281)
- Any other engineering question: the AI chooses the method, the tool does all the arithmetic
- Units in SI, SI engineering or US customary, with full unit names; suggested values and estimate helpers for missing data

The AI never performs calculations and the tool never invents engineering data. See `docs/` for the specification and the defaults awaiting engineering review.

## Stack
- Python + FastAPI
- SQLite + SQLAlchemy
- HTML + CSS + Vanilla JS
- Pytest

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

3. Run tests:
   ```bash
   pytest
   ```

## Optional services (environment variables)

| Variable | Purpose |
| --- | --- |
| `AI_PROVIDER` | `mock` (built-in reader, default), `gemini` or `openai` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | Key for the chosen AI service |
| `SERPAPI_KEY` | Real internet product search |
