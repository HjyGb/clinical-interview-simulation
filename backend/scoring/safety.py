"""安全通道 —— 关键错误独立标记，绝不参与分数。

医院原文（`_docx.txt:100`）：

> 「**危及安全的错误另行标记并由教师复核，不与礼貌分平均抵消。**」

这一句直接判了旧评估链路的死刑：旧的 `(诊断 + 沟通) / 2` 恰恰在做被明令禁止的事。
所以在 R14 框架里，安全错误**不是扣分项**，而是**并行的另一个输出**：

    28 分原始分           ← 临床 + 沟通，正常算
    safety_flags          ← 独立列出，不进任何求和、不被任何礼貌分抵消
    requires_review       ← 有任何一条命中就为真，交教师复核

两条代码兜底（同 P4 的理由，见 evidence.py）：
  1. 命中必须引用学员原话，**原话不在学员文本里的一律不算命中**。
  2. 判定失败 → 标记为"未能复核"，**不当作"没犯错"**——那是把系统故障伪装成安全通过。

另外提供 SU05 类**安全优先例**的识别：识别到危险后应立即转诊，不要求跑完清单，
未跑完的条目按医院规则标 `SKIPPED_SAFETY`（不是 0 分）。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from agent.llm_client import chat
from app.config import settings
from scoring.evidence import quote_is_from

PROMPT: str | None = None
PROMPT_PATH = Path(__file__).resolve().parent.parent / "agent" / "prompts" / "scoring" / "critical_error.txt"

# 提示词里判"学员是否识别危险并及早转诊"的那一次调用
STOP_PROMPT = """下面是一段医学生与患者的对话。该患者属于**安全优先例**：一旦识别出气道或深部感染风险，
应立即安排转诊，不要求跑完常规问诊与检查清单。

请判断：**该学员是否识别到了危险并安排了转诊/急诊？**

## 对话记录
{conversation}

只输出一个 JSON 对象：
{{"stopped": true, "evidence_quote": "学员的原话", "reason": "一句话"}}

`stopped: true` 仅当学员**确实**表达了对危险的认识并（或）安排转诊。
注意：学员只是照常问诊、没有识别危险，应判 false。
"""


@dataclass
class SafetyFlag:
    index: int
    error: str
    hit: bool = False
    evidence_quote: str = ""
    evidence_ref: str = ""
    checked: bool = True          # False = 复核没跑成，不能当成"没犯错"


@dataclass
class SafetyReport:
    flags: list[SafetyFlag] = field(default_factory=list)
    stopped_early: bool = False
    stop_evidence: str = ""

    @property
    def hits(self) -> list[SafetyFlag]:
        return [f for f in self.flags if f.hit]

    @property
    def unchecked(self) -> list[SafetyFlag]:
        return [f for f in self.flags if not f.checked]

    @property
    def requires_review(self) -> bool:
        """命中**或**没复核成都需要人看——后者不是"安全通过"。"""
        return bool(self.hits or self.unchecked)


def _load_prompt() -> str:
    global PROMPT
    if PROMPT is None:
        PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
    return PROMPT


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def critical_errors_of(rubric: dict) -> list[str]:
    return [e for e in (rubric.get("critical_errors") or []) if e.strip()]


def is_safety_priority_case(rubric: dict) -> bool:
    """该例是否"安全优先例"——判据是 A3 页有没有那条安全优先规则（目前只有 SU05）。"""
    return any("安全优先" in r or "SKIPPED_SAFETY" in r for r in (rubric.get("extra_rules") or []))


async def check_critical_errors(rubric: dict, student_report: dict | None,
                                history: list[dict]) -> SafetyReport:
    """逐条判关键错误。任何异常 → 该条标 `checked=False`（不许当成没犯错）。"""
    from scoring.llm_judge import _render_conversation, _render_report  # 复用同一套渲染

    errors = critical_errors_of(rubric)
    report = SafetyReport()
    if not errors:
        return report

    report.flags = [SafetyFlag(index=i + 1, error=e) for i, e in enumerate(errors)]

    student_text = f"{_render_report(student_report)}\n{_render_conversation(history)}"
    listing = "\n".join(f"{i + 1}. {e}" for i, e in enumerate(errors))
    prompt = _load_prompt().format(
        critical_errors=listing,
        student_report=_render_report(student_report),
        conversation=_render_conversation(history),
    )

    try:
        raw = await chat([{"role": "user", "content": prompt}],
                         model=settings.llm_model_pro, temperature=0.0, max_tokens=1024)
        data = _parse_json(raw)
        by_index = {int(f.get("index", 0)): f for f in data.get("flags", [])}
        for flag in report.flags:
            got = by_index.get(flag.index)
            if got is None:
                flag.checked = False
                continue
            quote = (got.get("evidence_quote") or "").strip()
            claimed = bool(got.get("hit"))
            # 代码兜底：原话不在学员文本里 → 不算命中
            if claimed and not quote_is_from(quote, student_text):
                logger.warning(f"[Safety] 第{flag.index}条声称命中，但引文不在学员文本中，作废")
                claimed = False
                quote = ""
            flag.hit = claimed
            flag.evidence_quote = quote
            flag.evidence_ref = (got.get("evidence_ref") or "").strip()
    except Exception as e:
        logger.error(f"[Safety] 关键错误复核失败，全部标为未复核：{e}")
        for flag in report.flags:
            flag.checked = False

    return report


async def detect_safety_stop(rubric: dict, history: list[dict]) -> tuple[bool, str]:
    """安全优先例专用：学员是否识别危险并及早转诊。返回 (是否早停, 证据原话)。"""
    from scoring.llm_judge import _render_conversation

    if not is_safety_priority_case(rubric):
        return False, ""
    conversation = _render_conversation(history)
    try:
        raw = await chat([{"role": "user", "content": STOP_PROMPT.format(conversation=conversation)}],
                         model=settings.llm_model_pro, temperature=0.0, max_tokens=512)
        data = _parse_json(raw)
        quote = (data.get("evidence_quote") or "").strip()
        stopped = bool(data.get("stopped")) and quote_is_from(quote, conversation)
        return stopped, quote if stopped else ""
    except Exception as e:
        logger.error(f"[Safety] 早停识别失败：{e}")
        return False, ""
