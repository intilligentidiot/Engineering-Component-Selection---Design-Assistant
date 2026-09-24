# Tesla Mechanical Designs — Engineering Motor & Gearbox Selection Platform

## Master Project Brief for Google Antigravity

### 1. Project Purpose

Build an engineering decision-support platform that helps a mechanical engineer select suitable motors and gearboxes from defined engineering requirements.

The platform should eventually allow a user to:

1. Enter mechanical requirements.
2. Convert requirements into structured engineering inputs.
3. Perform transparent engineering calculations.
4. Identify suitable motor and gearbox combinations.
5. Compare multiple candidates.
6. Show why each candidate meets or fails requirements.
7. Retrieve verified product information from permitted manufacturer/distributor sources.
8. Show product images.
9. Show CAD-model availability and relevant documentation.
10. Visualize the selected motor/gearbox and physical envelope.
11. Check basic fitment constraints.
12. Show calculations and assumptions.
13. Generate an engineering selection report.
14. Eventually interact through natural language.

The long-term architecture should support additional engineering tools such as bearing selection, shaft calculations, belt/chain selection, coupling selection, fastener calculations, material selection, tolerance stack-up, and other mechanical engineering utilities.

---

## 2. Company Context

The platform is being developed for the engineering workflow of **Tesla Mechanical Designs**, a mechanical engineering/CAD design services company.

The product should feel like a professional engineering application, not a generic AI chatbot.

Target users include mechanical engineers, CAD engineers, designers, engineering managers, and technical users.

Priorities:

- Engineering transparency
- Traceability
- Correct units
- Verifiable calculations
- Real component data
- CAD/design relevance
- Clear assumptions
- Professional UI
- Practical engineering workflow

---

## 3. Core Product Philosophy

This is NOT simply:

> “Ask AI which motor should I buy.”

It should be:

> **Engineering Calculation Engine + Component Database + Recommendation Engine + Product Data + CAD/3D Visualization + AI Interface**

The deterministic engineering calculation engine is the source of truth for calculations.

AI may assist with:

- Natural-language requirement parsing
- Asking for missing information
- Explaining calculations
- Explaining why candidates passed/failed
- Summarizing manufacturer documentation
- Helping users navigate the application

AI must NOT be the authoritative source for:

- Torque calculations
- Power calculations
- Gear-ratio calculations
- Efficiency calculations
- Component specifications
- Part numbers
- Availability
- Prices
- CAD links

---

# 4. Critical Development Rule

Build in controlled stages.

Do NOT build the whole system at once.

Required sequence:

### Stage 0 — Foundation
Project architecture, structure, conventions, testing strategy.

### Stage 1 — Engineering Calculation Engine
Deterministic calculations and tests.

### Stage 2 — Component Database
Verified motor and gearbox data.

### Stage 3 — Recommendation Engine
Matching and comparison logic.

### Stage 4 — Dashboard
Complete V1 user workflow.

### Stage 5 — Product/Internet Data
Permitted external product information.

### Stage 6 — CAD + 3D
CAD availability, visualization and fitment.

### Stage 7 — AI Interface
Natural-language input and explanations.

### Stage 8 — Production
Security, audit, monitoring, scaling, reporting and additional engineering modules.

Each stage must be implemented, tested, reviewed and stabilized before the next stage.

---

# 5. Initial V1 Scope

The first usable version should focus only on:

- Motor selection
- Gearbox selection
- Engineering calculations
- Candidate matching
- Transparent calculation display
- Small verified component dataset
- Basic comparison interface

Do NOT initially implement:

- Hundreds of manufacturers
- Complex web scraping
- Full CAD automation
- Advanced FEA
- Autonomous engineering approval
- Complex user management
- Every motor type
- Every gearbox type

Start small and correct.

---

# 6. Initial User Workflow

```text
USER REQUIREMENTS
       ↓
INPUT VALIDATION
       ↓
ENGINEERING CALCULATIONS
       ↓
REQUIRED PERFORMANCE
       ↓
COMPONENT DATABASE
       ↓
MOTOR + GEARBOX MATCHING
       ↓
CANDIDATE COMPARISON
       ↓
PRODUCT INFORMATION
       ↓
CAD / 3D / FITMENT
       ↓
CALCULATION AUDIT
       ↓
ENGINEERING REPORT
```

---

# 7. User Inputs

## Basic inputs

- Required output torque
- Required output speed
- Motor voltage
- Application/use case

## Additional inputs

- Duty cycle
- Desired gear ratio
- Available space
- Maximum component dimensions
- Shaft diameter
- Shaft length
- Mounting type
- Mounting-hole constraints
- Operating environment
- Temperature requirements where applicable
- Continuous/intermittent operation

Eventually provide Basic Mode and Advanced Mode.

Do not overwhelm users with every engineering parameter initially.

---

# 8. Units

Use SI/metric units internally.

- Torque: Nm
- Speed: RPM
- Power: W or kW
- Voltage: V
- Current: A
- Dimensions: mm
- Efficiency: %
- Gear ratio: ratio

Normalize all inputs internally.

---

# 9. Engineering Calculation Engine

The calculation engine must be deterministic.

## 9.1 Mechanical output power

```text
P(kW) = T(Nm) × RPM / 9550
```

Example:

```text
Torque = 12 Nm
Speed = 60 RPM

P = (12 × 60) / 9550
P = 0.0754 kW
P ≈ 75.4 W
```

## 9.2 Gear ratio

```text
Gear Ratio = Motor RPM / Output RPM
```

Example:

```text
Motor RPM = 1200
Output RPM = 60

Gear Ratio = 1200 / 60
Gear Ratio = 20:1
```

## 9.3 Gearbox output torque

Approximate relationship:

```text
T_output = T_motor × Gear Ratio × Efficiency
```

where efficiency is expressed as a decimal.

## 9.4 Design torque

```text
T_design = T_required × Service Factor
```

The service factor must NEVER be silently assumed.

Show:

- Applied factor
- Reason
- Source/reference where applicable

## 9.5 Motor input power

Where applicable:

```text
P_motor ≥ P_output / Total Efficiency
```

The calculation chain must be visible.

---

# 10. Calculation Transparency

Every recommendation must provide a **Show Calculations** section.

Example:

### Inputs

```text
Required torque: 12 Nm
Output speed: 60 RPM
Motor speed: 1200 RPM
Gearbox efficiency: 90%
Service factor: 1.5
```

### Formula

```text
P = T × RPM / 9550
```

### Substitution

```text
P = 12 × 60 / 9550
```

### Result

```text
P = 75.4 W
```

### Assumptions

```text
Gearbox efficiency = 90%
Service factor = 1.5
```

The user must be able to reproduce the calculation.

---

# 11. Calculation Trace

Every calculation run should be capable of storing:

```json
{
  "input": {},
  "formula": "",
  "substitution": "",
  "result": {},
  "unit": "",
  "assumption": "",
  "source": ""
}
```

This enables auditability, debugging, reporting and versioning.

---

# 12. Component Database

Start with approximately **20–50 verified real components**.

Quality is more important than quantity.

## Motor fields

- Manufacturer
- Part number
- Motor type
- Rated power
- Voltage
- Rated speed
- Rated torque
- Peak torque if available
- Current if available
- Dimensions
- Shaft diameter
- Shaft length
- Mounting information
- Operating conditions where available
- Datasheet URL
- Product URL
- Image URL/source
- CAD availability
- CAD source
- Data source
- Verification date

## Gearbox fields

- Manufacturer
- Part number
- Gearbox type
- Ratio
- Rated torque
- Peak torque if available
- Efficiency
- Input speed limit
- Output speed information
- Dimensions
- Mounting information
- Shaft information
- Datasheet
- Product page
- CAD availability
- Source
- Verification date

---

# 13. Product Data Integrity

Never fabricate product information.

If unavailable:

```text
Data not available
```

If availability cannot be verified:

```text
Availability not verified
```

Do not guess.

Every external product record should ideally contain:

- Source
- Source URL
- Retrieval timestamp
- Verification status

Manufacturer documentation should generally take precedence over secondary descriptions for technical specifications.

---

# 14. Recommendation Engine

Approximate workflow:

```text
User Requirements
       ↓
Normalize Units
       ↓
Calculate Minimum Requirements
       ↓
Filter Motor Candidates
       ↓
Filter Gearbox Candidates
       ↓
Generate Motor + Gearbox Combinations
       ↓
Check Torque
       ↓
Check Speed
       ↓
Check Power
       ↓
Check Voltage
       ↓
Check Ratio
       ↓
Check Envelope
       ↓
Check Mounting/Shaft Constraints
       ↓
Return Candidates
```

Do not claim one component is “perfect”.

Return several technically matching candidates when possible.

---

# 15. Candidate Status

Use:

### Meets requirement
Available data confirms the component satisfies the requirement.

### Does not meet requirement
Available data indicates a constraint failure.

### Data missing
Insufficient verified information to determine compliance.

---

# 16. Candidate Comparison

Example:

| Requirement | Required | Candidate | Status |
|---|---:|---:|---|
| Output Torque | ≥12 Nm | 22 Nm | Meets |
| Output Speed | 60 RPM | 60 RPM | Meets |
| Voltage | 24 V | 24 V | Meets |
| Power | ≥75 W | 150 W | Meets |
| Envelope | ≤150 mm | 135 mm | Meets |

Exact fields should depend on available data.

---

# 17. Product Search

Eventually integrate permitted sources:

- Manufacturer websites
- Authorized distributors
- Manufacturer APIs
- Structured product databases
- Other legally/technically permitted sources

Do not assume a website can be scraped.

Separate:

```text
Technical specification
```

from:

```text
Current availability
```

and:

```text
Price
```

---

# 18. CAD Integration

Eventually show whether a component has a CAD model.

Potential formats:

- STEP
- IGES
- Parasolid
- STL
- DXF where applicable

Do not redistribute CAD files unless licensing/source permissions allow it.

Initially it is sufficient to provide:

```text
CAD Available
```

and:

```text
Manufacturer CAD Page
```

Later, supported CAD assets can be rendered in a browser viewer.

---

# 19. 3D Visualization

Eventually show:

```text
MOTOR
   ↓
GEARBOX
   ↓
OUTPUT SHAFT
   ↓
DRIVEN MECHANISM
```

Visualization should communicate:

- Physical size
- Orientation
- Shaft direction
- Gearbox relationship
- Approximate mounting
- Available envelope

Later features:

- Rotation
- Zoom
- Exploded view
- Measurement
- Mounting-hole visualization
- Clearance/collision checking

---

# 20. Fitment Checking

Example available space:

```text
150 × 100 × 100 mm
```

Selected component:

```text
135 × 82 × 94 mm
```

Result:

```text
Fits within defined envelope
```

If component is:

```text
168 × 82 × 94 mm
```

Result:

```text
Envelope conflict:
Length exceeds available space by 18 mm.
```

---

# 21. Dashboard Structure

Eventually include:

### A. Requirement Panel
User enters engineering requirements.

### B. Calculation Panel
Shows calculated requirements.

### C. Recommendation Panel
Shows matching candidates.

### D. Comparison Panel
Compares candidates.

### E. 3D/Fitment Panel
Shows geometry and envelope.

### F. Product Information Panel
Manufacturer, part number, specifications, datasheet, source, availability and CAD information.

### G. Calculation Audit Panel
Formulas, substitutions, results and assumptions.

### H. Report Panel
Engineering report generation/export.

---

# 22. AI Layer

Add AI only after the deterministic system works.

Example:

> I need a 24 V motor that can provide approximately 15 Nm at 50 RPM for a continuously running conveyor.

AI converts it to structured data:

```json
{
  "voltage": 24,
  "required_output_torque": 15,
  "required_output_speed": 50,
  "duty_cycle": "continuous",
  "application": "conveyor"
}
```

The user should be able to review/edit those values.

Then:

```text
Structured Input
       ↓
Engineering Engine
       ↓
Recommendation Engine
```

---

# 23. Suggested Architecture

Initial:

```text
Frontend
    ↓
Backend API
    ↓
Engineering Calculation Engine
    ↓
Recommendation Engine
    ↓
Component Database
```

Later:

```text
External Product Sources
CAD Assets
AI Service
Background Workers
Reporting Service
Authentication
Monitoring
```

---

# 24. Suggested Technology Stack

Recommended starting stack:

### Frontend
Next.js / React

### Backend
Python + FastAPI

### Engineering Engine
Python

### Database
PostgreSQL

### 3D
Three.js or another suitable browser 3D/CAD visualization library

### AI
LLM API with structured outputs/function calling

### Testing
Pytest, API tests, integration tests, frontend tests

The exact stack may be adjusted during Stage 0 if there is a strong technical reason.

---

# 25. Proposed Database Entities

Initial entities:

```text
User
Project
EngineeringRequirement
CalculationRun
Motor
Gearbox
MotorGearboxCombination
Manufacturer
ProductSource
CADAsset
AvailabilityRecord
Recommendation
Assumption
EngineeringStandardReference
```

Do not over-engineer V1.

---

# 26. Stage-by-Stage Development

## STAGE 0 — FOUNDATION

Objectives:

- Create repository/project
- Establish frontend/backend structure
- Establish database strategy
- Define coding conventions
- Define environment variables
- Define API conventions
- Define unit conventions
- Create documentation
- Create test strategy

Do NOT build product search or AI yet.

---

## STAGE 1 — ENGINEERING CALCULATION ENGINE

Build:

- Input validation
- Unit normalization
- Power calculation
- Gear ratio calculation
- Torque conversion
- Efficiency handling
- Service factor
- Design torque
- Motor power requirement
- Calculation trace

Create automated test cases.

**Completion condition:** calculation engine produces correct, repeatable results for predefined scenarios.

---

## STAGE 2 — COMPONENT DATABASE

Build:

- Manufacturer schema
- Motor schema
- Gearbox schema
- Source metadata
- Verification metadata

Populate a small verified dataset.

**Completion condition:** system retrieves structured motor and gearbox records.

---

## STAGE 3 — RECOMMENDATION ENGINE

Build:

- Requirement filtering
- Motor filtering
- Gearbox filtering
- Combination generation
- Ratio checking
- Torque checking
- Speed checking
- Power checking
- Voltage checking
- Envelope checking
- Candidate status
- Explanation/reason field

**Completion condition:** user can enter requirements and receive technically matching candidates from the internal dataset.

---

## STAGE 4 — BASIC DASHBOARD

Build:

- Requirement form
- Calculation summary
- Candidate cards
- Comparison table
- Calculation details
- Assumptions
- Product details
- Save/export

**Completion condition:** user can complete the V1 workflow without command line interaction.

---

## STAGE 5 — PRODUCT/INTERNET DATA

Add:

- External source connectors
- Product-page information
- Datasheet links
- Availability status
- Retrieval timestamps
- Data provenance
- Refresh process

**Completion condition:** dashboard shows externally verified product information without fabricating missing data.

---

## STAGE 6 — CAD + 3D

Add:

- Product image
- CAD availability
- CAD source
- 3D visualization
- Bounding box
- Envelope check
- Basic motor/gearbox arrangement

**Completion condition:** user can visually understand selected component and physical fit.

---

## STAGE 7 — AI INTERFACE

Add:

- Natural-language requirements
- Requirement extraction
- Missing-input questions
- Calculation explanation
- Candidate explanation
- Product-document summarization

**Completion condition:** natural-language requirements become editable structured engineering inputs.

---

## STAGE 8 — PRODUCTION

Add:

- Authentication
- Roles
- Project history
- Calculation versioning
- Audit logs
- Data refresh
- Error monitoring
- Security
- Backups
- API rate limits
- Automated regression tests
- Production deployment
- Engineering report generation
- Additional engineering modules

---

# 27. What NOT To Do

The development agent must NOT:

1. Build the entire project in one pass.
2. Invent engineering specifications.
3. Invent product availability.
4. Invent CAD links.
5. Hide engineering assumptions.
6. Hard-code unexplained service factors.
7. Allow AI to replace deterministic calculations.
8. Automatically claim a component is safe for an application.
9. Treat incomplete product data as verified.
10. Add unnecessary complexity before V1 works.

---

# 28. Engineering Verification Principle

For every result, the user should be able to ask:

> Where did this number come from?

The application must answer through:

- Input
- Formula
- Substitution
- Result
- Unit
- Assumption
- Data source
- Calculation version

This is a core product requirement.

---

# 29. College Demonstration Scenario

Use a realistic example such as:

```text
Required output torque: 12 Nm
Output speed: 60 RPM
Motor voltage: 24 V
Duty cycle: Continuous
Application: Conveyor
```

Demonstration:

1. Enter requirements.
2. Show calculated output power.
3. Determine required motor/gearbox performance.
4. Search the internal verified dataset.
5. Produce several candidate combinations.
6. Compare candidates.
7. Open one candidate.
8. Show product specifications.
9. Show fitment/envelope.
10. Show CAD availability.
11. Open calculation trace.
12. Generate report.

---

# 30. Long-Term Expansion

After the motor/gearbox system is stable:

- Bearing selection
- Shaft sizing
- Shaft stress
- Key/keyway calculations
- Belt-drive selection
- Chain-drive selection
- Coupling selection
- Linear actuator selection
- Pneumatic cylinder selection
- Hydraulic cylinder selection
- Fastener calculations
- Spring selection
- Material selection
- Tolerance stack-up
- Sheet-metal DFM
- Mechanical design checks

Long-term product concept:

> **Mechanical Engineering Decision-Support Platform**

---

# 31. Instructions for Google Antigravity

You are the development agent for this project.

Read this entire document before making architectural or coding decisions.

## FIRST TASK: STAGE 0 ONLY

Do NOT implement the complete platform.

First:

1. Summarize your understanding.
2. Identify minimum V1 scope.
3. Propose project/folder structure.
4. Propose database schema at high level.
5. Propose API structure.
6. Propose calculation-engine module structure.
7. Propose testing strategy.
8. Identify critical technical questions before Stage 1.
9. Create Stage 0 implementation checklist.
10. Wait for project-owner confirmation before starting Stage 1.

Do not implement internet product search, AI, CAD visualization, authentication, or production infrastructure during Stage 0 unless required for the foundation.

Development philosophy:

```text
Simple → Testable → Traceable → Extensible
```

Prefer this over:

```text
Complex → Automated → Hard to verify
```

The engineering calculation engine must remain independent from the AI layer.

---

# 32. First Response Expected From Antigravity

After reading this document, respond with exactly these planning sections:

```text
PROJECT UNDERSTANDING
V1 SCOPE
PROPOSED ARCHITECTURE
FOLDER STRUCTURE
DATABASE PLAN
API PLAN
CALCULATION ENGINE PLAN
TEST PLAN
STAGE 0 CHECKLIST
OPEN TECHNICAL QUESTIONS
```

Do not start generating hundreds of files.

Do not move to Stage 1 until the Stage 0 plan is approved.

---

# 33. Final Success Definition

The final platform should provide:

```text
ENGINEERING REQUIREMENT
        ↓
STRUCTURED INPUT
        ↓
CALCULATION
        ↓
REQUIRED PERFORMANCE
        ↓
REAL COMPONENT DATA
        ↓
MOTOR + GEARBOX MATCHING
        ↓
TRANSPARENT COMPARISON
        ↓
PRODUCT VERIFICATION
        ↓
CAD / 3D VISUALIZATION
        ↓
FITMENT CHECK
        ↓
ENGINEERING CALCULATION AUDIT
        ↓
REPORT
```

The platform should make engineering work faster while keeping the engineer in control of the final decision.
