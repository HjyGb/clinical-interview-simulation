# 病例数据结构解耦设计（施工图）

> 状态：**设计文档，尚未实现**。待医院新数据格式确定后，按本文档实施。
> 目标：把散落在代码各处的「病例字段结构」收敛成**单一配置源**，使新数据格式只改一处。

---

## 1. 为什么需要解耦

当前病例数据是 `Case.data`（SQLAlchemy JSON 列）里的嵌套 dict，**没有 DB 层 schema**。系统靠硬编码的英文字段路径字符串从 dict 里取数。这些字符串散落在 6 个文件里，任何一处的字段名与真实数据不一致，都会导致**静默降级**（查不到事实 → 患者一律回答「不清楚」；或评估器拿到「未知」当标准答案），而不会报错。

医院新数据一旦改变字段结构，这 6 处必须同步修改，否则整个系统「看着能跑、实则答非所问」。解耦就是把这 6 处收敛成 1 处。

---

## 2. 完整耦合点清单（本次施工范围）

### 2.1 后端（必须改）

| # | 位置 | 耦合内容 | 静默失败表现 |
|---|---|---|---|
| 1 | `backend/agent/info_retriever.py:11-49` `INTENT_FIELD_MAP` | 每个 intent → 字段路径列表（`present_illness.onset` 等） | 查不到 → `{}` → 患者答「不清楚」 |
| 2 | `backend/agent/info_retriever.py:56-61` `TIER_ALLOWED_SECTIONS` | tier → 允许的 section 名集合 | 字段被 tier 过滤掉 |
| 3 | `backend/agent/patient_agent.py:38` | 开场白读 `basic_info.chief_complaint`（实际在顶层 `chief_complaint`） | **现存 bug**：永远回退到写死的「牙齿不舒服」 |
| 4 | `backend/agent/evaluator_agent.py:57-58` | `diagnosis.primary` / `treatment_plan.definitive` | 拿「未知」当标准答案 |
| 5 | `backend/agent/response_generator.py:68-71,77-79` | `basic_info.gender` / `basic_info.age_range` | 性别/年龄变「未知」 |
| 6 | `backend/app/services/case_service.py:9,35-37` `_TIER4_KEYS` + `_strip_tier4` | 只剥**顶层** `diagnosis`/`treatment_plan` 两个 key | 嵌套/改名 → **泄露 Tier 4** |
| 7 | `backend/app/services/case_service.py:60-62` `list_cases` | 列表元数据 `visit_type`/`chief_complaint`/`case_number` | 列表显示空值 |
| 8 | `backend/app/services/case_service.py:12-32` `_safe_get` | 双 schema 兼容（旧嵌套 vs 新顶层） | 需随新格式调整 |
| 9 | `backend/agent/prompts/patient/intent_classifier.txt:17-20` | Tier 段落硬编码 5 个 section 名 | 意图分类指引与实际 tier 脱节 |

### 2.2 前端（次要，可不动）

- `frontend/src/types/index.ts:21-29` `CaseSummary` 硬编码 `visit_type`/`chief_complaint`/`case_number`。
- `frontend/src/pages/CaseListPage.tsx:50-57,129-145` 搜索/展示这三个字段。
- `frontend/src/types/index.ts:31-37` `CaseDetail` 是 `Record<string, unknown>`，且**当前无页面调用 `getCase()`**——医疗 JSON 结构只被后端 Agent/评估器消费，前端从不解析它。因此前端对病例结构的耦合**只限于列表元数据**，风险低。

### 2.3 已发现的存量数据语义偏差（新数据接入时一并确认）

- `info_retriever.py:25-28` 的 `past_history.dental/medical/allergy/medication` 四条路径，与 v2 集成方案「既往史不拆子项、用 `full_text`」的决策**不一致**（代码落后于设计）。
- `diagnosis.secondary`、`diagnosis.icd_code`、`treatment_plan.emergency/restoration/notes` **运行时从未被消费**（评估器只读 `primary` 和 `definitive`）。
- 旧版 `clean_data.py` 产出**扁平字符串**（`present_illness: "..."`），新版 `enrich_cases.py` 产出**嵌套 dict**；`info_retriever._get_nested`（`info_retriever.py:64-77`）遇到扁平字符串会静默返回 `None`。两套 schema 在叶子层不兼容。

---

## 3. 目标设计：单一配置源 `case_schema`

新增一个模块（建议 `backend/app/case_schema.py`，与 `app/` 同级被 `agent/` 与 `app/` 共同引用），集中定义以下配置：

```python
# 语义说明（示意，非最终代码）
SECTION_TO_TIER = {
    "chief_complaint": 1,
    "present_illness": 2,
    "past_history": 2,
    "oral_examination": 3,
    "auxiliary_examination": 3,
}

INTENT_FIELD_MAP = { ... }          # 现 info_retriever 里的映射，迁到这里
TIER4_KEYS = {"diagnosis", "treatment_plan"}   # 现 _TIER4_KEYS

BASIC_INFO_FIELDS = {"gender": "basic_info.gender", "age_range": "basic_info.age_range"}
OPENING_FIELD = "chief_complaint"              # 修正 patient_agent.py:38 的路径
DIAGNOSIS_FIELDS = {"primary": "diagnosis.primary", ...}
TREATMENT_FIELDS = {"definitive": "treatment_plan.definitive", ...}

LIST_META_FIELDS = {"visit_type": ..., "chief_complaint": ..., "case_number": ...}
```

各消费者改为从该配置读取：

| 消费者 | 改造方式 |
|---|---|
| `info_retriever.py` | `INTENT_FIELD_MAP`、`TIER_ALLOWED_SECTIONS` 直接 import 自 `case_schema`（`SECTION_TO_TIER` 推导出 tier 过滤） |
| `patient_agent.py` | 开场白字段路径从 `OPENING_FIELD` 读（顺带修掉 :38 的 bug） |
| `evaluator_agent.py` | `DIAGNOSIS_FIELDS`/`TREATMENT_FIELDS` 提供标准答案字段 |
| `response_generator.py` | `BASIC_INFO_FIELDS` 提供性别/年龄路径 |
| `case_service.py` | `_TIER4_KEYS`/`_strip_tier4`/`list_cases` 元数据路径统一从配置读，`_strip_tier4` 支持嵌套路径剥除 |

### `intent_classifier.txt` 的 Tier 段落处理

二选一：
- **方案 A（推荐）**：把 Tier 段落改成**不写死 section 名的语义描述**（「层级 1=主诉，层级 2=症状细节+病史，层级 3=检查结果」），彻底与字段名解耦。
- 方案 B：由 `case_schema` 在加载时生成 Tier 段落的 section 名部分。

方案 A 更简单且稳健，因为意图分类器只需要知道「该不该给、给哪一层的量」，不需要知道具体字段名。

---

## 4. 附带修正清单（随解耦一并做）

1. 修 `patient_agent.py:38` 开场白路径 bug（`basic_info.chief_complaint` → 顶层 `chief_complaint`）。
2. `_strip_tier4` 支持**嵌套路径剥除**，避免新数据把诊断/治疗嵌套到别的 section 下时泄露。
3. 补一个「schema 校验/自检」：启动或导入病例时，用 `case_schema` 校验 `Case.data` 是否含关键字段，缺字段时**告警而非静默**（把现有的静默降级问题显性化）。

---

## 5. 实施顺序（拿到新数据格式后）

1. **先定 schema**：把医院新格式逐字段映射到 `case_schema`（语义对齐：哪层披露、考核边界在哪）。
2. **实现 `case_schema`** 并让 6 个消费者改读配置（重构，行为不变）。
3. **写 schema 校验**，跑通导入，确认缺字段时告警。
4. **接入新数据**：写新的导入脚本（参考现有 `scripts/enrich_cases.py` 的翻译+审校思路，但适配新格式）。
5. **跑通完整 E2E**：登录 → 选病例 → 问诊 → 诊断 → 评估，重点验证 Tier 4 不泄露、事实检索正确。
6. **再处理已记录缺陷**（与本次解耦正交，但建议随后做）：评估器静默 0 分、补测试、接 persona。

---

## 6. 验证方法

- **单元级**：`info_retriever.retrieve()` 对每个 intent/tier 组合，用一份已知结构的 `case_data` 断言返回的 facts 符合 `case_schema` 配置（这是纯 Python 函数，无 LLM 依赖，最易测）。
- **集成级**：用一份含完整字段 + 一份「改名/嵌套/扁平」的变异病例，验证：① 患者答对事实；② Tier 4 不泄露；③ 评估器拿到正确标准答案；④ 列表元数据正确。
- **回归**：现有 3 个 MVP 病例（`mvp_cases.json`，git 历史可捞）作为 golden case，改造前后跑同一批问题，输出应一致（改的是取值路径，不该改变结果）。
