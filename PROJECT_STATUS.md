# Project Status

## Current Stage: Stage 8 (Application-Based Sizing) — IMPLEMENTED, defaults awaiting engineering sign-off

**Completed Stages & Features:**
- **Stage 0 (Foundation):** Project structure, FastAPI setup, SQLite & SQLAlchemy configuration, `/health` endpoint.
- **Stage 1 (Engineering Calculation Engine):** `trace.py`, `power.py`, `ratio.py`, `torque.py`, structured validation, and pytest suite.
- **Stage 2 (Component Database):** Models for Manufacturers, Motors, Gearboxes with provenance tracking, seeding with 20 real motors and gearboxes, DB tests.
- **Stage 3 (Recommendation Engine):** Deterministic algorithm in `app/engine/recommend.py` matching motor & gearbox pairs using physical math and constraints, pytest suite.
- **Stage 4 (Dashboard Interface):** Initial user interface for requirements input, recommendation cards, and layout.
- **Stage 5 (Product Information / Local Component Intelligence - Source A):** Motor, Gearbox, Manufacturer APIs, local component browser, candidate calculation traces.
- **Stage 6 (Internet Product Discovery & External Data Integration - Source B):**
  - [x] Search Provider Abstraction Layer (`SearchProvider` ABC in `app/engine/search_provider.py`)
  - [x] Real `SerpApiSearchProvider` integration using official `google-search-results` package
  - [x] Secure API key handling via `SERPAPI_KEY` environment variable (never hard-coded, git-ignored `.env`)
  - [x] Query construction engine generating targeted engineering queries from calculated requirements
  - [x] External product normalization & sanitization module (`app/engine/discover.py`)
  - [x] `DiscoveredComponent` SQLAlchemy table caching external components
  - [x] Deterministic calculation engine evaluation applied to external components with objective engineering comparison statuses (`MEETS`, `DOES_NOT_MEET`, `DATA_MISSING`)
  - [x] Optional flag `include_internet_results` on `/api/recommend` (defaults to `false` for zero regression on local workflow)
  - [x] Graceful failure handling (`INTERNET_SEARCH_NOT_CONFIGURED`, `INTERNET_SEARCH_UNAVAILABLE` statuses, local search remains functional)
  - [x] Source-based availability, pricing, datasheets, CAD indicators, and product images
  - [x] Dual-source UI presentation on Dashboard distinguishing **SOURCE A (Verified Local DB)** from **SOURCE B (Internet Discovery)**
  - [x] Automated test suite in `tests/test_discover.py` using mocked external providers (no reliance on live websites for automated tests)


- **Stage 7.1 / 7.2 (AI Requirement Parsing):** natural-language extraction of torque/RPM/voltage; Gemini / OpenAI / Mock provider architecture. AI never calculates.
- **Stage 8 (Application-Based Sizing — primary workflow):**
  - [x] Spec: `docs/STAGE_8_APPLICATION_SIZING_SPEC.md`; defaults for review: `docs/ENGINEERING_DEFAULTS_TO_REVIEW.md`
  - [x] `app/engine/sizing/`: material + part → mass; conveyor, hoist, turntable/indexer, screw axis, rack & pinion / belt axis, winding
  - [x] Duty cycle (RMS torque), versioned service-factor table, full step-by-step calculation proof with input origins
  - [x] Missing inputs → `REQUIREMENTS_INCOMPLETE` (nothing guessed); hardness recorded but not used
  - [x] `POST /api/size`; `/api/recommend` gains optional `peak_torque_nm` and `speed_tolerance_pct`
  - [x] Peak-torque checks (motor peak + gearbox rating) for Source A and Source B; unified `MEETS / DOES_NOT_MEET / DATA_INCOMPLETE` (renamed from `DATA_MISSING`)
  - [x] Fit % comparison indicator (MEETS candidates only, labelled as comparison only)
  - [x] UI: "Size My Application" is the primary tab; the torque/RPM form remains as "Advanced"
  - [x] Plain-text description pre-fills the sizing form (`app/ai/sizing_parser.py`, `POST /api/parse-sizing`; mock / Gemini / OpenAI). Every value must quote the user's own words verbatim or it is rejected; densities, friction, efficiency etc. are never supplied by the AI; the user ticks a confirmation box before calculating

- **Engineer feedback round (2026-10-15):**
  - [x] One box for any engineering question (`POST /api/ask`): motor sizing and bearing life (ISO 281, `app/engine/bearing.py`) use checked modules; other topics use a method chosen by the AI and evaluated step by step by the tool (`app/engine/method_eval.py`, `POST /api/evaluate-method`), labelled "check before use"
  - [x] Suggested values for missing inputs, from a reviewed reference list, clearly marked and listed in the result (`app/engine/sizing/suggestions.py`)
  - [x] Machines recognised by their motion, not a fixed name list; unsupported machines explained, never forced into a type
  - [x] Live on Railway (auto-deploys from `main`)

**Pending Next Stages:**
- **Engineering sign-off** of Stage 8 defaults (`app/engine/sizing/defaults.py`)
- **Stage 8.x:** sourced material library (density with citations)
- CAD + 3D Fitment Visualization; PDF reporting



