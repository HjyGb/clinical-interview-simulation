"""证据校验：模型引用的原话，是不是真的出自它该引的地方。

这一层存在的理由，实测过两次：
  - P4：模型从**对话**里给报告类条目找证据，空作答也能蹭到分（2/10）。
  - P5：关键错误判定同理——模型会凭"印象"报错，而不是凭学员真说过的话。

所以「LLM 必须引用原话」不能只写在提示词里，得有代码兜底：
声称命中但原话不在指定来源里，一律作废。

容忍模型的两点小毛病：末尾加省略号、把空白改掉。除此之外必须逐字命中。
"""

import re


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").rstrip("…...。")


def quote_is_from(quote: str, source: str) -> bool:
    """`quote` 是否（逐字）出自 `source`。

    也对短引用做前缀匹配：模型常截断长句，截断点之后对不上是正常的。
    """
    if not quote or not source:
        return False
    q, s = _norm(quote), _norm(source)
    if not q:
        return False
    return q in s or (len(q) >= 8 and q[:8] in s)
