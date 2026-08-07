#!/usr/bin/env python3
"""
LLM enrichment pipeline: translate English dental cases to Chinese + structured extraction.

Two-step process per case:
  Step A: Translation Agent — English raw → Chinese structured JSON
  Step B: Review Agent — Cross-check against English source → corrected JSON

Input:  data/cases/intermediate/case_XXX.json (from clean_data_v2.py)
Output: data/cases/case_XXX.json (unified MVP schema, Chinese)

Requires:
  pip install openai python-dotenv
  .env file with LLM_API_KEY set for DashScope
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ─── Paths ───────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INTERMEDIATE_DIR = PROJECT_ROOT / "data" / "cases" / "intermediate"
CASES_DIR = PROJECT_ROOT / "data" / "cases"
CHECKPOINT_FILE = PROJECT_ROOT / "data" / "processed" / "enrich_checkpoint.json"

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

# ─── LLM Client ───────────────────────────────────────────────────────
API_KEY = os.getenv("LLM_API_KEY", "")
BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

# Model pool: ordered list, auto-advances on quota exhaustion
# Override via CLI: --models qwen3.7-flash,qwen3.7-plus,qwen3.7-max-preview
_DEFAULT_MODEL_POOL = [
    os.getenv("LLM_MODEL_LITE", "qwen-turbo"),          # start with cheap model
    "qwen3.7-plus",                                      # fallback 1
    "qwen3.7-max-preview",                               # fallback 2
    "qwen3.7-max-2026-05-17",                            # fallback 3
]

_active_model_idx = 0
_model_pool: list[str] = []


def get_model_pool() -> list[str]:
    """Return the current model pool (set by CLI or defaults)."""
    global _model_pool
    if not _model_pool:
        _model_pool = list(_DEFAULT_MODEL_POOL)
    return _model_pool


def set_model_pool(models: list[str]) -> None:
    """Override the model pool from CLI args."""
    global _model_pool
    _model_pool = list(models)


def get_active_model() -> str:
    """Return the current active model name."""
    pool = get_model_pool()
    global _active_model_idx
    if _active_model_idx >= len(pool):
        _active_model_idx = len(pool) - 1
    return pool[_active_model_idx]


def is_quota_error(error: Exception) -> bool:
    """Detect if an error is due to quota/token exhaustion."""
    msg = str(error).lower()
    # DashScope quota patterns (order: specific → general)
    quota_keywords = [
        "freetieronly", "free tier only", "free quota",
        "allocationquota", "arrearage", "insufficient_quota",
        "quota exceeded", "quota limit", "rate limit", "budget",
        "insufficient balance", "account balance", "no available",
        "exceeded your quota", "request throttled", "too many requests",
        "quota",  # general fallback — catch any quota-related error
    ]
    for kw in quota_keywords:
        if kw in msg:
            return True
    # Also check HTTP status-like patterns
    if hasattr(error, "status_code"):
        code = getattr(error, "status_code", 0)
        if code in (402, 429):
            return True
    if hasattr(error, "http_status"):
        code = getattr(error, "http_status", 0)
        if code in (402, 429):
            return True
    return False


def advance_model() -> bool:
    """Switch to next model in pool. Returns False if no more models available."""
    global _active_model_idx
    _active_model_idx += 1
    pool = get_model_pool()
    if _active_model_idx >= len(pool):
        return False
    return True


_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not API_KEY:
            print("ERROR: LLM_API_KEY not set in .env")
            sys.exit(1)
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _client


def llm_chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    max_retries: int = 3,
) -> str:
    """Send a chat completion with automatic model fallback on quota errors."""
    model_to_use = model or get_active_model()
    client = get_client()
    pool = get_model_pool()

    # Try each model in the remaining pool
    for model_attempt in range(len(pool) - _active_model_idx):
        model_to_use = get_active_model()

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=model_to_use,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content or ""
                return content
            except Exception as e:
                last_error = e
                if is_quota_error(e):
                    print(f"  ⚠ Quota exhausted for {model_to_use}")
                    break  # Don't retry same model on quota error
                delay = 2 ** attempt
                print(f"  LLM attempt {attempt+1}/{max_retries} failed: {e}, retry in {delay}s")
                if attempt < max_retries - 1:
                    time.sleep(delay)

        # Try next model
        if is_quota_error(last_error):
            if advance_model():
                new_model = get_active_model()
                print(f"  🔄 Switched to model: {new_model}")
                continue
            else:
                raise RuntimeError(
                    f"All models in pool exhausted. Last error: {last_error}"
                )

        # Non-quota error — re-raise
        raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_error}")

    raise RuntimeError(f"All models exhausted: {last_error}")


# ─── Prompts ──────────────────────────────────────────────────────────

TRANSLATION_SYSTEM_PROMPT = """\
你是口腔医学数据标注专家。你的任务是将英文牙科门诊记录翻译为中文，并提取关键信息填充结构化字段。

## 核心要求
1. basic_info 中的 gender/age_range/visit_type 必须使用输入中提供的值，不要修改也不得留空
2. 所有中文使用中国大陆口腔医学术语：
   - pulpitis → 牙髓炎
   - periodontitis → 牙周炎
   - caries → 龋病
   - impacted tooth → 阻生齿
   - apical periodontitis → 根尖周炎
   - gingivitis → 牙龈炎
   - percussion → 叩诊
   - probing → 探诊
   - mobility → 松动度
   - restoration → 修复
   - root canal treatment (RCT) → 根管治疗
   - extraction → 拔除
   - scaling → 洁治
   - crown → 冠修复
   - implant → 种植

3. 保留牙位标记不翻译：*14, *37, #16, 36, 47 等
4. 保留 ICD 编码
5. full_text 字段保留翻译后的完整段落原文
6. 子字段从 full_text 中提取，提取不到则留空字符串 ""
7. 不要编造原文没有的信息

## difficulty 判断标准
- beginner: 单一常见疾病，治疗方案简单明确（如单颗龋病、牙龈炎）
- intermediate: 涉及2-3颗牙或2个诊断，或需鉴别诊断（如牙髓炎+阻生齿、根尖周炎鉴别）
- advanced: 多牙位、复杂治疗计划、跨学科（如种植+牙周+修复联合治疗）

## 输出格式
只输出合法 JSON，不要输出 markdown 代码块标记，不要输出解释文字。"""


REVIEW_SYSTEM_PROMPT = """\
你是口腔医学审校专家。对照英文原文，逐项检查中文翻译和结构化提取的质量。

## 检查要点
1. 医学术语翻译是否准确
2. 症状描述是否有遗漏或扭曲（英文提到的症状中文必须有）
3. 牙位标记是否完整保留（*14, *37等不得丢失或改变）
4. ICD编码是否正确提取
5. full_text与子字段是否矛盾（子字段内容不应超出full_text范围）
6. 不要无中生有——只指出确实有问题的地方

## 输出格式
如果发现任何问题，输出修正后的完整 JSON。
如果翻译完全正确无需修改，输出原文（不做任何改动）。
只输出合法 JSON，不要输出 markdown 代码块标记，不要输出解释文字。"""


def build_translation_prompt(case: dict) -> str:
    """Build the user prompt for Step A translation."""
    raw = case["raw"]
    return f"""\
请翻译以下英文口腔门诊记录为中文结构化 JSON。

英文原文：
- 性别: {raw['gender']}
- 年龄段: {raw['age_range']}
- 主诉: {raw['chief_complaint_en']}
- 现病史: {raw['present_illness_en']}
- 既往史: {raw['past_history_en']}
- 口腔检查: {raw['oral_examination_en']}
- 诊断: {raw['diagnosis_primary_en']}
- ICD编码: {raw['icd_code']}
- 治疗方案: {raw['treatment_definitive_en']}
- 医生建议: {raw['treatment_notes_en']}

就诊类型: {case['visit_type']}
来源ID: {case['source_id']}

输出JSON（严格按此schema）:
{{
  "title": "病例标题（格式：部位+症状+诊断，如'左下后牙自发痛1天（急性牙髓炎）'）",
  "difficulty": "beginner|intermediate|advanced",
  "data": {{
    "basic_info": {{
      "gender": "{raw['gender']}",
      "age_range": "{raw['age_range']}",
      "visit_type": "{case['visit_type']}"
    }},
    "chief_complaint": "中文主诉",
    "present_illness": {{
      "full_text": "中文现病史完整原文",
      "onset": "起病时间和诱因",
      "duration": "持续时间",
      "character": "症状特征描述",
      "aggravating_factors": ["加重因素列表"],
      "relieving_factors": ["缓解因素列表"],
      "radiation": "放射痛描述或空字符串"
    }},
    "past_history": {{
      "full_text": "中文既往史完整原文"
    }},
    "oral_examination": {{
      "full_text": "中文口腔检查完整原文",
      "inspection": "视诊所见",
      "percussion": "叩诊结果",
      "palpation": "触诊结果",
      "mobility": "松动度",
      "thermal": "温度测试结果",
      "periodontal": "牙周情况"
    }},
    "auxiliary_examination": {{ "xray": "", "cbct": "" }},
    "diagnosis": {{
      "primary": "主诊断中文名",
      "secondary": [],
      "icd_code": "{raw['icd_code']}"
    }},
    "treatment_plan": {{
      "emergency": "急症处理方案或空",
      "definitive": "根治方案",
      "restoration": "修复方案或空",
      "notes": "医嘱备注或空"
    }}
  }}
}}"""


def build_review_prompt(case: dict, translation_output: str) -> str:
    """Build the user prompt for Step B review."""
    raw = case["raw"]
    return f"""\
请对照英文原文，逐项检查以下中文翻译的质量。

=== 英文原文 ===
主诉: {raw['chief_complaint_en']}
现病史: {raw['present_illness_en']}
既往史: {raw['past_history_en']}
口腔检查: {raw['oral_examination_en']}
诊断: {raw['diagnosis_primary_en']}
ICD编码: {raw['icd_code']}
治疗方案: {raw['treatment_definitive_en']}
医生建议: {raw['treatment_notes_en']}

=== 中文翻译（待审校） ===
{translation_output}

如果发现问题，输出修正后的完整JSON。如果完全正确，原样输出上述JSON。"""


# ─── JSON extraction ─────────────────────────────────────────────────

def extract_json_from_response(text: str) -> dict | None:
    """Extract a JSON object from an LLM response (may contain markdown code blocks)."""
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding the first { and last }
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ─── Field diff for quality marking ──────────────────────────────────

def count_fields_changed(original: dict, reviewed: dict, prefix: str = "") -> int:
    """Count how many leaf fields differ between two dicts."""
    changes = 0
    for key in original:
        orig_path = f"{prefix}.{key}" if prefix else key
        if key not in reviewed:
            changes += 1
            continue
        if isinstance(original[key], dict) and isinstance(reviewed[key], dict):
            changes += count_fields_changed(original[key], reviewed[key], orig_path)
        elif isinstance(original[key], list) and isinstance(reviewed[key], list):
            if json.dumps(original[key], ensure_ascii=False) != json.dumps(reviewed[key], ensure_ascii=False):
                changes += 1
        elif str(original[key]) != str(reviewed[key]):
            changes += 1
    return changes


def total_leaf_fields(d: dict, prefix: str = "") -> int:
    """Count total leaf fields in a nested dict."""
    count = 0
    for key, val in d.items():
        if isinstance(val, dict):
            count += total_leaf_fields(val, f"{prefix}.{key}")
        elif isinstance(val, list):
            count += 1  # count list as one field
        else:
            count += 1
    return count


# ─── Main pipeline ───────────────────────────────────────────────────

def enrich_case(case: dict, index: int, total: int) -> dict | None:
    """Run translation + review for a single case."""
    raw = case["raw"]
    case_label = f"[{index}/{total}] source_id={case['source_id']}: {raw['chief_complaint_en'][:50]}"
    print(f"\n{'─'*60}")
    print(f"Case {case_label}")

    # ── Step A: Translation ──
    print("  Step A: Translating...")
    translation_prompt = build_translation_prompt(case)
    try:
        translation_text = llm_chat(
            messages=[
                {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
                {"role": "user", "content": translation_prompt},
            ],
            temperature=0.0,
            max_tokens=4096,
        )
    except Exception as e:
        print(f"  ERROR (translation): {e}")
        return None

    translation_json = extract_json_from_response(translation_text)
    if translation_json is None:
        print(f"  ERROR: Could not parse translation JSON. Response preview:")
        print(f"  {translation_text[:200]}...")
        # Try saving the raw response for debugging
        return None

    # Validate required fields exist
    if "data" not in translation_json:
        print(f"  ERROR: Translation missing 'data' key")
        return None

    print(f"  Translation OK — title: {translation_json.get('title', 'N/A')[:60]}")

    # ── Step B: Review ──
    print("  Step B: Reviewing...")
    review_prompt = build_review_prompt(
        case, json.dumps(translation_json, ensure_ascii=False, indent=2)
    )
    try:
        review_text = llm_chat(
            messages=[
                {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": review_prompt},
            ],
            temperature=0.0,
            max_tokens=4096,
        )
    except Exception as e:
        print(f"  WARNING (review): {e}, using translation output as-is")
        # If review fails, still use the translation
        final_json = translation_json
        review_changes = 0
    else:
        review_json = extract_json_from_response(review_text)
        if review_json is None or "data" not in review_json:
            print(f"  WARNING: Could not parse review JSON, using translation as-is")
            final_json = translation_json
            review_changes = 0
        else:
            final_json = review_json
            # Count changes
            data_a = translation_json.get("data", {})
            data_b = review_json.get("data", {})
            total_f = max(total_leaf_fields(data_a), 1)
            changed_f = count_fields_changed(data_a, data_b)
            review_changes = changed_f
            print(f"  Review OK — {changed_f}/{total_f} fields revised")

    # ── Build final output ──
    # Add metadata not in LLM output
    final_json["department"] = case.get("department", "口腔科")
    final_json["status"] = "published"
    final_json["visit_type"] = case.get("visit_type", "首诊")

    # Ensure basic_info has visit_type (redundant but compatible)
    if "data" in final_json and "basic_info" in final_json["data"]:
        if "visit_type" not in final_json["data"]["basic_info"]:
            final_json["data"]["basic_info"]["visit_type"] = case.get("visit_type", "首诊")

    # Quality flag
    if review_changes > 0:
        change_ratio = review_changes / max(total_leaf_fields(translation_json.get("data", {})), 1)
        if change_ratio > 0.3:
            final_json["_review_flag"] = "needs_human_review"
            print(f"  ⚠ Flagged for human review (>30% fields revised: {change_ratio:.0%})")
        else:
            final_json["_review_flag"] = "auto_reviewed"
    else:
        final_json["_review_flag"] = "auto_passed"

    return final_json


def main() -> None:
    global _active_model_idx

    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Limit to first N cases (0=all)")
    ap.add_argument("--skip-review", action="store_true", help="Skip review step (faster, lower quality)")
    ap.add_argument(
        "--models",
        type=str,
        default="",
        help="Comma-separated model pool, e.g. 'qwen3.7-flash,qwen3.7-plus,qwen3.7-max-preview'",
    )
    args = ap.parse_args()

    # Configure model pool from CLI or defaults
    user_models = bool(args.models)
    if args.models:
        set_model_pool([m.strip() for m in args.models.split(",") if m.strip()])

    # ── Checkpoint recovery (before printing model info) ──
    completed_ids: set[int] = set()
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            cp = json.load(f)
            completed_ids = set(cp.get("completed_source_ids", []))
            if not user_models:
                saved_model_idx = cp.get("active_model_idx", 0)
                if saved_model_idx > _active_model_idx:
                    _active_model_idx = saved_model_idx

    pool = get_model_pool()
    active = get_active_model()

    print("=" * 60)
    print("enrich_cases: LLM Translation + Review Pipeline")
    print(f"  API:   {BASE_URL}")
    print(f"  Model pool:  {', '.join(pool)}")
    print(f"  Active:      {active}  (index {_active_model_idx})")
    print("=" * 60)

    # ── Load intermediate cases ──
    intermediate_files = sorted(INTERMEDIATE_DIR.glob("case_*.json"))
    if not intermediate_files:
        print("\nERROR: No intermediate case files found.")
        print(f"  Expected in: {INTERMEDIATE_DIR}")
        print("  Run clean_data_v2.py first.")
        sys.exit(1)

    cases = []
    for fp in intermediate_files:
        with open(fp, "r", encoding="utf-8") as f:
            cases.append(json.load(f))

    print(f"\nLoaded {len(cases)} intermediate cases.")

    if CHECKPOINT_FILE.exists():
        print(f"  Resuming: {len(completed_ids)} cases already completed")

    # ── Process each case ──
    success_count = 0
    fail_count = 0
    total = len(cases)
    limit = args.limit if args.limit > 0 else total

    for i, case in enumerate(cases[:limit], start=1):
        if case["source_id"] in completed_ids:
            print(f"\n[{i}/{total}] Skipping source_id={case['source_id']} (already done)")
            success_count += 1
            continue

        result = enrich_case(case, i, total)

        if result is None:
            fail_count += 1
            print(f"  FAILED — will retry on next run")
            continue

        # Write output: case_004.json → case_004.json
        # New IDs start from 4 (MVP cases use 1-3)
        output_index = 3 + success_count + 1
        output_path = CASES_DIR / f"case_{output_index:03d}.json"

        # Remove _review_flag before saving (internal metadata only)
        review_flag = result.pop("_review_flag", None)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"  Saved → {output_path.name} ({review_flag})")
        success_count += 1

        # Checkpoint every 5 cases (save model state too)
        if success_count % 5 == 0:
            with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                all_completed = completed_ids | {
                    cases[j]["source_id"]
                    for j in range(i)
                }
                json.dump(
                    {
                        "completed_source_ids": list(all_completed),
                        "last_index": i,
                        "active_model_idx": _active_model_idx,
                        "active_model": get_active_model(),
                    },
                    f,
                    ensure_ascii=False,
                )
            print(f"  [checkpoint saved: {len(all_completed)} completed, model={get_active_model()}]")

        # Rate limit: small delay between cases
        time.sleep(0.5)

    # ── Final report ──
    print(f"\n{'=' * 60}")
    print(f"ENRICHMENT COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Total intermediate cases:  {total}")
    print(f"  Successfully enriched:    {success_count}")
    print(f"  Failed:                   {fail_count}")
    print(f"  Model used:               {get_active_model()}")
    print(f"  Output directory:         {CASES_DIR}/")
    print(f"\n  Output files: case_004.json ~ case_{3 + success_count:03d}.json")

    if fail_count > 0:
        print(f"\n  ⚠ {fail_count} cases failed. Re-run to retry (checkpoint will skip completed).")

    # Clean up checkpoint on full success
    if fail_count == 0 and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print(f"  Checkpoint cleared.")

    print(f"\nNext step: scripts/seed_db.py")


if __name__ == "__main__":
    main()
