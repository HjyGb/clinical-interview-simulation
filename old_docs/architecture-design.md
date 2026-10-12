# Clinical Interview Simulation — 技术架构设计

> 版本：v0.1（初步架构）
> 更新日期：2026-08-01
> 状态：设计阶段，尚未实现

---

## 一、架构总览

### 1.1 架构原则

| 原则 | 说明 |
|---|---|
| **模块化三层解耦** | Agent 核心 / 后端 API / 前端 UI 各自独立，通过 HTTP + JSON 通信 |
| **配置外部化** | 模型选择、API 地址、数据库路径、Prompt 模板均通过环境变量或配置文件管理 |
| **可测试性优先** | 每个 LLM 调用节点可 Mock，Agent 核心逻辑可脱离 API 单独测试 |
| **先跑通再优化** | MVP 阶段不引入消息队列、缓存层、微服务等复杂基础设施 |

### 1.2 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端层 (Frontend)                         │
│                     React 18 + Vite + TypeScript                 │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ 登录页   │  │ 病例选择 │  │ 问诊对话 │  │ 评估报告页    │   │
│  │          │  │          │  │ (流式)   │  │ (可视化)      │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP/SSE (JSON + Server-Sent Events)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      后端层 (Backend)                            │
│                   Python 3.10+ / FastAPI                         │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  API Router  │  │  Auth 中间件 │  │  Session Manager     │  │
│  │  (REST)      │  │  (JWT)       │  │  (对话状态机)        │  │
│  └──────┬───────┘  └──────────────┘  └──────────────────────┘  │
│         │                                                        │
│  ┌──────┴──────────────────────────────────────────────────┐   │
│  │                     Service Layer                         │   │
│  │                                                           │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │   │
│  │  │ Case Service │  │ Dialog        │  │ Assessment     │  │   │
│  │  │ 病例管理     │  │ Service       │  │ Service        │  │   │
│  │  │             │  │ 对话编排      │  │ 评估引擎       │  │   │
│  │  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │   │
│  └─────────┼────────────────┼──────────────────┼───────────┘   │
│            │                │                  │                │
│  ┌─────────┴────────────────┴──────────────────┴───────────┐   │
│  │                    Data Access Layer                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐   │   │
│  │  │ Case     │  │ Session  │  │ Assessment           │   │   │
│  │  │ Repo     │  │ Repo     │  │ Repo                 │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────────┘   │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │ SQLAlchemy ORM                    │
│                             ▼                                   │
│                      ┌──────────────┐                           │
│                      │   SQLite     │                           │
│                      │   (开发)     │                           │
│                      │   PostgreSQL │                           │
│                      │   (生产)     │                           │
│                      └──────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Agent 核心层 (Agent Core)                    │
│                   Python / 纯逻辑 + LLM 调用                     │
│                                                                  │
│  ┌───────────────────────┐  ┌───────────────────────────────┐  │
│  │   Patient Agent       │  │   Evaluator Agent             │  │
│  │                        │  │                                │  │
│  │  ┌──────────────────┐ │  │  ┌──────────────────────────┐ │  │
│  │  │ Intent           │ │  │  │ Block A:                 │ │  │
│  │  │ Classifier       │ │  │  │ Diagnostic Scoring       │ │  │
│  │  │ (qwen flash)     │ │  │  │ (Station 4 标准)        │ │  │
│  │  └────────┬─────────┘ │  │  └──────────────────────────┘ │  │
│  │           │           │  │  ┌──────────────────────────┐ │  │
│  │  ┌────────▼─────────┐ │  │  │ Block B:                 │ │  │
│  │  │ Information      │ │  │  │ Communication Scoring    │ │  │
│  │  │ Retriever        │ │  │  │ (MAAS-Global 标准)      │ │  │
│  │  │ (结构化字段查找)  │ │  │  └──────────────────────────┘ │  │
│  │  └────────┬─────────┘ │  │  ┌──────────────────────────┐ │  │
│  │           │           │  │  │ Block C:                 │ │  │
│  │  ┌────────▼─────────┐ │  │  │ Teacher Comment          │ │  │
│  │  │ Response          │ │  │  │ (综合评语)              │ │  │
│  │  │ Generator         │ │  │  └──────────────────────────┘ │  │
│  │  │ (deepseek pro)   │ │  └───────────────────────────────┘  │
│  │  └────────┬─────────┘ │                                      │
│  │           │           │  ┌───────────────────────────────┐  │
│  │  ┌────────▼─────────┐ │  │   Embedding Service          │  │
│  │  │ Fact Verifier    │ │  │   (BGE-large-zh-v1.5 本地)   │  │
│  │  │ (qwen flash)     │ │  │   / 阿里百炼 Embedding API   │  │
│  │  └──────────────────┘ │  └───────────────────────────────┘  │
│  └───────────────────────┘                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP (OpenAI-compatible API)
                           ▼
                   ┌──────────────────┐
                   │  阿里百炼 API    │
                   │  DashScope       │
                   │                  │
                   │  deepseek-v4-pro │
                   │  qwen3.6-flash   │
                   │  text-embedding  │
                   └──────────────────┘
```

### 1.3 技术栈明细

| 层 | 技术 | 版本 | 选型理由 |
|---|---|---|---|
| **前端框架** | React | 18.x | 生态成熟，流式渲染方案丰富（EventSource / fetch stream） |
| **构建工具** | Vite | 5.x | 快速 HMR，零配置 TypeScript 支持 |
| **UI 组件库** | 待定（Ant Design / shadcn/ui） | — | MVP 可先用纯 CSS + 少量组件 |
| **状态管理** | Zustand 或 React Context | — | 轻量，避免 Redux 的样板代码 |
| **后端框架** | FastAPI | 0.110+ | 原生 async、自动 OpenAPI 文档、SSE 支持 |
| **ORM** | SQLAlchemy | 2.x | Python 生态事实标准 |
| **数据库(开发)** | SQLite | 3.x | 零配置，文件即数据库 |
| **数据库(生产)** | PostgreSQL | 15+ | 支持并发写入、JSON 字段、全文检索 |
| **LLM SDK** | openai (Python) | 1.x | 阿里百炼兼容 OpenAI 接口格式 |
| **Embedding** | sentence-transformers | 2.x | 本地运行 BGE 模型 |
| **向量检索** | FAISS | 1.x | 轻量本地索引，无外部依赖 |
| **日志** | loguru | — | 比标准 logging 更友好 |
| **测试** | pytest + pytest-asyncio | — | async 测试支持 |

---

## 二、核心数据流

### 2.1 问诊对话流（单轮）

```
学生输入提问
     │
     ▼
┌─────────────────┐
│ 1. Intent       │  LLM 调用 #1 (qwen3.6-flash, temperature=0)
│ Classifier      │  输入: 学生提问 + 对话历史摘要 + 当前病例上下文
│                 │  输出: 意图类别 + 所需信息层级（Tier 1/2/3）
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Information  │  非 LLM 调用（结构化字段查找）
│ Retriever       │  根据意图类别，从病例结构化字段中提取对应信息
│                 │  规则: Tier 1(主诉/现病史摘要) / Tier 2(详细病史) / Tier 3(检查结果)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. Response     │  LLM 调用 #2 (deepseek-v4-pro, temperature=0.3)
│ Generator       │  输入: 检索到的结构化事实 + 学生提问 + 对话历史 + Persona参数 + System Prompt
│                 │  输出: 流式逐 token 的自然语言患者回答
│                 │  System Prompt 核心约束: 只基于提供的事实回答,不足则说"不清楚"
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. Fact         │  LLM 调用 #3 (qwen3.6-flash, temperature=0)
│ Verifier        │  输入: 生成的回答(完整) + 检索到的事实
│                 │  输出: {pass: bool, violations: [...]}
│                 │  若 fail → 记录日志,流式内容已发出不可撤回
│                 │  但后续回答中可修正（或下次追问时用更保守的策略）
└────────┬────────┘
         │
         ▼
     返回 SSE 流到前端
```

> **关键设计决策**：事实校验在生成**之后**而非之前，因此已流出的 token 不可撤回。这是流式体验与准确性之间的权衡——通过在 Prompt 层面强化约束（temperature=0.3、严格限制只使用提供的事实）将校验失败率控制在可接受范围内。

### 2.2 评估流

```
学生提交诊断报告 + 完整对话历史
     │
     ▼
┌──────────────────────────────────────────────────┐
│             并行调用（无依赖关系）                 │
│                                                   │
│  ┌─────────────────────┐  ┌─────────────────────┐│
│  │ Block A             │  │ Block B             ││
│  │ Diagnostic Scoring  │  │ Communication       ││
│  │ (Station 4)         │  │ Scoring             ││
│  │                     │  │ (MAAS-Global)       ││
│  │ LLM 调用 #4         │  │ LLM 调用 #5         ││
│  │ (deepseek-v4-pro)   │  │ (deepseek-v4-pro)   ││
│  └─────────┬───────────┘  └─────────┬───────────┘│
│            │                        │            │
└────────────┼────────────────────────┼────────────┘
             │                        │
             ▼                        ▼
    ┌─────────────┐          ┌─────────────┐
    │ 维度分数    │          │ 维度分数    │
    │ + 扣分理由  │          │ + 评分理由  │
    │ + 遗漏项    │          │ + 改进建议  │
    └──────┬──────┘          └──────┬──────┘
           │                        │
           └────────┬───────────────┘
                    │
                    ▼
           ┌──────────────────┐
           │ Block C          │  LLM 调用 #6 (deepseek-v4-pro) [可选, P1]
           │ Teacher Comment  │  输入: Block A 结果 + Block B 结果
           │ 综合文字评语     │  输出: 带教老师风格的鼓励性评语
           └──────────────────┘
```

### 2.3 数据预处理流（离线）

```
medical_records.csv (2,124条)
     │
     ▼
┌──────────────────┐
│ 1. 隐私清洗      │  去除姓名、电话、住址等直接标识符
│                  │  保留: 性别(脱敏)、年龄(脱敏/区间化)、就诊日期(仅保留年月)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 2. 完整性过滤    │  过滤缺失核心字段(口腔检查/诊断/治疗方案)的记录
│                  │  2,124 → ~1,408 条合格病例
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 3. 标准化转换    │  - ICD编码标准化
│                  │  - 诊断名称归一化(处理"牙髓炎"/"急性牙髓炎"/"不可复性牙髓炎"等变体)
│                  │  - 字段结构化拆分(Tier 1/2/3/4 分类标注)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 4. 病例入库      │  写入 cases 表，每条记录一个完整结构化病例
│                  │  生成 Embedding 向量(用于相似病例检索,非必须)
└──────────────────┘
```

---

## 三、数据库设计

### 3.1 ER 图（核心实体）

```
┌──────────┐       ┌──────────────┐       ┌───────────────┐
│  User    │       │  Session     │       │  Assessment   │
├──────────┤      ├──────────────┤      ├───────────────┤
│ id (PK)  │──┐   │ id (PK)      │   ┌──│ id (PK)       │
│ username │  │   │ user_id (FK) │───┘  │ session_id(FK)│
│ role     │  │   │ case_id (FK) │──────│ type          │
│ ...      │  │   │ status       │      │ scores (JSON) │
└──────────┘  │   │ started_at   │      │ details (JSON)│
              │   │ ended_at     │      │ comment       │
              │   │ max_rounds   │      │ created_at    │
              │   └──────────────┘      └───────────────┘
              │         │
              │         │ 1:N
              │         ▼
              │   ┌──────────────┐
              │   │  Message     │
              │   ├──────────────┤
              │   │ id (PK)      │
              │   │ session_id   │
              │   │ role         │  (student / patient)
              │   │ content      │
              │   │ round_num    │
              │   │ intent       │  (仅 patient 消息, nullable)
              │   │ fact_verify  │  (JSON, 仅 patient 消息)
              │   │ created_at   │
              │   └──────────────┘
              │
              │
┌──────────┐  │
│  Case    │◄─┘
├──────────┤
│ id (PK)  │
│ title    │
│ department│  (口腔科/内科/...)
│ difficulty│  (beginner/intermediate/advanced)
│ data     │  (JSON — 完整结构化病例数据)
│ status   │  (draft/reviewed/published/archived)
│ created_at│
└──────────┘
```

### 3.2 核心表结构

#### `users`
```sql
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    VARCHAR(50)  NOT NULL UNIQUE,  -- 工号, 同时也是登录名
    password    VARCHAR(255) NOT NULL,          -- bcrypt hash
    role        VARCHAR(20)  NOT NULL DEFAULT 'student',  -- student / teacher / admin
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

#### `cases`
```sql
CREATE TABLE cases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       VARCHAR(200) NOT NULL,          -- 病例标题(用于列表展示)
    department  VARCHAR(50)  NOT NULL DEFAULT '口腔科',
    difficulty  VARCHAR(20)  NOT NULL DEFAULT 'intermediate',
    data        JSON         NOT NULL,          -- 完整结构化病例(见 3.3)
    status      VARCHAR(20)  NOT NULL DEFAULT 'draft',
    created_by  INTEGER      REFERENCES users(id),
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

#### `sessions`
```sql
CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    case_id     INTEGER NOT NULL REFERENCES cases(id),
    persona     JSON    NOT NULL,               -- 本次会话的人格参数快照
    status      VARCHAR(20) NOT NULL DEFAULT 'active',  -- active/ended/abandoned
    max_rounds  INTEGER NOT NULL DEFAULT 12,
    started_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at    TIMESTAMP
);
```

#### `messages`
```sql
CREATE TABLE messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES sessions(id),
    role         VARCHAR(10) NOT NULL,          -- student / patient
    content      TEXT    NOT NULL,
    round_num    INTEGER NOT NULL,
    intent       VARCHAR(50),                   -- 仅 patient 消息, 意图分类结果
    fact_verify  JSON,                          -- 仅 patient 消息, {pass: bool, violations: [...]}
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

#### `assessments`
```sql
CREATE TABLE assessments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL UNIQUE REFERENCES sessions(id),
    diagnostic    JSON   NOT NULL,              -- Block A: Station 4 维度分数
    communication JSON   NOT NULL,              -- Block B: MAAS-Global 维度分数
    comment       TEXT,                         -- Block C: 综合评语
    student_report JSON NOT NULL,               -- 学生提交的诊断报告快照
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 3.3 病例 JSON 数据结构 (`cases.data`)

```json
{
  "basic_info": {
    "gender": "女",
    "age": 35,
    "visit_type": "首诊"
  },
  "chief_complaint": "左下后牙反复疼痛一周，加重两天",       // Tier 1 — 首次对话即可披露
  "present_illness": {                                        // Tier 2 — 学生追问后披露
    "onset": "一周前开始出现左下后牙隐痛",
    "duration": "一周",
    "character": "持续性钝痛，近两日加重为搏动性疼痛",
    "aggravating_factors": ["冷热刺激加重", "夜间疼痛加剧"],
    "relieving_factors": ["含漱冷水暂时缓解"],
    "radiation": "向左侧耳颞部放射"
  },
  "past_history": {                                           // Tier 2
    "dental": "左下第一磨牙曾行银汞充填（2年前）",
    "medical": "否认高血压、糖尿病等全身病史",
    "allergy": "否认药物过敏史",
    "medication": "近两日自行服用布洛芬，疼痛可暂时缓解"
  },
  "oral_examination": {                                       // Tier 3 — 仅在学生询问检查结果时披露
    "inspection": "36远中邻面可见大面积龋坏，探诊可探入髓腔",
    "percussion": "36叩诊（++），垂直向叩痛明显",
    "palpation": "36根尖区扪诊不适，无明显波动感",
    "mobility": "36无明显松动",
    "thermal": "冷诊无反应，热诊激发剧烈疼痛且刺激去除后疼痛持续",
    "periodontal": "全口牙周情况尚可，36颊侧牙龈轻度充血"
  },
  "auxiliary_examination": {                                  // Tier 3
    "xray": "36根尖周可见约0.5cm直径低密度透射影，边界欠清晰",
    "cbct": null
  },
  "diagnosis": {                                              // Tier 4 — 永久隐藏
    "primary": "36慢性根尖周炎急性发作",
    "secondary": ["36深龋"],
    "icd_code": "K04.7"
  },
  "treatment_plan": {                                         // Tier 4 — 永久隐藏
    "emergency": "36开髓引流",
    "definitive": "36根管治疗",
    "restoration": "根管治疗后全冠修复",
    "notes": "术后口服抗生素3天，一周后复诊"
  }
}
```

---

## 四、API 设计

### 4.1 RESTful 端点

```
Base URL: http://localhost:8000/api/v1

POST   /auth/login                 # 工号登录 → JWT token
GET    /auth/me                    # 获取当前用户信息

GET    /cases                      # 病例列表（分页、按科室/难度筛选）
GET    /cases/:id                  # 病例详情（不含 Tier 4）
GET    /cases/:id/preview          # 病例预览（仅 Tier 1，用于学生选病例时查阅）

POST   /sessions                   # 创建新会话 {case_id, persona?}
GET    /sessions                   # 当前用户的会话列表
GET    /sessions/:id               # 会话详情（含状态、轮数、时间）
GET    /sessions/:id/messages      # 会话的消息历史
POST   /sessions/:id/messages      # 发送学生消息 → SSE 流式返回患者回答
POST   /sessions/:id/end           # 结束会话（正常结束）
POST   /sessions/:id/abandon       # 放弃会话（主动放弃）

POST   /sessions/:id/assessment    # 提交诊断报告 → 触发评估
GET    /sessions/:id/assessment    # 获取评估结果
```

### 4.2 SSE 流式响应格式

```
POST /api/v1/sessions/:id/messages
Content-Type: application/json

{"content": "请问您哪里不舒服？"}

→ Response:
Content-Type: text/event-stream

event: intent
data: {"class": "chief_complaint_inquiry", "confidence": 0.95}

event: token
data: {"token": "我"}

event: token
data: {"token": "左边"}

event: token
data: {"token": "下面"}

...

event: token
data: {"token": "。"}

event: done
data: {"round": 1, "fact_verify": {"pass": true, "violations": []}}

event: limit_warning
data: {"remaining_rounds": 1, "message": "本轮后仅剩 1 轮对话，请考虑提交诊断"}
```

### 4.3 评估结果 JSON 结构

```json
{
  "session_id": 42,
  "diagnostic": {
    "total_score": 85,
    "max_score": 100,
    "dimensions": [
      {
        "name": "主诊断准确性",
        "score": 25,
        "max_score": 30,
        "justification": "正确识别根尖周炎，但未区分急性/慢性，扣5分",
        "missed_items": ["未提及ICD编码K04.7"]
      },
      {
        "name": "鉴别诊断完整性",
        "score": 15,
        "max_score": 20,
        "justification": "列出了牙髓炎和牙周炎，但遗漏了三叉神经痛，扣5分",
        "missed_items": ["三叉神经痛"]
      }
    ]
  },
  "communication": {
    "total_score": 78,
    "max_score": 100,
    "dimensions": [
      {
        "name": "提问系统性",
        "score": 18,
        "max_score": 25,
        "justification": "基本遵循OLDCARTS框架，但未询问放射痛情况，扣7分",
        "suggestions": ["建议使用OLDCARTS记忆法逐一覆盖问诊维度"]
      }
    ]
  },
  "comment": "同学你好！整体问诊思路清晰，主诊断方向正确...",
  "evaluated_at": "2026-08-01T15:30:00Z"
}
```

---

## 五、Agent 核心设计

### 5.1 Patient Agent 架构

```
┌─────────────────────────────────────────────────────┐
│                  Patient Agent                       │
│                                                      │
│  输入:                                               │
│  ├── student_message: str                           │
│  ├── conversation_history: list[Message]            │
│  ├── case_data: CaseData                           │
│  └── persona: PersonaConfig                         │
│                                                      │
│  输出:                                               │
│  ├── response_tokens: AsyncIterator[str]  (流式)    │
│  └── fact_verify_result: FactVerifyResult           │
│                                                      │
│  内部流程:                                           │
│  ┌──────────────────────────────────────────────┐   │
│  │           Pipeline (chain)                    │   │
│  │                                               │   │
│  │  ┌─────────┐   ┌──────────┐   ┌───────────┐ │   │
│  │  │Classify │──▶│ Retrieve │──▶│ Generate  │ │   │
│  │  │Intent   │   │Info      │   │Response   │ │   │
│  │  └─────────┘   └──────────┘   └─────┬─────┘ │   │
│  │                                      │       │   │
│  │                               ┌──────▼──────┐│   │
│  │                               │   Verify    ││   │
│  │                               │   Facts     ││   │
│  │                               └─────────────┘│   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 5.2 意图分类设计

| 意图类别 | 对应信息层级 | 示例学生提问 |
|---|---|---|
| `chief_complaint_inquiry` | Tier 1 | "您哪里不舒服？"、"主要来看什么？" |
| `pain_character_inquiry` | Tier 2 | "疼痛是什么样的？"、"什么时候开始的？" |
| `medical_history_inquiry` | Tier 2 | "以前这牙有问题吗？"、"有糖尿病吗？" |
| `examination_inquiry` | Tier 3 | "叩诊疼吗？"、"拍片子了吗？" |
| `diagnosis_guess` | Tier 4 (拒绝) | "是不是牙髓炎？"、"诊断是什么？" |
| `treatment_inquiry` | Tier 4 (拒绝) | "需要拔牙吗？"、"怎么治疗？" |
| `greeting` | — | "您好" |
| `multiple_questions` | —(只回答第一个) | "您哪不舒服？疼多久了？发烧吗？" |
| `irrelevant` | —(表示困惑) | "今天天气怎么样？" |

### 5.3 信息四层分级（Tier System）

```
Tier 1 ──── 首次对话自动披露 ──── 主诉、就诊原因
Tier 2 ──── 学生主动询问后披露 ── 现病史详细描述、既往史
Tier 3 ──── 学生询问检查后披露 ── 口腔检查结果、辅助检查
Tier 4 ──── 永久隐藏 ──────────── 诊断、治疗方案、ICD编码
```

### 5.4 Persona 人格参数设计

```python
@dataclass
class PersonaConfig:
    """患者人格参数 — 共 3×3×3×3 = 81 种组合"""
    
    anxiety_level: int = 1       # 焦虑程度: 1(平静) / 2(轻度焦虑) / 3(高度焦虑)
    verbosity: int = 2           # 话量:      1(寡言) / 2(正常)   / 3(健谈)
    trust_level: int = 2         # 信任度:    1(防备) / 2(正常)   / 3(高度信任)
    language_style: int = 2      # 语言风格:  1(通俗/方言) / 2(普通话) / 3(略带医学术语)
    
    def to_prompt_fragment(self) -> str:
        """将人格参数转为 Prompt 中的行为描述片段"""
        ...
```

**人格参数仅影响表达方式，不影响医学事实**。同一病例 + 不同 Persona 配置会产生自然的表达差异（如焦虑患者描述症状更情绪化、健谈患者会主动补充细节），但核心医学事实保持一致。

### 5.5 Prompt 模板架构

```
prompts/
├── patient/
│   ├── system_base.txt          # Patient Agent 基础 System Prompt
│   ├── intent_classifier.txt    # 意图分类 Prompt
│   ├── response_generator.txt   # 回答生成 Prompt（含 {case_context} {persona} 占位符）
│   └── fact_verifier.txt        # 事实校验 Prompt
├── evaluator/
│   ├── station4_scoring.txt     # Station 4 诊断评分 Prompt
│   ├── maas_global_scoring.txt  # MAAS-Global 沟通评分 Prompt
│   └── teacher_comment.txt      # 教师评语 Prompt
└── persona/
    ├── anxiety_low.txt
    ├── anxiety_high.txt
    └── ...
```

**Prompt 设计原则**：
- 所有 Prompt 模板独立于代码，作为 `.txt` 文件管理，便于迭代和 A/B 测试
- 使用 `{variable}` 占位符在运行时填充病例数据、对话历史、人格参数
- 分类类 Prompt 使用 `temperature=0`，生成类 Prompt 使用 `temperature=0.3`
- 每个 Prompt 文件头部注明版本号和变更记录

---

## 六、项目目录结构(提案)

```
clinical-interview-simulation/
├── CLAUDE.md                          # Claude Code 项目指南
├── project-requirements-overview.md   # 需求文档
├── docs/
│   └── architecture-design.md         # 本文档
├── data/
│   ├── medical_records.csv            # 原始数据（不进 Git）
│   ├── cases/                         # 标准化病例 JSON 文件
│   │   ├── case_001_periapical.json
│   │   └── ...
│   └── processed/                     # 预处理中间产物
├── backend/
│   ├── requirements.txt
│   ├── alembic/                       # 数据库迁移
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI 入口
│   │   ├── config.py                  # 配置管理（环境变量）
│   │   ├── database.py                # SQLAlchemy engine + session
│   │   ├── models/                    # ORM 模型
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── case.py
│   │   │   ├── session.py
│   │   │   ├── message.py
│   │   │   └── assessment.py
│   │   ├── schemas/                   # Pydantic 请求/响应模型
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── case.py
│   │   │   ├── session.py
│   │   │   └── assessment.py
│   │   ├── api/                       # API 路由
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── cases.py
│   │   │   ├── sessions.py
│   │   │   └── assessments.py
│   │   ├── services/                  # 业务逻辑层
│   │   │   ├── __init__.py
│   │   │   ├── case_service.py
│   │   │   ├── session_service.py
│   │   │   └── assessment_service.py
│   │   └── middleware/
│   │       ├── __init__.py
│   │       └── auth.py                # JWT 验证中间件
│   ├── agent/                         # Agent 核心层 ⭐
│   │   ├── __init__.py
│   │   ├── patient_agent.py           # Patient Agent 主逻辑
│   │   ├── intent_classifier.py       # 意图分类
│   │   ├── info_retriever.py          # 结构化字段查找
│   │   ├── response_generator.py      # 回答生成 + 流式输出
│   │   ├── fact_verifier.py           # 事后事实校验
│   │   ├── persona.py                 # PersonaConfig + Prompt 生成
│   │   ├── evaluator_agent.py         # Evaluator Agent 主逻辑
│   │   ├── llm_client.py              # LLM API 客户端封装（重试、日志）
│   │   └── prompts/                   # Prompt 模板文件
│   │       ├── patient/
│   │       │   ├── system_base.txt
│   │       │   ├── intent_classifier.txt
│   │       │   ├── response_generator.txt
│   │       │   └── fact_verifier.txt
│   │       ├── evaluator/
│   │       │   ├── station4_scoring.txt
│   │       │   ├── maas_global_scoring.txt
│   │       │   └── teacher_comment.txt
│   │       └── persona/
│   │           └── ...
│   ├── data/                          # 数据处理
│   │   ├── __init__.py
│   │   ├── preprocess.py              # 病例清洗与标准化
│   │   └── import_cases.py            # 批量导入病例到数据库
│   └── tests/
│       ├── __init__.py
│       ├── test_patient_agent.py
│       ├── test_intent_classifier.py
│       ├── test_fact_verifier.py
│       ├── test_evaluator_agent.py
│       └── conftest.py                # Fixtures: Mock LLM, test DB
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/                       # API 调用封装
│   │   │   ├── client.ts              # Axios/fetch 实例
│   │   │   ├── auth.ts
│   │   │   ├── cases.ts
│   │   │   ├── sessions.ts
│   │   │   └── assessments.ts
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── CaseListPage.tsx
│   │   │   ├── InterviewPage.tsx      # ⭐ 核心问诊页
│   │   │   ├── AssessmentPage.tsx     # 评估报告页
│   │   │   └── HistoryPage.tsx
│   │   ├── components/
│   │   │   ├── ChatBubble.tsx
│   │   │   ├── ChatInput.tsx
│   │   │   ├── StreamingText.tsx      # 流式文本渲染
│   │   │   ├── DiagnosisForm.tsx      # 诊断提交表单
│   │   │   ├── ScoreCard.tsx          # 评分卡片
│   │   │   └── Timer.tsx
│   │   ├── hooks/
│   │   │   ├── useSSE.ts              # SSE 流式 Hook
│   │   │   └── useAuth.ts
│   │   ├── stores/
│   │   │   └── interviewStore.ts      # 问诊状态管理 (Zustand)
│   │   └── types/
│   │       └── index.ts               # TypeScript 类型定义
│   └── public/
└── scripts/
    ├── setup_dev.sh                   # 开发环境初始化
    └── seed_data.py                   # 种子数据导入
```

---

## 七、关键技术决策记录

| 决策 ID | 决策 | 理由 | 权衡 |
|---|---|---|---|
| **D001** | 结构化字段查找 vs 纯 RAG | 口腔病例字段结构化程度高（OLDCARTS框架），结构化查找可以做到零幻觉 | 泛化到非结构化病例时需要额外处理 |
| **D002** | 事后事实校验 vs 事前约束 | 流式体验要求逐 token 输出，校验只能在生成后 | 已流出的错误 token 不可撤回，依赖 Prompt 约束兜底 |
| **D003** | Tier 分级披露 vs 全部可查 | 模拟真实问诊的信息渐进披露过程，考核学生的问诊系统性 | 需要人工对每条病例做 Tier 标注（一次性成本） |
| **D004** | Block A/B 并行调用 | 诊断评分与沟通评分关注不同维度，无依赖关系 | 增加 1 次 LLM 调用，但 Wall-clock 时间不变 |
| **D005** | SSE vs WebSocket | SSE 更简单（单向流），问诊场景不需要双向实时通信 | 前端只能接收，无法通过同一连接取消生成 |
| **D006** | SQLite 本地 vs 直接上 PostgreSQL | 单人开发，SQLite 零运维成本，开发迭代快 | 部署前需迁移，SQLAlchemy 使迁移成本可控 |

---

*本文档随项目实现持续更新。实现过程中发现的设计偏差应及时回写到本文档。*

