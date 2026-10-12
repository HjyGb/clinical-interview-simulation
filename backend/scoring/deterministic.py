"""R01–R04 的纯 Python 判定——不调 LLM。

为什么这四项能脱离模型：**患者/检查模块已经替我们记下了证据**（设计文档 §7）。

    R01 主诉与病程询问        ← Message.disclosed 里有没有 H01 / H02
    R02 鉴别症状及危险征象     ← 有没有 H03 / H04
    R03 诊疗史、用药和全身风险  ← 有没有 H05 / H06 / H07
    R04 必要检查选择          ← 有没有申请该例 level=="关键" 的 E 项

R04 的必做项**就是**该例 `level=="关键"` 的 E 项——已逐条比对（EN01 的 R04 锚点写的
「一般口内视诊、36及对照牙冷测叩诊、36根尖片」，正是 E01/E02/E03 三个 [关键]；E04 是 [补充]）。
所以这一项也完全是确定性的。

**医院两条约束的落实**（`_docx.txt:100`、`1308`）：
  - 「不能因系统宽召回了整个 E 包，就把包内全部项目记为学员已主动选择」
    → 整项命中（disclosed 里是裸 `E02`）与子项命中（`E02.cold`）都算作"申请了该 E 项"，
      但**保留原始请求文本**（返回 `requested_raw`）供复核；不做"包内全给分"。
  - 「复合项目逐子项匹配，不能把冷测、叩诊、视诊、探诊互换计分」
    → 子项粒度信息保留在 `requested_subitems` 里。

**已知缺陷的兜底**：selector 偶尔对"预计阴性"的问句答对了却漏记披露轨迹。
目前只做一处确定性兜底：`intent == "open"` 时门控必然放行 H01–H04，轨迹为空就按它补。
针对 `targeted` 的兜底需要把 `asked_facts` 落库（当前只落了问句类型），见 dev-plan P3 记录。
"""

import re

from scoring.aggregate import SubAnchorResult, ItemScore, score_item

CODE_ITEMS = ("R01", "R02", "R03", "R04")

# 患者事实编号：只认 H##/P##，检查子项键（E02.cold）绝不混进来
FACT_ID = re.compile(r"^[HP]\d{2}$")

# 开放式问诊门控必然放行的四条（对应 disclosure.gate 的 open 分支）
OPEN_ALLOWED = ["H01", "H02", "H03", "H04"]

# R01/R02/R03 各自要求问出来的事实
ELICIT_REQUIREMENTS = {
    "R01": ["H01", "H02"],
    "R02": ["H03", "H04"],
    "R03": ["H05", "H06", "H07"],
}


def elicited_fact_ids(trace: list[dict]) -> set[str]:
    """患者侧实际披露过的 H/P 编号 = 学员实际问到的。

    打底用 `disclosed`；轨迹为空且该轮是 `open` 时，按门控规则补 H01–H04。
    """
    out: set[str] = set()
    for m in trace:
        if m.get("role") != "patient":
            continue
        disclosed = m.get("disclosed") or []
        out.update(x for x in disclosed if isinstance(x, str) and FACT_ID.match(x))
        if not disclosed and m.get("intent") == "open":
            out.update(OPEN_ALLOWED)
    return out


def requested_exam_ids(trace: list[dict]) -> set[str]:
    """学员实际申请过的 E 项。`E02.cold` 与裸 `E02` 都归到 `E02`。"""
    out: set[str] = set()
    for m in trace:
        if m.get("role") != "exam":
            continue
        for x in m.get("disclosed") or []:
            if isinstance(x, str) and x.startswith("E"):
                out.add(x.split(".", 1)[0])
    return out


def requested_subitems(trace: list[dict]) -> list[str]:
    """保留子项粒度（`E02.cold`），供人复核"宽召回"是否被误判为主动选择。"""
    out = []
    for m in trace:
        if m.get("role") != "exam":
            continue
        for x in m.get("disclosed") or []:
            if isinstance(x, str) and "." in x:
                out.append(x)
    return out


def required_exam_ids(exam_data: dict | None) -> list[str]:
    """该例的必做检查 = level == "关键" 的 E 项（E04 那种 [补充] 不算）。"""
    exams = (exam_data or {}).get("exams") or {}
    return [eid for eid, e in exams.items() if (e or {}).get("level") == "关键"]


def judge_r01_r04(rubric: dict, exam_data: dict | None, trace: list[dict]) -> dict[str, ItemScore]:
    """判 R01–R04，返回 {item_id: ItemScore}。

    Args:
        rubric:    该例的 *.rubric.json（含 items[].refs）
        exam_data: 该例的 exam.json（用于取 level=="关键"）
        trace:     [{"role": "student"|"patient"|"exam", "content": str,
                     "intent": str|None, "disclosed": list[str]|None}, …]

    每个子锚点的证据原话都**从轨迹里现取**（学员那句问话 / 检查申请），
    不是外部传进来的——否则的话 `enforce_evidence` 会把所有命中都降级掉。
    """
    elicited = elicited_fact_ids(trace)
    requested = requested_exam_ids(trace)
    refs_by_item = {it["id"]: list(it.get("refs") or []) for it in rubric.get("items", [])}

    out: dict[str, ItemScore] = {}

    for rid in ("R01", "R02", "R03"):
        required = refs_by_item.get(rid) or ELICIT_REQUIREMENTS[rid]
        results = [
            SubAnchorResult(n=i + 1, met=hid in elicited,
                            evidence_quote=_quote_for(trace, hid),
                            evidence_ref=f"disclosed:{hid}")
            for i, hid in enumerate(required)
        ]
        out[rid] = score_item(rid, results)

    required_exams = refs_by_item.get("R04") or required_exam_ids(exam_data)
    results = [
        SubAnchorResult(n=i + 1, met=eid in requested,
                        evidence_quote=_exam_quote_for(trace, eid),
                        evidence_ref=f"exam_request:{eid}")
        for i, eid in enumerate(required_exams)
    ]
    score = score_item("R04", results)
    subs = requested_subitems(trace)
    if subs:
        score.note = (score.note + " " if score.note else "") + \
            f"含子项请求 {subs}（宽召回复核用）"
    out["R04"] = score
    return out


def _exam_quote_for(trace: list[dict], exam_id: str) -> str:
    """找一条能证明该 E 项被申请过的学员原话。"""
    for m in trace:
        if m.get("role") != "exam":
            continue
        hit = any(isinstance(x, str) and x.split(".", 1)[0] == exam_id
                  for x in (m.get("disclosed") or []))
        if not hit:
            continue
        rnd = m.get("round_num")
        for s in trace:
            if s.get("role") == "student" and (rnd is None or s.get("round_num") == rnd):
                return (s.get("content") or "").strip()[:120]
    return ""


def _quote_for(trace: list[dict], fact_id: str) -> str:
    """找一条能证明该事实被问出来的学员原话。

    这是"证据强制"在代码侧的落法：把**学员那句问话**抄出来，而不是写"已问到"。
    """
    for m in trace:
        disclosed = m.get("disclosed") or []
        if m.get("role") == "patient" and fact_id in disclosed:
            rnd = m.get("round_num")
            for s in trace:
                if s.get("role") == "student" and (rnd is None or s.get("round_num") == rnd):
                    return (s.get("content") or "").strip()[:120]
        if m.get("role") == "patient" and m.get("intent") == "open" and not disclosed \
                and fact_id in OPEN_ALLOWED:
            rnd = m.get("round_num")
            for s in trace:
                if s.get("role") == "student" and (rnd is None or s.get("round_num") == rnd):
                    return (s.get("content") or "").strip()[:120]
    return ""
