"""Scoring package — R01–R14 assessment for the clinical interview simulator.

Split by what each part needs:

    sub_anchors.py   把一条 R 拆成可判定的最小单元（纯逻辑）
    aggregate.py     子锚点命中 → 项分 0/1/2（纯逻辑）
    deterministic.py R01–R04 的纯 Python 判定（读披露轨迹与检查申请轨迹，不调 LLM）

设计依据见 docs/scoring-system-design.md。
"""
