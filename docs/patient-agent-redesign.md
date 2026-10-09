# 患者 Agent 改造方案（MVP 阶段）

> 目标：用新数据（`*.patient.json`）把「病人对话」核心链路跑通，优先做 MVP。
> 范围：只改患者侧。检查模块后置（真实 SP 场景里检查结果由图片/提示卡交给学生，不由患者说出）。
> 日期：2026-10-09。**本文档只做设计，不含代码改动。**

---

## 一、现状：当前 Agent 的架构 / prompt / 数据流

### 1.1 数据流（已逐文件核对）

```
DB cases.data  (JSON blob)
   │  case_service.get_case_full()            app/services/case_service.py:82
   ▼
API 层 sessions.py                           app/api/sessions.py:39, 94
   │  把 case["data"] 原样传下去
   ▼
session_service                              app/services/session_service.py:44, 156
   │  create_session() / add_student_message()
   ▼
patient_agent.process_message()              agent/patient_agent.py:60
   ├─ ① intent_classifier.classify_intent()   agent/intent_classifier.py:25   LLM(lite)
   ├─ ② info_retriever.retrieve()             agent/info_retriever.py:80      纯 Python
   ├─ ③ response_generator.generate_response() agent/response_generator.py:46 LLM(pro) 流式
   └─ ④ fact_verifier.verify()                agent/fact_verifier.py:35       LLM(lite)
   ▼
SSE: intent → token… → done                  patient_agent.py:87, 103, 114
   ▼
session_service 落库 Message(intent, fact_verify)
```

**关键点**：`case["data"]` 一路原样透传到 Agent，中间没有任何转换。
这意味着——**只要把新的患者数据塞进 `Case.data`，整条链路不用动就能接上。**

### 1.2 四个步骤各自做什么

| 步骤 | 文件 | 输入 → 输出 | 模型 |
|---|---|---|---|
| ① 意图分类 | [intent_classifier.py](backend/agent/intent_classifier.py) | 学生问句 + 最近4条历史 → `{intent, tier, confidence}` | lite, temp 0 |
| ② 信息检索 | [info_retriever.py](backend/agent/info_retriever.py) | `case_data` + intent + tier → `{字段标签: 值}` | 无 |
| ③ 回答生成 | [response_generator.py](backend/agent/response_generator.py) | facts + 问句 + 历史 + persona → token 流 | pro, temp 0.3 |
| ④ 事实校验 | [fact_verifier.py](backend/agent/fact_verifier.py) | 回答 + facts → `{pass, violations}` | lite, temp 0 |

### 1.3 检索机制（现系统的核心）

`info_retriever` 里两张**硬编码表**：

- [`INTENT_FIELD_MAP`](backend/agent/info_retriever.py#L11)：9 种意图 → 各自的字段路径清单（如 `pain_character_inquiry` → `present_illness.onset/duration/character/...`）
- [`TIER_ALLOWED_SECTIONS`](backend/agent/info_retriever.py#L56)：4 个层级 → 允许的顶层 section

所以取数逻辑是：**意图 → 字段路径 → 按 tier 过滤整片 section**。
`tier 4` 让 `TIER_ALLOWED_SECTIONS[4] = set()`，配合 `INTENT_FIELD_MAP` 里 `diagnosis_guess`/`treatment_inquiry` 是空列表，实现"诊断/治疗永不透露"。

### 1.4 四个 prompt 的分工

| 文件 | 作用 | 关键内容 |
|---|---|---|
| [system_base.txt](backend/agent/prompts/patient/system_base.txt) | 患者行为总则 | 5 条规则：绝不编造／绝不透露诊断治疗／口语化／**每次只回答一个问题**／保持角色 |
| [response_generator.txt](backend/agent/prompts/patient/response_generator.txt) | 单轮回答指令 | 身份 + 可说的信息 + 风格 + 学生提问 + 6 条回答要求 + 对话历史 |
| [intent_classifier.txt](backend/agent/prompts/patient/intent_classifier.txt) | 意图分类 | 9 个意图类别 + 4 个 tier 说明 + JSON 输出格式 |
| [fact_verifier.txt](backend/agent/prompts/patient/fact_verifier.txt) | 事后校验 | 5 条校验规则 + JSON 输出格式 |

占位符：`{gender}` `{age_range}` `{retrieved_facts}` `{persona_style}` `{student_question}` `{conversation_history}`（`str.format()` 渲染，字面量花括号须转义）。

### 1.5 开场白机制

[`get_opening_statement()`](backend/agent/patient_agent.py#L30) 读 `basic_info.chief_complaint`，
**调 LLM 生成**开场白（temp 0.3），失败则回退"你好…（患者暂时无法说话）"。

---

## 二、现状与新数据的差距（逐条）

| # | 差距 | 具体表现 | 严重度 |
|---|---|---|---|
| **G1** | **字段路径全错** | `INTENT_FIELD_MAP` 指向 `present_illness.onset`、`past_history.dental`…，而新数据里只有 `facts.H01–H07`、`psychology.P01–P03`。**一条都对不上 → 患者什么都答不出** | 🔴 阻塞 |
| **G2** | **检索粒度错** | 现系统按 section 整片给（问"疼什么样"会把整个 `present_illness` 倒出去）。新数据是 7 条离散事实，应精确到 H 编号 | 🔴 高 |
| **G3** | **Tier 概念对新数据无意义** | 文档的分层是"开放式问 H01–H04 / 针对性追问 / 检查单独 / 诊断永不"，与 tier1–4 不是一回事 | 🟡 中 |
| **G4** | **开场白路径 + 机制都不对** | 读 `basic_info.chief_complaint`（新数据里没有）；且文档要求开场白是**固定文本**，不该每轮 LLM 生成（有成本也有变数） | 🟡 中 |
| **G5** | **"缺失≠阴性"未实现** | 文档要求区分「H 里明确写了"无/否认"」和「病例未设定」。现系统一律回"不清楚"，两者混为一谈 | 🔴 高（安全） |
| **G6** | **抗错误前提未实现** | 学生说"疼的是右下，两个月对吧"，现系统无任何纠正机制，LLM 很可能迎合 | 🔴 高（安全） |
| **G7** | **P01/P02/P03 完全未支持** | 问"你最担心什么"→ 分类不到 → 无事实 → 答"不清楚"。P03 的动态复述更是没有 | 🔴 高 |
| **G8** | **多问题规则与验收测试冲突** | `system_base.txt` 第 4 条明写"每次只回答一个问题"，而 B01/B03 **就是连续多问**且要求合并回答（B03 三问 → 一条 H03） | 🔴 高 |
| **G9** | **检查模块不存在** | 现系统 `examination_inquiry` 从 `case_data` 取 `oral_examination.*`。新数据里检查在 `exam.json`，且本阶段后置 | ⚪ 本阶段不处理 |
| **G10** | **披露轨迹未记录** | `Message` 只存 `intent`/`fact_verify`，没有"本轮披露了哪几条 H"。B 测试断言"依据：H03"需要它 | 🟡 中 |
| **G11** | **病例标题会泄露诊断** | `Case.title` 若用文档里的标题（"冷甜刺激短痛：36深龋相关可复性牙髓炎"），列表页直接剧透 | 🔴 高（安全） |

---

## 三、目标设计

### 3.1 核心转变：从「意图 → tier → 整片字段」到「问句 → 事实 ID」

这是整个改造的主轴。

```
现在： 学生问句 → [LLM] intent + tier → [查表] 字段路径 → 按 tier 过滤 section → 一大堆事实
目标： 学生问句 → [LLM] 事实 ID 集合 → [校验] 合法性 + 记录披露 → 精确的那几条事实
```

**为什么这样改**：

1. **数据本身就是 ID 化的** —— H01–H07 是固定七槽，30 例含义一致。既然编号稳定，就没必要再发明一层 `intent→path→tier` 的映射，直接寻址更短、更准。
2. **可审计** —— 每轮能明确记录"解锁了 H03"，B 类测试可以直接断言 ID，不用人读文本判断。
3. **抗过度披露** —— 模型只能从有限集合里选，选中了也不一定能全给（下面 3.3 的门控）。
4. **P01–P03 天然接入** —— 心理项就在同一个集合里，不需要另开一条路。

### 3.2 新流水线（仍是 4 步，但第 ①②步换了）

```
学生问句 + 对话历史 + 患者数据(patient.json)
   │
   ├─ ① 事实选择  fact_selector        [LLM lite, temp 0]
   │     输入：问句 + 最近历史 + 候选清单（H01–H07 + P01–P03 的标签与原文）
   │     输出：{ "facts": ["H03"], "psychology": [],
   │             "question_type": "targeted|open|exam|meta|irrelevant",
   │             "needs_case_completion": false }
   │
   ├─ ② 披露门控 + 轨迹  disclosure      [纯 Python]
   │     · 校验 ID 合法（防模型编出 H09）
   │     · 开放式问句 → 只允许 H01–H04（文档规则）
   │     · 未命中任何事实 → 标记 NEEDS_CASE_COMPLETION
   │     · 记录本轮披露的 ID（披露轨迹）
   │
   ├─ ③ 回答生成  response_generator   [LLM pro, temp 0.3, 流式]
   │     输入：选中事实原文 + 身份 + 问句 + 完整对话历史 + 行为规则
   │
   └─ ④ 事实校验  fact_verifier        [LLM lite]（保留，事后审计）
```

### 3.3 披露门控（第 ② 步）具体规则

| 情况 | 处理 |
|---|---|
| `question_type = open`（"请从头讲讲"） | 允许 H01–H04；模型若返回 H05–H07 则裁剪掉 |
| `question_type = targeted`（"咬东西疼吗"） | 允许模型返回的事实 ID（通常 1–2 条） |
| `question_type = exam`（"拍片结果呢"） | **不给任何事实** → 走"回避"话术（见 3.6） |
| `question_type = meta`（"把答案发我"） | 不给任何事实 → 走"不知道你在说什么"话术 |
| 无任何 ID 命中 | `needs_case_completion = true` → 患者用不确定口吻回答 |

> 门控是**结构性**的，不靠 prompt 纪律。模型说错了，代码直接裁剪，并记一条日志。

### 3.4 "缺失 ≠ 阴性" 的落地

这是数据层 + prompt 层配合：

| 数据里的情况 | 患者该怎么说 | 例子 |
|---|---|---|
| H 里**明确写了"无"** | 明确否定 | H03「无自发痛、夜间痛」→「不疼，晚上也不疼醒」 |
| H 里写了"不详" | **不确定口吻** | 「这个我不太记得了」 |
| 压根不在 H 里的（未设定） | **不确定口吻 + 不否认** | 「这个我没太注意过」 |

判断逻辑在门控里：**命中了事实 → 按事实文本说；没命中 → `NEEDS_CASE_COMPLETION`**。
prompt 里写清"没被问到过的事，你只能说没注意，不能说'没有'"。

### 3.5 抗错误前提（B06）

数据侧不需要新字段——**权威事实就在 `facts` 里**。做法是 prompt 层给一条硬规则：

> 学生如果说了与你病情不符的话（说错了哪边、多久、吃什么药），你要礼貌纠正，
> **绝不能因为对方坚持就改口**。你的事实以下方"已知事实"为唯一依据。

生成时把选中事实的原文一并放进上下文，模型有对照才纠得动。
这一条要重点测（B06，跑 3 次）。

### 3.6 检查问题的处理（本阶段）

按你的判断，检查结果以后由前端以图片/提示卡形式给出，不由患者说出。所以本阶段：

- `question_type = exam` → 患者**回避**，例如「医生是给我看了看/拍了个片子，但结果没跟我说」。
- **不返回 `exam.json` 的任何内容**，患者运行时根本不加载它。

这跟文档的角色划分一致（患者不可读 E 检查全文），也和真实 SP 的体验一致。

### 3.7 心理项 P01–P03

- **P01/P02** 是静态事实，跟 H 一样参与选择与生成。
- **P03 特殊**：它不是"事实"，是行为规则（"只复述学生确实解释过的、保留不确定性、不夸大成保证治愈"）。
  实现上：**规则进 prompt**；当 `question_type` 是"复核/复述"时，生成时把**学生之前说过的话**作为依据，
  而不是从数据里取 P03 文本。P03 的文本内容只作为风格提示。

### 3.8 多问题合并回答

删掉 `system_base.txt` 第 4 条"每次只回答一个问题"，改为：

> 学生一次问了几个问题，你可以一起回答；**但如果其中某些问题你没有相应信息，就只回答你会的部分**。

这直接对齐 B01（两问 → H01）、B03（三问 → H03）。

### 3.9 病例标题防泄露

| 字段 | 值 | 说明 |
|---|---|---|
| `Case.title` | `"EN01"` 之类的**中性编号** | 学生列表页只看到这个 |
| `Case.data.opening` | 患者开场白 | 列表页展示的"主诉"来源 |
| 教学主题（含诊断） | **不进 `Case.data`** | 留作以后的教师端字段 |

同时 `case_service.list_cases` 现在从 `data` 里 `_safe_get("chief_complaint", "basic_info.chief_complaint")` —— 新数据里没有这两个路径，要改成读 `data.opening`。

---

## 四、数据侧要做的加工

**原则（你定的）：数据服务 Agent，不反过来。** 所以加工只做 Agent 真正需要的那几样。

### 4.1 `Case.data` 装什么

```json
{
  "case_id": "EN01",
  "identity":  { "gender": "女", "age": 28 },
  "opening":   "左下后牙喝冰水、吃甜的会酸痛，差不多两个星期了。",
  "facts":     { "H01": {"label": "...", "text": "..."}, ... },
  "psychology":{ "P01": {"label": "...", "text": "..."}, ... }
}
```

即：**现在切好的 `*.patient.json` 直接就是 `Case.data`**，无缝对接。

> `exam.json` 本阶段不进 `Case.data`。以后要做检查模块时，再决定是加 `data.exams` 还是单独存。

### 4.2 刻意不放进数据的

| 内容 | 去哪 |
|---|---|
| 披露/缺失/抗错误前提/P03 等规则 | prompt（全局，30 例一致） |
| 诊断 D / 鉴别 DD / 计划 T / 沟通 G | 不进（隐藏答案） |
| 评分 R01–R14 | 本阶段不做 |
| B/S 测试 | 独立测试用例，不是运行时数据 |
| 病例标题（含诊断） | 不进（防泄露） |

### 4.3 需不需要给事实加"开放/针对"标记？

**先不加。** 由 ① 步的 `question_type` + ② 步的门控来判断，比在数据里多存一个字段更灵活。
如果以后发现门控判断不准，再回来加。

---

## 五、需要改动的文件清单

| 文件 | 改动 | 说明 |
|---|---|---|
| `agent/intent_classifier.py` | **重写为 `fact_selector.py`** | 换 prompt，输出事实 ID |
| `agent/prompts/patient/intent_classifier.txt` | **替换为 `fact_selector.txt`** | 新的分类指令 |
| `agent/info_retriever.py` | **重写为 `disclosure.py`** | 删掉两张硬编码表，改为 ID 校验 + 门控 + 轨迹 |
| `agent/patient_agent.py` | 改编排 + 修开场白 | 开场白直接读 `data.opening`，不再调 LLM |
| `agent/response_generator.py` | 小改 | 占位符 `age_range`→`age`；facts 格式化带 ID |
| `agent/prompts/patient/system_base.txt` | 改规则 | 补缺失≠阴性、抗错误前提、删"只答一个问题" |
| `agent/prompts/patient/response_generator.txt` | 小改 | 同步占位符 |
| `agent/fact_verifier.py` | 基本不动 | facts 格式变了，`_format_facts` 跟一下 |
| `app/services/session_service.py` | 小改 | 落库时存披露轨迹 |
| `app/models/message.py` | 加一列 | `disclosed` (JSON)，记本轮披露的 H/P 编号 |
| `app/services/case_service.py` | 小改 | 列表页改读 `data.opening`；标题防泄露 |
| `scripts/seed_db.py` | 加一条路径 | 能导入新的 5 例 |
| `data/cases/*.patient.json` | 已有 | 5 例已就绪 |

> `persona.py`、`llm_client.py`、SSE 契约、前端：**本阶段不动**。

---

## 六、分步落地（每步可独立验证）

| 步 | 做什么 | 怎么验证 |
|---|---|---|
| **M1** | 把 5 例 `patient.json` 灌进 DB（新 seed 路径），改 `case_service` 读 `opening`、中性标题 | 病例列表页显示 5 例，标题不泄露诊断 |
| **M2** | 写 `fact_selector`（新 prompt + 模块），替换分类器 | 拿 B01–B08 的"发送"逐条喂进去，**只看输出的 ID 对不对**（不调生成，零成本、可断言） |
| **M3** | 写 `disclosure` 门控 + 轨迹；改 `patient_agent` 编排；修开场白 | 开场白 = `data.opening` 原文；门控对越界 ID 能裁剪 |
| **M4** | 改 `system_base`/`response_generator` 规则与占位符 | 端到端跑一轮 EN01 完整问诊，人工读 |
| **M5** | 跑 B01–B08 / B11 / B12（每例每项 3 次） | 按"核心语义"判过/不过，记录失败项 |

**M2 是最有价值的一步**：它把"事实选择对不对"这个最关键的问题**从 LLM 生成里隔离出来单独测**，
不花钱、可断言、可回归。如果 M2 过不了，后面调 prompt 都是白费。

---

## 七、待你拍板的 5 件事

1. **病例标题**用中性编号（`EN01`）而非文档标题 —— 确认？
2. **检查问题本阶段走"回避"**（患者说"结果没给我看"），不返回 `exam.json` —— 确认？
3. **披露轨迹**加一列 `Message.disclosed`（JSON）—— DB 反正要重建，可以接受吗？
4. **彻底废弃 tier 概念**（不再有 1–4 层级，只留"给哪些 H"）—— 确认？
5. **`fact_selector` 给 LLM 看什么**：我建议**标签 + 原文全给**（7+3 条，约 400 token）。
   之前我提议只给标签，但看过真实数据后改主意了——H03"鉴别性症状"这类标签太抽象，
   而"咬合痛"这个词只在正文里，只给标签容易选错。多花 400 token 换准确率，值。

---

## 八、本阶段明确不做的

- 检查模块（E 的别名匹配、子项裁剪、未提供状态）→ 后置，等前端形态确定
- 评分（R01–R14）、评价器
- persona 接入会话创建（保持默认人格）
- 前端任何改动
- 数据解耦抽象（`case_schema` 那套）—— 新数据结构简单，暂不需要那一层
- 全 30 例批量切分（先 5 例跑通）
