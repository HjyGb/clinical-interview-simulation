"""子锚点：把一条 R 拆成「可判定的最小单元」。

设计见 docs/scoring-system-design.md §5.1。两种拆法，取决于这条 R 由谁判：

  R01–R04  **每个参照 ID 一个子锚点**——机械可判，纯代码。
           例：R01 refs=[H01,H02] → 「引出 H01」「引出 H02」
               R04 必做项=E01/E02/E03 → 「申请 E01」「申请 E02」「申请 E03」

  R05–R14  **不强行拆分**——整条 2 分锚点就是一个判据。
           这些锚点是"解释得准不准""理由充不充分"这类整体判断，硬拆成子句
           只会把模型的语言切分错误伪装成评分结构的严谨。它们由 LLM 对照
           本例 2 分锚点 + 册前共同 1/0 锚点直接判 0/1/2（见 aggregate.direct_score）。

注意：医院给的 2 分锚点默认就是**多分句合取**（如 R01 的"部位/时间" + "发展经过"），
所以 R01–R03 按 ref 拆出来的子锚点，正好对上医院自己的分句。
"""

# 这四个由纯代码判（读披露轨迹 / 检查申请轨迹），其余由 LLM 判。
CODE_JUDGED = frozenset({"R01", "R02", "R03", "R04"})

# 子锚点类型：elicit=从患者处问出来；request=申请了某项检查；judge=整体语义判定
ELICIT, REQUEST, JUDGE = "elicit", "request", "judge"


def decompose(item: dict) -> list[dict]:
    """Return the sub-anchors of one rubric item.

    Args:
        item: a rubric item dict: {id, name, anchor, refs, evidence, judge}

    Returns:
        [{"n": int, "kind": str, "refs": list[str], "criterion": str}, …]
        A code-judged item with no refs yields [] — and [] scores 0 (see aggregate).
    """
    rid = item["id"]
    refs = list(item.get("refs") or [])

    if rid in CODE_JUDGED:
        kind = REQUEST if rid == "R04" else ELICIT
        verb = "申请" if kind is REQUEST else "引出"
        return [
            {"n": i + 1, "kind": kind, "refs": [r], "criterion": f"{verb} {r}"}
            for i, r in enumerate(refs)
        ]

    # 整体判定：整条锚点就是判据；refs 保留用于溯源，不参与拆分
    return [{"n": 1, "kind": JUDGE, "refs": refs, "criterion": item.get("anchor") or ""}]


def decompose_rubric(rubric: dict) -> dict[str, list[dict]]:
    """{item_id: [sub_anchor, …]} for a whole rubric."""
    return {it["id"]: decompose(it) for it in rubric.get("items", [])}
