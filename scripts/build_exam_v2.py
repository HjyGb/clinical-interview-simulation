#!/usr/bin/env python3
"""Build exam data at schema v2.2 — sub-item layer, with **machine-enforced** fidelity.

The LLM proposes how to split an exam's result across sub-items. This script then
proves the proposal is faithful before accepting it:

  V1  每个 result_fragment 是 result 的逐字连续子串       → 模型没改写原文
  V2  片段按原序拼接后覆盖整条 result（去空白标点比较）   → 模型没丢句子
  V3  子项名能在该组别名里找到出处                        → 模型没自创名词

任一不过 → 该项 `split_verified: false`，退回整包返回，并进入待人工清单。
**不静默降级**：失败要留在数据里看得见。

同时产出一份人可读的映射核对表，供人工/医院复核。

Usage:
    python scripts/build_exam_v2.py --case EN01
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from loguru import logger  # noqa: E402

from agent.exam_subitem_splitter import propose_split  # noqa: E402

CASES_DIR = ROOT / "data" / "cases"          # 最终数据落这里
STAGING_DIR = ROOT / "data" / "staging"      # extract_exam_items.py 的中间产物
REVIEW_DIR = ROOT / "data" / "tests"

# 覆盖比较时忽略空白与标点——切分必然会在断点处丢掉分隔标点（如"36叩诊阴性，松动度0。")
_PUNCT = re.compile(r"[\s，,。.；;：:、！!？?（）()【】\[\]“”\"'‘’～~\-—_/／]+")

# 校验失败时带反馈重试几次；仍不过则该项退回整包
MAX_ATTEMPTS = 3

# 自补子项名的长度上限。超过多半是把整串别名抄下来当名字了（如 SU01 E02 曾出现 40+ 字的"名字"）
MAX_LABEL_LEN = 12

# key 用英文短标识，供披露轨迹引用；按子项名做保守映射
KEY_HINTS = [
    ("冷", "cold"), ("叩", "percussion"), ("松动", "mobility"), ("牙髓", "pulp"),
    ("牙周", "perio"), ("探诊", "probing"), ("附着", "attachment"), ("出血", "bleeding"),
    ("根分叉", "furcation"), ("影像", "imaging"), ("牙片", "xray"), ("全景", "opg"),
    ("体温", "temperature"), ("淋巴", "lymph"), ("视诊", "inspection"), ("触诊", "palpation"),
    ("黏膜", "mucosa"), ("颌面", "maxillofacial"), ("咬合", "occlusion"), ("张口", "mouth_opening"),
    ("血", "blood"), ("菌斑", "plaque"), ("牙石", "calculus"), ("牙龈", "gingiva"),
    ("缺损", "defect"), ("裂纹", "crack"), ("磨损", "wear"), ("气吹", "air_blast"),
]


def normalize(text: str) -> str:
    return _PUNCT.sub("", text or "")


def make_key(label: str, used: set[str]) -> str:
    """Derive a stable ascii key from a Chinese sub-item name."""
    for hint, key in KEY_HINTS:
        if hint in label and key not in used:
            return key
    base = "sub"
    i = 1
    while f"{base}{i}" in used:
        i += 1
    return f"{base}{i}"


def validate(item: dict, proposal: dict, groups: list[dict]) -> tuple[list[dict], list[str]]:
    """Check the proposal against V1–V3. Returns (accepted_subitems, failures)."""
    result = item.get("result") or ""
    failures: list[str] = []
    subitems: list[dict] = []

    raw_items = proposal.get("subitems") or []
    if not isinstance(raw_items, list) or not raw_items:
        return [], ["提案为空"]

    # ── V1：每段都必须是 result 的逐字连续子串，并定位 ────────────────
    # 一个子项可以拥有多段（中间隔着别的子项的句子），所以逐段处理。
    spans: list[tuple[int, int, dict]] = []   # (start, end, owner)
    for entry in raw_items:
        if not isinstance(entry, dict):
            failures.append("条目不是对象")
            continue

        gi = entry.get("group_index")
        label = str(entry.get("label") or "").strip()
        frags = entry.get("result_fragments")

        if gi is not None and (not isinstance(gi, int) or not (1 <= gi <= len(groups))):
            failures.append(f"group_index={gi!r} 越界")
            continue
        if frags is None:
            frags = []
        if not isinstance(frags, list):
            failures.append(f"「{label}」result_fragments 不是数组")
            continue

        located: list[str] = []
        for frag in frags:
            frag = str(frag).strip()
            if not frag:
                continue
            if frag not in result:
                failures.append(f"「{label}」片段不是原文子串（可能取自规则说明）：{frag[:40]!r}")
                continue
            located.append(frag)

        if failures:
            continue

        # 定位：每段独立查找；重复片段按出现顺序依次取用
        search_from = 0
        for frag in located:
            pos = result.find(frag, search_from)
            if pos == -1:
                pos = result.find(frag)
            if pos == -1:
                failures.append(f"「{label}」片段定位失败：{frag[:40]!r}")
                break
            spans.append((pos, pos + len(frag), {"group_index": gi, "label": label, "fragment": frag}))
            search_from = pos + len(frag)

    if failures:
        return [], failures
    if not spans:
        return [], ["没有任何结果片段"]

    # ── V2：片段必须不重叠且完整覆盖 result ─────────────────────────
    spans.sort(key=lambda x: x[0])
    for (s1, e1, a), (s2, e2, b) in zip(spans, spans[1:]):
        if s2 < e1:
            failures.append(
                f"片段重叠：「{a['label']}」与「{b['label']}」都占用了同一段文字"
                f"（{result[max(s1, s2):min(e1, e2)][:30]!r}）"
            )
    if failures:
        return [], failures

    joined = normalize("".join(s[2]["fragment"] for s in spans))
    if joined != normalize(result):
        failures.append(
            f"覆盖不完整：拼接后 {len(joined)} 字，原文 {len(normalize(result))} 字"
            f"（多/少内容，说明有改写或丢句）"
        )
        return [], failures

    # ── V3：组名有出处 + 生成 key ────────────────────────────────
    by_group: dict = {}
    for _, _, entry in spans:
        by_group.setdefault(entry["group_index"], {"label": entry["label"], "frags": []})
        by_group[entry["group_index"]]["frags"].append(entry["fragment"])

    # 伞形组（提案里给了但没有任何片段）也要保留
    for entry in raw_items:
        if isinstance(entry, dict) and not (entry.get("result_fragments") or []):
            gi = entry.get("group_index")
            if gi is not None and gi not in by_group:
                by_group[gi] = {"label": str(entry.get("label") or "").strip(), "frags": []}

    used_keys: set[str] = set()
    for gi in sorted(by_group, key=lambda g: (g is None, g)):
        entry = by_group[gi]
        label = entry["label"]
        if not label:
            failures.append("子项名为空")
            continue
        authored = bool(gi is not None and groups[gi - 1].get("label"))
        if gi is not None and not authored:
            # 自补的组名必须像一个"名字"：太长的多半是把整串别名抄了下来
            if len(label) > MAX_LABEL_LEN:
                failures.append(f"组名「{label[:20]}…」过长（{len(label)} 字），不像子项名")
                continue
            if any(sep in label for sep in "；;／/、，,"):
                failures.append(f"组名「{label}」含分隔符，像是把整串别名抄下来了")
                continue
            aliases = groups[gi - 1].get("aliases") or []
            if not any(label in a or a in label for a in aliases):
                failures.append(f"组名「{label}」在该组别名里找不到出处（疑似自创）")
                continue

        key = make_key(label, used_keys)
        used_keys.add(key)
        # aliases 必须从输入分组带出来——子项级匹配全靠它。
        # （第一版漏了这一行，导致子项永远匹配不到、退化成整包。）
        aliases = list(groups[gi - 1].get("aliases") or []) if gi is not None else []
        subitems.append({
            "key": key,
            "label": label,
            "group_index": gi,
            "aliases": aliases,
            "result_fragments": entry["frags"],
            "source": "authored" if authored else "derived",
        })

    if failures:
        return [], failures
    return subitems, []


def build_review_table(case_id: str, exams: dict) -> str:
    """Human-readable mapping table for review (this is what the hospital would check)."""
    lines = [
        f"# 检查子项切分核对表 — {case_id}",
        "",
        f"> 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}。",
        "> **请人工核对两件事**：① 子项名起得对不对；② 结果片段切得对不对。",
        "> 每个片段都经过机器校验（V1 逐字子串 / V2 完整覆盖 / V3 组名有出处），",
        "> 所以**内容一定没有被改写或丢失**；需要人看的是**归属**对不对。",
        "",
    ]
    for eid, e in exams.items():
        ok = e.get("split_verified")
        mark = "✅ 已切分" if ok else "⚠️ 未切分（整包返回）"
        lines.append(f"## `{eid}` {e['label']} [{e['level']}] — {mark}")
        lines.append("")
        lines.append(f"**完整结果**：{e.get('result') or '（未提供）'}")
        lines.append("")
        if not ok:
            reason = e.get("split_failures") or []
            lines.append("未切分原因：" + ("；".join(reason) if reason else "该检查项无结果或无需切分"))
            lines.append("")
            continue
        lines.append("| 子项 | 来源 | 学生可能怎么问（别名示例） | 只返回这几段 |")
        lines.append("|---|---|---|---|")
        for s in e["subitems"]:
            gi = s.get("group_index")
            aliases = (e.get("_groups") or [{}])[gi - 1].get("aliases", []) if gi else []
            preview = "、".join(aliases[:5]) + ("…" if len(aliases) > 5 else "")
            frags = s.get("result_fragments") or []
            frag = "　+　".join(f"`{f}`" for f in frags) if frags else "（伞形：问它返回整包）"
            lines.append(f"| **{s['label']}** `{s['key']}` | {s['source']} | {preview} | {frag} |")
        lines.append("")
    return "\n".join(lines)


async def build_case(case_id: str) -> None:
    src = STAGING_DIR / f"{case_id.lower()}.exam.new.json"
    if not src.exists():
        print(f"错误：staging/{src.name} 不存在，请先运行 scripts/extract_exam_items.py")
        return
    data = json.loads(src.read_text(encoding="utf-8"))

    exams = {}
    for eid, item in data["exams"].items():
        groups = item.get("subitems") or []
        result = item.get("result")

        out = {
            "label": item["label"],
            "level": item["level"],
            "result": result,
            "boundary": item.get("boundary", ""),
            "aliases": item.get("aliases", []),
            "subitems": [],
            "split_verified": False,
            "_groups": groups,
        }

        if not result:
            # 未提供项：没有结果可切分，不是失败
            out["split_verified"] = True
            out["split_note"] = "未提供项，无结果可切分"
            out["aliases"] = item.get("aliases", [])
            exams[eid] = out
            print(f"  {eid}: — 未提供（无结果）")
            continue

        # 只有一个别名组 → 医院没有做子项划分，整项即子项，不拆。
        # （强行拆会让模型去猜医院没写的结构；SU01 E02 的医院原文就写着"固定查体文字整包"。）
        if len(groups) <= 1:
            out["split_verified"] = True
            out["subitems"] = []
            out["split_note"] = "单一别名组，整项即子项，无需子项裁剪"
            exams[eid] = out
            print(f"  {eid}: — 整项（单组，无需裁剪）")
            continue

        # 带反馈重试：校验失败时把原因喂回去让模型改正，而不是直接放弃该项
        subitems: list[dict] = []
        failures: list[str] = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            proposal = await propose_split(item, groups, feedback=failures or None)
            if proposal is None:
                failures = ["模型调用或解析失败"]
                continue
            subitems, failures = validate(item, proposal, groups)
            if not failures:
                break
            if attempt < MAX_ATTEMPTS:
                print(f"     {eid} 第 {attempt} 次未过（{failures[0][:40]}…），重试")

        if failures:
            out["split_failures"] = failures
            out["split_attempts"] = MAX_ATTEMPTS
            exams[eid] = out
            print(f"  {eid}: ❌ {MAX_ATTEMPTS} 次后仍未过 — {failures[0]}")
            continue

        out["subitems"] = subitems
        out["split_verified"] = True
        exams[eid] = out
        print(f"  {eid}: ✅ {len(subitems)} 个子项 — " +
              "、".join(f"{s['label']}{'' if s['result_fragments'] else '(伞形)'}" for s in subitems))

    # 校验产物：去掉内部辅助字段后落盘
    clean = {
        "case_id": data["case_id"],
        "schema_version": "2.2",
        "exams": {
            eid: {k: v for k, v in e.items() if k != "_groups"}
            for eid, e in exams.items()
        },
    }
    out_path = CASES_DIR / f"{case_id.lower()}.exam.json"
    out_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n数据已写入 {out_path.relative_to(ROOT)}")

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    review_path = REVIEW_DIR / f"exam_split_review_{case_id}.md"
    review_path.write_text(build_review_table(data["case_id"], exams), encoding="utf-8")
    print(f"核对表已写入 {review_path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="EN01")
    args = parser.parse_args()

    logging.disable(logging.INFO)
    sys.stdout.reconfigure(encoding="utf-8")
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    asyncio.run(build_case(args.case))


if __name__ == "__main__":
    main()
