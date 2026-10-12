#!/usr/bin/env python3
"""L2 —— 统计「学员常问、但病例没设定」的信息，产出给医院的资料缺口清单。

**为什么做这个**：问诊中必然有人问喝酒、家族史、熬夜这类**生活细节**，
而病例只写了 H01–H07。医院的规定是"未设定就标 NEEDS_CASE_COMPLETION"（见
`_docx.txt:83`），但更根本的问题是——**这些信息该不该补进病例**？
那是数据问题，不是模拟问题，只有医院能定。

所以这里不生成任何患者台词，只**统计**：哪些常见问题在哪些病例上落进了 `unknown`。
产出一张表，下次对接时直接给医院看。

探针是**常见问诊条目**的固定清单（不是真实学员流量）。真实流量统计要等有学生用；
在那之前，这份清单已经足够说明问题。

Usage:
    python scripts/report_data_gaps.py                    # 5 例
    python scripts/report_data_gaps.py --cases EN01,PE01
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from fastapi.testclient import TestClient  # noqa: E402
from loguru import logger  # noqa: E402

logger.remove()
for _n in ("sqlalchemy", "sqlalchemy.engine"):
    logging.getLogger(_n).disabled = True

from app.main import app  # noqa: E402

CASES = ["EN01", "PE01", "PR01", "MU01", "SU01"]

# 常见问诊条目。挑的是"牙科问诊里正常会问到、但多半不在 H01–H07 里"的那些。
PROBES = [
    ("吸烟", "你平时抽烟吗？"),
    ("饮酒", "你平时喝酒吗？"),
    ("家族史", "你家里人有没有类似的牙齿问题？"),
    ("睡眠", "你最近睡眠怎么样？"),
    ("夜磨牙", "你睡觉会磨牙或者咬牙吗？"),
    ("近期发热", "最近有没有感冒发烧？"),
    ("长期用药", "你平时在吃什么长期吃的药吗？"),
    ("洗牙史", "你以前洗过牙吗？"),
    ("刷牙习惯", "平时一天刷几次牙？"),
    ("工作压力", "你平时工作压力大吗？"),
    ("体重变化", "最近体重有没有明显变化？"),
    ("月经妊娠", "你最近有怀孕或者哺乳吗？"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", default=",".join(CASES))
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    client = TestClient(app)
    token = client.post("/api/v1/auth/login",
                        json={"username": "test001", "password": "123456"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    cases = {c["title"]: c for c in client.get("/api/v1/cases", headers=headers).json()["cases"]}
    wanted = [c.strip() for c in args.cases.split(",") if c.strip() in cases]

    # gap[topic][case] = True 表示该病例没有这项信息
    gap: dict[str, dict[str, bool]] = {t: {} for t, _ in PROBES}
    sessions = []
    for cid in wanted:
        for topic, q in PROBES:
            sid = client.post("/api/v1/sessions", json={"case_id": cases[cid]["id"]},
                              headers=headers).json()["id"]
            sessions.append(sid)
            resp = client.post(f"/api/v1/sessions/{sid}/messages",
                               json={"content": q}, headers=headers)
            qtype = None
            for block in resp.text.split("\n\n"):
                nm = pl = None
                for line in block.split("\n"):
                    if line.startswith("event: "):
                        nm = line[7:].strip()
                    elif line.startswith("data: "):
                        pl = line[6:]
                if nm == "done" and pl:
                    qtype = json.loads(pl).get("question_type")
            gap[topic][cid] = qtype == "unknown"

    print(f"资料缺口统计 · {len(wanted)} 例 × {len(PROBES)} 个常见问诊条目\n")
    header = "条目".ljust(10) + "".join(c.rjust(7) for c in wanted) + "   缺失数"
    print(header)
    print("-" * len(header))
    lines = ["| 条目 | " + " | ".join(wanted) + " | 缺失 |",
             "|---|" + "---|" * (len(wanted) + 1)]
    for topic, _ in PROBES:
        cells = ["✗" if gap[topic][c] else "✓" for c in wanted]
        n = sum(1 for c in wanted if gap[topic][c])
        print(topic.ljust(10) + "".join(x.rjust(7) for x in cells) + f"   {n}/{len(wanted)}")
        lines.append(f"| {topic} | " + " | ".join(cells) + f" | {n}/{len(wanted)} |")

    print("\n（✗ = 该病例未设定，问到时系统提示「模拟资料不足」；✓ = 能从既有事实回答）")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "data" / "tests" / f"data_gap_report_{ts}.json"
    out.write_text(json.dumps({"cases": wanted, "gap": gap}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    md = ROOT / "data" / "tests" / f"data_gap_report_{ts}.md"
    md.write_text(f"# 病例资料缺口统计（{ts}）\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"→ {md.relative_to(ROOT)}")

    for sid in sessions:
        client.delete(f"/api/v1/sessions/{sid}", headers=headers)
    print(f"已清理 {len(sessions)} 个测试会话")


if __name__ == "__main__":
    main()
