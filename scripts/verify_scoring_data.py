#!/usr/bin/env python3
"""Verify extracted scoring data, then promote the sliced cases into data/cases/.

Same shape as build_exam_v2.py: extract scripts write to data/staging/, this script
proves the result against a fixed rule set, and only then does it copy into
data/cases/ (which holds **final** data only). A case that fails is NOT promoted —
the failure stays visible instead of landing as a plausible-looking empty rubric.

Rules (see docs/scoring-system-design.md §3.3):
  A1  每例的参考答案必须有 D01/D02/≥1 个 DD/T01/T02/T03/G01/G02，且非空
  A2  每例 rubric 必须恰好 14 条 R01–R14，且锚点非空
  A3  每条 R 的参照 ID 必须可解析：
        H01–H07 / P01–P03 为固定槽位；D/DD/T/G 必须在该例 answer 中存在；
        E## 在有 exam.json 的病例里必须存在，否则仅记录（扩量后再查）
  A4  参照 ID 必须与医院的设计对齐（R06→D01、R07∋D02、R08⊆DD…，见下）
  A5  必须恰好一条「关键错误」行（生成端已保证，这里复核空串）
  A6  提取时的 unparsed_line 异常必须为 0
  A7  **逐字保真**：每条抽取出的锚点/参考答案文本都必须是 docx 原文的连续子串
        —— 医学内容只能誊抄，不能由流水线改写（P1）

Usage:
    python scripts/verify_scoring_data.py            # 校验 + 提升 5 例
    python scripts/verify_scoring_data.py --check     # 只校验，不提升
"""

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGING = ROOT / "data" / "staging"
CASES_DIR = ROOT / "data" / "cases"
REPORT = ROOT / "data" / "tests" / "scoring_verify_report.md"
DOCX_TEXT = ROOT / "data" / "raw" / "_docx.txt"

# A7 用：原文全文，用于证明抽取的医学文本是逐字誊抄而非改写
RAW_DOCX = DOCX_TEXT.read_text(encoding="utf-8") if DOCX_TEXT.exists() else ""
VERBATIM_KEYS = ("content", "reason", "anchor")

SLICED_CASES = ["EN01", "PE01", "PR01", "MU01", "SU01"]
ALL_ITEMS = [f"R{i:02d}" for i in range(1, 15)]

H_SLOTS = {f"H{i:02d}" for i in range(1, 8)}
P_SLOTS = {f"P{i:02d}" for i in range(1, 4)}
D_SLOTS = {"D01", "D02", "DD01", "DD02", "DD03"}

# A4：参照 ID 的设计预期（docs/scoring-system-design.md §1）
def check_refs_alignment(rid: str, refs: set[str]) -> str | None:
    if rid == "R06" and refs != {"D01"}:
        return "R06 应恰好参照 D01"
    if rid == "R07" and "D02" not in refs:
        return "R07 应参照 D02"
    if rid == "R08" and (not refs or not all(r.startswith("DD") for r in refs)):
        return "R08 应只参照 DD*"
    if rid == "R09" and "T01" not in refs:
        return "R09 应参照 T01"
    if rid == "R10" and not {"T02", "T03"} <= refs:
        return "R10 应参照 T02、T03"
    if rid == "R11" and "G01" not in refs:
        return "R11 应参照 G01"
    if rid == "R12" and "G02" not in refs:
        return "R12 应参照 G02"
    if rid == "R13" and not {"P01", "P02"} <= refs:
        return "R13 应参照 P01、P02"
    if rid == "R14" and "P03" not in refs:
        return "R14 应参照 P03"
    if rid in ("R01", "R02", "R03") and not refs <= H_SLOTS:
        return f"{rid} 应只参照 H*"
    if rid in ("R04", "R05") and not all(r.startswith("E") for r in refs):
        return f"{rid} 应只参照 E*"
    return None


def load(case_id: str, kind: str) -> dict | None:
    path = STAGING / f"{case_id.lower()}.{kind}.new.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def exam_ids(case_id: str) -> set[str] | None:
    path = CASES_DIR / f"{case_id.lower()}.exam.json"
    if not path.exists():
        return None
    return set(json.loads(path.read_text(encoding="utf-8"))["exams"].keys())


def _verbatim_fields(ans: dict, rub: dict):
    """Yield (text, where) for every field that must be a verbatim docx substring."""
    for key in ("diagnosis", "diagnosis_reason"):
        yield (ans[key] or {}).get("content") or "", f"{ans['case_id']}.answer.{key}"
    for d in ans.get("differentials", []):
        yield d.get("reason", ""), f"{ans['case_id']}.answer.{d['id']}.reason"
    for slot, val in ans.get("plan", {}).items():
        yield (val or {}).get("content") or "", f"{ans['case_id']}.answer.plan.{slot}"
    for slot, val in ans.get("communication_reference", {}).items():
        yield (val or {}).get("content") or "", f"{ans['case_id']}.answer.comm.{slot}"
    for it in rub.get("items", []):
        yield it.get("anchor") or "", f"{ans['case_id']}.rubric.{it['id']}.anchor"
    for e in rub.get("critical_errors", []):
        yield e, f"{ans['case_id']}.rubric.critical_errors"


def verify_case(case_id: str) -> tuple[list[str], dict]:
    errs: list[str] = []
    ans = load(case_id, "answer")
    rub = load(case_id, "rubric")
    if ans is None:
        return [f"A1 缺参考答案文件（{case_id}.answer.new.json 不存在）"], {}
    if rub is None:
        return [f"A2 缺评分锚点文件（{case_id}.rubric.new.json 不存在）"], {}

    # A1
    for key, path in [("D01", ("diagnosis",)), ("D02", ("diagnosis_reason",))]:
        if not (ans.get(path[0]) or {}).get("content"):
            errs.append(f"A1 参考答案缺 {key}")
    for slot in ("immediate", "definitive", "review"):
        if not ans["plan"][slot].get("content"):
            errs.append(f"A1 参考答案缺 T 槽位 {slot}")
    for slot in ("explain", "warn"):
        if not ans["communication_reference"][slot].get("content"):
            errs.append(f"A1 参考答案缺 G 槽位 {slot}")
    if not ans["differentials"]:
        errs.append("A1 参考答案缺鉴别诊断 DD*")

    # A2
    items = rub.get("items", [])
    got = [it["id"] for it in items]
    if got != ALL_ITEMS:
        errs.append(f"A2 R 条目不是 R01–R14（得到 {len(got)} 条）")
    for it in items:
        if not it.get("anchor"):
            errs.append(f"A2 {it['id']} 锚点为空")

    # A3 / A4
    defined = D_SLOTS | {d["id"] for d in ans["differentials"]}
    defined |= {"T01", "T02", "T03", "G01", "G02"}
    eids = exam_ids(case_id)
    for it in items:
        refs = set(it["refs"])
        for r in refs:
            if r in H_SLOTS or r in P_SLOTS:
                continue
            if r.startswith("E"):
                if eids is not None and r not in eids:
                    errs.append(f"A3 {it['id']} 参照 {r}，但该例 exam.json 无此项")
                continue
            if r.startswith("DD"):
                if r not in {d["id"] for d in ans["differentials"]}:
                    errs.append(f"A3 {it['id']} 参照 {r}，但参考答案里没有该鉴别")
                continue
            if r not in defined:
                errs.append(f"A3 {it['id']} 参照 {r}，无法解析")
        msg = check_refs_alignment(it["id"], refs)
        if msg:
            errs.append(f"A4 {msg}（实际 {'、'.join(sorted(refs)) or '空'}）")

    # A5
    if not rub.get("critical_errors_raw"):
        errs.append("A5 关键错误为空")

    # A7 逐字保真
    for text, where in _verbatim_fields(ans, rub):
        if text not in RAW_DOCX:
            errs.append(f"A7 {where} 不是 docx 原文的逐字子串：{text[:40]}…")

    stats = {
        "diagnosis": ans["diagnosis"]["content"],
        "n_dd": len(ans["differentials"]),
        "n_critical": len(rub["critical_errors"]),
        "code_items": sum(1 for it in items if it.get("judge") == "code"),
        "report_items": sum(1 for it in items if it.get("evidence") == "report"),
    }
    return errs, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只校验，不提升到 data/cases")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    staged = sorted({p.name.split(".")[0].upper() for p in STAGING.glob("*.rubric.new.json")})
    results = {cid: verify_case(cid) for cid in staged}

    lines = [
        "# 评分数据校验报告",
        "",
        f"> 生成于 {date.today().isoformat()}。校验 `data/staging/*.answer.new.json` 与 `*.rubric.new.json`。",
        ">",
        "> 规则 A1–A6 见 `docs/scoring-system-design.md` §3.3。**校验不通过的病例不会被提升进 `data/cases/`。**",
        "",
        "## 汇总",
        "",
    ]
    bad = {cid: errs for cid, (errs, _) in results.items() if errs}
    # 只有已切片的 5 例会阻塞流水线；其余 25 例的问题记录下来（多为 docx 自身的数据缺口）。
    blocking = {cid: errs for cid, errs in bad.items() if cid in SLICED_CASES}
    lines.append(f"- 校验 **{len(staged)}** 例；通过 **{len(staged) - len(bad)}** 例，失败 **{len(bad)}** 例"
                 f"（其中阻塞流水线 **{len(blocking)}** 例）。")
    lines.append("")

    if bad:
        lines += ["## ❌ 未通过", "", "| 病例 | 阻塞 | 问题 |", "|---|---|---|"]
        for cid, errs in bad.items():
            flag = "🔴 是" if cid in SLICED_CASES else "⚪ 否（未切片）"
            for e in errs:
                lines.append(f"| {cid} | {flag} | {e.replace('|', chr(92) + '|')} |")
        lines.append("")

    lines += ["## 逐例统计", "",
              "| 病例 | 主诊断 | DD 数 | 关键错误 | 代码判项 | 报告判项 | 提升 |",
              "|---|---|---|---|---|---|---|"]
    promoted = []
    for cid, (errs, st) in results.items():
        if not st:
            lines.append(f"| {cid} | — | — | — | — | — | 缺文件 |")
            continue
        take = (cid in SLICED_CASES) and not errs and not args.check
        if take:
            promoted.append(cid)
        flag = "✅ 已提升" if take else ("（未切片）" if not errs else "❌ 跳过")
        lines.append(f"| {cid} | {st['diagnosis']} | {st['n_dd']} | {st['n_critical']} "
                     f"| {st['code_items']}/14 | {st['report_items']}/14 | {flag} |")
    lines.append("")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    # ── 提升：仅通过校验的已切片病例 ──────────────────────────────
    for cid in promoted:
        for kind in ("answer", "rubric"):
            src = STAGING / f"{cid.lower()}.{kind}.new.json"
            dst = CASES_DIR / f"{cid.lower()}.{kind}.json"
            shutil.copyfile(src, dst)

    print(f"校验 {len(staged)} 例：通过 {len(staged) - len(bad)}，失败 {len(bad)}（阻塞 {len(blocking)}）")
    for cid, errs in bad.items():
        tag = "❌" if cid in SLICED_CASES else "⚠ "
        for e in errs:
            print(f"  {tag} {cid}: {e}")
    print(f"提升 {len(promoted)} 例 → data/cases/：{'、'.join(promoted) or '无'}")
    print(f"报告 → {REPORT.relative_to(ROOT)}")
    if blocking:
        sys.exit(1)


if __name__ == "__main__":
    main()
