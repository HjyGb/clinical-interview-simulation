# 患者模拟 MVP 开发方案（阶段施工图）

> **性质**：这是施工图，不是一次性交付的文档。每个阶段做完，若与预判有出入，**先在本文档对应阶段标注"实际/偏差"，再进入下一阶段**。
> **基线**：五原则见 [positioning-and-principles.md](positioning-and-principles.md)，目标架构见 [patient-roleplay-architecture.md](patient-roleplay-architecture.md)。
> **约定**：先不改代码。文中的 `文件:行号` 是**当前代码**（2026-10-09）的位置，随改动会漂移，仅作定位参考。
> **测试分工**：每阶段分"我自测"与"你测"两类——**你测的是需要人眼/产品判断的，我不替你下结论**。

---

## 0. 总览

```
M1 数据入库+病例服务   →   M2 fact_selector 验证(spike)   →   M3 门控+编排
        (低风险地基)          (最不确定、信息量最大)            (接进流水线)
                                   ↓
        M5 B测试回归   ←   M4 生成+prompt 改造
        (量化验收)           (角色扮演效果)
```

- **M1 / M2 互不依赖**，可并行；M3 起依赖 M2 通过。
- 每条主线只有 M2、M4、M5 会碰 LLM 调用；M1、M3 是纯数据/纯 Python。

---

## 阶段 M1：数据入库 + 病例服务改造

**目标**：5 例 `patient.json` 灌进 DB，列表页显示中性标题 + 开场主诉，不泄露诊断。

**改动文件**

| 文件 | 改动点 | 说明 |
|---|---|---|
| `scripts/seed_db.py` | 新增一段导入 `data/cases/*.patient.json` 的逻辑（[seed_db.py:36](scripts/seed_db.py#L36) 之后） | `title`=case_id（`EN01`…）；`department`=group（牙体牙髓…）；`difficulty`=难度；`data`=整份 patient.json；`status`="published" |
| `backend/app/services/case_service.py` | [case_service.py:61](backend/app/services/case_service.py#L61) `list_cases` 的 `chief_complaint` 改读 `data.opening` | 新数据没有 `chief_complaint`，列表页主诉来自 `opening` |
| `backend/app/services/case_service.py` | [case_service.py:35](backend/app/services/case_service.py#L35) `_strip_tier4` 保留但不生效 | 新数据无 `diagnosis/treatment_plan` 顶层 key，此函数变 no-op，可留可删 |

**交付物**：DB 里有 5 例；`GET /api/v1/cases` 返回中性标题 + 开场主诉。

**我自测**：跑 `seed_db.py`，核对输出 `5 cases`；查 DB 确认 `title` 无诊断字样。

**你测**：打开前端病例列表页 → 看到 EN01/PE01/PR01/MU01/SU01 五个中性标题，点开不剧透诊断。

**风险/回退**：纯数据层，风险最低。出错直接重跑 `seed_db.py`（title 去重，可安全重跑）。

---

## 阶段 M2：fact_selector 独立验证（spike）

**目标**：用**独立脚本**验证 lite 模型能否把"学生问句"正确映射到事实 ID。**不接进后端**，先探边界。

**改动文件**

| 文件 | 改动点 | 说明 |
|---|---|---|
| `data/tests/behavior_tests.json`（新） | 从 docx 抽取 5 例的 B 测试（`send`/`basis`/`object`/`question_type 期望`） | B 测试是规格，做成数据，不写死在代码里 |
| `backend/agent/fact_selector.py`（新） | 输入问句+历史+事实清单(标签+原文) → 输出 `{question_type, asked_facts}` | 替代 `intent_classifier.py` |
| `backend/agent/prompts/patient/fact_selector.txt`（新） | 选事实 ID 的 prompt | 替代 `intent_classifier.txt` |
| `scripts/spike_fact_selector.py`（新） | 读 5 例 patient.json + behavior_tests.json，逐条喂 lite 模型，比对输出 ID 与 `basis` | 不碰后端 |

**测试矩阵**（患者对象 10 条 × 5 例 = 50 条；B09/B10 是检查模块，本阶段排除）

| B 测试 | 期望选中的事实 | 问句类型 |
|---|---|---|
| B01 | H01 | targeted |
| B02 | H02 | targeted |
| B03 | H03 | targeted（多问合并） |
| B04 | H05 | targeted（指代） |
| B05 | H01 | targeted |
| B06 | H01–H07 | targeted + 错误前提 |
| B07 | H01–H04 | **open** |
| B08 | ∅（不选任何事实） | **meta/越权** |
| B11 | P01、P02 | targeted |
| B12 | P03 | 理解/复述 |

**交付物**：一份控制台准确率报告（逐条：选了什么 / 该选什么 / 对不对）。

**我自测**：跑 spike，统计 ID 命中率 + `question_type` 命中率。

**你测**：**看准确率报告，做 GO / NO-GO**。这是关键决策点——
- 命中率高（比如 ≥90%）→ 继续 M3。
- 命中率低 → 说明"深度角色扮演"在当前模型上有问题，我们回头调（换模型 / 改 prompt / 加结构），**先不往下走**。

**风险/回退**：spike 是独立脚本，失败零副作用。这是"先跑通看效果"的正确姿势。

---

## 阶段 M3：披露门控 + 编排改造

**目标**：把新流水线（fact_selector → disclosure → generator）接进 `patient_agent`，修开场白，落披露轨迹。

**改动文件**

| 文件 | 改动点 | 说明 |
|---|---|---|
| `backend/agent/disclosure.py`（新） | ID 合法性校验 + 开放/针对门控 + 记录本轮 `disclosed` | 替代 `info_retriever.py`，删掉 `INTENT_FIELD_MAP`/`TIER_ALLOWED_SECTIONS` |
| `backend/agent/patient_agent.py` | [patient_agent.py:38](backend/agent/patient_agent.py#L38) 开场白改读 `case_data["opening"]` 直接返回，不再调 LLM | 修 bug + 开场白固定 |
| `backend/agent/patient_agent.py` | [patient_agent.py:60-114](backend/agent/patient_agent.py#L60-L114) `process_message` 改编排：①→`fact_selector` ②→`disclosure` ③→生成 ④删除校验 | 4 步→3 步 |
| `backend/app/models/message.py` | [message.py:21](backend/app/models/message.py#L21) 附近加 `disclosed` JSON 列（nullable） | 记本轮披露的 H/P 编号 |
| `backend/app/services/session_service.py` | [session_service.py:177-184](backend/app/services/session_service.py#L177-L184) 存 `disclosed`，去掉 `fact_verify` | 落库披露轨迹 |
| 删除 | `backend/agent/intent_classifier.py`、`info_retriever.py`、`fact_verifier.py` 及对应 prompt | 已被替代（git 可恢复） |

**交付物**：EN01 端到端能对话；开场白 = 数据原文；DB 里每条患者消息带 `disclosed`。

**我自测**：起后端 → 建 EN01 会话 → 发消息，核对：`intent` 事件带 `question_type+asked_facts`；`done` 事件带 `disclosed`；门控能裁剪越界 ID（如问检查 → 选不到任何事实）。

**你测**：前端选 EN01，看开场白是原文；问"哪里不舒服"，患者正确答 H01。

**风险/回退**：`message.py` 加列要**删库重建**（无 Alembic），跑一次 `seed_db.py` 即可。

---

## 阶段 M4：生成 + prompt 改造

**目标**：角色扮演式生成（人格在上下文 + 本轮 allowed_facts）。

**改动文件**

| 文件 | 改动点 | 说明 |
|---|---|---|
| `backend/agent/response_generator.py` | [response_generator.py:69-84](backend/agent/response_generator.py#L69-L84) 改：稳定人格(全部 H/P + 规则)进 system；每轮只变 `allowed_facts`；占位符 `age_range`→`age` | 人格在上下文 |
| `backend/agent/prompts/patient/system_base.txt` | [system_base.txt:8](backend/agent/prompts/patient/system_base.txt#L8) 删"每次只答一个问题"；补"缺失≠阴性""抗错误前提"两条硬规则 | 对齐 B01/B03/B06 |
| `backend/agent/prompts/patient/response_generator.txt` | 从"改写检索事实"改为"以患者身份自然对话" | 角色扮演 |
| `backend/agent/prompts/patient/fact_selector.txt` | 据 M2 结果微调 | 若 M2 有漏网问法 |

**交付物**：自然、忠实于事实的患者回答。

**我自测**：用 EN01 的 B01–B08"发送"逐条跑，人工读输出，查：无诊断泄露、无编造、缺失项用不确定口吻。

**你测**：**这是你最该亲自测的一环**——和患者聊几句，判断"像不像人"：语气自然吗、前后一致吗、会编造吗、问诊断/检查时守得住吗。你的体感是 M5 之外最重要的验收。

**风险/回退**：prompt 是纯文本，改起来最快，也最容易反复调。此阶段预计要迭代几轮。

---

## 阶段 M5：B 测试回归

**目标**：量化验收。跑 B01–B08 / B11 / B12（患者对象 10 条），5 例 × 每条 3 次，记录通过率。

**改动文件**

| 文件 | 改动点 | 说明 |
|---|---|---|
| `scripts/run_behavior_tests.py`（新） | 每条测试独立初始化会话 → 发 `send` → 断言（披露 ID + 关键词/语义） | 驱动整条链路 |
| `data/tests/behavior_tests.json` | 补全 `预期`/`禁止` 字段，供断言使用 | M2 已建骨架，此处补全 |

**交付物**：一张通过率表（case × 测试 × 3 次结果）。

**我自测**：跑脚本，出报告，把失败项分成两类：① 我们实现不好；② 测试/数据本身有问题。

**你测**：**看报告，和我一起裁决失败项**——是改实现，还是回给医生调整测试/数据。医院明说 B 测试"均未实际运行"，所以不排除测试本身要改。

**风险/回退**：3 次 × 10 条 × 5 例 = 150 次会话，LLM 成本要留意（可先只跑 EN01 一例探成本，再扩全量）。

---

## 附 A：改动文件总清单（汇总）

| 文件 | 动作 | 阶段 |
|---|---|---|
| `scripts/seed_db.py` | 改 | M1 |
| `backend/app/services/case_service.py` | 改 | M1 |
| `data/tests/behavior_tests.json` | 新建 | M2（补全于 M5） |
| `backend/agent/fact_selector.py` | 新建 | M2 |
| `backend/agent/prompts/patient/fact_selector.txt` | 新建 | M2 |
| `scripts/spike_fact_selector.py` | 新建 | M2 |
| `backend/agent/disclosure.py` | 新建 | M3 |
| `backend/agent/patient_agent.py` | 改 | M3 |
| `backend/app/models/message.py` | 改（加列） | M3 |
| `backend/app/services/session_service.py` | 改 | M3 |
| `backend/agent/response_generator.py` | 改 | M4 |
| `backend/agent/prompts/patient/system_base.txt` | 改 | M4 |
| `backend/agent/prompts/patient/response_generator.txt` | 改 | M4 |
| `scripts/run_behavior_tests.py` | 新建 | M5 |
| `backend/agent/intent_classifier.py` + prompt | 删除 | M3 |
| `backend/agent/info_retriever.py` | 删除 | M3 |
| `backend/agent/fact_verifier.py` + prompt | 删除 | M3 |

**不动**：`llm_client.py`、`persona.py`、`app/api/*`、其余 models/schemas/middleware、前端全部。

## 附 B：测试分工总览

| 阶段 | 我自测（自动/代码层） | 你测（人眼/产品判断） |
|---|---|---|
| M1 | seed 输出、DB 核对 | 前端列表页看 5 个中性病例 |
| M2 | spike 准确率脚本 | **看报告，做 GO/NO-GO** |
| M3 | 事件字段、门控裁剪、DB 落库 | 前端开场白 + 问一句 |
| M4 | B 测试逐条人工读 | **和患者聊天，判断像不像人** |
| M5 | 通过率脚本 + 失败分类 | **裁决失败项：改实现 or 回给医生** |

---

## 附 C：本方案的三条纪律

1. **每个阶段结束先更新本文档再进下一阶段**（记录"实际 vs 预判"的偏差）。
2. **M2 是闸门**：准确率不达标就不进 M3，避免用错误的地基盖楼。
3. **引擎/内容分离贯穿始终**：任何科室特有的东西只进数据/配置，不写进代码（对应 P3）。
