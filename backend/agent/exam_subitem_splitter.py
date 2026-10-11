"""Exam sub-item splitter — proposes which sentence of an exam result belongs to which sub-item.

**This module only proposes. It never decides.** The model's output is checked by
`scripts/build_exam_v2.py` against hard rules; anything that fails is discarded and
the item falls back to returning its whole `result`.

Why the split exists at all: several E items' 实际返回 say "相关子项请求仅返回该项结果，
不可返回整个 E 项" — a student who asks only for 冷测 must not be handed 叩诊 too.

Why the model cannot be trusted with the text (P1): asking an LLM to *restructure* a
sentence invites silent rewriting/merging/dropping — the exact failure mode seen
repeatedly in this project. So the model is constrained to **selecting spans** of the
original; the validator proves nothing was rewritten (V1) or lost (V2).

Region this touches: structure/metadata only. Every fragment must be a verbatim
substring of `result`, so no medical content is authored here.
"""

import json
import re
from pathlib import Path

from loguru import logger

from agent.llm_client import chat
from app.config import settings

SPLITTER_PROMPT: str | None = None


def _load_prompt() -> str:
    global SPLITTER_PROMPT
    if SPLITTER_PROMPT is None:
        path = Path(__file__).resolve().parent / "prompts" / "exam" / "subitem_splitter.txt"
        SPLITTER_PROMPT = path.read_text(encoding="utf-8")
    return SPLITTER_PROMPT


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def render_groups(groups: list[dict]) -> str:
    """Render alias groups for the prompt, marking which already have a hospital-given name."""
    lines = []
    for i, g in enumerate(groups, 1):
        name = g.get("label")
        head = f"组{i}【{name}】(医院已命名)" if name else f"组{i}（组名缺失，需你补）"
        lines.append(f"{head}：" + " / ".join(g.get("aliases") or []))
    return "\n".join(lines)


async def propose_split(
    item: dict, groups: list[dict], feedback: list[str] | None = None
) -> dict | None:
    """Ask the model how to split one exam item.

    Returns the model's raw proposal ({"subitems": [...]}), or None if the item has no
    result / the call failed. **The caller must validate the result — this makes no
    attempt to check the fragments are faithful.**

    `feedback` carries the validator's rejection reasons from a previous attempt, so the
    model can correct an overlap or a dropped clause instead of the item being given up on.
    """
    if not item.get("result"):
        return None

    prompt = _load_prompt().format(
        label=item.get("label", ""),
        level=item.get("level", ""),
        result=item["result"],
        boundary=item.get("boundary", "（无）"),
        groups=render_groups(groups),
    )

    user_msg = "请按规则输出这一项的切分 JSON。"
    if feedback:
        user_msg += (
            "\n\n注意：你上一次的输出被机器校验否决了，原因如下——\n"
            + "\n".join(f"- {f}" for f in feedback)
            + "\n请改正后重新输出。特别检查：片段之间**不能重叠**，每一句只能归给一个子项，"
            "且拼起来要完整覆盖整条结果。"
        )

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_msg},
    ]

    raw = ""
    try:
        raw = await chat(messages, model=settings.llm_model_pro, temperature=0.0, max_tokens=1024)
        return json.loads(_strip_fences(raw))
    except json.JSONDecodeError as e:
        logger.error(f"[Splitter] {item.get('label')!r} JSON 解析失败: {e}, raw={raw[:200]!r}")
    except Exception as e:
        logger.error(f"[Splitter] {item.get('label')!r} 调用失败: {e}")
    return None
