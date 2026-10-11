#!/usr/bin/env python3
"""Re-extract exam items from the docx text dump, **preserving the sub-item grouping**.

Why this exists: the first hand-slice of exam.json flattened 可接受表达 into one flat
alias list, which threw away structure the hospital had already written:

    【牙周检查】牙周检查／检查牙周／…；【探诊深度】牙周探诊／…；【附着/出血】…

Those 【group】 labels — and the ／ ; separators — are the hospital's own sub-item
taxonomy, and several E items' `实际返回` state an explicit sub-item rule
("相关子项请求仅返回该项结果，不可返回整个E02"). Flattening lost that.

Two outputs:
  data/cases/<case>.exam.json   — re-sliced, with `subitems` (only for the 5 sliced cases)
  data/tests/exam_subitem_gaps.md — which E items lack 【】 labels, for the hospital to fill in

Separator fidelity was verified against the docx XML: 【】 131=131, ／ 1636=1636, ； 2784=2784.

Usage:
    python scripts/extract_exam_items.py --report-only    # 只看缺标签清单，不写 exam.json
"""

import argparse
import json
import re
import sys
from collections import OrderedDict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCX_TEXT = ROOT / "data" / "raw" / "_docx.txt"
CASES_DIR = ROOT / "data" / "cases"          # 只放最终进系统的数据
STAGING_DIR = ROOT / "data" / "staging"      # 中间产物，可随时重建
GAP_REPORT = ROOT / "data" / "tests" / "exam_subitem_gaps.md"

SLICED_CASES = ["EN01", "PE01", "PR01", "MU01", "SU01"]

SECTION = re.compile(r"^\[\d+\]\s+([A-Z]{2}\d{2})\s+(A\d)\s+(.+?)\s*$")
EXAM_LINE = re.compile(r"^(E\d{2})\s+\[([^\]]+)\]\s+(.*)$")
GROUP_LABEL = re.compile(r"【([^】]+)】")
# 别名分隔符：全角/半角斜杠、全角/半角分号；【】标签单独处理
ALIAS_SEP = re.compile(r"[／/;；]+")
GROUP_SEP = re.compile(r"[；;]+")
# 中文/英文括号内的内容不属于别名，里面的 ；／ 不能当分隔符
PAREN = re.compile(r"[（(][^（()）]*[）)]")


def split_outside_parens(text: str, sep: re.Pattern) -> list[str]:
    """Split on `sep` but never inside （…） / (…).

    The docx puts commentary in parentheses, e.g.
    "探诊、探查（未说明牙周袋，可能为龋洞或裂纹探查；需澄清。）" — a naive split
    on ； turns that commentary into fake "sub-items".
    """
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        if depth == 0 and sep.match(ch):
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def strip_parens(text: str) -> str:
    """Drop parenthetical commentary — it is guidance, not an alias."""
    return PAREN.sub("", text)


def parse_docx_text(lines: list[str]) -> dict[str, list[dict]]:
    """Return {case_id: [ {id, level, label, aliases_raw, boundary_raw}, … ]} in document order."""
    cases: dict[str, list[dict]] = OrderedDict()
    current_case: str | None = None
    current_item: dict | None = None
    in_a2 = False

    def flush() -> None:
        nonlocal current_item
        if current_item and current_case:
            cases.setdefault(current_case, []).append(current_item)
        current_item = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        sec = SECTION.match(line)
        if sec:
            case_id, kind, _rest = sec.groups()
            flush()
            if kind == "A2":
                current_case = case_id
                in_a2 = True
                cases.setdefault(case_id, [])
            else:
                in_a2 = False
                current_case = None
            continue

        if not in_a2 or not current_case:
            continue

        exam = EXAM_LINE.match(line)
        if exam:
            flush()
            exam_id, level, rest = exam.groups()
            current_item = {"id": exam_id, "level": level.strip(), "tail": rest.strip()}
            continue

        if current_item is None:
            continue
        if line.startswith("可接受表达"):
            current_item["aliases_raw"] = line.split("：", 1)[-1].strip()
        elif line.startswith("实际返回"):
            current_item["boundary_raw"] = line.split("：", 1)[-1].strip()
        # 标题/元信息等其它行直接忽略

    flush()
    return cases


def split_aliases(aliases_raw: str) -> tuple[list[dict], bool]:
    """Split 可接受表达 into sub-items.

    Returns (subitems, has_labels).
    A group starts at a 【label】; text before the first 【 is its own unlabelled group.
    Groups without labels are still separated (by ；) but named None.
    """
    # 去掉行首重复的"可接受表达："与括号内的说明文字，再谈分组
    cleaned = aliases_raw.strip()
    while cleaned.startswith("可接受表达"):
        cleaned = cleaned.split("：", 1)[-1].strip() if "：" in cleaned else cleaned[5:].strip()
    cleaned = strip_parens(cleaned)

    has_labels = bool(GROUP_LABEL.search(cleaned))

    groups: list[tuple[str | None, str]] = []
    if has_labels:
        # 第一个【】之前的内容算作一个无标签组
        first = GROUP_LABEL.search(cleaned)
        if first and first.start() > 0:
            head = cleaned[: first.start()].strip(" ／/；;、")
            if head:
                groups.append((None, head))
        for m in GROUP_LABEL.finditer(cleaned):
            start = m.end()
            stop = cleaned.find("【", start)
            body = cleaned[start: stop if stop != -1 else len(cleaned)]
            groups.append((m.group(1).strip(), body))
    else:
        for part in split_outside_parens(cleaned, GROUP_SEP):
            if part.strip():
                groups.append((None, part))

    subitems = []
    for label, body in groups:
        aliases = [a.strip(" ／/；;、【】") for a in ALIAS_SEP.split(body)]
        aliases = [a for a in aliases if a]
        if aliases:
            subitems.append({"label": label, "aliases": aliases})
    return subitems, has_labels


def build_report(cases: dict[str, list[dict]]) -> str:
    """Markdown list of which E items lack 【】 labels — to take back to the hospital."""
    lines = [
        "# 检查项（E）子项标签缺口清单",
        "",
        f"> 生成于 {date.today().isoformat()}，供向医院方核对使用。",
        ">",
        "> 医院在「可接受表达」里用 `【子项名】` 标注子项分组，并在部分项的「实际返回」里写明",
        "> 「相关子项请求仅返回该项结果，不可返回整个 E 项」。凡是**没有 `【】` 标签**的项，",
        "> 子项与结果片段的对应关系无法机械确定，只能整包返回，做不到子项裁剪。",
        "",
        "## 汇总",
        "",
    ]

    total = labelled = 0
    missing_cases = []
    for case_id, items in cases.items():
        case_missing = [it["id"] for it in items if it.get("aliases_raw") and not GROUP_LABEL.search(it["aliases_raw"])]
        case_total = len([it for it in items if it.get("aliases_raw")])
        total += case_total
        labelled += case_total - len(case_missing)
        if case_missing:
            missing_cases.append(case_id)

    lines.append(f"- 全册共 {total} 个有别名表的 E 项，其中 **{labelled} 个带 `【】` 子项标签**，"
                 f"**{total - labelled} 个没有**。")
    lines.append(f"- 涉及病例：{len(missing_cases)} 个 —— {'、'.join(missing_cases) if missing_cases else '无'}")
    lines.append("")
    # ── 需要医院补的清单：用 ； 分过组但没有【】组名 ──────────────
    lines.append("## ★ 需要医院补组名的项（可直接照此填写）")
    lines.append("")
    lines.append("这些项的别名已经用 `；` 分组，但**每组叫什么没写**，因此无法确定"
                 "「学生问的这一小项」对应结果里的哪一段。请在每组前补一个 `【组名】`。")
    lines.append("")
    ask_count = 0
    for case_id, items in cases.items():
        rows = [it for it in items
                if it.get("aliases_raw")
                and not GROUP_LABEL.search(it["aliases_raw"])
                and len([g for g in GROUP_SEP.split(it["aliases_raw"]) if g.strip()]) > 1]
        if not rows:
            continue
        lines.append(f"**{case_id}**")
        lines.append("")
        for it in rows:
            ask_count += 1
            subitems, _ = split_aliases(it["aliases_raw"])
            lines.append(f"- `{it['id']}` [{it['level']}] 现有 {len(subitems)} 组待命名：")
            for gi, s in enumerate(subitems, 1):
                preview = "、".join(s["aliases"][:5]) + ("…" if len(s["aliases"]) > 5 else "")
                lines.append(f"    {gi}. 【待补组名】 {preview}")
        lines.append("")
    lines.append(f"合计 **{ask_count}** 项。")
    lines.append("")

    # ── 疑似的分隔符笔误：某条别名以同组另一条别名为前缀 ──────────
    # 例：`牙周检查结果牙周探诊` 以 `牙周检查` 开头 —— 中间显然丢了一个 `/`
    lines.append("## ★ 疑似丢分隔符的别名（请医院核对）")
    lines.append("")
    lines.append("检测规则：同一子项内，别名 B 以另一条别名 A 开头、**且 B 比 A 长出 ≥4 个字**，")
    lines.append("则 B 很可能本是 A 和另一条粘在一起（如 `牙周检查结果牙周探诊`）。")
    lines.append("")
    lines.append("> 这是启发式检测，**仍可能有误报**（如 `生命体征及循环评估` 是合法写法）。")
    lines.append("> 按「多出的字数」降序排列，越靠前越可疑。")
    lines.append("")
    all_hits = []
    for case_id, items in cases.items():
        for it in items:
            subitems, _ = split_aliases(it.get("aliases_raw", ""))
            for s in subitems:
                for tok in s["aliases"]:
                    prefix = [a for a in s["aliases"] if a != tok and len(a) >= 3 and tok.startswith(a)]
                    if prefix:
                        best = max(prefix, key=len)
                        overflow = len(tok) - len(best)
                        if overflow >= 4:
                            all_hits.append((overflow, case_id, it["id"], tok, best))
    all_hits.sort(key=lambda x: -x[0])
    if not all_hits:
        lines.append("未检测到。")
        lines.append("")
    else:
        lines.append("| 多出字数 | 病例 | E 项 | 疑似粘连的别名 | 其中已命中的前缀（仅供参考，拆分点需人工判断） |")
        lines.append("|---|---|---|---|---|")
        for overflow, case_id, eid, tok, best in all_hits:
            lines.append(f"| {overflow} | {case_id} | `{eid}` | `{tok}` | `{best}` |")
        lines.append("")
        lines.append(f"合计 **{len(all_hits)}** 条。")
        lines.append("")

    lines.append("## 逐项明细（全册）")
    lines.append("")

    for case_id, items in cases.items():
        rows = [it for it in items if it.get("aliases_raw")]
        if not rows:
            continue
        lines.append(f"### {case_id}")
        lines.append("")
        lines.append("| E 项 | 等级 | 子项标签 | 说明 |")
        lines.append("|---|---|---|---|")
        for it in rows:
            subitems, _ = split_aliases(it["aliases_raw"])
            labels = [s["label"] for s in subitems if s["label"]]
            if labels:
                tag = "✅ " + "、".join(labels)
                note = f"{len(labels)} 个子项"
            else:
                tag = "❌ 无"
                note = f"用 `；` 分成 {len(subitems)} 组但**组名缺失**，需要医院补【子项名】" if len(subitems) > 1 \
                    else "整项无分组，无需子项裁剪"
            lines.append(f"| `{it['id']}` | {it['level']} | {tag} | {note} |")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true", help="只写缺口清单，不动 exam.json")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    lines = DOCX_TEXT.read_text(encoding="utf-8").split("\n")
    cases = parse_docx_text(lines)

    GAP_REPORT.parent.mkdir(parents=True, exist_ok=True)
    GAP_REPORT.write_text(build_report(cases), encoding="utf-8")
    print(f"缺口清单已写入 {GAP_REPORT.relative_to(ROOT)}")

    if args.report_only:
        return

    # 只重切已有的 5 例；其余 25 例等扩量时再切
    for case_id in SLICED_CASES:
        items = cases.get(case_id) or []
        if not items:
            print(f"  Warning: {case_id} 未在 docx 中找到 A2 段")
            continue

        # 项名/等级/结果沿用已核对过的那份最终数据；没有则退回 data/old 里的旧扁平版
        final_path = CASES_DIR / f"{case_id.lower()}.exam.json"
        legacy_path = ROOT / "data" / "old" / f"{case_id.lower()}.exam.flat.json"
        base_path = final_path if final_path.exists() else legacy_path
        base = json.loads(base_path.read_text(encoding="utf-8")) if base_path.exists() else {"exams": {}}

        exams = {}
        for it in items:
            exam_id = it["id"]
            old = base.get("exams", {}).get(exam_id, {})
            subitems, has_labels = split_aliases(it.get("aliases_raw", ""))
            exams[exam_id] = {
                "label": old.get("label", ""),
                "level": old.get("level", it["level"]),
                "aliases": [a for s in subitems for a in s["aliases"]],   # 扁平并集，兼容旧匹配
                "subitems": subitems,                                     # 医院的子项分组
                "subitems_labelled": has_labels,
                "result": old.get("result"),
                "boundary": it.get("boundary_raw", old.get("boundary", "")),
            }

        out = {"case_id": case_id, "exams": exams}
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        staging = STAGING_DIR / f"{case_id.lower()}.exam.new.json"
        staging.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        n_sub = sum(len(e["subitems"]) for e in exams.values())
        n_lab = sum(1 for e in exams.values() if e["subitems_labelled"])
        print(f"  {case_id}: {len(exams)} 项 → {n_sub} 个子项（{n_lab} 项有标签） → staging/{staging.name}")


if __name__ == "__main__":
    main()
