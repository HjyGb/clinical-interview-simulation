"""子锚点命中 → 项分（0/1/2）。

设计见 docs/scoring-system-design.md §5.3、§5.4。两条规则**都由代码执行，不由模型执行**：

  1. **证据强制**：一个子锚点声称"命中"却没有证据原话 → 降级为**未命中**。
     让模型想给分就得先把学员原话抄出来。这是把 P1（忠实优先于聪明）搬到评分侧。
  2. **聚合**：全部命中 → 2；部分命中 → 1；全部未命中 → 0。
     对应医院册前的 1 分锚点「部分完成」/ 0 分锚点「未完成或错误」。

R05–R14 不拆子锚点，由 LLM 直接给 0/1/2（`direct_score`），但**同样必须先引用证据**。
"""

from dataclasses import dataclass, field

MAX_PER_ITEM = 2

# 项的状态。NE/NA/SKIPPED_SAFETY 不是分数，是"这一项没法评/不该评"——
# 医院原文（_docx.txt:99）：「NE/NA 不自动给 0 或满分，同时报告可评上限」。
SCORED, NE, NA, SKIPPED_SAFETY = "scored", "ne", "na", "skipped_safety"
UNSCORED = frozenset({NE, NA, SKIPPED_SAFETY})


@dataclass
class SubAnchorResult:
    """One sub-anchor's verdict."""

    n: int
    met: bool
    evidence_quote: str = ""      # 学员原话 / 作答片段；缺了就等于没给分
    evidence_ref: str = ""        # 可定位的引用（如 msg#23 / report.evidence）
    downgraded: bool = False      # 因缺证据被降级（供报告解释，不参与计分）


@dataclass
class ItemScore:
    item_id: str
    score: int
    sub_anchors: list[SubAnchorResult] = field(default_factory=list)
    note: str = ""
    status: str = SCORED

    @property
    def max_score(self) -> int:
        return MAX_PER_ITEM

    @property
    def counted(self) -> bool:
        return self.status == SCORED


def enforce_evidence(results: list[SubAnchorResult]) -> list[SubAnchorResult]:
    """Downgrade any `met=True` that carries no evidence quote. Returns the same list."""
    for r in results:
        if r.met and not (r.evidence_quote or "").strip():
            r.met = False
            r.downgraded = True
    return results


def aggregate(results: list[SubAnchorResult]) -> int:
    """全部命中 2；部分命中 1；全未命中 0。空列表 → 0。"""
    if not results:
        return 0
    n_met = sum(1 for r in results if r.met)
    if n_met == len(results):
        return MAX_PER_ITEM
    return 1 if n_met > 0 else 0


def score_item(item_id: str, results: list[SubAnchorResult]) -> ItemScore:
    """证据强制 → 聚合，一步出项分。"""
    enforce_evidence(results)
    note = ""
    n_down = sum(1 for r in results if r.downgraded)
    if n_down:
        note = f"{n_down} 个子锚点因缺证据被降级为未命中"
    return ItemScore(item_id=item_id, score=aggregate(results),
                     sub_anchors=list(results), note=note)


def direct_score(item_id: str, score: int, evidence_quote: str = "",
                 evidence_ref: str = "", note: str = "") -> ItemScore:
    """R05–R14 通道：LLM 直接给 0/1/2，但**没有证据的给分一律归零**。

    证据原话会被保留在 sub_anchors 里，供报告展示"这一分凭什么"——
    归零也记一条，说明它本来声称了几分。
    """
    if score < 0 or score > MAX_PER_ITEM:
        raise ValueError(f"{item_id}: score {score} out of range 0..{MAX_PER_ITEM}")

    if score > 0 and not (evidence_quote or "").strip():
        return ItemScore(
            item_id=item_id, score=0,
            sub_anchors=[SubAnchorResult(n=1, met=False, downgraded=True)],
            note=f"声称 {score} 分但未引用证据 → 归零",
        )

    sub = SubAnchorResult(n=1, met=score > 0,
                          evidence_quote=(evidence_quote or "").strip(),
                          evidence_ref=(evidence_ref or "").strip())
    return ItemScore(item_id=item_id, score=score, sub_anchors=[sub], note=note)


def unscored(item_id: str, status: str, note: str) -> ItemScore:
    """NE / NA / SKIPPED_SAFETY：不计分，但也不假装是 0 分。"""
    if status not in UNSCORED:
        raise ValueError(f"unscored() 只接受 {sorted(UNSCORED)}，收到 {status}")
    return ItemScore(item_id=item_id, score=0, status=status, note=note)


def total(scores: list[ItemScore]) -> int:
    """原始分合计。**这里是合计，不是平均**——见设计文档 §8.3。

    NE/NA/SKIPPED_SAFETY 不计入——但它们也不变成 0 分，而是进 `report_ceiling`。
    """
    return sum(s.score for s in scores if s.counted)


def report_ceiling(scores: list[ItemScore]) -> dict:
    """可评上限。医院要求 NE/NA「同时报告可评上限」，不能让人以为满分就是 28。"""
    counted = [s for s in scores if s.counted]
    excluded = {s.status: [x.item_id for x in scores if x.status == s.status]
                for s in scores if not s.counted}
    return {
        "raw_total": total(scores),
        "raw_max_counted": len(counted) * MAX_PER_ITEM,   # 真正可能拿到的上限
        "raw_max_nominal": len(scores) * MAX_PER_ITEM,    # 名义上限（14×2=28）
        "excluded": excluded,                              # {"ne": ["R04"], …}
    }
