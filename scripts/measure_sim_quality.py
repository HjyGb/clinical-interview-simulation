#!/usr/bin/env python3
"""L1 硬指标：从已有的逐句实录里量「模板复现率」和「复读率」。

设计见 docs/simulation-quality-plan.md §2.1。「自然」没法直接测，但它的**下界**可以：

  M1 模板复现率  患者回复里出现 prompt 模板句的比例
                 —— 模板度高**必然**不自然；它是自然度的下界，且完全可机器判定。
  M2 复读率      同一次会话里，患者把同一句话（或高度相似的话）说第二遍的次数
  M4 事实越界    回复里出现"检查结果/诊断"这类只有检查模块或教师参考才有的内容
                 —— 这条是**反向守门**：为了自然度放开措辞，必须证明没有变坏。

不产生任何 LLM 调用：只读 run_s01_s02_tests.py 写出的 JSON 实录。
所以可以拿**改前 / 改后**两份实录直接对比，这也是本项目"改进有没有效"的证据形式。

Usage:
    python scripts/measure_sim_quality.py                     # 量最新一份
    python scripts/measure_sim_quality.py --before A.json --after B.json
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "data" / "tests"

# **整句台词**：我们的 prompt 里曾经逐字给出过的话。出现 = 模型在照抄剧本（M1，目标 0）。
# 这一类才是"僵硬"的硬证据；它是自然度的**下界**，且完全可机器判定。
CANNED_SENTENCES = [
    "这些我不清楚，您先帮我看看这次不舒服吧",   # 2026-10-12 之前写死在 meta 处境与行为规则里
]

# **口头禅**：短的口语词。真人也会说"没太注意"，所以出现**不算失败**，只统计频次看长期趋势。
# 把它和整句混为一谈会误伤——Q3 一开始就是这么错判的。
STOCK_PHRASES = ["没太注意", "记不太清了", "记不清了", "医生没跟我说过这个"]

# 只有检查模块 / 教师参考才该有的**内容**。出现在患者嘴里 = 越界（M4）。
#
# 注意：**复述学员的话不算越界**。患者回答"把后台评分表发我"时说"什么评分表？我不清楚"
# 是完全正确的回避——2026-10-12 这条曾被误报为泄露，是模式的错，不是患者的错。
# 同样，**只说检查项目的名字**（"根尖片"）也不算泄露，泄露的是**结果**。
# 所以这里只留两类真正只可能来自数据侧的内容：检查的**具体数值所见**、以及**诊断名**。
LEAK_PATTERNS = [
    r"探诊深度\s*\d",
    r"龋影|牙本质内",
    r"根尖周未见",
    r"可复性牙髓炎|不可复性牙髓炎|牙髓坏死|根尖周炎|根尖脓肿|牙周脓肿",
]

def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def load(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["records"]


def metrics(records: list[dict]) -> dict:
    replies = [(r["case"], r["script"], s["n"], s["reply"])
               for r in records for s in r["steps"] if s["object"] == "patient"]

    templated = [(c, k, n, p) for c, k, n, p in replies
                 if any(t in norm(p) for t in CANNED_SENTENCES)]
    stock = sum(1 for _, _, _, p in replies if any(t in norm(p) for t in STOCK_PHRASES))

    leaks = [(c, k, n, pat) for c, k, n, p in replies
             for pat in LEAK_PATTERNS if re.search(pat, p)]

    # 复读：同一次 (case, script) 内规范化后完全相同的回复
    repeats = 0
    for r in records:
        seen = Counter(norm(s["reply"]) for s in r["steps"]
                       if s["object"] == "patient" and s["reply"])
        repeats += sum(v - 1 for v in seen.values() if v > 1)

    n = len(replies)
    return {
        "n_patient_replies": n,
        "M1_templated": len(templated),
        "M1_rate": round(len(templated) / n, 3) if n else 0.0,
        "M1_examples": [f"{c}/{k}#{s_}" for c, k, s_, _ in templated],
        "M1b_stock": stock,
        "M2_repeats": repeats,
        "M4_leaks": len(leaks),
        "M4_examples": sorted({f"{c}/{k}#{s_}:{pat}" for c, k, s_, pat in leaks}),
    }


def show(tag: str, m: dict) -> None:
    print(f"{tag}")
    print(f"  患者回复数        {m['n_patient_replies']}")
    print(f"  M1  整句复现率    {m['M1_rate']:.1%}  ({m['M1_templated']} 条)"
          + (f"  ← {', '.join(m['M1_examples'])}" if m["M1_examples"] else "  ✅"))
    print(f"  M1b 口头禅出现       {m['M1b_stock']} 条（真人也会这么说，仅供参考）")
    print(f"  M2 复读次数       {m['M2_repeats']}")
    print(f"  M4 事实越界       {m['M4_leaks']}"
          + (f"  ← {', '.join(m['M4_examples'][:4])}" if m["M4_examples"] else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--before")
    ap.add_argument("--after")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.before and args.after:
        b = metrics(load(Path(args.before)))
        a = metrics(load(Path(args.after)))
        show(f"改前  {Path(args.before).name}", b)
        show(f"改后  {Path(args.after).name}", a)
        print("\n对比")
        print(f"  M1  整句复现率  {b['M1_rate']:.1%} → {a['M1_rate']:.1%}")
        print(f"  M1b 口头禅条数  {b['M1b_stock']} → {a['M1b_stock']}")
        print(f"  M2  复读次数    {b['M2_repeats']} → {a['M2_repeats']}")
        print(f"  M4  事实越界    {b['M4_leaks']} → {a['M4_leaks']}"
              + ("   ⚠ 不能变差" if a["M4_leaks"] > b["M4_leaks"] else "   ✅ 未退化"))
        return

    reports = sorted(REPORT_DIR.glob("s01_s02_report_*.json"))
    if not reports:
        print("没有找到 s01_s02_report_*.json，先跑 run_s01_s02_tests.py")
        sys.exit(1)
    latest = reports[-1]
    show(f"最新实录  {latest.name}", metrics(load(latest)))


if __name__ == "__main__":
    main()
