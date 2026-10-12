# 现状说明：当前系统架构与实现

> **性质**：描述**现在是什么样**，不是计划，也不是设计提案。
> 开工前的设计文档（`architecture-design.md`、`patient-agent-redesign.md`、`patient-simulation-roadmap.md`）
> 已被本文取代并归档至 `old_docs/`。
>
> 最后一次全面核对：**2026-10-11**（对照代码逐文件确认，非凭记忆）。
> 施工过程与逐阶段的"实际 vs 预判"记录见 [patient-simulation-dev-plan.md](patient-simulation-dev-plan.md)。

---

## 1. 一句话

**学生与 AI 患者对话问诊，患者扮演一个稳定的人、按学生问什么给什么；学生申请检查时，由一个独立于患者的「检查模块」返回检查结果。** 评分模块沿用旧代码，**当前与新版数据不兼容**（见 §9）。

---

## 2. 系统全貌

```
前端 React (Vite + TS + Zustand)
  │  /api/v1  (JWT Bearer)   ← SSE 手写解析，见 frontend/src/api/client.ts
  ▼
backend/app/api/        4 个路由：auth / cases / sessions / assessments
backend/app/services/   编排：session_service 调 Agent；assessment_service 调 Evaluator
backend/app/{models,schemas,middleware}/
  ▼
backend/agent/          LLM 核心（不碰数据库，只收 dict）
  ▼
阿里百炼 DashScope（OpenAI 兼容端点）
```

**关键约定**：`app` 与 `agent` 是两个平级顶层包、互相 import，所以**后端必须从 `backend/` 目录启动**。
`DATABASE_URL` 是 CWD 相对的，从仓库根启动会另造一个空库。

---

## 3. 三个「会说话的角色」

系统里只有三个角色会产出面向学生的内容。**它们的数据在存储层就是分开的**，不是靠提示词约束。

| 角色 | 代码 | 说什么 | 用什么模型 |
|---|---|---|---|
| **患者** | `agent/patient_agent.py` | 症状、病史、担忧、感受 | pro（生成）+ lite（选事实） |
| **检查** | `agent/exam_module.py` | 检查项目的文字结果 | **纯 Python，不调 LLM** |
| **评分** | `backend/scoring/` | R01–R14 项分 + 安全标记 | R01–R04 纯 Python；R05–R14 LLM |

### 3.1 患者侧流水线（`patient_agent.process_message`）

```
学生这句话
  → ① 事实选择  fact_selector (lite LLM, temp=0)
       输出 {question_type, asked_facts[], reason}
       question_type ∈ open | targeted | unknown | meta | exam | error
  → ② 分流：question_type == "exam" ?  ⇒ 交给检查模块（§3.2），结束
  → ③ 披露门控  disclosure.gate (纯 Python)
       决定"本轮允许说哪些事实" → allowed_facts
  → ④ 回答生成  response_generator (pro LLM, temp=0.3, 流式)
       稳定人格 + 行为规则（system）+ 本轮 allowed_facts（user）→ 口语化回答
```

**五个 question_type 的含义与对应行为**（这是本系统的行为骨架）：

| 类型 | 何时 | 门控给什么 | 患者该做什么 |
|---|---|---|---|
| `open` | 学生请患者不受限地自述 | H01–H04 | 自然叙述一段 |
| `targeted` | 针对性追问（**必须至少命中一条事实**） | 命中的事实 | 照给 |
| `unknown` | 问的是患者本人的事，但清单里没有（家族史、饮酒…） | 无 | **患者不回答**：由控制器出 `data_gap`「模拟资料不足」（见 §4.2） |
| `meta` | 与患者本人无关（要后台答案、让你别扮演…） | 无 | 患者口吻回避，然后继续正常对话 |
| `exam` | 要求出具检查/化验/影像结果 | — | 转检查模块 |
| `explain` | 学员在**向患者交代**病情/计划/注意事项（陈述而非提问） | P03 | 更新理解：复述要点、**追问没听懂的术语**、保留担忧 |

> `unknown` 的处理依据医院原文（`_docx.txt:83`）：「问及未设定事实时标记 `NEEDS_CASE_COMPLETION`，
> **由控制器说明模拟资料不足**；不能把病例缺失默认成患者否认**或患者记不清**」。
> 所以不出一句患者台词——让他装糊涂既不像真人，也把"病例没设"混同成了"患者记不清"。
| `error` | **上游调用失败**（刻意不在合法类型内） | 无 | "没听清，能再说一遍吗" |

### 3.2 检查模块（`exam_module.py`）

**纯 Python、确定性**，两级匹配：

```
① 项级：在 E 项的 label + aliases 里找 → 命中哪些 E 项
   包含规则：命中串是别人命中串的子串时只留长的
   整项优先：学生话里出现了该项 label ⇒ 直接返回整条 result，不再拆子项
② 子项级：在该 E 项的 subitems 里找 → 只返回命中子项的 result_fragments
   未命中的子项内容绝不带出（医院明令："不可返回整个E项"）
③ 拼接：保留原文两段之间的标点；夹着别的子项内容时用"；"断开
④ 未命中任何 E 项 → 返回"本病例未提供…"，并明确"没有记录不等于结果正常"
```

### 3.3 数据的「权限层」是物理隔离

| 数据 | 存哪 | 谁能读 |
|---|---|---|
| 患者事实/心理/开场白 | `Case.data` | 只进患者侧 |
| 检查项/别名/结果/子项 | `Case.exam_data` | 只进检查模块 |
| 诊断/治疗/评分依据 | **不入库** | 无（评估器将来需要时另建） |

患者 Agent 拿不到检查结果，检查模块拿不到患者事实——**结构性成立，不靠提示词自觉**。

---

## 4. 数据流

### 4.1 一次消息的完整链路

```
POST /api/v1/sessions/{id}/messages  {content}
  → session_service.add_student_message()
      ① 轮次检查（current_round = 学生消息数 + 1，> max_rounds 则 error 返回）
      ② 落库学生消息
      ③ 取全量历史，调 process_message(...)
           → 依次 yield 事件，session_service 转成 SSE
      ④ 落库回复（role = patient 或 exam）
      ⑤ remaining ≤ 2 时 yield limit_warning
```

### 4.2 SSE 事件契约

`frontend/src/api/client.ts` 的 `apiPostSSE` 是**手写解析**，加事件类型要同时改后端和前端。

| 事件 | 载荷 | 谁发 |
|---|---|---|
| `intent` | `{question_type, asked_facts, [exam_ids], [reason]}` | 每次都有 |
| `token` | `{token}` — 多个 | 患者回答（流式） |
| `exam` | `{exam_ids, subitem_keys, content}` | 检查结果（整段，不流式） |
| `data_gap` | `{message, question_type}` | **模拟资料不足**（问的是病例没设定的信息）。患者**不说话**，由控制器说明 |
| `done` | `{round, question_type, disclosed, exam_ids, subitem_keys}` | 每次都有 |
| `limit_warning` | `{remaining_rounds, message}` | 剩 ≤2 轮时 |
| `error` | `{message}` | 轮次超限 / 会话失效 |

### 4.3 一次会话的生命周期

```
POST /api/v1/sessions  {case_id}
  → 建 Session(max_rounds=25, persona=DEFAULT)
  → 开场白 **直接取自 case_data["opening"]**（固定文本，不调 LLM，存为 round_num=0 的 patient 消息）
  → 返回 {id, ..., opening_message}
```

---

## 5. 数据模型

### 5.1 病例数据（文件 → DB）

```
data/cases/<case>.patient.json   ──┐
                                   ├─→ seed_db.py → cases 表
data/cases/<case>.exam.json      ──┘   （data / exam_data 两列分开存）
```

**评分素材（2026-10-12 新切出，尚未入库）**：

```
data/cases/<case>.answer.json    ← A2 隐藏参考答案（D/DD/T/G），scripts/extract_answer_key.py
data/cases/<case>.rubric.json    ← 逐例 R01–R14 锚点 + 关键错误，scripts/extract_rubric.py
data/scoring/rubric_common.json  ← 册前共同 1/0 锚点 + 全局规则
```

切出流程：`extract_*.py → data/staging/ → verify_scoring_data.py（校验 A1–A7）→ data/cases/`。
**未通过校验的病例不会进 `data/cases/`。** 逐字保真 120/120。见 [scoring-system-design.md](scoring-system-design.md)。

范本见 [case-data-schema.md](case-data-schema.md)（v2.2，含 V1–V7 校验规则）。
- `patient.json`：`identity` / `opening` / `facts`(H01–H07，槽位固定) / `psychology`(P01–P03)
- `exam.json`：`exams[E##]` = `label`/`level`/`result`/`boundary`/`aliases`/`subitems`
  - `subitems[].result_fragments` **必须是 `result` 的逐字连续子串**（机器校验 V1/V2）
  - `subitems[].source` = `authored`(医院写的) / `derived`(我们补的)

**当前 5 例**：EN01(牙体牙髓) · PE01(牙周) · PR01(修复) · MU01(黏膜) · SU01(颌面外科)。全部 `schema_version: 2.2`。

### 5.2 数据库表

| 表 | 关键字段 |
|---|---|
| `users` | username / password(bcrypt) / role。**登录会自动注册**未知用户名 |
| `cases` | title(中性编号,如 EN01) / department / difficulty / **data** / **exam_data** / **answer_key** / **scoring_rubric** / status |
| `sessions` | user_id / case_id / persona / status / **max_rounds=25** / started_at / ended_at |
| `messages` | session_id / **role(student\|patient\|exam\|system)** / content / round_num / intent / **disclosed** / fact_verify(废弃) |
| `assessments` | session_id / **report**（14 项 + 视图 + 可评上限 + 安全标记）/ raw_total / comment / student_report |

**没有 Alembic**：改模型必须删库重建（`rm backend/data/app.db && python ../scripts/seed_db.py`）。

---

## 6. Prompt 清单

| 文件 | 用途 | 占位符 |
|---|---|---|
| `prompts/patient/system_base.txt` | **患者稳定人格**：身份 + 全部事实 + 8 条行为规则 | `{gender}` `{age}` `{facts_catalog}` `{persona_style}` |
| `prompts/patient/response_generator.txt` | 每轮变量：本轮可说什么 + 问句 + 历史 | `{situation}` `{allowed_facts}` `{already_disclosed}` `{student_question}` `{conversation_history}` |
| `prompts/patient/fact_selector.txt` | 选事实 ID + 判问句类型 | `{facts_catalog}` `{conversation_history}` |
| `prompts/exam/subitem_splitter.txt` | **构建期**用（切子项），不在运行时链路 | `{label}` `{level}` `{result}` `{boundary}` `{groups}` |
| `prompts/evaluator/*.txt` | 旧评分 prompt，**当前与新版数据不兼容** | — |

**注意**：
- 模板用 `str.format()` 渲染，字面大括号必须转义成 `{{` `}}`
- prompt 是 `.txt`、模块级懒加载缓存，**改了要重启服务**（`--reload` 只监听 `.py`）

### 患者的行为规则（8 条，写在 `system_base.txt`）

1. 医学事实固定、语言可改写（不添症状、不改时间、不编数字、不主动报牙位）
2. **只使用【本轮可以说的】**——清单外的即使记得也不说
3. 不一次倒出所有病史
4. **缺失 ≠ 阴性**——不知道就说"没太注意"，绝不说成"没有/正常"；**说了"没太注意"就不再补具体说法**
5. **抗错误前提**——学生说错了要礼貌纠正，不因坚持而改口
6. 不知道诊断/治疗（不在脑子里）；被要求交出后台答案时用患者口吻回避，然后继续正常问诊
7. **复述只复述确实听到过的**；没讲过就如实说"您还没跟我讲过"
8. 保持同一个人；讲过的不反复念叨

---

## 7. 轮次、记忆与披露轨迹

| 机制 | 现状 | 说明 |
|---|---|---|
| **轮次** | 一轮 = **学生一次发言** | 按学生消息数算，不按总消息数（检查结果是第三种行） |
| **上限** | `max_rounds = 25` | 医院 S01 常规路径有 13 步，12 轮装不下 |
| **记忆窗口** | **60 条消息 / 每条 500 字** | ≈29 轮，盖得住 25 轮上限的 51 条。**窗口必须 ≥ 2 × max_rounds + 1**，顶破会打 WARNING |
| **已披露轨迹** | `Message.disclosed` | 患者存 `["H01","P02"]`；检查存 `["E02.cold"]` |
| **患者的"我记得说过什么"** | `already_disclosed` | 读历史里所有 `disclosed`，**按 `^[HP]\d{2}$` 过滤**——检查子项键不能喂给患者 |

**这三者是有耦合的**：调大 `max_rounds` 就必须同步调大记忆窗口，否则患者会静默遗忘开场白。

---

## 8. 测试与验收体系

**没有单元测试框架**（`pytest` 跑空）。实际用的是四套**独立脚本**：

| 脚本 | 性质 | 规模 | 最近结果 |
|---|---|---|---|
| `scripts/spike_fact_selector.py` | 事实选择准确率（对 docx 的「依据」） | 5 例 × 10 测试 × 3 次 | **135/135** |
| `scripts/run_behavior_tests.py` | B 测试回归（走真实 HTTP） | 5 例 × 11 项 × 3 次 | **165/165** |
| `scripts/run_exam_subitem_tests.py` | 子项裁剪（纯 Python） | 18 条 | **18/18** |
| `scripts/verify_exam_coverage.py` | 检查模块需求逐条核对（走真实 HTTP） | 6 类 55 次调用 | **全通过** |

**数据构建脚本**（可重跑）：

| 脚本 | 作用 |
|---|---|
| `extract_behavior_tests.py` | docx → `data/tests/behavior_tests.json`（B1/B2 段） |
| `extract_exam_items.py` | docx → `data/staging/*.exam.new.json` + 缺标签清单 |
| `build_exam_v2.py` | staging → `data/cases/*.exam.json`（**含 V1–V3 校验，不过则退回整包**） |
| `seed_db.py` | 病例文件 → DB |

**目录约定**：`data/cases/` 只放**最终进系统的数据**；`data/staging/` 中间产物；`data/old/` 弃用；`data/tests/` 测试与报告；`data/raw/` 医院原始 docx。

---

## 9. 已知边界与缺口

### ✅ 评分功能已重建（2026-10-12，取代旧双轨）

旧 `evaluator_agent.py`（Station 4 + MAAS，标准答案恒为 `"未知"`）**已删除**。
现在的评分链路是医院的 `R01–R14`：`backend/scoring/`（子锚点分解 → 聚合 → 代码判 R01–R04 →
LLM 判 R05–R14 → 安全通道 → 报告组装），参考答案与 R 锚点存在 `Case.answer_key` /
`Case.scoring_rubric`。设计与施工记录见
[scoring-system-design.md](scoring-system-design.md)、[scoring-dev-plan.md](scoring-dev-plan.md)。

**仍缺**：SU05 早停例只有单元测试覆盖（该例未切片）；人工一致性实验待医院。

### 🟡 评分侧的其余缺口

| 缺口 | 影响 |
|---|---|
| **「学员四项作答」到底是哪四项** —— 医院文档只出现过这五个字，从未列举 | 我们按 R06–R10 反推了**五项**答卷，待医院确认 |
| **权重与及格线未定** —— 医生批注「评分非均匀分配，权重后续需专家讨论决定」 | 报告只给原始分与可评上限，**不给综合分**（也不替医院发明） |
| SU05 早停例无真实端到端 | 只有 `run_scoring_deterministic_tests.py` 的 F5 覆盖 |


### 🔴 医院数据自身的缺口（S1 提取时实测发现）

| 缺口 | 影响 |
|---|---|
| **SU06 无「教师参考草案（隐藏）」块**（30 例里只有 29 块） | 该例目前**无法评分** |
| **EN02 的隐藏块缺「医学依据」行** | 只影响 K 编号溯源，不影响评分 |

详见 `data/tests/answer_key_gaps.md`。

### 🟡 检查模块

1. **子项标签未经医院确认**：5 例共 19 项里，切分的子项名与归属**全是我们补的（`derived`）**。
   核对表在 `data/tests/exam_split_review_*.md`，待医院勾选；冲突时以医院为准。
2. **口语化说法不召回**：严格别名匹配，`叩一下这颗牙` 这类匹配不上 → 返回"未提供"。
   **经确认这属于安全方向、且不在使用场景内**（学生用直接明了的说法），故不修。

### 🟡 患者侧

1. **"预计阴性"问题偶尔漏记披露轨迹**（问"有没有便血"有时答对但 `disclosed` 为空）。
2. **偶尔软性编造**：`qwen-plus` 偶尔在"没太注意"后补一句病历里没有的说法。

### ⚪ 明确不做 / 未做

- **B3 段的 S01/S02 多轮脚本**（医院写的连续多轮规格）——从未运行过。所有测试都是单轮独立重置。
- **全 30 例**：只切了 5 例（其余 25 例未切分）。
- **persona 81 组合**：未接入会话创建，固定默认。
- **检查结果展示形态**：当前走对话；不做卡片 UI。

---

## 10. 与开工前设计的差异（速查）

| 项 | 开工前设计 | 现状 |
|---|---|---|
| 患者流水线 | 4 步：意图分类→信息检索→生成→事实校验 | **3 步**：事实选择→披露门控→生成（校验步骤删除，它在流式之后无法撤回） |
| 事实寻址 | 9 类意图 + Tier 1–4 分档 | **事实 ID 寻址**（`asked_facts`）+ 子项键 |
| 披露控制 | `TIER_ALLOWED_SECTIONS` 按 section 整片放行 | `disclosure.gate` 按 ID 精确裁剪 |
| 开场白 | 每轮调 LLM 生成 | **数据原文，不调 LLM** |
| 检查 | 无独立角色 | **独立检查模块 + 独立数据列** |
| 病例数据 | 嵌套 schema（`basic_info`/`present_illness`/`diagnosis`…） | `patient.json` + `exam.json`（v2.2，含子项层） |
| pro 模型 | `deepseek-v3.1` | **`qwen-plus`**（v3.1 已被百炼下架） |
| 轮次上限 | 12 | **25** |
| 记忆窗口 | 最近 4–6 条 | **全量（60 条 / 500 字）** |
