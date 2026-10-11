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
- **即时反馈**：问诊结束后自动生成双轨评估报告（诊断能力 + 沟通能力）

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
│  Patient Agent                    Evaluator Agent        │
│  ┌──────────────────────┐        ┌──────────────────┐   │
│  │ Intent Classifier    │        │ Track A:          │   │
│  │  (意图识别)          │        │ Station 4 诊断    │   │
│  ├──────────────────────┤        ├──────────────────┤   │
│  │ Info Retriever       │        │ Track B:          │   │
│  │  (结构化字段查找)    │        │ MAAS-Global 沟通  │   │
│  ├──────────────────────┤        ├──────────────────┤   │
│  │ Response Generator   │        │ Track C:          │   │
│  │  (自然语言生成)      │        │ 综合评语          │   │
│  ├──────────────────────┤        └──────────────────┘   │
│  │ Fact Verifier        │                                │
│  │  (事实校验)          │                                │
│  └──────────────────────┘                                │
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

### 🩺 虚拟标准化患者

- **4 步流水线**：意图分类 → 信息检索 → 回答生成 → 事实校验
- **4 级信息分层披露**：患者事实按 Tier 1–4 分级，Tier 4（诊断/治疗）永久隐藏
- **绝不编造医学事实**：信息不足时回答"不清楚/不知道"，确保零幻觉
- **流式输出**：Token-by-token 实时渲染，模拟真实患者逐句说话
- **81 种人格组合**：焦虑程度 × 话量 × 信任度 × 语言风格可调节（基础设施已就绪）

### 📋 双轨智能评估

| 评估轨道 | 评分标准 | 满分 |
|----------|----------|------|
| **Track A：诊断能力** | 中国口腔执医 Station 4（主诉采集、既往史、检查利用、诊断准确性、治疗方案） | 100 |
| **Track B：沟通能力** | MAAS-Global（开场、提问方式、共情回应、信息确认、总结收尾） | 100 |
| **综合评分** | (Track A + Track B) / 2 | 100 |

### 🎓 教学场景闭环

```
教师准备病例 → 学生选择病例 → AI患者开场 → 学生逐轮提问 →
AI患者回答 → 学生提交诊断 → 系统自动评估 → 学生查看评估报告
```

- 对话轮数上限控制（默认 12 轮，对标执医考试时间约束）
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
| **测试** | pytest + pytest-asyncio | ≥8.0 | async 测试支持 |
| **LLM 平台** | 阿里百炼 DashScope | — | OpenAI 兼容接口, qwen / deepseek 系列模型 |

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
│   ├── agent/                      # Agent 核心层
│   │   ├── patient_agent.py        # 患者 Agent 编排 (4-step pipeline)
│   │   ├── intent_classifier.py    # 意图分类器 (LLM)
│   │   ├── info_retriever.py       # 结构化信息检索 (非LLM)
│   │   ├── response_generator.py   # 回答生成器 (LLM + streaming)
│   │   ├── fact_verifier.py        # 事实校验器 (LLM)
│   │   ├── persona.py              # 人格配置 (81种组合)
│   │   ├── llm_client.py           # LLM 调用封装 (重试/超时)
│   │   └── evaluator_agent.py      # 双轨评估引擎
│   ├── prompts/                    # Prompt 模板文件
│   ├── tests/                      # 测试用例
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
├── data/                           # 数据目录 (不纳入版本控制)
│   ├── cases/                      # 病例 JSON 文件 (300+个)
│   │   ├── mvp_cases.json          # MVP 精选病例索引
│   │   └── intermediate/           # 按难度分级病例
│   ├── processed/                  # 处理后的数据
│   └── raw/                        # 原始数据
│       └── medical_records.csv     # 2124条口腔门诊病历 (含PHI, 不进git)
├── docs/                           # 设计文档
│   ├── patient-simulation-roadmap.md      # 当前阶段入口（病人模拟）
│   ├── patient-simulation-dev-plan.md     # 施工图（M1–M5，含各阶段实测记录）
│   ├── model-selection.md                  # 模型选型（角色/现选/落地规模）
│   ├── project-requirements-overview.md  # 项目需求总览 (PRD)
│   └── architecture-design.md            # 技术架构设计
├── old_docs/                       # 归档文档（推迟/已过时）
├── local/                          # 本地开发资源
│   └── FRONTEND_STYLING_GUIDE.md   # 前端样式参考文档
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

```bash
# 后端测试
cd backend
pytest

# 前端测试
cd frontend
npm test
```

---

## 功能模块

### 模块 A：病例管理

- 支持从原始病历数据批量导入生成标准化病例
- 病例包含完整结构化信息：基本信息、主诉、现病史、既往史、口腔检查、辅助检查、诊断、治疗方案
- 按科室分类、难度分级（初级 / 中级 / 高级）
- 当前病例库规模：**300+ 个结构化口腔病例**

### 模块 B：AI 患者仿真

| 功能 | 说明 | 状态 |
|------|------|------|
| 意图分类 + 分层披露 | 理解学生提问意图，按层级返回信息 | ✅ 已实现 |
| 零幻觉保障 | 信息不足时回答"不清楚/不知道" | ✅ 已实现 |
| 诊断信息隐藏 | Tier 4（诊断/治疗）永久不主动透露 | ✅ 已实现 |
| 流式输出 | Token-by-token 实时渲染 | ✅ 已实现 |
| 人格多样性 | 焦虑度 × 话量 × 信任度 × 语言风格 (81种) | 🟡 基础已就绪 |
| 多问题处理 | 识别连续多问，逐条引导 | 🔲 计划中 |

### 模块 C：问诊对话

- Web 界面自然语言对话，流式实时渲染
- 对话轮数上限控制（默认 12 轮，对标执医 Station 4）
- 对话记录完整保存（含时间戳和轮次标记）
- 支持会话删除、中途结束
- 历史回放（只读模式）

### 模块 D：诊断提交

- 5 字段结构化诊断报告：主诊断、鉴别诊断、诊断依据、建议检查、治疗方案
- 表单验证与提交流程

### 模块 E：智能评估

- **Track A**：Station 4 诊断评分（5 维度：主诉采集 30 + 既往史 15 + 检查利用 15 + 诊断准确性 25 + 治疗方案 15）
- **Track B**：MAAS-Global 沟通评分（5 维度：开场 20 + 提问方式 25 + 共情回应 20 + 信息确认 20 + 总结收尾 15）
- 每条扣分/加分均有具体理由
- 遗漏项指明（"还应询问……"）
- 评估结果持久化存储

### 模块 F：用户与会话管理

- 工号快速登录（无需注册）
- 会话历史与学生账号关联
- 历史记录查看与管理

---

## AI Agent 设计

### Patient Agent — 4-Step Pipeline

```
学生输入提问
     │
     ▼
┌─────────────────┐
│ 1. Intent       │  LLM 调用 #1 (轻量模型, temperature=0)
│    Classifier   │  输入: 学生提问 + 对话摘要 + 病例上下文
│                 │  输出: 意图类别 + 所需信息层级 (Tier 1/2/3)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Information  │  非 LLM 调用 — 结构化字段查找
│    Retriever    │  从病例 JSON 中按 key 直接提取事实
│                 │  设计原则: 查找优于生成，杜绝幻觉
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. Response     │  LLM 调用 #2 (主力模型, streaming)
│    Generator    │  将结构化事实转换为自然中文口语表达
│                 │  融入人格风格，模拟真实患者语气
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. Fact         │  LLM 调用 #3 (轻量模型, temperature=0)
│    Verifier     │  逐条比对回答内容与病例事实
│                 │  发现编造 → 标记并重试或回退
└─────────────────┘
```

### 信息分层披露机制 (Tiered Disclosure)

| 层级 | 内容 | 披露条件 | 示例 |
|------|------|----------|------|
| **Tier 1** | 基本信息 | 开场即披露 | 年龄、性别 |
| **Tier 2** | 主诉 + 现病史 | 学生主动询问症状时披露 | "牙疼3天了，一阵一阵的" |
| **Tier 3** | 检查结果 + 既往史 | 学生询问检查或病史时披露 | "拍过X光片，医生说牙根发炎" |
| **Tier 4** | 诊断 + 治疗方案 | **永久隐藏** | 学生需自己诊断 |

### Evaluator Agent — 双轨并行评估

两条评估流水线通过 `asyncio.gather` 并行执行，互不干扰：

- **Track A (诊断能力)**：学生报告 vs 病例标准答案 + 对话历史
- **Track B (沟通能力)**：仅分析对话历史中的沟通行为

---

## 评估体系

### 评分维度详表

#### Track A: Station 4 诊断能力 (100分)

| # | 维度 | 满分 | 评估要点 |
|---|------|------|----------|
| 1 | 主诉与现病史采集 | 30 | OLDCARTS 框架：部位、性质、程度、时间、诱因、缓解因素 |
| 2 | 既往史采集 | 15 | 口腔既往史、全身病史、用药史、过敏史 |
| 3 | 检查结果利用 | 15 | 口腔检查结果、辅助检查（X光/CBCT） |
| 4 | 诊断准确性 | 25 | 主诊断正确性、次要诊断覆盖 |
| 5 | 治疗方案合理性 | 15 | 方案与诊断匹配、急症处理考虑 |

#### Track B: MAAS-Global 沟通能力 (100分)

| # | 维度 | 满分 | 评估要点 |
|---|------|------|----------|
| 1 | 开场 | 20 | 自我介绍、说明目的、建立 rapport |
| 2 | 提问方式 | 25 | 开放到聚焦、避免诱导性提问、逻辑顺序 |
| 3 | 共情回应 | 20 | 倾听、回应患者情绪、适当安抚 |
| 4 | 信息确认 | 20 | 关键信息确认、汇总反馈 |
| 5 | 总结收尾 | 15 | 告知下一步、给予患者提问机会 |

### 颜色阈值

| 分数区间 | 颜色 | 含义 |
|----------|------|------|
| ≥85 | 🟢 绿色 | 优秀 |
| 70–84 | 🟡 琥珀色 | 良好 |
| <70 | 🔴 红色 | 需改进 |

---

## 数据资产

| 数据资源 | 规模 | 状态 | 用途 |
|----------|------|------|------|
| 原始口腔门诊病历 | 2,124 条 | 本地私有（含 PHI，不进 Git） | 病例库原始数据源 |
| 标准化口腔病例 | 300+ 个 | 已生成，JSON 格式 | 虚拟患者仿真数据 |
| MVP 精选病例 | 3 个 | 人工校验完成 | 开发测试 & Demo |

> ⚠️ **数据特征提示**：原始病历主体为**英文临床描述**，以**中文结构化标签**组织。系统 UI、对话、Prompt 均为中文，Agent 需具备在英文事实基础上用中文自然表达的能力——这是一个已知的跨语言挑战。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [病人模拟路线图](docs/patient-simulation-roadmap.md) | **当前阶段入口**：现状、新数据(30例 docx)结构、数据处理、分步落地 |
| [病人模拟开发方案](docs/patient-simulation-dev-plan.md) | **施工图（M1–M5）**：各阶段改动文件、自测/你测分工、每阶段"实际 vs 预判"记录 |
| [模型选型](docs/model-selection.md) | 三种模型角色、当前选型、真正落地所需规模 |
| [定位与原则](docs/positioning-and-principles.md) | 五原则（P1–P5）：忠实优先、引擎/内容分离 |
| [项目需求总览](docs/project-requirements-overview.md) | 完整 PRD：背景、用户画像、功能需求、数据资产、MVP 范围 |
| [技术架构设计](docs/architecture-design.md) | 系统架构图、数据流、DB Schema、API 设计、Agent 核心设计 |
| [归档文档](old_docs/) | 评分标准、数据解耦、前端改造、persona、旧数据集成、会议准备（推迟/已过时） |
| [前端样式参考](local/FRONTEND_STYLING_GUIDE.md) | PatientAgent 2.0 设计系统：颜色、排版、组件、动画、布局 |

---

## 开发路线图

### ✅ 已完成 (MVP)

- [x] 后端 API 框架搭建（FastAPI + SQLAlchemy + SQLite）
- [x] Patient Agent 4-step pipeline（意图分类 → 信息检索 → 回答生成 → 事实校验）
- [x] Evaluator Agent 双轨评估（Station 4 + MAAS-Global）
- [x] 前端完整页面（登录 → 病例选择 → 问诊对话 → 评估报告 → 历史记录）
- [x] 流式输出（SSE token-by-token 实时渲染）
- [x] JWT 认证（工号登录）
- [x] 会话管理（创建、删除、历史查看、只读回放）
- [x] 300+ 标准化病例生成
- [x] Tailwind CSS 4 迁移 + CSS 变量设计系统
- [x] Toast 通知系统、Modal 组件、StatusBadge 等 UI 基础设施

### 🟡 进行中

- [ ] 人格风格系统激活（基础设施已就绪，待接入会话创建流程）
- [ ] 真实病例精选与中文翻译（精选 100 个，翻译 + 审校双 Agent 流程）

### 🔲 计划中

- [ ] 教师管理端（病例审核、学生统计、教学数据分析）
- [ ] 批量病例导入自动化（LLM 驱动的端到端流水线）
- [ ] 综合文字评语（带教老师风格，鼓励性 + 具体改进建议）
- [ ] 自动草稿保存
- [ ] 多科室扩展支持
- [ ] 向量检索增强（BGE Embedding + FAISS 语义相似病例推荐）
- [ ] PostgreSQL 生产部署支持
- [ ] Docker 容器化部署

---

## 开发说明

### 设计约束

- LLM API 是**唯一外部依赖**——单点故障，所有 LLM 调用均有重试逻辑
- SQLite 仅用于开发/演示；并发写入会阻塞，生产环境需迁移至 PostgreSQL
- 所有 LLM 分类/校验步骤使用 `temperature=0`
- API Key 仅通过环境变量注入，**绝不硬编码**
- `medical_records.csv` **绝不提交到 Git**（包含患者隐私数据）
- 单开发者项目——范围纪律是头等大事，MVP 优先于完美主义

### 关键设计决策

1. **结构化字段查找 > 纯 RAG**：事实基于精确字段匹配，幻觉天花板 <5%
2. **双轨评估并行**：诊断评分和沟通评分互不干扰，同时执行
3. **信息分层披露**：Tier 1–3 按需披露，Tier 4 永久隐藏，确保考核公平
4. **中文 UI + 英文源数据**：跨语言事实传递是已知技术挑战

---

## 许可证

本项目仅用于学术研究和教育目的。

---

> 🏥 让每一位口腔医学生都能在安全、可控、标准化的环境中充分练习临床问诊技能。
