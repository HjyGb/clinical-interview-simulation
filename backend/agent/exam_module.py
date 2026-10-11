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

# 用于判断两段之间是否"只有标点"——有任何实质字符就说明夹着别的内容
_SUBSTANTIVE = re.compile(r"[^\s，,。.；;：:、！!？?（）()“”\"'‘’～~\-—_/／]")


def normalize(text: str) -> str:
    """Fold punctuation, quotes and case so alias matching is robust."""
    return _PUNCT.sub("", text or "").lower()


def _match_candidates(haystack: str, candidates: list[tuple[str, list[str]]]) -> list[str]:
    """Return the ids whose longest matched phrase is not subsumed by another's.

    Containment rule: when one matched phrase is a substring of another, only the
    longer one counts. Without it, "缺牙区及邻牙检查" (E01) also matches E02's alias
    "邻牙检查", and the reply would splice two exams' findings together — exactly
    what the docx forbids ("把其他牙结果复制过来").

    `candidates` is [(id, [phrases…])]; used at both the exam level (id = E id) and
    the sub-item level (id = sub-item key).
    """
    hits: dict[str, str] = {}
    for candidate_id, phrases in candidates:
        best = ""
        for phrase in phrases:
            needle = normalize(phrase)
            if needle and needle in haystack and len(needle) > len(best):
                best = needle
        if best:
            hits[candidate_id] = best

    kept = {
        cid: needle for cid, needle in hits.items()
        if not any(needle != other and needle in other for other in hits.values())
    }
    return sorted(kept, key=lambda cid: -len(kept[cid]))


def match_exams(message: str, exam_data: dict | None) -> list[str]:
    """Return the E ids whose label or an alias appears in the message.

    Pure Python and deterministic: findings are only ever returned for an exam the
    student actually named.
    """
    haystack = normalize(message)
    if not haystack or not isinstance(exam_data, dict):
        return []
    exams = exam_data.get("exams") or {}
    candidates = [
        (eid, [item.get("label", "")] + list(item.get("aliases") or []))
        for eid, item in exams.items() if isinstance(item, dict)
    ]
    return _match_candidates(haystack, candidates)


def match_subitems(message: str, exam_id: str, exam_data: dict | None) -> list[str]:
    """Return the sub-item keys the message asks about, within one exam item.

    Empty list means "the student named the item but not any particular sub-item",
    which falls back to returning the whole package.
    """
    haystack = normalize(message)
    exams = (exam_data or {}).get("exams") or {}
    item = exams.get(exam_id) or {}
    subitems = item.get("subitems") or []
    if not haystack or not subitems:
        return []

    # 学生**按项名**申请整项时，整项优先，不再往下拆子项。
    # 例：EN01 E02 的项名是「36及对照牙冷测、叩诊」，本身含"冷测"，
    # 若不做这层判断，"请提供『36及对照牙冷测、叩诊』的结果"会被截胡成只返回冷测那一段。
    item_label = normalize(item.get("label", ""))
    if item_label and item_label in haystack:
        return []
    candidates = [
        (s.get("key", ""), [s.get("label", "")] + list(s.get("aliases") or []))
        for s in subitems if isinstance(s, dict) and s.get("key")
    ]
    return _match_candidates(haystack, candidates)


def _join_fragments(result: str, fragments: list[str]) -> str:
    """Join a sub-item's fragments, keeping the original punctuation between them.

    The split necessarily cut at punctuation, so the raw text between two fragments
    is usually just "；" or "，". Putting it back makes the output read normally
    ("无临床附着丧失BOP约35%" → "无临床附着丧失；BOP约35%").

    Only punctuation/whitespace may be re-inserted. If anything substantive sits
    between two fragments of the same sub-item (another sub-item's text), that gap is
    NOT copied — and a separator is used instead so the two spans don't run together.
    """
    located = sorted((result.find(f), f) for f in fragments if f)
    if not located:
        return ""

    out = located[0][1]
    for (prev_pos, prev), (cur_pos, cur) in zip(located, located[1:]):
        gap = result[prev_pos + len(prev): cur_pos]
        if not gap:
            pass                       # 两段在原文里紧挨着，什么都不用加
        elif not _SUBSTANTIVE.search(gap):
            out += gap                 # 中间只有标点：原文本来就是这个标点，照搬
        elif out and out[-1] not in "，,、；;：:":
            out += "；"                 # 中间隔着别的子项的内容，用分隔符断开
            # 若上一段自带收尾标点就不再补，否则会出现"；；"
        out += cur
    return out.rstrip("，,、；;：:")


def render_findings(exam_ids: list[str], exam_data: dict, message: str = "") -> str:
    """Render findings for the matched exams — **only the requested sub-items**.

    The docx requires this: "相关子项请求仅返回该项结果，不可返回整个 E 项
    （如仅询问冷诊，不可同时返回叩诊结果）". So when the student names a sub-item,
    only that sub-item's fragments are returned; naming no sub-item (or hitting an
    umbrella one) returns the whole package.
    """
    exams = (exam_data or {}).get("exams") or {}
    blocks: list[str] = []
    for exam_id in exam_ids:
        item = exams.get(exam_id) or {}
        label = item.get("label", exam_id)
        result = item.get("result")

        if not result or item.get("level") == "未提供":
            # 该检查项存在，但病例没有给出结果（如 MU01 E04 血常规）
            blocks.append(f"【{label}】\n{NOT_PROVIDED}")
            continue

        keys = match_subitems(message, exam_id, exam_data) if message else []
        by_key = {s.get("key"): s for s in (item.get("subitems") or [])}
        chosen = [by_key[k] for k in keys if k in by_key]

        fragments: list[str] = []
        names: list[str] = []
        for sub in chosen:
            names.append(sub.get("label", ""))
            fragments.extend(sub.get("result_fragments") or [])

        if not fragments:
            # 没点名子项，或命中的是伞形子项（问它等于问整项）
            blocks.append(f"【{label}】\n{result}")
            continue

        # 多子项命中时按各段在原文中的位置排序——按列表顺序拼是错的
        text = _join_fragments(result, fragments)
        blocks.append(f"【{label} · {'、'.join(n for n in names if n)}】\n{text}")

    return "\n\n".join(blocks)


def answer(message: str, exam_data: dict | None) -> dict:
    """Handle an exam request.

    Returns:
        {
          "matched": bool,            # 是否命中病例里已有的检查项
          "exam_ids": [str],
          "subitem_keys": [str],      # 命中的子项，形如 "E02.cold"；空 = 整包
          "content": str,             # 直接展示给学生的文本
        }
    """
    exam_ids = match_exams(message, exam_data)
    if not exam_ids:
        return {"matched": False, "exam_ids": [], "subitem_keys": [], "content": NOT_PROVIDED}

    subitem_keys = [
        f"{eid}.{key}"
        for eid in exam_ids
        for key in match_subitems(message, eid, exam_data)
    ]
    return {
        "matched": True,
        "exam_ids": exam_ids,
        "subitem_keys": subitem_keys,
        "content": render_findings(exam_ids, exam_data, message),
    }
