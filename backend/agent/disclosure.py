"""Disclosure gate — decides which facts this turn may use, and records the trace.

Pure Python, no LLM. It sits between the selector (which says *what was asked*)
and the generator (which says it in character), and it is the only place that
decides *what may be disclosed*.

Two things it enforces structurally rather than by prompt discipline:

  1. **Only H/P can ever be allowed.** The candidate set comes from
     `build_facts_catalog`, which reads `facts` / `psychology` and nothing else.
     A model that hallucinates an ID gets it dropped here.
  2. **Open questions expand to the scripted range.** The docx says an open
     question lets the patient narrate H01–H04; the selector only reports
     "this is open", and the expansion happens here.

Replaces `info_retriever` (INTENT_FIELD_MAP / TIER_ALLOWED_SECTIONS).
"""

from loguru import logger

from agent.fact_selector import ERROR_QUESTION_TYPE, OPEN_QUESTION_DEFAULT, build_facts_catalog


def gate(case_data: dict, selector_result: dict) -> dict:
    """Turn the selector's verdict into this turn's allowed facts.

    Args:
        case_data: The case's patient data.
        selector_result: Output of `fact_selector.select_facts`.

    Returns:
        {
          "question_type": "open"|"targeted"|"meta",
          "allowed_facts": {fact_id: {"label", "text"}},   # 本轮可以引用的
          "disclosed": [fact_id, ...],                      # 写进披露轨迹的
        }
    """
    catalog = {f["id"]: f for f in build_facts_catalog(case_data)}
    question_type = selector_result.get("question_type", "targeted")
    asked = selector_result.get("asked_facts") or []

    # exam 在到达门控之前就已被 patient_agent 分流给检查模块；列在这里只是兜底，
    # 保证"检查请求永远不会拿到患者事实"这一条在门控层也成立。
    if question_type in ("meta", "unknown", "exam", ERROR_QUESTION_TYPE):
        # 越权请求 / 患者本人但数据没有：一个事实都不给。
        # 真正的防线是数据边界——D/DD/T/G/R 根本不在 case_data 里，
        # 所以即便是 meta，模型也无从泄露，只是"答不上来"。
        allowed_ids: list[str] = []
    elif question_type == "open":
        # 开放式问诊：按脚本给 H01–H04，再并入 selector 额外点中的（去重、保序）
        allowed_ids = [i for i in OPEN_QUESTION_DEFAULT if i in catalog]
        allowed_ids += [i for i in asked if i in catalog and i not in allowed_ids]
    else:
        allowed_ids = [i for i in asked if i in catalog]

    dropped = [i for i in asked if i not in catalog]
    if dropped:
        logger.warning(f"[Disclosure] dropped unknown fact ids {dropped}")

    allowed_facts = {i: catalog[i] for i in allowed_ids}

    logger.debug(f"[Disclosure] {question_type} → allowed {allowed_ids}")

    return {
        "question_type": question_type,
        "allowed_facts": allowed_facts,
        "disclosed": allowed_ids,
    }


def to_generator_facts(allowed_facts: dict) -> dict[str, str]:
    """Flatten the gate's output into the {label: text} shape the generator expects."""
    return {
        f"{fact_id} {item['label']}": item["text"]
        for fact_id, item in allowed_facts.items()
    }
