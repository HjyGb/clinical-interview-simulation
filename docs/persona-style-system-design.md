# 患者 AI 性格风格系统 — 设计方案

> 状态：方案设计阶段 | 代码基础已就绪 | 待激活开发  
> 最后更新：2026-08-02

---

## 一、当前状态

### 1.1 已就绪的基础设施

[backend/agent/persona.py](backend/agent/persona.py) 中 `PersonaConfig` 已完整实现：

```python
@dataclass
class PersonaConfig:
    anxiety_level: int = 2    # 1=平静  2=轻度担忧  3=高度紧张
    verbosity: int = 2        # 1=寡言  2=正常      3=健谈
    trust_level: int = 2      # 1=戒备  2=配合      3=高度信任
    language_style: int = 2   # 1=方言  2=标准普通话  3=略懂术语
```

- `to_prompt_fragment()` 将 4 个参数转为自然语言 prompt 片段
- `session` 表已有 `persona` JSON 列存储快照
- `system_base.txt` 和 `response_generator.txt` 已预留 `{persona_style}` 占位符
- Patient Agent 流水线接受 `persona: PersonaConfig` 参数

**4×3×3×3 = 81 种组合已就绪，仅缺激活逻辑。**

### 1.2 当前枷锁点（3处）

| # | 文件:行 | 当前行为 | 需改为 |
|---|---------|----------|--------|
| 1 | `session_service.py:22-27` | 硬编码 4 个 `2` | 从 case 配置或用户选择读取 |
| 2 | `session_service.py:42` | `get_opening_statement(case_data, DEFAULT_PERSONA)` | 传入实际 persona |
| 3 | `session_service.py:156` | `process_message(...)` 未传 persona | 从 session 读取并传入 |

---

## 二、四级风格体系设计

### 2.1 维度详解

#### 焦虑水平（anxiety_level）

决定患者对话中的情绪基调。不影响医学事实，只影响表达方式和辅助行为。

| 级别 | 值 | Prompt 片段 | 行为预期 |
|------|-----|-------------|----------|
| 平静 | 1 | "你是一个比较平静的人，不会过度担心自己的健康问题。" | 回答直接，不过度追问，不会反复确认 |
| 轻度担忧 | 2 | "你对自己的牙痛有些担忧，但整体还算镇定。" | 偶尔表达担心，配合问诊但略显不安 |
| 高度紧张 | 3 | "你非常担心自己的牙齿问题，说话时可能有些紧张和着急，会反复询问'严不严重'。" | 频繁反问"严重吗"、"要拔牙吗"，可能抢话，需要安抚 |

#### 话量（verbosity）

决定患者回答的长度和主动扩展程度。

| 级别 | 值 | Prompt 片段 | 行为预期 |
|------|-----|-------------|----------|
| 寡言 | 1 | "你平时话不多，回答问题时比较简短，不太会主动多说。" | 单句回答，不主动补充，学生不问就不说完整 |
| 正常 | 2 | "你说话比较正常，会把自己的感受说清楚，但不会啰嗦。" | 2-3 句回答，覆盖问题要点 |
| 健谈 | 3 | "你比较健谈，描述病情时会多说一些细节，有时会扯到不太相关的话题上。" | 3-5 句回答，附带无关细节（"对了，我邻居说..."），学生需提炼关键信息 |

#### 信任度（trust_level）

决定患者对"年轻实习生"问诊的配合程度，直接影响信息获取效率。

| 级别 | 值 | Prompt 片段 | 行为预期 |
|------|-----|-------------|----------|
| 戒备 | 1 | "你对年轻医生（实习生）有些不太信任，回答问题时会稍微迟疑或反问'你们到底行不行'。" | 回答犹豫，可能反问/质疑，需要更多安抚才能获取完整信息 |
| 配合 | 2 | "你对医生比较配合，觉得来医院就是要把问题说清楚。" | 正常配合，如实回答 |
| 高度信任 | 3 | "你非常信任医生，即使对方是年轻实习生，你也愿意详细地回答所有问题。" | 主动配合，甚至主动补充"对了医生还说过..." |

#### 语言风格（language_style）

决定患者的语言习惯，影响学生理解难度。

| 级别 | 值 | Prompt 片段 | 行为预期 |
|------|-----|-------------|----------|
| 方言口语 | 1 | "你习惯用大白话描述，带一点方言口吻，比如'俺'、'不咋'、'老疼了'。" | 使用方言词汇，表达模糊（"那块儿不得劲"），学生需追问澄清 |
| 标准普通话 | 2 | "你说标准的普通话，用普通的日常用语描述症状。" | 清晰日常表达，无理解障碍 |
| 略懂术语 | 3 | "你偶尔会蹦出一两个从别的医生那听来的词，但不太确定是什么意思，比如'是不是要做那个...叫什么根管？'。" | 掺杂半懂不懂的医学术语，可能误导学生或提供额外线索 |

### 2.2 预置风格组合（5 种推荐配置）

从 81 种组合中精选 5 种实用配置，覆盖从最简单到最困难：

| 预设名 | 焦虑 | 话量 | 信任 | 语言 | 难度 | 适用场景 |
|--------|------|------|------|------|------|----------|
| **neutral** | 2 | 2 | 2 | 2 | ★★ | 默认：标准患者（当前 MVP 唯一使用） |
| **easy** | 1 | 2 | 3 | 2 | ★ | 新手友好：平静+信任高，信息容易获取 |
| **difficult** | 3 | 1 | 1 | 1 | ★★★★ | 挑战：紧张+寡言+不信任+方言，多维度沟通障碍 |
| **talkative** | 1 | 3 | 2 | 2 | ★★☆ | 信息量大考验：健谈但夹杂无关细节，考察信息提炼能力 |
| **guarded** | 2 | 1 | 1 | 2 | ★★★ | 冷面患者：寡言+不信任，每个信息点都需要技巧性追问 |

### 2.3 预置风格的 prompt 拼接效果

以 **difficult** 为例（焦虑=3, 话量=1, 信任=1, 语言=1），`to_prompt_fragment()` 输出：

```
你非常担心自己的牙齿问题，说话时可能有些紧张和着急，会反复询问"严不严重"。
你平时话不多，回答问题时比较简短，不太会主动多说。
你对年轻医生（实习生）有些不太信任，回答问题时会稍微迟疑或反问"你们到底行不行"。
你习惯用大白话描述，带一点方言口吻，比如"俺"、"不咋"、"老疼了"。
```

---

## 三、激活方案设计

### 方案 A：按病例难度自动匹配（推荐：P0 优先实现）

**逻辑**：根据 `case.difficulty` 字段自动选择 persona 预设。

| 病例难度 | persona 预设 | 设计意图 |
|----------|-------------|----------|
| `beginner` | **easy** (1,2,3,2) | 降低沟通难度，让学生聚焦诊断本身 |
| `intermediate` | **neutral** (2,2,2,2) | 标准患者，问诊与诊断兼顾 |
| `advanced` | **difficult** (3,1,1,1) | 沟通+诊断双高难度，模拟真实疑难场景 |

**优势**：零前端改动，自动生效，教师无需额外配置  
**改动点**：仅 `session_service.py` 中 `create_session()` 一处

```python
# 伪代码
PERSONA_BY_DIFFICULTY = {
    "beginner": PersonaConfig(anxiety_level=1, verbosity=2, trust_level=3, language_style=2),
    "intermediate": PersonaConfig(anxiety_level=2, verbosity=2, trust_level=2, language_style=2),
    "advanced": PersonaConfig(anxiety_level=3, verbosity=1, trust_level=1, language_style=1),
}

def create_session(...):
    difficulty = case.difficulty  # "beginner" | "intermediate" | "advanced"
    persona = PERSONA_BY_DIFFICULTY.get(difficulty, DEFAULT_PERSONA)
    ...
```

### 方案 B：前端学生自选（P1）

在 `CaseListPage` 或进入问诊前增加 persona 选择器，让学生自主决定练习难度。

```tsx
// 进入问诊前弹出
<PersonaSelector
  options={['easy', 'neutral', 'difficult', 'talkative', 'guarded']}
  selected={selected}
  onChange={setSelected}
/>
```

将 `persona_preset` 作为 `POST /api/v1/sessions` 的可选参数传递。

### 方案 C：Session 级别恢复 persona（必须修复的 Bug）

当前 `session.persona` 存储了快照，但 `add_student_message()` 不读取它，导致后续消息全部回退 `DEFAULT_PERSONA`。

**修复**：在 `add_student_message()` 中从 `session.persona` JSON 重建 `PersonaConfig` 并传入 `process_message()`。

```python
# session_service.py add_student_message()
stored = session.persona
persona = PersonaConfig(
    anxiety_level=stored["anxiety_level"],
    verbosity=stored["verbosity"],
    trust_level=stored["trust_level"],
    language_style=stored["language_style"],
)
async for event in process_message(..., persona=persona):
    ...
```

### 方案 D：教师后台配置面板（P2）

教师端增加病例 persona 绑定配置：可为每个病例单独指定 persona 组合，覆盖难度默认值。

---

## 四、需改动的文件清单

| 优先级 | 文件 | 改动内容 |
|--------|------|----------|
| **P0** | `backend/agent/persona.py` | 增加 `PERSONA_PRESETS` 字典和 `PERSONA_BY_DIFFICULTY` 映射 |
| **P0** | `backend/app/services/session_service.py` | `create_session()` 按 case 难度选 persona；`add_student_message()` 从 session 恢复 persona |
| **P0** | `backend/app/schemas/session.py` | Session 响应增加 `persona` 字段（可选：前端展示当前患者风格） |
| **P1** | `frontend/src/types/index.ts` | SessionInfo 增加 `persona` 类型 |
| **P1** | `frontend/src/pages/CaseListPage.tsx` | 进入问诊前可选 persona 选择器 |
| **P2** | `backend/agent/prompts/persona/` | 创建独立 persona prompt 片段文件（精细化控制，替代纯 Python 字符串） |
| **P2** | 教师管理后台 | 病例-persoa 绑定配置界面 |

---

## 五、技术注意事项

### 5.1 persona 不影响评估

Persona 仅改变 **患者的表达方式**，不改变 **可披露的医学事实**。评估标准（Station 4 / MAAS-Global）的评分维度与 persona 正交：
- Station 4 考察诊断准确性和信息采集完整性——学生能否从不同 persona 的患者口中获取相同的关键信息
- MAAS-Global 考察沟通能力——高难度 persona 确实会增加沟通技巧的权重，这与真实临床场景一致

### 5.2 persona 不泄露 Tier 4

无论 persona 的信任度多高、话量多大，`system_base.txt` 中的规则 2（不透露诊断/治疗方案）和规则 1（不编造医学事实）的优先级始终高于 persona 风格指令。

### 5.3 兼容性

- `PersonaConfig` 是纯数据类，序列化到 JSON 再反序列化完全无损
- 旧 session（persona 列已存 `{2,2,2,2}`）向后兼容——重建后行为和当前完全一致
- 如果未来新增维度，`PersonaConfig` 只需加字段，旧 session 反序列化时使用默认值

### 5.4 风格参数边界

`PersonaConfig.__post_init__` 已有校验：每个参数必须在 1-3 范围内。确保不会因输入错误导致异常 prompt。

---

## 六、实施路线图

```
Phase 1 (P0): 基础激活 — 按难度自动匹配    预计半天
  ├── persona.py: 添加 PRESETS + DIFFICULTY_MAP
  ├── session_service.py: create_session 选 persona
  ├── session_service.py: add_student_message 恢复 persona
  └── 测试: beginner/intermediate/advanced 各开一个会话验证风格差异

Phase 2 (P1): 学生自选                          预计半天
  ├── 后端: 新增 persona_preset 参数 → POST /sessions
  ├── 前端: CaseListPage 增加 persona 选择器 UI
  └── 前端: 选择后传入 createSession

Phase 3 (P2): 独立 prompt 文件 + 教师面板       预计 1-2 天
  ├── persona/ 目录创建独立 .txt 文件
  ├── PersonaConfig.to_prompt_fragment() 改为读取文件
  ├── 教师端病例-persoa 绑定 UI
  └── 教师端全局默认 persona 设置

Phase 4 (P3): 精细化控制                        视需求
  ├── 新增维度？（如 cooperativeness, emotional_lability）
  ├── 多人格切换（同一病例可体验不同风格对比学习）
  └── persona 效果评估（学生评分与 persona 难度的相关性分析）
```

---

## 七、相关文件索引

| 文件 | 角色 |
|------|------|
| [backend/agent/persona.py](backend/agent/persona.py) | PersonaConfig 数据类 + 81 组合 + DEFAULT_PERSONA |
| [backend/agent/patient_agent.py](backend/agent/patient_agent.py) | Pipeline 编排，接受 persona 参数 |
| [backend/agent/response_generator.py](backend/agent/response_generator.py) | 将 persona_style 注入 system + user prompt |
| [backend/agent/prompts/patient/system_base.txt](backend/agent/prompts/patient/system_base.txt) | 患者 system prompt（含 `{persona_style}` 占位） |
| [backend/agent/prompts/patient/response_generator.txt](backend/agent/prompts/patient/response_generator.txt) | 患者 user prompt（含 `{persona_style}` 占位） |
| [backend/app/services/session_service.py](backend/app/services/session_service.py) | Session 创建与消息处理（需改动 3 处） |
| [backend/app/models/session.py](backend/app/models/session.py) | Session 模型（`persona` JSON 列） |
| [backend/agent/prompts/persona/.gitkeep](backend/agent/prompts/persona/.gitkeep) | 预留目录（Phase 3 使用） |
