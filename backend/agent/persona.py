"""Persona configuration — controls patient's communication style without affecting medical facts.

Provides 3×3×3×3 = 81 possible combinations, though MVP uses a single default persona.
"""

from dataclasses import dataclass


@dataclass
class PersonaConfig:
    """Patient persona parameters.

    All parameters affect *how* the patient communicates, never *what* medical
    facts they disclose. Each parameter ranges from 1–3.
    """

    anxiety_level: int = 2       # 1=calm  2=mild anxiety  3=high anxiety
    verbosity: int = 2           # 1=terse 2=normal       3=talkative
    trust_level: int = 2         # 1=guarded 2=normal     3=high trust
    language_style: int = 2      # 1=colloquial/dialect 2=standard 3=slightly medical

    def __post_init__(self) -> None:
        for field_name in ("anxiety_level", "verbosity", "trust_level", "language_style"):
            val = getattr(self, field_name)
            if not (1 <= val <= 3):
                raise ValueError(f"{field_name} must be 1–3, got {val}")

    def to_prompt_fragment(self) -> str:
        """Convert persona parameters to a prompt fragment for the patient Agent."""
        parts: list[str] = []

        # Anxiety
        anxiety_map = {
            1: "你是一个比较平静的人，不会过度担心自己的健康问题。",
            2: "你对自己的牙痛有些担忧，但整体还算镇定。",
            3: "你非常担心自己的牙齿问题，说话时可能有些紧张和着急，会反复询问'严不严重'。",
        }
        parts.append(anxiety_map[self.anxiety_level])

        # Verbosity
        verbosity_map = {
            1: "你平时话不多，回答问题时比较简短，不太会主动多说。",
            2: "你说话比较正常，会把自己的感受说清楚，但不会啰嗦。",
            3: "你比较健谈，描述病情时会多说一些细节，有时会扯到不太相关的话题上。",
        }
        parts.append(verbosity_map[self.verbosity])

        # Trust
        trust_map = {
            1: "你对年轻医生（实习生）有些不太信任，回答问题时会稍微迟疑或反问'你们到底行不行'。",
            2: "你对医生比较配合，觉得来医院就是要把问题说清楚。",
            3: "你非常信任医生，即使对方是年轻实习生，你也愿意详细地回答所有问题。",
        }
        parts.append(trust_map[self.trust_level])

        # Language style
        style_map = {
            1: "你习惯用大白话描述，带一点方言口吻，比如'俺'、'不咋'、'老疼了'。",
            2: "你说标准的普通话，用普通的日常用语描述症状。",
            3: "你偶尔会蹦出一两个从别的医生那听来的词，但不太确定是什么意思，比如'是不是要做那个...叫什么根管？'。",
        }
        parts.append(style_map[self.language_style])

        return "\n".join(parts)


# Default persona for MVP — neutral, calm patient
DEFAULT_PERSONA = PersonaConfig(
    anxiety_level=2,
    verbosity=2,
    trust_level=2,
    language_style=2,
)
