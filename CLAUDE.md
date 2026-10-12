# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Clinical Interview Simulation — an LLM-powered virtual standardized patient (SP) system for dental education. Students practice clinical interviewing by conversing with AI patients, then receive automated dual-track assessment (diagnostic accuracy + communication skills).

**Tech stack:** Python 3.10+ / FastAPI backend, React 18 + Vite + TypeScript + Tailwind CSS 4 + Zustand frontend, SQLite (dev) → PostgreSQL (prod), LLM via 阿里百炼 DashScope (OpenAI-compatible API, `openai` SDK), JWT auth.

**Where things stand (2026-10-11):** the **patient-simulation core is built and verified** — patient roleplay, a separate exam module, and a data schema with sub-item trimming. **The assessment/evaluation code is stale and currently incompatible with the new case data** (see Known Defects). Details: [docs/architecture-current.md](docs/architecture-current.md).

## Repository State

- `backend/data/app.db` holds **2 users / 5 cases** (`EN01` `PE01` `PR01` `MU01` `SU01`), all `schema_version: 2.2`.
- The 5 cases also have scoring data on disk — `<case>.answer.json` (hidden D/DD/T/G reference answer) and `<case>.rubric.json` (R01–R14 anchors + critical errors) — **extracted but not yet in the DB**. See [docs/scoring-system-design.md](docs/scoring-system-design.md).
- **`data/` is gitignored** (protects `medical_records.csv`'s PHI). The 5 sliced cases and the test data therefore exist **only on the owner's machine**.
- Directory convention: `data/cases/` = **final data only**; `data/staging/` = regenerable intermediates; `data/old/` = superseded; `data/tests/` = specs, review tables, reports; `data/raw/` = the hospital docx.
- **There is no test suite** in the pytest/vitest sense (`pytest` and `npm test` both pass while running nothing). Verification lives in the four scripts listed under Testing below.

Key docs:

| File | Purpose |
|---|---|
| `docs/architecture-current.md` | **Current-state entry point** — roles, data flow, prompts, SSE, known gaps |
| `docs/patient-simulation-dev-plan.md` | Construction record M1–M7 (patient sim) + S1 (scoring data) — per-phase changes and "actual vs expected" |
| `docs/scoring-system-design.md` | **Scoring design** — R01–R14 framework, why LLM judges anchors but code scores, data-extraction plan |
| `docs/scoring-dev-plan.md` | **Scoring construction record** — S1–P3 done, P4–P7 pending; the assessment module's own plan (kept separate from the patient-sim one) |
| `docs/case-data-schema.md` | **Case data template v2.2** — field tables, validation rules V1–V7 |
| `docs/data-requirements.md` | Why the data has the shape it does (four-level label hierarchy) |
| `docs/case-data-structure.md` | The hospital docx's own numbering system (H/P/E/D/R/B/S/K/V) |
| `docs/positioning-and-principles.md` | P1–P5: faithfulness over cleverness, engine/content separation |
| `docs/model-selection.md` | Model roles, current picks, production-scale answer |
| `docs/patient-roleplay-architecture.md` | **Design rationale** (why this architecture) — implemented; §2 is historical |
| `docs/project-requirements-overview.md` | Original PRD |
| `old_docs/` | Archived: pre-implementation architecture design, agent redesign proposal, old roadmap, scoring standards, persona, frontend plan |

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

# Seed DB (also from backend/ — see the CWD note below)
cd backend
python ../scripts/seed_db.py             # test001/123456 + teacher001/123456, loads data/cases/*.patient.json + *.exam.json
```

### Configuration gotchas

- `.env` lives at the **repo root** and is loaded by absolute path (`backend/app/config.py`), so it is found regardless of CWD.
- **Models (verified working 2026-10-11): `LLM_MODEL_PRO=qwen-plus`, `LLM_MODEL_LITE=qwen-turbo`** — both non-reasoning. `deepseek-v3.1` (the previous `pro`) was **removed from DashScope**; `/models` now lists only the `deepseek-v4*` line.
- **Reasoning ("thinking") models break the pipeline — verify before switching.** `agent/llm_client.py` reads only `message.content`, ignores `reasoning_content`, and never checks `finish_reason`. A reasoning model burns its budget on reasoning first: on a `max_tokens=2048` prompt, `deepseek-v4.1-flash` returned `reasoning_tokens=2048, text_tokens=0, content='', finish_reason='length'`. Detect the class via `usage.completion_tokens_details.reasoning_tokens` (>0 ⇒ reasoning). Known reasoning models: `deepseek-v4.1-flash`, `deepseek-v4-pro-0813`, `qwen3.7-flash-2026-07-15`, `qwen3.5-flash/plus`. Known non-reasoning: `qwen-turbo`, `qwen-plus`, `qwen-max`, `qwen-flash`, `qwen-long`.
- **DashScope error codes are not interchangeable.** `Arrearage` (**400**, account in arrears) blocks **every** model regardless of quota — check the 费用与成本 page, not the model console. `AllocationQuota.FreeTierOnly` (**403**) means one model row's free quota is spent and the account is in stop-at-quota mode. `model_not_found` (**404**) means the model id no longer exists. Free quota is granted **per model row**, and expiry silently switches to pay-as-you-go unless "用完即停" is enabled.
- `DATABASE_URL=sqlite:///./data/app.db` is **CWD-relative**. Run everything from `backend/` or you will silently create a second empty `data/app.db` at the repo root. **Scripts that import `app` must `os.chdir(ROOT / "backend")` first** — the test scripts do.
- **No Alembic.** Tables are created by `Base.metadata.create_all` on startup, which creates missing tables but never alters existing ones. **After changing a model, delete `backend/data/app.db` and re-run `seed_db.py`.**
- Prompt templates are `.txt` files lazily cached in module-level globals. Editing a `.txt` needs a **server restart** — `--reload` only watches `.py`.
- Prompt templates are rendered with `str.format()`, so any literal brace must be escaped as `{{` / `}}`. A typo'd brace raises at generation time, not import time.

## Architecture

Full current-state description: [docs/architecture-current.md](docs/architecture-current.md). The essentials:

### Three roles, three data sets

| Role | Code | Model |
|---|---|---|
| **Patient** | `agent/patient_agent.py` | pro (generate) + lite (select) |
| **Exam** | `agent/exam_module.py` | **pure Python, no LLM** |
| ~~Evaluator~~ | `agent/evaluator_agent.py` | pro — **stale, see Known Defects** |

### Patient pipeline — 3 steps, not the old 4

`patient_agent.process_message()` yields SSE events:

1. **`fact_selector.select_facts()`** — LLM (lite, `temperature=0`). Returns `{question_type, asked_facts[], reason}`. `question_type ∈ open | targeted | unknown | meta | exam | error`. Yields an `intent` event.
2. **Exam branch** — if `question_type == "exam"`, hand off to `exam_module` and return.
3. **`disclosure.gate()`** — **pure Python**. Turns `asked_facts` into this turn's `allowed_facts`, records the trace. `open` expands to H01–H04; `unknown`/`meta`/`error` allow nothing.
4. **`response_generator.generate_response()`** — LLM (pro, `temperature=0.3`, streaming).

The old post-hoc fact verifier is **gone**: it ran after tokens were streamed, so it could only log, never retract. The real defences are the data boundary plus the gate.

**To change what the patient may say**, edit the case JSON — not the code. The system prompt carries the patient's whole persona; per-turn trimming happens in `disclosure.py`.

### Exam module — two-level matching, pure Python

`exam_module.answer()`:
1. **Item level** — match the message against each E item's `label` + `aliases`. Containment rule: when one matched phrase is a substring of another, only the longer wins (otherwise "缺牙区及邻牙检查" also matches E02's alias "邻牙检查" and splices two exams together). **Whole-item precedence**: if the item's `label` appears in the message, return the whole `result` and skip sub-item resolution.
2. **Sub-item level** — return only the matched sub-items' `result_fragments`. The docx requires this ("相关子项请求仅返回该项结果，不可返回整个 E 项").
3. No match → `NOT_PROVIDED`, which explicitly says missing ≠ normal.

### Scoring module — `backend/scoring/`

`R01–R14` scoring, replacing the deleted self-made dual-track (Station 4 + MAAS). The hospital's own framework:
14 items × 0–2 = 28 raw points, **no pass mark, weights undecided**. Full design: [docs/scoring-system-design.md](docs/scoring-system-design.md).

**The split that matters** — LLM judges anchors, code does arithmetic:

| | Items | How |
|---|---|---|
| **Pure Python** | R01–R04 | Read the disclosure trace (`Message.disclosed`) and exam-request trace — the patient/exam modules already recorded the evidence |
| **LLM** | R05–R14 | Judge against the item anchor + the shared 1/0 anchors, but **must quote evidence**; a score with no quote is zeroed |

- `scoring/sub_anchors.py` — R01–R04 get one sub-anchor per reference ID; R05–R14 are *not* split (a holistic criterion)
- `scoring/aggregate.py` — all sub-anchors met → 2, partial → 1, none → 0; `enforce_evidence` downgrades unsupported hits; `NE/NA/SKIPPED_SAFETY` are *not* 0 (see `report_ceiling`)
- `scoring/deterministic.py` — R01–R04 judging. **R04's required exams are exactly the case's `level == "关键"` E items** (verified item by item)
- `scoring/llm_judge.py` — R05–R14, one item per call. `ANSWER_FIELDS` is the single authority for the 5-field answer sheet; the frontend form must match it
- `scoring/evidence.py` — `quote_is_from`: **the quote must actually come from where that item is supposed to look** (report items → the report, dialogue items → the dialogue). Caught the model sourcing report items from the conversation
- `scoring/safety.py` — critical errors as a **separate channel**, never summed in. `requires_review` is true for hits *and* for un-checked errors (a failed check is not "safe")
- `scoring/runner.py` — assembles the report: raw total + two views, **no composite score**

**Scoring only ever reads `Case.answer_key` / `Case.scoring_rubric`.** It never touches the patient slice, and the patient pipeline never touches the answer key (proven by `verify_scoring_isolation.py`).

### Data boundary is physical, not prompt-enforced

| Data | Where | Who reads it |
|---|---|---|
| `identity` / `opening` / `facts` / `psychology` | `Case.data` | patient only |
| `exams` (label/level/aliases/result/subitems) | `Case.exam_data` | exam module only |
| `D/DD/T/G` reference answer | `Case.answer_key` | **scoring chain only** |
| `R01–R14` anchors + critical errors | `Case.scoring_rubric` | **scoring chain only** |

> The diagnosis is back in the DB (as `answer_key`) since the scoring module landed. The patient
> pipeline still only ever receives `case["data"]` — proven by `scripts/verify_scoring_isolation.py`.

### SSE contract

`POST /api/v1/sessions/{id}/messages` returns `text/event-stream`. Events: `intent`, `token` (many), `exam`, `done`, `limit_warning`, `error`. The frontend parses these by hand in `apiPostSSE` (`frontend/src/api/client.ts`), so adding an event type means touching the backend `yield`, that parser, **and** `interviewStore.ts`.

### Rounds, memory, and the disclosure trace

- **A round = one student message.** `current_round` counts student rows, not all rows — exam results add a third row type and broke the old `message_count // 2`.
- `max_rounds = 25` (the hospital's S01 script has 13 steps; 12 did not fit).
- **The patient's memory is a window**: `MAX_HISTORY_MSGS = 60` messages × 500 chars ≈ 29 turns. **It must stay ≥ 2 × max_rounds + 1** — raising `max_rounds` without raising this makes the patient silently forget the opening. The code logs a WARNING when the window is exceeded.
- `Message.disclosed` records what each reply gave away: `["H01","P02"]` for patient replies, `["E02.cold"]` for exam replies. `already_disclosed` (fed to the patient) **filters to `^[HP]\d{2}$`** so exam keys never leak into the patient's prompt.

### Prompt inventory

`agent/prompts/patient/system_base.txt` (stable persona + 8 behaviour rules) · `response_generator.txt` (per-turn) · `fact_selector.txt` (selection) · `prompts/exam/subitem_splitter.txt` (build-time only) · `prompts/evaluator/*.txt` (stale).

## Data pipeline

```
data/raw/Oral_Agent_SP_Development_Cases30_v2.docx   (hospital source, 30 cases)
  → scripts/extract_exam_items.py     → data/staging/<case>.exam.new.json  (+ a report of missing sub-item labels)
  → scripts/build_exam_v2.py          → data/cases/<case>.exam.json        (validated, sub-items resolved)
  → scripts/seed_db.py                → cases rows (data + exam_data columns)

scripts/extract_behavior_tests.py     → data/tests/behavior_tests.json     (B1/B2 tests from the docx)

# Scoring data (S1, 2026-10-12) — extract → verify → promote; never hand-copied, never paraphrased
scripts/extract_answer_key.py  → data/staging/<case>.answer.new.json  (+ data/tests/answer_key_gaps.md)
scripts/extract_rubric.py      → data/staging/<case>.rubric.new.json  (+ data/scoring/rubric_common.json)
scripts/verify_scoring_data.py → data/cases/<case>.{answer,rubric}.json  (only if A1–A7 pass)
```

**`verify_scoring_data.py` is the safety net for the scoring data**: it proves each rule A1–A7,
including **A7 — every anchor/reference-answer string must be a verbatim substring of the docx**
(medical content may only be transcribed, never rewritten). A case that fails is **not promoted**;
a silent paraphrase would otherwise land as a plausible-looking rubric.

**`build_exam_v2.py` is the safety net for sub-item splitting**: an LLM proposes which sentence of an exam result belongs to which sub-item, then the script proves it — V1 every fragment is a verbatim substring of `result`, V2 the fragments cover `result` completely with no overlap, V3 the sub-item name traces to an alias. Failures retry with feedback, then fall back to returning the whole item — **never silently accept a bad split**.

`clean_data_v2.py` / `enrich_cases.py` are the **legacy** pipeline for the old English CSV (PHI, never committed). They are not used by the current case set.

## Testing

Four standalone scripts, run from the repo root (they `chdir` to `backend/` themselves):

| Script | What it proves | Last result |
|---|---|---|
| `scripts/spike_fact_selector.py` | Fact-ID accuracy vs the docx's own `依据` | 135/135 |
| `scripts/run_behavior_tests.py` | B01–B12 through the real HTTP API, 3 runs each | 165/165 |
| `scripts/run_exam_subitem_tests.py` | Sub-item trimming (pure Python) | 18/18 |
| `scripts/verify_exam_coverage.py` | Exam module against the requirement, item by item | all pass |
| `scripts/verify_scoring_isolation.py` | **The answer key can't reach the patient or the student** (LLM stubbed, no real calls) | 5/5 checks, I1–I5 |
| `scripts/run_scoring_deterministic_tests.py` | Sub-anchor decomposition, aggregation, R01–R04 (pure Python) | 76/76 |
| `scripts/run_scoring_llm_tests.py` | R05–R14 LLM judging — discrimination (good vs empty), evidence enforcement, safety channel | 8/8 (EN01/MU01/SU01) |
| `scripts/run_scoring_report.py` | **Prints a full R14 report for human review** (not an assertion) | EN01/MU01 good/empty artefacts in `data/tests/` |

B06 is excluded from ID scoring: its `依据` means "the whole fact base must not be contradicted", not "these are the facts being asked about".

**B09/B10 cannot catch sub-item bugs** — they request a *whole* item, so trimming good or bad both pass. That is why `run_exam_subitem_tests.py` exists.

## Known Defects

1. ~~**The evaluator is incompatible with the current case data.**~~ **Fixed (P6, 2026-10-12):** the stale dual-track evaluator was deleted and replaced by the R01–R14 chain (`backend/scoring/`), which scores against `Case.answer_key` + `Case.scoring_rubric`. See [docs/scoring-system-design.md](docs/scoring-system-design.md).
2. ~~**Evaluator failures render as a real 0 分.**~~ **Fixed (P6, 2026-10-12):** a failed scoring call returns `NE` (unscorable, reported separately) and the scoring chain as a whole raises instead of persisting a plausible-looking 0. `report_ceiling` reports the achievable maximum alongside the raw total, so NE/NA can't be misread as lost marks.
3. **Sub-item names/attribution are `derived`** (we supplied them; the hospital left most groups unnamed). Review tables: `data/tests/exam_split_review_*.md`. If the hospital disagrees, their answer wins — the data keeps the original `result` and a `source` marker so it can be replaced.
4. **Minor patient-side residues**: the selector occasionally records an empty disclosure trace for "probably negative" questions it answers correctly; `qwen-plus` occasionally appends an invented soft clause after a hedge.
5. **Two holes in the hospital's own docx** (found during S1 extraction, not our parsing): **SU06 has no `教师参考草案（隐藏）` block** (29 of 30 cases do) → that case cannot be scored; **EN02's block lacks the `医学依据` line**. Report in `data/tests/answer_key_gaps.md`; both need to go back to the hospital.

## Architecture Constraints

- The LLM API is the **only external dependency** — a single point of failure. All calls go through `agent/llm_client.py` (shared `AsyncOpenAI` singleton, 3 attempts with exponential backoff). `chat_stream` cannot truly retry a partial stream.
- SQLite for dev/demo only; concurrent writes block under load.
- `temperature=0` for selection; `0.3` for patient generation.
- API keys via environment variables only, never hardcoded.
- `medical_records.csv` must never be committed (`data/` and `*.db` are gitignored).
- Login **auto-registers** any unknown username as a `student` — there is no registration endpoint or invite check.
- **Failures must look like failures.** Never let an LLM fallback return something that reads as a legitimate business value; the selector uses `question_type: "error"`, deliberately outside `VALID_QUESTION_TYPES`.
