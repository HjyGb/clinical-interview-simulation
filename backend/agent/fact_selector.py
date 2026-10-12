"""Fact selector — maps a student utterance to the patient facts it asks about.

Replaces `intent_classifier`: instead of guessing a 9-way intent plus a tier,
the model answers two narrow questions — what kind of question is this, and
which fact IDs does it touch. Everything downstream (disclosure gating,
generation) works on those IDs, so this is the one place where a
misclassification needs to be caught by tests.

The selector sees H/P only — never D/DD/T/G/R. They are not in `case_data`.
"""

import json
import re
from pathlib import Path

from loguru import logger

from agent.llm_client import chat
from app.config import settings

FACT_SELECTOR_PROMPT: str | None = None

# `unknown` = 问的是患者本人的情况，但事实清单里没有对应条目（家族史/饮酒…）。
# 与 `meta`（问的根本不是患者的事）区分开：两者都不给事实，但患者该做的反应不同。
# `exam` = 学生要检查/化验/影像的客观结果。不由患者回答，转给检查模块（见 exam_module）。
VALID_QUESTION_TYPES = {"open", "targeted", "meta", "unknown", "exam", "explain"}

# `explain` = 学生在**向患者交代**（解释病情/计划、交代注意事项），不是在问。
# 医院 S01 第 12 步的期望依据就是 [P03]——即"学员解释完之后，患者该更新理解"。
# 没有这个类型时，这类陈述会被塞进 `meta`，患者就去回避了（实测踩过，见
# docs/simulation-quality-plan.md §1.1）。
EXPLAIN_QUESTION_TYPE = "explain"

# `unknown` = 问的是患者本人的事，但病例里根本没设定。
# 医院规则（_docx.txt:83）：这种情况**由控制器说明"模拟资料不足"**，
# 不能让患者假装记不清。见 patient_agent 的 data_gap 分支。
UNKNOWN_QUESTION_TYPE = "unknown"

# 那一句话就是控制器的说明，不是患者台词。
DATA_GAP_MESSAGE = (
    "模拟资料不足：本病例未设定这项信息。"
    "未设定不等于「没有」或「正常」，也不影响本次练习的评定。"
)

# 学员在解释时，患者要做的是"更新理解"，而不是复述事实——由门控发放 P03。
EXPLAIN_ALLOWED = ["P03"]

EXAM_QUESTION_TYPE = "exam"

# 调用失败时使用。刻意**不在** VALID_QUESTION_TYPES 里：它必须能被一眼认出，
# 不能让一次故障伪装成"模型判断成 unknown"。同类教训见 CLAUDE.md 里
# "评估器失败静默渲染成 0 分"那条缺陷。
ERROR_QUESTION_TYPE = "error"

# 开放式问诊默认放行的前四条事实（对应文档"开放式询问自然叙述 H01–H04"）
OPEN_QUESTION_DEFAULT = ["H01", "H02", "H03", "H04"]

_FALLBACK = {
    "question_type": ERROR_QUESTION_TYPE,
    "asked_facts": [],
    "reason": "selector call failed",
}


def _load_prompt() -> str:
    """Lazy-load the fact selector prompt template."""
    global FACT_SELECTOR_PROMPT
    if FACT_SELECTOR_PROMPT is None:
        prompt_path = Path(__file__).resolve().parent / "prompts" / "patient" / "fact_selector.txt"
        FACT_SELECTOR_PROMPT = prompt_path.read_text(encoding="utf-8")
    return FACT_SELECTOR_PROMPT


def build_facts_catalog(case_data: dict) -> list[dict]:
    """Flatten a case's facts + psychology into [{id, label, text}] in ID order.

    Only H/P are returned: 患者可知事实。D/DD/T/G/R 从不在 patient.json 里。
    """
    catalog: list[dict] = []
    for section in ("facts", "psychology"):
        block = case_data.get(section) or {}
        for fact_id, item in block.items():
            if isinstance(item, dict):
                catalog.append({
                    "id": fact_id,
                    "label": item.get("label", ""),
                    "text": item.get("text", ""),
                })
    return sorted(catalog, key=lambda f: f["id"])


def render_catalog(catalog: list[dict]) -> str:
    """Render the catalog for the prompt. 标签 + 原文都给——判断用的关键词在正文里。"""
    return "\n".join(
        f"{f['id']} {f['label']}：{f['text']}" if f["label"] else f"{f['id']}：{f['text']}"
        for f in catalog
    )


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


async def select_facts(
    student_message: str,
    case_data: dict,
    conversation_history: str = "",
) -> dict:
    """Decide which facts the student's message asks about.

    Args:
        student_message: The student's latest utterance.
        case_data: The case's patient data (only `facts` / `psychology` are read).
        conversation_history: Prior turns as plain text, for resolving references.

    Returns:
        {"question_type": "open"|"targeted"|"meta", "asked_facts": [str], "reason": str}
    """
    catalog = build_facts_catalog(case_data)
    valid_ids = {f["id"] for f in catalog}

    prompt = _load_prompt().format(
        facts_catalog=render_catalog(catalog),
        conversation_history=conversation_history or "（本次为会话开始，尚无历史）",
    )

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"学生这句话：{student_message}"},
    ]

    raw = ""
    try:
        raw = await chat(
            messages,
            model=settings.llm_model_lite,
            temperature=0.0,
            max_tokens=256,
        )
        result = json.loads(_strip_fences(raw))

        question_type = result.get("question_type")
        if question_type not in VALID_QUESTION_TYPES:
            logger.warning(f"[Selector] bad question_type {question_type!r}, falling back to targeted")
            question_type = "targeted"

        # 结构性校验：只接受清单里存在的 ID，重复去掉，保持稳定顺序
        asked = result.get("asked_facts") or []
        if not isinstance(asked, list):
            asked = []
        asked_facts = []
        for fact_id in asked:
            if isinstance(fact_id, str) and fact_id in valid_ids and fact_id not in asked_facts:
                asked_facts.append(fact_id)
            else:
                logger.warning(f"[Selector] dropped unknown fact id {fact_id!r}")

        # meta / unknown 都不给事实——选中任何 ID 都是模型自相矛盾，一律清空。
        # open 的 H01–H04 展开不在这里做：那是披露门控（disclosure）的职责，selector 保持"只报模型说的"。
        if question_type in ("meta", "unknown"):
            asked_facts = []
        elif question_type == "targeted" and not asked_facts:
            # targeted 按定义必须至少命中一条；模型给了空数组说明它其实想表达"对不上"。
            # 归到 unknown（患者口吻的非回答），而不是 meta（回避越权请求）。
            logger.warning(f"[Selector] targeted with no facts for {student_message[:30]!r} → unknown")
            question_type = "unknown"

        logger.debug(
            f"[Selector] {student_message[:30]!r} → {question_type} {asked_facts}"
        )
        return {
            "question_type": question_type,
            "asked_facts": asked_facts,
            "reason": str(result.get("reason", ""))[:200],
        }

    except json.JSONDecodeError as e:
        logger.error(f"[Selector] parse error for {student_message[:30]!r}: {e}, raw={raw[:200]!r}")
    except Exception as e:
        logger.error(f"[Selector] call failed for {student_message[:30]!r}: {e}")

    return dict(_FALLBACK)
