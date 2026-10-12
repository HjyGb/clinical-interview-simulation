# 临床问诊模拟系统 · Clinical Interview Simulation

> LLM 驱动的虚拟标准化患者（Virtual Standardized Patient）教学训练平台 —— 面向口腔医学教育

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.x-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.4-3178C6?logo=typescript)](https://www.typescriptlang.org)
[![Vite](https://img.shields.io/badge/Vite-5.x-646CFF?logo=vite)](https://vitejs.dev)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-4.x-06B6D4?logo=tailwindcss)](https://tailwindcss.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 目录

- [项目背景](#项目背景)
- [系统架构](#系统架构)
- [核心特性](#核心特性)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [功能模块](#功能模块)
- [AI Agent 设计](#ai-agent-设计)
- [评估体系](#评估体系)
- [数据资产](#数据资产)
- [文档索引](#文档索引)
- [开发路线图](#开发路线图)

---

## 项目背景

### 问题

医学教育中，**标准化患者（Standardized Patient, SP）** 是训练医学生临床问诊能力的关键手段。然而真人 SP 面临三大困境：

| 困境 | 具体表现 |
|------|----------|
| **成本高昂** | 招募、培训、排班、薪酬——单所医学院年均 SP 支出可达数十万元 |
| **资源稀缺** | 合格 SP 数量有限，每位学生每学期仅有 2–3 次练习机会 |
| **一致性差** | 同一病例由不同 SP 扮演时表达差异大，评分缺乏标准化基线 |

**口腔科**的 SP 需求尤为突出：口腔问诊有其独特的 OLDCARTS 框架、牙位描述体系和检查流程，且中国口腔执业医师考试（Station 4）对问诊能力有明确的评分标准。

### 解决方案

利用**大语言模型（LLM）**构建虚拟标准化患者 Agent，实现：

- **低成本**：一次部署，无限次复用，边际成本趋近于 API 调用费用
- **可扩展**：支持大量学生并发练习，不受物理时空限制
- **可控一致**：同一病例的核心事实始终一致，人格风格可调节但不影响医学事实
- **即时反馈**：问诊结束后按医院 R01–R14 逐项评分，生成评估报告（临床能力 + 沟通人文）

> **2026-10-12 更新**：旧的「双轨评估」（Station 4 + MAAS-Global，两分取平均）已废弃并删除，
> 改用医院提供的 R01–R14 框架。见 [docs/scoring-system-design.md](docs/scoring-system-design.md)。

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端层 (Frontend)                      │
│              React 18 + Vite + TypeScript                │
│              Tailwind CSS 4 + Zustand                    │
│                                                          │
│  登录页  │  病例选择  │  问诊对话(流式)  │  评估报告     │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP/SSE (JSON + Server-Sent Events)
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   后端层 (Backend)                        │
│                Python 3.10+ / FastAPI                    │
│                                                          │
│  API Router (REST)  │  Auth 中间件 (JWT)  │  Session    │
│  ───────────────────────────────────────────────────    │
│  Case Service  │  Dialog Service  │  Assessment Service │
│  ───────────────────────────────────────────────────    │
│  SQLAlchemy ORM → SQLite (dev) / PostgreSQL (prod)      │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                 Agent 核心层 (Agent Core)                 │
│                 Python / 纯逻辑 + LLM 调用               │
│                                                          │
│  Patient Agent                    Scoring (R01–R14)      │
│  ┌──────────────────────┐        ┌──────────────────┐   │
│  │ Fact Selector        │        │ R01–R04 纯 Python │   │
│  │  (选事实 ID/问句类型)│        │  (读披露/申请轨迹)│   │
│  ├──────────────────────┤        ├──────────────────┤   │
│  │ Disclosure Gate      │        │ R05–R14 LLM       │   │
│  │  (纯 Python 门控)    │        │  (逐条 + 证据强制)│   │
│  ├──────────────────────┤        ├──────────────────┤   │
│  │ Response Generator   │        │ Safety Channel    │   │
│  │  (流式生成)          │        │  (独立, 不平均)   │   │
│  └──────────────────────┘        └──────────────────┘   │
└────────────────────────┬────────────────────────────────┘
                         │ OpenAI-compatible API
                         ▼
                 ┌──────────────────┐
                 │  阿里百炼 API     │
                 │  DashScope       │
                 └──────────────────┘
```

### 架构原则

| 原则 | 说明 |
|------|------|
| **模块化三层解耦** | Agent 核心 / 后端 API / 前端 UI 各自独立，通过 HTTP + JSON 通信 |
| **配置外部化** | 模型选择、API 地址、数据库路径、Prompt 模板均通过环境变量管理 |
| **可测试性优先** | 每个 LLM 调用节点可 Mock，Agent 核心逻辑可脱离 API 单独测试 |
| **先跑通再优化** | MVP 阶段不引入消息队列、缓存层、微服务等复杂基础设施 |
| **零幻觉设计** | 结构化字段查找优先于 LLM 自由生成，信息不足时回答"不清楚" |

---

## 核心特性

### 🩺 虚拟标准化患者（*2026-10-11 更新*）

- **3 步流水线**：事实选择 → 披露门控 → 回答生成（旧的第 4 步"事后事实校验"已删除——它跑在流式之后，撤回不了）
- **按事实 ID 精确披露**：学生问哪条给哪条；对外开放式问诊才给 H01–H04
- **数据边界即安全**：诊断/治疗数据**根本不进患者侧**，不是"被告知别说"，而是模型脑子里没有
- **绝不编造**：缺失就说"没太注意"，**绝不把不知道说成"没有/正常"**；学生会话里说错了要礼貌纠正
- **稳定人格**：全部已知事实 + 8 条行为规则常驻 system prompt；跨轮记忆覆盖整场会话
- **独立检查模块**：学生申请检查由**另一个角色**返回结果，支持子项裁剪（只给申请的那一小项）
- **流式输出**：Token-by-token 实时渲染，模拟真实患者逐句说话

### 📋 R01–R14 逐项评估（*2026-10-12 更新*）

| 分组 | 条目 | 怎么判 |
|------|------|--------|
| **病史采集** | R01–R03 | 纯 Python：读患者披露轨迹 |
| **检查运用** | R04–R05 | R04 纯 Python（申请轨迹 vs 该例「关键」检查）；R05 LLM |
| **诊断与推理** | R06–R08 | LLM：对照参考答案逐条判，**必须引用学员原话** |
| **处理与计划** | R09–R10 | LLM：同上 |
| **解释与告知** | R11–R12 | LLM：评对话里的解释与安全告知 |
| **以患者为中心** | R13–R14 | LLM：评对担忧/偏好的回应与用语 |

**每项 0–2 分，原始分上限 28**（非百分制；医院未给及格线，权重待专家定）。
**不给综合分**——安全错误另列并交人工复核，**不与沟通表现取平均**。

### 🎓 教学场景闭环

```
教师准备病例 → 学生选择病例 → AI患者开场 → 学生逐轮提问 →
AI患者回答 → 学生提交诊断 → 系统自动评估 → 学生查看评估报告
```

- 对话轮数上限控制（当前 25 轮，为开发测试值；医院 S01 常规路径有 13 步）
- 会话历史完整保存，支持回放查看
- 快速登录（工号制，无需注册）
- 只读历史回放模式

---

## 技术栈

| 层 | 技术 | 版本 | 选型理由 |
|---|------|------|----------|
| **前端框架** | React | 18.x | 生态成熟，SSE 流式渲染支持完善 |
| **构建工具** | Vite | 5.x | 快速 HMR，零配置 TypeScript |
| **CSS 方案** | Tailwind CSS | 4.x | Utility-first，CSS 变量统一主题 |
| **状态管理** | Zustand | 4.5 | 轻量，无样板代码 |
| **路由** | React Router DOM | 6.x | 标准前端路由 |
| **后端框架** | FastAPI | 0.110+ | 原生 async、自动 OpenAPI 文档、SSE 支持 |
| **ORM** | SQLAlchemy | 2.x | Python ORM 标准 |
| **数据库(开发)** | SQLite | 3.x | 零配置，文件即数据库 |
| **数据库(生产)** | PostgreSQL | 15+ | 支持并发写入、JSON 字段 |
| **LLM SDK** | openai (Python) | 1.x | 阿里百炼兼容 OpenAI 接口 |
| **Embedding** | sentence-transformers | 2.7 | 本地 BGE 模型运行 |
| **向量检索** | FAISS | 1.x | 轻量本地索引 |
| **日志** | loguru | ≥0.7 | 比标准 logging 更友好 |
| **测试** | 独立验收脚本（非 pytest） | — | 见「快速开始 → 5. 运行测试」 |
| **LLM 平台** | 阿里百炼 DashScope | — | OpenAI 兼容接口；当前 `qwen-plus`(生成) + `qwen-turbo`(选择) |

---

## 项目结构

```
Clinical Interview Simulation/
├── backend/                        # Python 后端 (FastAPI)
│   ├── app/                        # 应用层
│   │   ├── main.py                 # FastAPI 入口 + CORS + 路由注册
│   │   ├── config.py               # 环境变量配置 (pydantic-settings)
│   │   ├── database.py             # SQLAlchemy engine + session
│   │   ├── api/                    # REST API 路由
│   │   │   ├── auth.py             # 登录认证 (JWT)
│   │   │   ├── cases.py            # 病例 CRUD
│   │   │   ├── sessions.py         # 会话管理 + 对话消息
│   │   │   └── assessments.py      # 评估提交 + 查询
│   │   ├── models/                 # SQLAlchemy 数据模型
│   │   │   ├── user.py             # 用户表
│   │   │   ├── case.py             # 病例表
│   │   │   ├── session.py          # 会话表 (含 persona 快照)
│   │   │   ├── message.py          # 消息表
│   │   │   └── assessment.py       # 评估表
│   │   ├── schemas/                # Pydantic 请求/响应 Schema
│   │   │   ├── auth.py
│   │   │   ├── case.py
│   │   │   ├── session.py
│   │   │   └── assessment.py
│   │   ├── services/               # 业务逻辑层
│   │   │   ├── auth_service.py     # 认证逻辑
│   │   │   ├── case_service.py     # 病例管理
│   │   │   ├── session_service.py  # 对话编排 (调用 Agent)
│   │   │   └── assessment_service.py # 评估流程
│   │   └── middleware/
│   │       └── auth.py             # JWT 认证中间件
│   ├── agent/                      # Agent 核心层（不碰数据库，只收 dict）
│   │   ├── patient_agent.py        # 编排：事实选择 → 披露门控 → 生成（3 步）
│   │   ├── fact_selector.py        # ① 问句类型 + 命中哪几条事实 ID (LLM)
│   │   ├── disclosure.py           # ② 披露门控 + 披露轨迹（纯 Python）
│   │   ├── response_generator.py   # ③ 稳定人格 + 本轮允许的事实 → 流式口语 (LLM)
│   │   ├── exam_module.py          # 检查模块：两级匹配 + 子项裁剪（纯 Python）
│   │   ├── exam_subitem_splitter.py# 构建期：切分子项的提案（LLM，不在运行时链路）
│   │   ├── persona.py              # 人格配置 (81种组合，当前固定默认)
│   │   ├── llm_client.py           # LLM 调用封装 (重试/退避)
│   ├── prompts/                    # Prompt 模板 (.txt，改了要重启服务)
│   │   ├── patient/                # system_base / response_generator / fact_selector
│   │   ├── exam/                   # subitem_splitter（构建期）
│   │   └── scoring/                # r14_item（逐条评分）/ critical_error（关键错误）
│   ├── scoring/                    # R01–R14 评分（纯逻辑 + LLM 判定）
│   ├── tests/                      # 仅 __init__.py —— 没有测试套件，见下方「测试」
│   └── requirements.txt            # Python 依赖
├── frontend/                       # React 前端 (Vite + TypeScript)
│   ├── src/
│   │   ├── App.tsx                 # 路由配置
│   │   ├── main.tsx                # 入口
│   │   ├── index.css               # CSS 变量 + 全局样式 + Tailwind
│   │   ├── api/                    # API 调用层
│   │   │   ├── client.ts           # axios/fetch 封装
│   │   │   ├── auth.ts             # 登录 API
│   │   │   ├── cases.ts            # 病例 API
│   │   │   ├── sessions.ts         # 会话 API
│   │   │   └── assessments.ts      # 评估 API
│   │   ├── pages/                  # 页面组件
│   │   │   ├── LoginPage.tsx       # 登录页
│   │   │   ├── CaseListPage.tsx    # 病例选择页
│   │   │   ├── InterviewPage.tsx   # 问诊训练主界面 (4列Grid布局)
│   │   │   ├── AssessmentPage.tsx  # 评估报告页
│   │   │   └── HistoryPage.tsx     # 历史记录页
│   │   ├── components/             # 可复用组件
│   │   │   ├── ChatBubble.tsx      # 聊天气泡 (医/患双角色)
│   │   │   ├── ChatInput.tsx       # 消息输入框
│   │   │   ├── DiagnosisForm.tsx   # 诊断提交表单 (5字段)
│   │   │   ├── ScoreCard.tsx       # 评分卡片
│   │   │   └── ui/                 # 基础 UI 组件
│   │   │       ├── Modal.tsx       # 模态框
│   │   │       ├── ToastContainer.tsx # Toast 通知
│   │   │       ├── StatusBadge.tsx    # 状态标签
│   │   │       ├── DifficultyBadge.tsx # 难度标签
│   │   │       ├── Alert.tsx          # 提示条
│   │   │       ├── LoadingDots.tsx    # 加载动画
│   │   │       └── ProgressBar.tsx    # 进度条
│   │   ├── stores/                 # Zustand 状态管理
│   │   │   ├── authStore.ts        # 认证状态
│   │   │   ├── interviewStore.ts   # 问诊会话状态
│   │   │   └── toastStore.ts       # Toast 通知状态
│   │   └── types/                  # TypeScript 类型定义
│   │       └── index.ts
│   ├── package.json
│   ├── vite.config.ts
│   └── index.html
├── data/                           # 数据目录 (整目录不进 git)
│   ├── cases/                      # **只放最终进系统的数据**
│   │   ├── en01.patient.json …     # 患者侧 ×5（identity/opening/facts/psychology）
│   │   └── en01.exam.json …        # 检查侧 ×5（E 项 + 子项，schema v2.2）
│   ├── staging/                    # 中间产物（extract 的输出，可随时重建）
│   ├── old/                        # 弃用：旧扁平 exam、mvp_cases.json
│   ├── tests/                      # B 测试规格、子项核对表、各次报告
│   └── raw/                        # 医院原始 docx + 文本快照
├── docs/                           # 设计文档
│   ├── architecture-current.md            # **现状说明（入口）**：角色/数据流/prompt/缺口
│   ├── patient-simulation-dev-plan.md     # 施工记录 M1–M7（含各阶段"实际 vs 预判"）
│   ├── case-data-schema.md                # 病例数据范本 v2.2（含 V1–V7 校验规则）
│   ├── data-requirements.md               # 为什么数据长这样（四层标签）
│   ├── case-data-structure.md             # 医院 docx 的编号体系解读
│   ├── positioning-and-principles.md      # 五原则 P1–P5
│   ├── patient-roleplay-architecture.md   # 设计论证（已实施；§2 为历史）
│   ├── model-selection.md                 # 模型角色与选型
│   └── project-requirements-overview.md   # 原 PRD
├── old_docs/                       # 归档：开工前架构设计、agent 改造提案、旧路线图、评分标准、persona、前端计划
├── local/                          # 本地开发资源
├── memory/                         # Claude Code 持久记忆
├── .claude/                        # Claude Code 配置
├── .gitignore
├── CLAUDE.md                       # Claude Code 项目指引
└── README.md                       # 本文件
```

---

## 快速开始

### 环境要求

- **Python** 3.10+
- **Node.js** 18+
- **阿里百炼 DashScope API Key**（[免费注册](https://bailian.console.aliyun.com)）

### 1. 克隆仓库

```bash
git clone <repo-url>
cd "Clinical Interview Simulation"
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# LLM (阿里百炼 DashScope)
LLM_API_KEY=your-dashscope-api-key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_PRO=qwen-plus
LLM_MODEL_LITE=qwen-turbo

# Database
DATABASE_URL=sqlite:///data/app.db

# Auth
SECRET_KEY=your-secret-key-here

# App
APP_NAME=Clinical Interview Simulation
DEBUG=true
```

### 3. 启动后端

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

后端 API 文档自动生成：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器：http://localhost:5173

### 5. 运行测试

> ⚠️ **本项目没有单元测试套件**——`pytest` 和 `npm test` 都会"成功但什么都不跑"。
> 验收靠下面四个独立脚本（从**仓库根目录**运行即可，脚本会自己切到 `backend/`）：

```bash
python scripts/spike_fact_selector.py         # 事实选择准确率（对医院 docx 的「依据」）
python scripts/run_behavior_tests.py          # B01–B12 端到端回归（走真实 HTTP，3 次/条）
python scripts/run_exam_subitem_tests.py      # 检查子项裁剪（纯 Python）
python scripts/verify_exam_coverage.py        # 检查模块逐条需求核对
```

最近一次结果：**135/135 · 165/165 · 18/18 · 全通过**。

---

## 功能模块

### 模块 A：病例管理

- 病例来自医院提供的 30 例 docx，按 `patient.json`（患者侧）+ `exam.json`（检查侧）两份文件组织
- 患者侧：身份、开场白（固定原文）、H01–H07 事实、P01–P03 心理
- 检查侧：E 项（项名 / 重要程度 / 别名 / 结果 / 子项片段）
- 标题用**中性编号**（EN01…）——医院原题含诊断，绝不进学生端
- 当前病例库规模：**5 例**（EN01 牙体牙髓 / PE01 牙周 / PR01 修复 / MU01 黏膜 / SU01 颌面外科），其余 25 例未切分

### 模块 B：AI 患者仿真（*2026-10-11 更新*）

| 功能 | 说明 | 状态 |
|------|------|------|
| 问句类型判定 + 按事实 ID 披露 | 判 open/targeted/unknown/meta，只给命中那几条 | ✅ 已实现并验收 |
| 零幻觉保障 | 缺失用"没太注意"口吻，**不把不知道说成没有** | ✅ 已实现（探针验证） |
| 诊断信息隐藏 | **数据边界**：诊断/治疗不入患者侧数据 | ✅ 已实现 |
| 抗错误前提 | 学生说错侧别/时间要纠正，不因坚持改口 | ✅ B06 验证 |
| 越权请求回避 | 要后台答案时以患者口吻回避，之后继续正常问诊 | ✅ B08 验证 |
| 跨轮记忆 | 窗口覆盖整场会话（60 条消息），实测跨 24 轮仍记得 | ✅ 已实现 |
| 流式输出 | Token-by-token 实时渲染 | ✅ 已实现 |
| 独立检查模块 + 子项裁剪 | 申请冷测只返回冷测，不带上叩诊 | ✅ 已实现并验收 |
| 人格多样性 | 焦虑度 × 话量 × 信任度 × 语言风格 (81种) | 🟡 未接入会话创建，固定默认 |
| 多问题处理 | 一次问好几件事，一并回答 | ✅ 已实现（旧"只答第一个"规则已删） |

### 模块 C：问诊对话

- Web 界面自然语言对话，流式实时渲染
- 对话轮数上限控制（当前 25 轮；医院 S01 常规路径有 13 步，12 轮装不下）
- 对话记录完整保存（含时间戳和轮次标记）
- 支持会话删除、中途结束
- 历史回放（只读模式）

### 模块 D：诊断提交

**答卷五项**（*2026-10-12 更新*，一一对应 R06–R10）：
① 主诊断（部位 + 确定性）、② 诊断理由、③ 鉴别诊断（含区分依据）、④ 近期处理、⑤ 阶段计划与复评

> 旧的 建议检查 字段已删除——R04 看的是**对话里实际申请过什么**，留一个事后填空的字段会让学生补写没问过的检查。

### 模块 E：智能评估

- **R01–R14 逐项评分**（每项 0–2，原始分上限 28）
- 每个得分点都附**学员原话证据**；没有证据的判定一律归零
- 系统无法评价的条目记 NE/NA，并同时报告**可评上限**（不折成 0 分）
- **关键错误独立标记**，交人工复核，**不参与计分**
- 评估结果持久化存储

### 模块 F：用户与会话管理

- 工号快速登录（无需注册）
- 会话历史与学生账号关联
- 历史记录查看与管理

---

## AI Agent 设计

> ⚠️ **2026-10-11 重写**：本节原先描述的是开工前的 4 步流水线（意图分类 → 信息检索 → 生成 → 事实校验）。
> 那三步模块（`intent_classifier` / `info_retriever` / `fact_verifier`）**均已删除**。
> 完整现状见 [docs/architecture-current.md](docs/architecture-current.md)。

系统里有**三个会说话的角色**，各自的数据在存储层就是分开的：

### 患者 Agent — 3 步流水线

```
学生输入提问
     │
     ▼
┌─────────────────┐
│ 1. 事实选择      │  LLM (轻量模型, temperature=0)
│  fact_selector  │  输出: 问句类型 + 问到了哪几条事实 ID
│                 │  open / targeted / unknown / meta / exam
└────────┬────────┘
         │  type == exam ? ──→ 交给检查模块（见下），患者不参与
         ▼
┌─────────────────┐
│ 2. 披露门控      │  **纯 Python，无 LLM**
│  disclosure     │  决定"本轮允许说哪些事实" + 记披露轨迹
│                 │  open → H01–H04；unknown/meta → 什么都不给
└────────┬────────┘
         ▼
┌─────────────────┐
│ 3. 回答生成      │  LLM (主力模型, streaming, temperature=0.3)
│  response_gen   │  稳定人格 + 行为规则(system) + 本轮允许的事实(user)
└─────────────────┘
```

**为什么去掉第 4 步（事实校验）**：它跑在流式**之后**，只能记日志、无法撤回已经发出去的话。
真正的防线在上游——**数据边界**（诊断/治疗压根不在患者侧数据里）+ **披露门控**（结构性裁剪）。

### 检查模块 — 两级匹配（纯 Python）

学生申请检查时，由一个**独立于患者**的模块返回结果。真实患者不可能背出"各位点探诊深度 2–3 mm"，
所以这是两个角色，数据也分两列存（`Case.data` / `Case.exam_data`）。

```
① 项级匹配：在 E 项的 label + aliases 里找 → 命中哪几项
     · 包含规则：命中串是别人命中串的子串时只留长的（防串项）
     · 整项优先：话里出现该项 label ⇒ 直接返回整条结果
② 子项级匹配：只返回命中子项的结果片段
     · 医院明令："相关子项请求仅返回该项结果，不可返回整个 E 项"
③ 未命中 → 明确"未提供"，并说明"没有记录不等于结果正常"
```

### 安全边界：数据分层，不是提示词约束

| 数据 | 存哪 | 谁能读 |
|---|---|---|
| 身份 / 开场白 / H 事实 / P 心理 | `Case.data` | 仅患者 |
| E 检查项 / 别名 / 结果 / 子项 | `Case.exam_data` | 仅检查模块 |
| 诊断 / 治疗 / 评分依据 | **不入库** | 无 |

> **2026-10-11 变更**：原先的「Tier 1–4 分层披露」机制已废弃。
> Tier 是旧数据嵌套结构逼出来的粗粒度分档（tier2 = 主诉+现病史+既往史**整片**放行），
> 会一次倒出过多病史。现改为**按事实 ID 精确裁剪**，安全则由**数据边界**承担。
> （完整论证见 [docs/patient-roleplay-architecture.md](docs/patient-roleplay-architecture.md) §4.4）

### Scoring — R01–R14 逐项评估（*2026-10-12 更新*）

> 旧的 Evaluator Agent（Station 4 + MAAS 双轨）**已删除**——它读的标准答案字段在新数据里不存在，
> 标准答案恒为 `"未知"`；而且把两个分取平均正好违反医院「危及安全的错误不与礼貌分平均抵消」的规定。
> 设计与施工记录：[docs/scoring-system-design.md](docs/scoring-system-design.md)、[docs/scoring-dev-plan.md](docs/scoring-dev-plan.md)。

设计原则是**让模型判锚点，让代码算分**：

- **R01–R04** 纯 Python——患者/检查模块早就把证据记在 `Message.disclosed` 里了，不需要再问模型
- **R05–R14** 逐条问模型一个窄问题：对照这条锚点该得几分、证据是哪句原话；
  没有原话、或原话不出自该看的地方（报告类条目只能引作答、对话类只能引对话），**代码一律归零**
- **安全通道**独立输出：关键错误命中或未复核成，都交人工，**不进任何求和**

---

## 评估体系（*2026-10-12 更新*）

评分框架改为**医院提供的 R01–R14**（每项 0–2 分，原始上限 28），
取代旧的自造双轨。逐条定义、数据来源与实现细节见
[docs/scoring-system-design.md](docs/scoring-system-design.md)。

| ID | 条目 | 证据来自 | 判定 |
|---|---|---|---|
| R01 | 主诉与病程询问 | 对话 | 代码 |
| R02 | 鉴别症状及危险征象询问 | 对话 | 代码 |
| R03 | 诊疗史、用药和全身风险 | 对话 | 代码 |
| R04 | 必要检查选择 | 对话中的**检查申请** | 代码 |
| R05 | 检查结果解释与边界 | 对话 | LLM |
| R06 | 诊断与部位/确定性 | 作答 | LLM |
| R07 | 诊断理由 | 作答 | LLM |
| R08 | 鉴别诊断分析 | 作答 | LLM |
| R09 | 近期处理和安全优先 | 作答 | LLM |
| R10 | 阶段计划与复评 | 作答 | LLM |
| R11 | 病情及计划解释 | 对话 | LLM |
| R12 | 注意事项与安全告知 | 对话 | LLM |
| R13 | 担忧、偏好与理解核查 | 对话 | LLM |
| R14 | 尊重表达与术语使用 | 对话 | LLM |

> **无及格线、无权重**——医生批注：「评分非均匀分配，权重后续需专家讨论决定」。
> 报告只给原始分与可评上限，不替医院发明一个综合分。

### 颜色阈值

| 分数区间 | 颜色 | 含义 |
|----------|------|------|
| ≥85 | 🟢 绿色 | 优秀 |
| 70–84 | 🟡 琥珀色 | 良好 |
| <70 | 🔴 红色 | 需改进 |

---

## 数据资产

> *2026-10-11 更新*：下表左列原为旧的英文 CSV 管线（`clean_data_v2.py` → `enrich_cases.py`），
> 现已**不再使用**。当前病例数据全部来自医院提供的 docx。

| 数据资源 | 规模 | 状态 | 用途 |
|----------|------|------|------|
| 医院提供的病例 docx | 30 例 | 本地私有（`data/raw/`） | **当前唯一数据源** |
| 已切分入库的病例 | **5 例** | schema v2.2，已验收 | 虚拟患者仿真 |
| 行为测试规格 | 5 例 × 12 条 | 已转成可断言的 JSON | 回归验收 |
| 检查子项 | 5 例 19 项 | 13 项已切分（名称与归属为**我们补的**，待医院核对） | 子项裁剪 |
| 旧英文门诊病历 CSV | 2,124 条 | 本地私有（含 PHI，不进 Git） | **已弃用的旧管线** |

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [现状说明](docs/architecture-current.md) | **当前入口**：三个角色、数据流、prompt、SSE、记忆机制、已知缺口 |
| [病人模拟开发方案](docs/patient-simulation-dev-plan.md) | 施工记录 M1–M7：各阶段改动文件、测试分工、每阶段"实际 vs 预判" |
| [病例数据范本](docs/case-data-schema.md) | schema v2.2 字段表 + V1–V7 校验规则（切新病例照这个来） |
| [数据需求](docs/data-requirements.md) | 为什么数据长这样：四层标签（权限/模块/项/子项） |
| [病例数据结构解读](docs/case-data-structure.md) | 医院 docx 的编号体系（H/P/E/D/R/B/S/K/V）与四角色权限 |
| [定位与原则](docs/positioning-and-principles.md) | 五原则（P1–P5）：忠实优先、引擎/内容分离 |
| [设计论证](docs/patient-roleplay-architecture.md) | 为什么是「角色扮演」而非「问答系统」；§4 五个决策的完整论证 |
| [模型选型](docs/model-selection.md) | 三种模型角色、当前选型、真正落地所需规模 |
| [项目需求总览](docs/project-requirements-overview.md) | 原 PRD：背景、用户画像、功能需求 |
| [归档文档](old_docs/) | 开工前架构设计、agent 改造提案、旧路线图、评分标准、persona、前端计划、会议准备 |

---

## 开发路线图

> *2026-10-11 重写*。施工细节与逐阶段实测记录见 [docs/patient-simulation-dev-plan.md](docs/patient-simulation-dev-plan.md)。

### ✅ 病人模拟核心（已建成并验收）

- [x] 数据管道：docx → 分角色 JSON（`patient.json` / `exam.json`），schema v2.2
- [x] 患者 Agent 重建为**角色扮演**：稳定人格 + 披露门控 + 数据边界
- [x] 事实选择器（LLM）判问句类型 + 选事实 ID —— 准确率 135/135
- [x] 披露门控（纯 Python）+ 披露轨迹落库
- [x] 独立检查模块 + 两级匹配 + **子项裁剪**
- [x] 行为测试回归 165/165 · 子项测试 18/18 · 检查覆盖核对全通过
- [x] 跨轮记忆：窗口覆盖整场会话（实测跨 24 轮仍记得）
- [x] 前端完整页面（登录 → 病例选择 → 问诊对话 → 评估报告 → 历史记录）
- [x] 流式输出（SSE）+ JWT 认证 + 会话管理

### 🟡 进行中 / 待办

- [ ] **评分功能修复**：评估器仍读旧字段，与新版病例数据不兼容（最优先）
- [ ] **其余 25 例切分入库**（当前 5 例）
- [ ] **子项标签送医院核对**：现有子项名与归属全是 `derived`（核对表已生成）
- [ ] 医院 B3 段的 S01/S02 多轮脚本（从未运行过）
- [ ] 人格风格系统激活（81 组合，基础设施已就绪但未接入会话创建）
- [ ] 患者侧两处小残留：偶发漏记披露轨迹、偶发软性编造

### 🔲 计划中

- [ ] 教师管理端（病例审核、学生统计、教学数据分析）
- [ ] 综合文字评语（带教老师风格）
- [ ] 多科室扩展支持（引擎泛化，需另一份专家撰写的数据验证）
- [ ] PostgreSQL 生产部署支持 / Docker 容器化

---

## 开发说明

### 设计约束

- LLM API 是**唯一外部依赖**——单点故障，所有 LLM 调用均有重试逻辑
- SQLite 仅用于开发/演示；并发写入会阻塞，生产环境需迁移至 PostgreSQL
- 所有 LLM 分类/校验步骤使用 `temperature=0`
- API Key 仅通过环境变量注入，**绝不硬编码**
- `medical_records.csv` **绝不提交到 Git**（包含患者隐私数据）
- 单开发者项目——范围纪律是头等大事，MVP 优先于完美主义

### 关键设计决策（*2026-10-11 更新*）

1. **查找优于生成**：患者说出的每条事实都由"事实 ID 精确寻址"决定（不是 RAG），医学内容不进模型自由发挥
2. **数据边界即安全**：诊断/治疗数据**不入患者侧**——不是"被告知别说"，是模型脑子里没有，越狱也拿不到
3. **引擎 / 内容分离**：科室特有的东西只进数据文件，不写进代码（换科室 = 换一份专家数据）
4. **失败必须长得像失败**：任何 LLM 调用的兜底值都不许是正常业务值（如选择器失败返回 `question_type: "error"`）
5. **让模型判锚点，让代码算分**（*2026-10-12 更新*）：LLM 只回答「这条锚点是否命中、证据是哪句原话」，分数由代码聚合；不引用原话的判定一律归零；安全错误独立输出，不与任何分数抵消

---

## 许可证

本项目仅用于学术研究和教育目的。

---

> 🏥 让每一位口腔医学生都能在安全、可控、标准化的环境中充分练习临床问诊技能。
