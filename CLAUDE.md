# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Clinical Interview Simulation — an LLM-powered virtual standardized patient (SP) system for dental education. Students practice clinical interviewing by conversing with AI patients, then receive automated dual-track assessment (diagnostic accuracy + communication skills).

**Tech stack:** Python 3.10+ / FastAPI backend, React 18 + Vite + TypeScript + Tailwind CSS 4 + Zustand frontend, SQLite (dev) → PostgreSQL (prod), LLM via 阿里百炼 DashScope (OpenAI-compatible API, `openai` SDK), JWT auth.

## Repository State

MVP-complete E2E flow: login → case selection → AI interview (SSE streaming) → diagnosis submission → dual-track assessment → history replay.

**`data/` is empty in the working tree and gitignored** (untracked in commit `3b30ce9`). 600 of the case files still exist in history:

```bash
git checkout HEAD~1 -- data/cases   # restores 599 case_*.json + mvp_cases.json
```

Without this, `scripts/seed_db.py` cannot find `data/cases/mvp_cases.json`, the seeded DB has **0 cases**, and the case list page is empty. `backend/data/app.db` currently holds 1 user and 0 cases.

This command **stages** the restored files, so a later `git commit` would re-add 600 case files the owner deliberately untracked. Prefer `git checkout HEAD~1 -- data/cases && git reset -- data/cases` to restore the working tree without staging, and check `git status` before any commit.

`data/cases/intermediate/` is **not** recoverable from git (never tracked), and `data/raw/medical_records.csv` was never committed at all (PHI). Rebuilding the full enriched case set therefore means re-running the whole pipeline from the CSV, which is only present on the owner's machine.

**There is no test suite.** `backend/tests/` contains only `__init__.py`; there is no `pytest.ini`/`conftest.py`, and `frontend/src` has no `*.test.*` files. `pytest` and `npm test` both succeed while running nothing. Do not describe test coverage as existing.

Key docs:

| File | Purpose |
|---|---|
| `docs/patient-simulation-roadmap.md` | **Current phase entry point** — project state, the new 30-case docx data structure, data processing, step-by-step roadmap |
| `docs/patient-simulation-dev-plan.md` | **Construction plan (M1–M5)** — per-phase file changes, self/you test split, and "actual vs expected" records per phase |
| `docs/model-selection.md` | Model roles (generation/selection/evaluation), current pick, production scale answer |
| `docs/positioning-and-principles.md` | 5 principles (P1–P5) — faithfulness over cleverness, engine/content separation |
| `docs/project-requirements-overview.md` | Full PRD — personas, functional/non-functional requirements, data assets, risks |
| `docs/architecture-design.md` | Technical architecture — system diagrams, data flow, DB schema, API design, Agent core design |
| `old_docs/` | Archived (deferred/superseded): assessment standards, data-schema decoupling, frontend plan, persona, old data pipeline, meeting prep |
| `README.md` | Project README (Chinese). Note: its path claims are stale — prompts live in `backend/agent/prompts/`, not `backend/prompts/`. |

## Development Commands

**Run the backend from `backend/`.** `app` and `agent` are two sibling top-level packages that import each other (`agent/llm_client.py` does `from app.config import settings`; `app/services/session_service.py` does `from agent.patient_agent import ...`), so `backend/` must be the working directory / on `sys.path`.

```bash
# Backend (from backend/)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000   # Swagger at /docs, health at /health

# Frontend (from frontend/)
cd frontend
npm install
npm run dev          # :5173, proxies /api → :8000 (see vite.config.ts)
npm run build        # tsc && vite build
npm test             # vitest — no test files exist yet

# Seed DB (also from backend/ — see the CWD note below)
cd backend
python ../scripts/seed_db.py             # test001/123456 + teacher001/123456, loads MVP + enriched cases

# Environment sanity check (Python version, venv, deps, API key, raw data, SQLite write)
python scripts/check_env.py
```

The title-based dedupe in `seed_db.py` means re-running is safe; it also only imports cases whose `status == "published"`.

### Configuration gotchas

- `.env` lives at the **repo root** and is loaded by absolute path (`backend/app/config.py`), so it is found regardless of CWD.
- `.env` sets `LLM_MODEL_PRO` / `LLM_MODEL_LITE`, overriding the `qwen-plus`/`qwen-turbo` defaults in `config.py`. These are two different model tiers: `pro` for generation/evaluation, `lite` for classification/verification.
- **Model choice interacts badly with reasoning ("thinking") models — verify before switching.** `agent/llm_client.py` only reads `message.content`, ignoring `reasoning_content`, and nothing checks `finish_reason`. A reasoning model spends its token budget on reasoning first: on the evaluator prompt (`max_tokens=2048`) `deepseek-v4.1-flash` returned `reasoning_tokens=2048, text_tokens=0, content='', finish_reason='length'`, so `json.loads("")` raised `Expecting value: line 1 column 1 (char 0)` and `evaluator_agent` fell back to **0/100 on both tracks with no error shown to the student** — `AssessmentPage.tsx` computes the composite score without checking the `error` field, so a total evaluation failure renders as a legitimate 0 分. Detect the class by inspecting `usage.completion_tokens_details.reasoning_tokens` (>0 ⇒ reasoning model). Verified 2026-09-25: `deepseek-v4.1-flash`, `deepseek-v4-pro-0813`, `qwen3.7-flash-2026-07-15` are reasoning models; `deepseek-v3.2`, `deepseek-v3.1`, `deepseek-v3`, `qwen-plus`, `qwen-turbo` are not.
- DashScope free quota is granted **per model row**, independently. A bare alias and its dated snapshot are separate rows with separate quotas — `qwen3.7-flash` was exhausted while `qwen3.7-flash-2026-07-15` still worked. `403 AllocationQuota.FreeTierOnly` means that specific model row's free quota is gone while the account is in free-tier-only mode; it is not an invalid-key error (a bad key returns 401). Disabling that mode (百炼控制台) frees the rows that were blocked; some stay blocked regardless.
- **Verified working pair (2026-09-25): `LLM_MODEL_PRO=deepseek-v3.1`, `LLM_MODEL_LITE=qwen-turbo`** — both non-reasoning, both available, full 4-step pipeline plus dual-track evaluator confirmed error-free end to end. Avoid reasoning models for the `pro` tier: the evaluator fails *intermittently* (one track scored 30/100 while the other returned 0/100 with `Unterminated string` in the same run), and streaming time-to-first-token degrades from ~0.25s to ~2.5s, which students feel as silence after every question.
- `DATABASE_URL=sqlite:///./data/app.db` is **CWD-relative** (verified: the resolved URL is identical from both directories, so SQLAlchemy expands it at connect time against the CWD). Running from `backend/` uses `backend/data/app.db` — the real DB, currently 1 user / 0 cases. Running `uvicorn` or `seed_db.py` from the repo root instead creates a **second, empty** `data/app.db` at the root, and the app will look seeded-but-empty. Keep the CWD at `backend/` for every backend command.
- **No Alembic.** Tables are created by `Base.metadata.create_all` on startup, which creates missing tables but never alters existing ones. After changing a model, delete `backend/data/app.db` and re-run `seed_db.py`.
- Prompt templates are `.txt` files lazily cached in module-level globals (`RESPONSE_PROMPT`, `INTENT_CLASSIFIER_PROMPT`, …). Editing a `.txt` needs a **server restart** — `--reload` only watches `.py`.
- Prompt templates are rendered with `str.format()` and contain literal JSON examples, so any literal brace must be escaped as `{{` / `}}`. Placeholders in use: `{gender}`, `{age_range}`, `{retrieved_facts}`, `{persona_style}`, `{student_question}`, `{conversation_history}`, `{generated_response}`, plus the evaluator's `{true_diagnosis}` / `{true_treatment_plan}` / `{student_*}` fields. A typo'd or unescaped brace raises at generation time, not at import time.

## Architecture

### Layering

```
frontend/src/{pages,components,stores,api}   React + Zustand + fetch/SSE wrapper
        ↓ /api/v1 (JWT Bearer)
backend/app/api/         4 routers: auth, cases, sessions, assessments
backend/app/services/    orchestration; session_service calls the Agent, assessment_service calls the Evaluator
backend/app/{models,schemas,middleware}/  SQLAlchemy models, Pydantic I/O, JWT dependency
        ↓
backend/agent/           LLM core — no DB access, takes case_data dicts
        ↓ OpenAI-compatible API
阿里百炼 DashScope
```

Services are module-level **functions**, not classes. `deps`: routers get a `Session` via `get_db()` and the JWT payload via `get_current_user` (a FastAPI dependency, not ASGI middleware despite the directory name). User id is `int(current_user["sub"])`; every session/assessment route calls `_verify_ownership` (404 if missing, 403 if not the owner).

### Patient Agent pipeline (`backend/agent/`)

`patient_agent.process_message()` runs 4 steps and yields SSE events as it goes:

1. **`intent_classifier.classify_intent()`** — LLM (lite, `temperature=0`). Returns `{intent, tier, confidence}`; on JSON parse failure falls back to `chief_complaint_inquiry`/tier 1. Yields an `intent` event.
2. **`info_retriever.retrieve()`** — **pure Python, no LLM**. Maps intent → field paths (`INTENT_FIELD_MAP`) then filters by tier (`TIER_ALLOWED_SECTIONS`). This is the anti-hallucination mechanism: facts come from exact dict lookups, never from the model.
3. **`response_generator.generate_response()`** — LLM (pro, `temperature=0.3`, streaming). Turns the retrieved facts into colloquial Chinese, styled by the persona fragment.
4. **`fact_verifier.verify()`** — LLM (lite, `temperature=0`) comparing the finished response against the facts. Runs **after** tokens have already been streamed, so violations are logged, not retracted; it also fails open (`{"pass": True}`) on any exception or parse error.

**To make a new fact retrievable** you must edit `INTENT_FIELD_MAP` (which intents can see it) *and* `TIER_ALLOWED_SECTIONS` (at which tier) in `backend/agent/info_retriever.py`. Field labels sent to the prompt are derived from the dotted path (`present_illness.onset` → `present_illness → onset`); a path whose top-level section isn't in the allowed tier set is silently dropped.

### Tiered disclosure (Tier 4 = diagnosis/treatment)

Enforced in two independent places — change one and the other still holds:

- `case_service._strip_tier4()` removes top-level `diagnosis` / `treatment_plan` keys for the student-facing API (`get_case`). Internal callers use `get_case_full()`, which deliberately returns them.
- `info_retriever.TIER_ALLOWED_SECTIONS[4] = set()` plus the empty field lists for `diagnosis_guess` / `treatment_inquiry` — the Agent gets no facts for Tier 4 questions.

The Agent never sees a stripped case, so Tier 4 discipline for the *dialogue* rests on the retriever plus the prompt's "answer 不清楚 when you have no facts" rule.

### Evaluator (`backend/agent/evaluator_agent.py`)

`evaluate()` runs `evaluate_diagnostic` (Station 4) and `evaluate_communication` (MAAS-Global) concurrently with `asyncio.gather` (pro model, `temperature=0`); neither can fail the other. Both return `{total_score, max_score, dimensions[]}` and degrade to a zero-score dict with an `error` field. `_normalize_dimensions()` backfills missing `missed_items` / `suggestions` arrays before persisting.

`POST /api/v1/sessions/{id}/assessment` is **synchronous** — it blocks through both LLM calls and returns the stored result. Re-submitting returns the existing assessment unchanged (no re-evaluation).

### SSE contract

`POST /api/v1/sessions/{id}/messages` returns `text/event-stream`, produced by `session_service.add_student_message()`. Event names: `intent`, `token` (many), `done`, `error`, `limit_warning`. The frontend parses these by hand in `apiPostSSE` (`frontend/src/api/client.ts`), so adding an event type means touching both the backend `yield` and that parser, plus `interviewStore.ts` for state.

`interviewStore.appendToken` accumulates tokens into a synthetic message with `id: -1`; that sentinel is how the UI knows it's still streaming.

### Round accounting

Round number is **derived, not stored**: `current_round = message_count // 2 + 1`, because each round is one student message plus one patient message. The opening statement is stored as a patient message with `round_num=0`. Any new message row (a system message, a retry) shifts every subsequent round number and the `max_rounds=12` limit check.

### Case data shape

`Case.data` is a JSON blob (SQLAlchemy JSON column); there is no per-field schema. The Agent expects root-level sections:

```
basic_info{gender, age_range, visit_type}, chief_complaint,
present_illness{onset, duration, character, aggravating_factors, relieving_factors, radiation},
past_history{dental, medical, allergy, medication},
oral_examination{inspection, percussion, palpation, mobility, thermal, periodontal},
auxiliary_examination{xray, cbct},
diagnosis{primary, …}, treatment_plan{definitive, …}     # Tier 4
```

Two shapes have existed historically — MVP cases put `chief_complaint` at the root, auto-generated ones nested it under `basic_info`. `case_service._safe_get()` handles both for list/detail views, but note that `patient_agent.get_opening_statement()` reads `basic_info.chief_complaint` while `info_retriever` reads root-level `chief_complaint`; a case carrying only one of the two will have a correct opening but a blank answer to "哪里不舒服".

## Data pipeline (`scripts/`)

Run in order; each stage feeds the next and the outputs are gitignored:

```
data/raw/medical_records.csv  (2,124 English clinical records, PHI — never commit)
  → clean_data_v2.py    → data/cases/intermediate/case_XXX.json  (English, quality-filtered)
  → enrich_cases.py     → data/cases/case_XXX.json               (Chinese, unified schema)
  → seed_db.py          → Cases rows (published only)
```

`enrich_cases.py` is a two-step LLM process per case: a Translation Agent (English → Chinese structured JSON) then a Review Agent cross-checking against the English source. `clean_data_v1` is superseded. **Cross-lingual fact transfer is the known weak point** — the source facts are English while all dialogue, prompts, and UI are Chinese.

**Restoring `data/cases` does not give you 599 usable cases — it gives you 3.** `seed_db.py` skips any case whose `status != "published"`, and *every one* of the 599 `case_XXX.json` files in history lacks a `status` key entirely (verified against `HEAD~1`), so they all fall through the `"draft"` default and are silently skipped; the script only reports them as `skipped_count`. `enrich_cases.py:467` does write `status: "published"`, so those 599 are stale outputs from before that line existed. Only `mvp_cases.json` carries `status: "published"` — 3 hand-curated cases, and their `data` is the shape the Agent actually expects (`basic_info`, `chief_complaint`, `present_illness`, `past_history`, `oral_examination`, `auxiliary_examination`, `diagnosis`, `treatment_plan`). To load the wider set, backfill `status` into those files or relax the filter in `seed_db.py` — but check the schema first, since untracked-from-birth enrichment output may not match the retriever's field paths.

## Key Design Decisions

1. **Structured field lookup > pure RAG** for fact grounding — hallucination ceiling target <5%.
2. **Dual-track assessment**: Station 4 (diagnostic) + MAAS-Global (communication), run in parallel, averaged for the composite score.
3. **Tiered information disclosure**: facts split into 4 tiers; the Agent reveals 1–3, Tier 4 is permanently hidden.
4. **Chinese UI/dialogue, English clinical source data.**
5. **Single-developer project** — scope discipline matters; MVP trumps completeness. No message queue, cache layer, or microservices at this stage.

## Architecture Constraints

- The LLM API is the **only external dependency** — a single point of failure. All LLM calls go through `agent/llm_client.py`, which owns the shared `AsyncOpenAI` singleton and does exponential-backoff retries (3 attempts). `chat_stream` cannot truly retry a partial stream.
- SQLite for dev/demo only; concurrent writes block under load.
- `temperature=0` for classification and verification; `0.3` for patient generation.
- API keys via environment variables only, never hardcoded.
- `medical_records.csv` must never be committed (`data/` and `*.db` are gitignored).
- Login **auto-registers** any unknown username as a `student` with the supplied password — there is no registration endpoint or invite check.
