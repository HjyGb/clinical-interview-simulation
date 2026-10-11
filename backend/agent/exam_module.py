"""Exam module — answers requests for examination findings.

A **different role** from the patient. The docx marks these tests `[检查模块]`,
and the split is not cosmetic: a real patient cannot recite "各位点探诊深度 2–3 mm",
and letting the patient voice findings would make them un-auditable. So the patient
role never reports examination findings, and this module never speaks in the
patient's voice.

Division of labour — same shape as the patient pipeline:

    fact_selector (lite)   → *is this* a request for an examination result?
    exam_module   (Python) → *which* exam? then return its `result` **verbatim**

The model decides the kind of question; Python decides the content. Findings are
copied from the case data, never generated (P1).

Design notes:
  - Findings live in a **separate** case column (`Case.exam_data`), so the exam
    module structurally cannot see patient facts and the patient agent structurally
    cannot see findings.
  - Sub-item control (docx E02: "仅询问冷诊，不可同时返回叩诊结果") is **not**
    implemented yet — the result text is not split into sub-items in the data.
    Returning the whole package verbatim is the conservative choice: paraphrasing
    a finding to fit a sub-item would violate P1. See dev-plan M6 record.
"""

import re

# 匹配不到任何检查项时的回答（对应 B10「预期：本病例未提供所请求的具体结果」）。
# 最后一句直接对应 B10「禁止：把未提供等同未患病」。
NOT_PROVIDED = (
    "本病例未提供这项检查的结果，资料里没有相关记录。\n"
    "需要说明的是：没有记录不等于结果正常，也不能据此推断未患病。"
)

# 标点、引号、空白一律剥掉再比对，这样「请提供“一般口内视诊”的文字结果」
# 与别名「一般口内视诊」能对上。
_PUNCT = re.compile(r"[\s“”\"'‘’（）()【】\[\]、，,。.；;：:！!？?～~\-—_/／]+")


def normalize(text: str) -> str:
    """Fold punctuation, quotes and case so alias matching is robust."""
    return _PUNCT.sub("", text or "").lower()


def match_exams(message: str, exam_data: dict | None) -> list[str]:
    """Return the E ids whose label or an alias appears in the message.

    Pure Python and deterministic: findings are only ever returned for an exam the
    student actually named.

    Containment rule: when one matched phrase is a substring of another, only the
    longer one counts. Without it, "缺牙区及邻牙检查" (E01) also matches E02's alias
    "邻牙检查", and the reply would splice two exams' findings together — exactly
    what the docx forbids ("把其他牙结果复制过来").
    """
    haystack = normalize(message)
    if not haystack or not isinstance(exam_data, dict):
        return []

    exams = exam_data.get("exams") or {}
    hits: dict[str, str] = {}       # exam_id → 命中的最长别名（归一化后）
    for exam_id, item in exams.items():
        if not isinstance(item, dict):
            continue
        candidates = [item.get("label", "")] + list(item.get("aliases") or [])
        best = ""
        for candidate in candidates:
            needle = normalize(candidate)
            if needle and needle in haystack and len(needle) > len(best):
                best = needle
        if best:
            hits[exam_id] = best

    # 丢掉"命中串是别人命中串的子串"的那些（更笼统的匹配）
    kept = {
        exam_id: needle for exam_id, needle in hits.items()
        if not any(needle != other and needle in other for other in hits.values())
    }
    return sorted(kept, key=lambda eid: -len(kept[eid]))


def render_findings(exam_ids: list[str], exam_data: dict) -> str:
    """Render the findings for the matched exams, verbatim from the case data."""
    exams = (exam_data or {}).get("exams") or {}
    blocks: list[str] = []
    for exam_id in exam_ids:
        item = exams.get(exam_id) or {}
        label = item.get("label", exam_id)
        result = item.get("result")
        if not result or item.get("level") == "未提供":
            # 该检查项存在，但病例没有给出结果（如 MU01 E04 血常规）
            blocks.append(f"【{label}】\n{NOT_PROVIDED}")
        else:
            blocks.append(f"【{label}】\n{result}")
    return "\n\n".join(blocks)


def answer(message: str, exam_data: dict | None) -> dict:
    """Handle an exam request.

    Returns:
        {
          "matched": bool,          # 是否命中病例里已有的检查项
          "exam_ids": [str],
          "content": str,           # 直接展示给学生的文本
        }
    """
    exam_ids = match_exams(message, exam_data)
    if not exam_ids:
        return {"matched": False, "exam_ids": [], "content": NOT_PROVIDED}
    return {
        "matched": True,
        "exam_ids": exam_ids,
        "content": render_findings(exam_ids, exam_data),
    }
