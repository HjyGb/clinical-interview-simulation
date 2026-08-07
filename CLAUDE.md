# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Clinical Interview Simulation — an LLM-powered virtual standardized patient (SP) system for dental education. Students practice clinical interviewing skills by conversing with AI patients, then receive automated dual-track assessment (diagnostic accuracy + communication skills).

**Tech Stack (planned):** Python 3.10+ backend (FastAPI), Node.js 18+ frontend (React/Vite), SQLite (dev) → PostgreSQL (prod), LLM via 阿里百炼 DashScope (OpenAI-compatible API), BGE-large-zh-v1.5 for local embeddings.

## Repository State

This is an **MVP-complete project** with full E2E functionality (login → case selection → AI interview → diagnosis submission → dual-track assessment). Key artifacts:

| File | Purpose |
|---|---|
| `docs/project-requirements-overview.md` | Full PRD — background, user personas, functional/non-functional requirements, data assets, risks, delivery plan |
| `docs/architecture-design.md` | Technical architecture design — system diagrams, data flow, DB schema, API design, Agent core design, directory structure proposal |
| `docs/assessment-evaluation-standards.md` | Assessment scoring standards — Station 4 + MAAS-Global evaluation rubrics |
| `docs/persona-style-system-design.md` | Persona system design — 81 personality combinations (anxiety × verbosity × trust × language) |
| `docs/real-case-data-integration-plan-v2.md` | Real case data integration plan — translation + review pipeline, data structure design |
| `docs/frontend-improvement-plan.md` | Frontend migration plan — inline style → Tailwind CSS 4 + CSS variables |
| `data/raw/medical_records.csv` | 2,124 raw dental outpatient records (1.59 MB) — source data for case library. **Not in git** (contains PHI). English clinical text with Chinese structural labels |
| `data/cases/` | 300+ structured case JSON files + 3 hand-curated MVP cases |
| `README.md` | Project README with full documentation |

## Key Design Decisions (from requirements doc)

1. **Structured field lookup > pure RAG** for fact grounding — hallucination ceiling set at <5%
2. **Dual-track assessment**: Station 4 (diagnostic) + MAAS-Global (communication)
3. **Tiered information disclosure**: patient facts split into 4 tiers, Agent only reveals Tier 1–3, Tier 4 (diagnosis/treatment) permanently hidden
4. **Chinese UI/dialogue, English clinical source data** — cross-lingual fact transfer is a known technical challenge
5. **Single-developer project** — scope discipline is critical; MVP trumps completeness

## Development Commands

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Run tests
cd backend && pytest
cd frontend && npm test
```

## Architecture Constraints

- LLM API is the **only external dependency** — single point of failure
- SQLite for dev/demo only; concurrent writes will block under load
- All LLM calls must have retry logic and temperature=0 for classification steps
- API keys via environment variables only, never hardcoded
- `medical_records.csv` must never be committed to git
