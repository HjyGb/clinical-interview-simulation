# 诊断结果评估标准体系说明

> 版本：v1.0 | 日期：2026-08-02 | 基于 MVP 代码实际实现梳理

---

## 一、总体架构

系统采用 **双轨并行评估**（Dual-Track Assessment）机制，学生提交诊断报告后同时触发两条独立的评估流水线，互不干扰，并行执行。

```
学生提交诊断报告
      │
      ├──→ Track A: Station 4 诊断能力评估 ──→ diagnostic (100分)
      │        输入：学生报告 + 病例标准答案 + 对话历史
      │
      └──→ Track B: MAAS-Global 沟通能力评估 ──→ communication (100分)
               输入：仅对话历史
      
      综合评分 = (diagnostic + communication) / 2
```

**代码位置**：[backend/agent/evaluator_agent.py](backend/agent/evaluator_agent.py) — `evaluate()` 函数使用 `asyncio.gather` 并行执行两条轨道。

---

## 二、学生提交的诊断表单（5 个字段）

学生在结束问诊后需填写诊断报告，字段定义见 [frontend/src/components/DiagnosisForm.tsx](frontend/src/components/DiagnosisForm.tsx)：

| 字段 | 类型 | 说明 | 前端 placeholder |
|------|------|------|-----------------|
| `primary_diagnosis` | 必填 | 主诊断 | "右下第一磨牙慢性牙髓炎" |
| `differential_diagnosis` | 选填 | 鉴别诊断 | "列出需要考虑的其他可能诊断" |
| `evidence` | 选填 | 诊断依据 | "根据问诊获得的信息，说明你的诊断依据" |
| `suggested_exams` | 选填 | 建议检查 | "X光片、CBCT、冷热诊" |
| `treatment_plan` | 选填 | 治疗方案 | "急症处理 + 根治方案 + 修复方案" |

后端 Pydantic Schema：[backend/app/schemas/assessment.py](backend/app/schemas/assessment.py) — `DiagnosisSubmit`：
```python
class DiagnosisSubmit(BaseModel):
    primary_diagnosis: str = ""
    differential_diagnosis: str = ""
    evidence: str = ""
    suggested_exams: str = ""
    treatment_plan: str = ""
```

---

## 三、Track A：Station 4 诊断能力评估（100 分）

基于中国口腔执业医师资格考试 **Station 4（临床问诊站）** 的评分框架，由 LLM 作为模拟考官对照病例标准答案进行评分。

**Prompt 文件**：[backend/agent/prompts/evaluator/station4_scoring.txt](backend/agent/prompts/evaluator/station4_scoring.txt)

### 3.1 五个评分维度

| # | 维度 | 满分 | 评估要点 | 扣分规则 |
|---|------|------|----------|----------|
| 1 | **主诉与现病史采集** | 30 | 是否系统询问了主诉（部位、性质、程度、时间、诱因、缓解因素）；是否覆盖 OLDCARTS 框架 | 遗漏重要维度每个 -5 分 |
| 2 | **既往史采集** | 15 | 是否询问口腔既往史；是否询问全身病史、用药史、过敏史 | 遗漏关键既往史 -5 分/项 |
| 3 | **检查结果利用** | 15 | 是否主动询问口腔检查结果；是否询问辅助检查（X光/CBCT） | 未询问检查结果 -10 分 |
| 4 | **诊断准确性** | 25 | 主诊断是否正确；次要诊断是否遗漏 | 主诊断错误 -20 分；遗漏次要诊断 -5 分/个 |
| 5 | **治疗方案合理性** | 15 | 治疗方案是否与诊断匹配；是否考虑急症处理 | 方案明显不合理 -10 分 |

### 3.2 评估输入

LLM 收到的 prompt 包含三段信息：

1. **病例真实诊断**（`true_diagnosis` + `true_treatment_plan`）— 来自 `case.data.diagnosis` 和 `case.data.treatment_plan`（Tier 4 数据）
2. **学生提交的诊断报告** — 5 个字段全部传入
3. **学生问诊对话记录** — 完整对话历史，格式化为 `学生: xxx\n患者: xxx`

### 3.3 输出格式

```json
{
  "total_score": <0-100>,
  "max_score": 100,
  "dimensions": [
    {
      "name": "主诉与现病史采集",
      "score": <0-30>,
      "max_score": 30,
      "justification": "具体扣分/加分理由",
      "missed_items": ["遗漏项1", "遗漏项2"]
    }
    // ...其余4个维度同结构
  ]
}
```

**注意**：Track A 的 dimensions 中只有 `missed_items`（遗漏项），**没有** `suggestions`（改进建议），后者由 `_normalize_dimensions()` 补空数组确保数据结构一致。

---

## 四、Track B：MAAS-Global 沟通能力评估（100 分）

基于 **马斯特里赫特临床沟通技能评估量表（MAAS-Global）**，评估学生与患者沟通的软技能。

**Prompt 文件**：[backend/agent/prompts/evaluator/maas_global_scoring.txt](backend/agent/prompts/evaluator/maas_global_scoring.txt)

### 4.1 六个评分维度

| # | 维度 | 满分 | 评估要点 | 扣分规则 |
|---|------|------|----------|----------|
| 1 | **问诊开场** | 10 | 是否恰当介绍自己并说明问诊目的；是否营造舒适氛围 | 开场生硬、未自我介绍 -5 分 |
| 2 | **提问系统性** | 25 | 是否按合理逻辑顺序提问；是否遵循问诊框架（OLDCARTS）；是否避免跳跃式提问 | 提问零散无逻辑 -10 分；反复问同类问题 -5 分 |
| 3 | **倾听与共情** | 20 | 是否对患者描述给予适当回应；是否表现对患者痛苦的理解和关心 | 打断患者 -5 分；对明显痛苦无回应 -10 分 |
| 4 | **语言表达** | 15 | 是否使用患者能理解的语言；是否避免过多专业术语 | 全程大量医学术语 -10 分 |
| 5 | **信息归纳能力** | 15 | 是否在问诊中适时总结已获信息；核对信息准确性 | 完全没有总结 -10 分 |
| 6 | **问诊效率** | 15 | 是否在合理轮次内完成问诊；是否提冗余或无关问题 | 严重偏题 -5 分/次 |

### 4.2 评估输入

**仅对话历史** `conversation_history` — 不提供病例标准答案，LLM 仅从对话质量本身评判沟通技能。

### 4.3 输出格式

```json
{
  "total_score": <0-100>,
  "max_score": 100,
  "dimensions": [
    {
      "name": "问诊开场",
      "score": <0-10>,
      "max_score": 10,
      "justification": "具体评分理由",
      "suggestions": ["改进建议"]
    }
    // ...其余5个维度同结构
  ]
}
```

**注意**：Track B 的 dimensions 中只有 `suggestions`（改进建议），**没有** `missed_items`，后者由 `_normalize_dimensions()` 补空数组。

---

## 五、综合评分计算

前端 [frontend/src/pages/AssessmentPage.tsx](frontend/src/pages/AssessmentPage.tsx) 计算综合分：

```typescript
const compositeScore = (diagnostic.total_score + communication.total_score) / 2;
```

颜色阈值（适用于综合分和单个维度得分率）：

| 得分率 | 颜色 | 含义 |
|--------|------|------|
| ≥ 85% | 绿色 `text-green-600` | 优秀 |
| 70%–84% | 琥珀色 `text-amber-600` | 良好/一般 |
| < 70% | 红色 `text-red-600` | 需改进 |

---

## 六、技术实现细节

### 6.1 LLM 调用配置

| 参数 | 值 | 说明 |
|------|------|------|
| 模型 | `settings.llm_model_pro`（默认 `qwen-plus`） | 通过环境变量 `.env` 覆盖 |
| temperature | `0.0` | 评分需确定性，禁用随机采样 |
| max_tokens | `2048` | 跨所有评估调用 |
| 重试 | 最多 3 次，指数退避（2^attempt 秒） | [agent/llm_client.py](backend/agent/llm_client.py) |
| 并行 | `asyncio.gather` 同时启动两条 Track | 无相互依赖 |

### 6.2 数据存储

评估结果存入 `assessments` 表（[backend/app/models/assessment.py](backend/app/models/assessment.py)）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `diagnostic` | JSON | Track A 完整结果 |
| `communication` | JSON | Track B 完整结果 |
| `student_report` | JSON | 学生提交的诊断报告快照 |
| `comment` | Text | 预留：教师评语（当前未使用） |

### 6.3 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/sessions/{id}/assessment` | 提交诊断 → 触发评估 → 返回结果 |
| `GET` | `/api/v1/sessions/{id}/assessment` | 获取已有的评估结果 |

评估为**同步阻塞**（MVP 阶段）——POST 请求等待 LLM 返回后才响应。已存在评估时直接返回缓存结果。

### 6.4 归一化处理

`_normalize_dimensions()`（[evaluator_agent.py:101](backend/agent/evaluator_agent.py)）确保两端数据结构对称：
- Track A 的 dimensions 自动补 `suggestions: []`
- Track B 的 dimensions 自动补 `missed_items: []`

### 6.5 JSON 解析容错

`_parse_json()` 自动处理 LLM 输出的 markdown 代码块包装（`` ```json ... ``` ``），确保 API 返回与 prompt 要求一致。

---

## 七、前端展示

### 7.1 评估报告页

[frontend/src/pages/AssessmentPage.tsx](frontend/src/pages/AssessmentPage.tsx)

- 顶部：综合评分大数字（颜色阈值着色）
- 两个 ScoreCard：
  - 🏥 诊断能力评估 (Station 4 标准)
  - 💬 沟通能力评估 (MAAS-Global 标准)

### 7.2 ScoreCard 组件

[frontend/src/components/ScoreCard.tsx](frontend/src/components/ScoreCard.tsx)

每个维度展示：
- 维度名称 + 得分（分数/满分，颜色阈值着色）
- ProgressBar 进度条
- `justification` — 评分理由文字
- `missed_items` — 红色"遗漏"标记（Station 4）
- `suggestions` — 蓝色"建议"标记（MAAS-Global）

---

## 八、评估维度速查表

### Track A — Station 4

```
主诉与现病史采集  ██████████████████████████████  30分
既往史采集        ███████████████                15分
检查结果利用      ███████████████                15分
诊断准确性        █████████████████████████      25分
治疗方案合理性    ███████████████                15分
                             Total ──────────  100分
```

### Track B — MAAS-Global

```
问诊开场          ██████████                    10分
提问系统性        █████████████████████████      25分
倾听与共情        ████████████████████          20分
语言表达          ███████████████                15分
信息归纳能力      ███████████████                15分
问诊效率          ███████████████                15分
                             Total ──────────  100分
```

---

## 九、系统边界与局限

### 当前实现的边界

1. **评估者身份**：LLM 同时扮演 Station 4 考官和 MAAS-Global 评估专家两个角色，非独立双重评估
2. **无教师审核层**：评估结果直接返回学生，无人类教师 review 环节
3. **同步阻塞**：评估为同步执行，大模型响应延迟直接影响用户体验
4. **无历史对比**：重复练习同一病例不会自动提示"上次得分 XX，本次进步 XX"
5. **评分精确度**：LLM 给出整数评分，但评分的一致性和可复现性受模型版本影响
6. **`comment` 字段未启用**：数据库中预留了教师评语字段但当前未使用

### 已知幻觉风险

| 风险点 | 缓解措施 |
|--------|----------|
| LLM 误判诊断正确性 | temperature=0，提供病例标准答案作为 ground truth |
| 评分尺度不一致（不同会话间浮动） | temperature=0 减小方差；但不同模型/版本间仍可能存在系统偏差 |
| LLM 编造未发生的对话 | prompt 要求仅依据提供的对话记录评分，不自行补充 |
| 中文医学术语理解偏差 | 使用千问（qwen）中文优化模型 |

---

## 十、相关文件索引

| 文件 | 角色 |
|------|------|
| [backend/agent/evaluator_agent.py](backend/agent/evaluator_agent.py) | 评估核心逻辑 — 并行触发两条 Track |
| [backend/agent/prompts/evaluator/station4_scoring.txt](backend/agent/prompts/evaluator/station4_scoring.txt) | Station 4 评分 prompt 模板 |
| [backend/agent/prompts/evaluator/maas_global_scoring.txt](backend/agent/prompts/evaluator/maas_global_scoring.txt) | MAAS-Global 评分 prompt 模板 |
| [backend/agent/llm_client.py](backend/agent/llm_client.py) | LLM API 客户端（重试、流式） |
| [backend/app/services/assessment_service.py](backend/app/services/assessment_service.py) | 评估业务逻辑 — 编排提交、执行、存储 |
| [backend/app/api/assessments.py](backend/app/api/assessments.py) | API 路由 — `POST/GET assessment` |
| [backend/app/schemas/assessment.py](backend/app/schemas/assessment.py) | Pydantic 数据模型 |
| [backend/app/models/assessment.py](backend/app/models/assessment.py) | SQLAlchemy 数据表模型 |
| [backend/app/config.py](backend/app/config.py) | 模型配置（llm_model_pro） |
| [frontend/src/components/DiagnosisForm.tsx](frontend/src/components/DiagnosisForm.tsx) | 学生诊断提交表单 |
| [frontend/src/pages/AssessmentPage.tsx](frontend/src/pages/AssessmentPage.tsx) | 评估报告展示页 |
| [frontend/src/components/ScoreCard.tsx](frontend/src/components/ScoreCard.tsx) | 评分维度卡片组件 |
| [frontend/src/components/ui/ProgressBar.tsx](frontend/src/components/ui/ProgressBar.tsx) | 进度条组件 |
