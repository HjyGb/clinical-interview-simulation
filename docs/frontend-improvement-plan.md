# 前端界面改造方案

> 生成日期：2026-08-01  
> 参考：`local/FRONTEND_STYLING_GUIDE.md`（PatientAgent 2.0 样式体系）  
> 当前版本：MVP v0.1（全量 inline style，无设计系统）

---

## 目录

1. [现状分析](#1-现状分析)
2. [改造目标与原则](#2-改造目标与原则)
3. [技术选型变更](#3-技术选型变更)
4. [分阶段实施计划](#4-分阶段实施计划)
5. [附录：变更文件清单](#附录变更文件清单)

---

## 1. 现状分析

### 1.1 当前技术栈

| 层级 | 当前 | 参考项目 |
|------|------|----------|
| 框架 | React 18 + TypeScript 5.4 | React 19 + TypeScript 6.0 |
| 构建 | Vite 5.3 | Vite 8.x |
| CSS 方案 | **无（全量 inline style）** | Tailwind CSS 4 + CSS 自定义属性 |
| 路由 | React Router DOM 6.23 | React Router DOM 7.x |
| 状态管理 | Zustand 4.5 | Zustand 5.x |
| 图标 | 无（emoji 占位 🩺📋🤒） | Lucide React 1.x |

### 1.2 现存问题

#### 问题 1：零 CSS 基础设施
- 无 `index.css`、无全局样式、无 CSS 变量
- 颜色值全部硬编码（`#1677ff`、`#d9d9d9`、`#e8e8e8`、`#fafafa`、`#999`）
- 缺少 `font-family` 定义，依赖浏览器默认
- 滚动条为浏览器默认样式（Windows 下粗且丑陋）

#### 问题 2：inline style 泛滥
- 每个组件 50-100 行内联样式，混合在 JSX 中
- 无复用：同样的按钮样式在 LoginPage、InterviewPage、AssessmentPage、DiagnosisForm 中重复定义
- 无交互态：仅 CaseListPage 有 hover shadow，其余缺少 `:hover`/`:focus`/`:active` 伪态
- 过渡/动画几乎为零（仅 `transition: 'box-shadow 0.2s'` 一处）

#### 问题 3：缺乏 UI 基础设施
- 无 Toast 通知系统 → 错误/成功用 `alert()` 和内部 state 显示
- 无 Modal 组件 → 诊断提交直接内嵌在页面底部
- 无 Loading 骨架/动画 → 仅文字 "正在加载..."
- 无 StatusBadge → 难度用纯色圆角矩形
- 输入框无 focus ring → 焦点态无声反馈
- 禁用按钮无一贯样式 → 各处写法不一致

#### 问题 4：布局简陋
- LoginPage：渐变背景 + 居中卡片（尚可）
- CaseListPage：单列 800px 居中（可接受）
- InterviewPage：720px 单列聊天窗（功能可用但缺乏信息密度）
- AssessmentPage：720px 单列堆叠（缺乏视觉层次）

#### 问题 5：视觉一致性问题
- 主色不统一：Login 用 `#667eea→#764ba2` 渐变，其余用 `#1677ff`
- 圆角不统一：8px / 12px / 16px 混用
- 字号不统一：无字号层级体系
- 间距不统一：无标准 spacing 尺度

### 1.3 可保留的部分

以下部分功能正常，无需重构：

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 路由 | `App.tsx` | ✅ 保留 | 5 条路由清晰，无需改动 |
| 状态管理 | `stores/*.ts` | ✅ 保留 | Zustand stores 逻辑正确，与 UI 无关 |
| API 层 | `api/*.ts` | ✅ 保留 | fetch 封装、JWT 注入、SSE 解析均正常 |
| 类型定义 | `types/index.ts` | ✅ 保留 | TypeScript 接口完整 |
| 业务逻辑 | `pages/*.tsx` | ⚠️ 保留逻辑层 | 保留 hooks/state/effect，替换 render 层 |

---

## 2. 改造目标与原则

### 2.1 核心目标

1. **建立设计系统** — CSS 变量定义颜色/字号/间距/圆角令牌，全局统一
2. **迁移到 Tailwind CSS 4** — 使用 utility-first 类名替代 90% 的 inline style
3. **补齐 UI 基础设施** — Toast、Modal、Alert、StatusBadge、Loading 组件
4. **打磨交互体验** — hover/active/focus 三态完整，过渡动画流畅
5. **保持 MVP 范围** — 不增加功能，不修改业务逻辑，只改造表现层

### 2.2 设计原则

1. **纯 Tailwind + CSS 变量** — 不引入 shadcn/ui、MUI、Ant Design 等第三方 UI 库
2. **CSS 变量统一主题** — 所有颜色通过 `--color-*` 引用，一次修改全局生效
3. **桌面优先** — 面向 1920×1080 教学终端，无需响应式
4. **轻阴影、低对比** — `shadow-sm` + 细边框，视觉轻盈
5. **统一圆角体系** — 卡片 `rounded-xl`，按钮/输入框 `rounded-lg`，气泡 `rounded-2xl`
6. **统一间距尺度** — 面板 `p-4`，表单 `space-y-4`，标题区 `px-4 py-3`
7. **交互即反馈** — hover/active/disabled 三态完整，过渡 `duration-200`
8. **中文友好** — 系统字体栈 + `Noto Sans SC`，emoji 过渡到 Lucide 图标

### 2.3 不做的事

- ❌ 不升级 React 18 → 19（破坏性变更风险，独立评估）
- ❌ 不升级 Vite 5 → 8（需要 Node 版本确认）
- ❌ 不引入 TanStack React Query（MVP 数据请求简单，不需要缓存层）
- ❌ 不引入 react-hook-form + zod（诊断表单 5 个字段，手写即可）
- ❌ 不改变页面路由结构
- ❌ 不改变后端 API

---

## 3. 技术选型变更

### 3.1 新增依赖

```bash
cd frontend
npm install tailwindcss @tailwindcss/vite
npm install lucide-react
```

| 依赖 | 版本 | 用途 | 选型依据 |
|------|------|------|----------|
| `tailwindcss` | 4.x | CSS 工具类框架 | 参考项目同款 |
| `@tailwindcss/vite` | 4.x | Vite 集成插件，无 `tailwind.config.js` | 参考项目同款 |
| `lucide-react` | 1.x | 图标库（替代 emoji 占位） | 轻量 tree-shakeable，MIT 协议 |

### 3.2 不新增的依赖

| 不引入 | 理由 |
|--------|------|
| `@radix-ui/*` / shadcn/ui | 参考项目原则：纯手写组件 |
| `@tanstack/react-query` | MVP 仅 3-4 个 API 调用，Zustand 已够 |
| `react-hook-form` + `zod` | 仅 1 个诊断表单 5 字段 |
| `framer-motion` | Tailwind 内置动画足够 |
| `clsx` / `tailwind-merge` | 初期不需要复杂的 className 拼接 |

---

## 4. 分阶段实施计划

### Phase 1：基础设施（预计 1-2 小时）

#### 1.1 安装 Tailwind + 配置 Vite

**文件：`frontend/vite.config.ts`** — 添加 `tailwindcss()` 插件

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";  // 新增

export default defineConfig({
  plugins: [react(), tailwindcss()],  // 新增 tailwindcss()
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

#### 1.2 创建全局 CSS

**文件：`frontend/src/index.css`**（新建）

```css
@import "tailwindcss";

/* ═══════════════════════════════════
   设计令牌 — Design Tokens
   ═══════════════════════════════════ */
:root {
  /* 品牌主色 — 保持与原系统的蓝色调一致 */
  --color-primary:        #1677ff;
  --color-primary-light:  #e6f4ff;
  --color-primary-dark:   #0958d9;

  /* 中性色 — 参考 PatientAgent 的 slate 色系 */
  --color-bg:             #f8fafc;
  --color-card:           #ffffff;
  --color-border:         #e2e8f0;
  --color-text:           #1e293b;
  --color-text-secondary: #64748b;

  /* 语义色 */
  --color-success:        #16a34a;
  --color-warning:        #f59e0b;
  --color-error:          #ef4444;
}

/* ═══════════════════════════════════
   全局重置
   ═══════════════════════════════════ */
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background-color: var(--color-bg);
  color: var(--color-text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ═══════════════════════════════════
   滚动条定制 (WebKit)
   ═══════════════════════════════════ */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

/* ═══════════════════════════════════
   自定义动画
   ═══════════════════════════════════ */

/* Toast 滑入 — 从右侧滑入 */
@keyframes slide-in-right {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

/* Toast 滑出 — 向右滑出 */
@keyframes slide-out-right {
  from {
    opacity: 1;
    transform: translateX(0);
  }
  to {
    opacity: 0;
    transform: translateX(100%);
  }
}

/* 淡入 */
@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* 流式光标闪烁 */
@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0; }
}

/* Tailwind 可用的动画类 */
.animate-slide-in {
  animation: slide-in-right 0.3s ease-out;
}

.animate-fade-in {
  animation: fade-in 0.2s ease-out;
}

.animate-blink {
  animation: blink-cursor 0.8s step-end infinite;
}
```

#### 1.3 改造入口文件

**文件：`frontend/src/main.tsx`** — 引入 index.css

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";  // 新增

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

---

### Phase 2：UI 基础设施组件（预计 2-3 小时）

#### 2.1 Toast 通知系统

**文件：`frontend/src/stores/toastStore.ts`**（新建）

```ts
import { create } from "zustand";

export type ToastType = "success" | "error" | "warning" | "info";

interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

interface ToastState {
  toasts: Toast[];
  addToast: (type: ToastType, message: string) => void;
  removeToast: (id: number) => void;
}

let nextId = 1;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (type, message) => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts, { id, type, message }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 4000);
  },
  removeToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

// 便捷方法
export const toast = {
  success: (msg: string) => useToastStore.getState().addToast("success", msg),
  error:   (msg: string) => useToastStore.getState().addToast("error", msg),
  warning: (msg: string) => useToastStore.getState().addToast("warning", msg),
  info:    (msg: string) => useToastStore.getState().addToast("info", msg),
};
```

**文件：`frontend/src/components/ui/ToastContainer.tsx`**（新建）

```tsx
import { useToastStore } from "../../stores/toastStore";

const COLORS: Record<string, { border: string; bg: string; text: string; icon: string }> = {
  success: { border: "border-green-400", bg: "bg-green-50", text: "text-green-800", icon: "✅" },
  error:   { border: "border-red-400",   bg: "bg-red-50",   text: "text-red-800",   icon: "❌" },
  warning: { border: "border-amber-400",  bg: "bg-amber-50",  text: "text-amber-800",  icon: "⚠️" },
  info:    { border: "border-blue-400",  bg: "bg-blue-50",  text: "text-blue-800",  icon: "ℹ️" },
};

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2">
      {toasts.map((t) => {
        const c = COLORS[t.type];
        return (
          <div
            key={t.id}
            className={`animate-slide-in flex items-center gap-2 px-4 py-3 rounded-lg
                        border-l-4 shadow-md min-w-[280px] max-w-[420px] ${c.border} ${c.bg} ${c.text}`}
          >
            <span className="shrink-0">{c.icon}</span>
            <span className="text-sm flex-1">{t.message}</span>
            <button
              onClick={() => removeToast(t.id)}
              className="text-sm opacity-60 hover:opacity-100 shrink-0"
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
```

**挂载点：`App.tsx`** — 在 Router 外套一层

```tsx
<BrowserRouter>
  <ToastContainer />
  <Routes>...</Routes>
</BrowserRouter>
```

#### 2.2 通用组件库

以下组件在 `frontend/src/components/ui/` 下新建，每个 20-40 行：

| 组件 | 文件 | 说明 |
|------|------|------|
| `StatusBadge` | `StatusBadge.tsx` | 状态标签：`active`/`ended`/`evaluated` |
| `DifficultyBadge` | `DifficultyBadge.tsx` | 难度标签：`beginner`/`intermediate`/`advanced` |
| `Alert` | `Alert.tsx` | 提示条：`info`/`warning`/`error` 三种变体 |
| `Modal` | `Modal.tsx` | 通用模态框 — 遮罩 + 居中卡片 + sticky 头部 |
| `LoadingDots` | `LoadingDots.tsx` | 三点弹跳加载动画 |
| `ProgressBar` | `ProgressBar.tsx` | 评分进度条（颜色阈值：≥85 绿 / ≥70 琥珀 / <70 红） |
| `EmptyState` | `EmptyState.tsx` | 空状态占位（图标 + 提示文字 + 操作按钮） |
| `PageHeader` | `PageHeader.tsx` | 页面标题栏（标题 + 副标题 + breadcrumb） |

---

### Phase 3：页面改造（预计 3-5 小时）

#### 3.1 LoginPage — 登录页

**改造要点**：
- 背景：保留渐变，使用 Tailwind `bg-gradient-to-br from-[#667eea] to-[#764ba2]`
- 卡片：`bg-white rounded-xl shadow-sm border border-[var(--color-border)] p-8 w-full max-w-md`
- 标题：移除 emoji 🩺，改用 Lucide `Stethoscope` 图标
- 输入框：统一 `input-base` 样式（focus ring-2）
- 按钮：`btn-primary` 统一类名
- 底部提示：`text-xs text-[var(--color-text-secondary)]`

**目标代码量**：inline style 从 ~100 行降至 0，全部 Tailwind 类名

#### 3.2 CaseListPage — 病例选择页

**改造要点**：
- 布局：保持 `max-w-3xl mx-auto p-10`
- 病例卡片：
  - `rounded-xl border border-[var(--color-border)] hover:border-blue-200 hover:bg-blue-50/50 transition-colors cursor-pointer`
  - 加载/禁用态：`opacity-60 pointer-events-none`
- 难度标签：抽出 `DifficultyBadge` 组件
- 主诉文字：`text-sm text-[var(--color-text-secondary)] line-clamp-2`
- 空状态 + 加载态：用 `LoadingDots` / `EmptyState` 组件

#### 3.3 InterviewPage — 问诊页（改造重点）

**方案选择**：

参考项目 InterviewPage 使用 **4 列 Grid 布局**（侧栏 1fr : 对话 3fr : 表单 2fr : 评分 2fr），但这对应的是"模拟考试"场景——学生在限定时间内完成问诊+诊断，四个面板同时可见。

我们的 MVP 是 **渐进式流程**：问诊 → 结束 → 提交诊断 → 跳转评估页。问诊时诊断表单不可见，提交后评估在单独页面。因此 **保持单列聊天布局**，重点打磨 Chat UI 体验。

**布局结构**：
```
┌───────────────────────────────┐
│  Header (h-14)                │
│  🩺 AI患者 · 第3/12轮 · 结束  │
├───────────────────────────────┤
│                               │
│  Messages (flex-1 overflow)   │
│  ┌─────────────────────┐      │
│  │  患: 您好...         │      │
│  │    医: 你哪里不舒服？  │      │
│  │  患: 牙疼...         │      │
│  └─────────────────────┘      │
│                               │
├───────────────────────────────┤
│  Alert (轮次警告/只读提示)     │
├───────────────────────────────┤
│  ChatInput / DiagnosisForm    │
└───────────────────────────────┘
```

**组件改造**：

`ChatBubble.tsx`：
- 医生（右对齐）：`bg-[var(--color-primary)] text-white rounded-2xl rounded-br-md`
- 患者（左对齐）：`bg-gray-100 text-[var(--color-text)] rounded-2xl rounded-bl-md`
- 系统消息（居中）：`text-center text-xs text-[var(--color-text-secondary)] py-2`
- 流式光标：`animate-blink` 闪烁竖线
- 最大宽度：`max-w-[80%]`（参考项目标准）

`ChatInput.tsx`：
- 输入框：`flex-1 px-4 py-2.5 border border-[var(--color-border)] rounded-lg focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent text-sm`
- 发送按钮：`btn-primary` 统一样式，禁用态 `bg-gray-200 text-gray-400 cursor-not-allowed`

`DiagnosisForm.tsx`：
- 每个 Field：`label (text-sm font-medium) + input/textarea (统一 input-base)`
- 提交按钮：绿色 `bg-[var(--color-success)]` 区别于常规操作
- 必填标记：红色星号

**交互增强**：
- 新消息到达自动滚到底部（已有 `chatEndRef`，加 `smooth` 行为）
- 发送消息时输入框禁用 + 按钮显示 loading
- 轮次接近上限时黄色 Alert，达到上限红色 Alert

#### 3.4 AssessmentPage — 评估报告页

**改造要点**：
- 布局：`max-w-3xl mx-auto py-8 px-4`
- 总分大数字：`text-5xl font-bold`（参考 PatientAgent）
- 颜色阈值调整为 ≥85 绿 / ≥70 琥珀 / <70 红（与参考项目一致，当前是 80/60）
- ScoreCard：
  - 外层：`bg-white rounded-xl p-6 shadow-sm border border-[var(--color-border)]`
  - 维度条：抽出 `ProgressBar` 组件
  - 遗漏/建议：保留色彩区分（红色遗漏 / 蓝色建议）
- 按钮组：轮廓按钮"查看详细反馈" + 主按钮"练习其他病例"

---

### Phase 4：打磨与自检（预计 1-2 小时）

#### 4.1 交互细节检查清单

- [ ] 所有按钮 hover/active/disabled 三态
- [ ] 所有输入框 focus ring + 过渡
- [ ] 所有可点击元素 cursor 变化
- [ ] 过渡动画不过于缓慢（`duration-200` 为主）
- [ ] 加载态有反馈（LoadingDots / 脉冲 / 骨架）
- [ ] 错误态有提示（Toast / Alert / inline error）
- [ ] 空状态有引导（EmptyState 组件）

#### 4.2 视觉一致性检查清单

- [ ] 颜色全部通过 CSS 变量引用，无硬编码色值
- [ ] 圆角统一：卡片 `rounded-xl`，输入框 `rounded-lg`，气泡 `rounded-2xl`
- [ ] 间距统一：面板 `p-4`，标题区 `px-4 py-3`，表单 `space-y-4`
- [ ] 字号层级一致：`text-5xl`(总分) → `text-xl`(页面标题) → `text-sm`(正文) → `text-xs`(辅助)
- [ ] 阴影统一：`shadow-sm` 为主，不出现默认大阴影
- [ ] 边框色统一：`border-[var(--color-border)]`

#### 4.3 E2E 回归测试

按现有 7 步手动流程验证：
1. 打开 `http://localhost:5173` → 登录页，视觉正常
2. 输入工号登录 → 跳转病例列表
3. 点击病例 → 进入问诊页，AI 开场白显示
4. 输入问题 → 流式回复正常
5. 点击"结束问诊" → 诊断表单出现
6. 填写提交 → 跳转评估页，两个评分卡片正常
7. "练习其他病例" → 回到病例列表

---

## 附录：变更文件清单

### 新增文件（8 个）

| 文件 | 说明 |
|------|------|
| `frontend/src/index.css` | 全局样式：CSS 变量、重置、滚动条、动画 |
| `frontend/src/stores/toastStore.ts` | Toast 通知状态管理 |
| `frontend/src/components/ui/ToastContainer.tsx` | Toast 通知渲染组件 |
| `frontend/src/components/ui/Modal.tsx` | 通用模态框 |
| `frontend/src/components/ui/StatusBadge.tsx` | 状态标签 |
| `frontend/src/components/ui/DifficultyBadge.tsx` | 难度标签 |
| `frontend/src/components/ui/Alert.tsx` | 提示条 |
| `frontend/src/components/ui/LoadingDots.tsx` | 三点加载动画 |
| `frontend/src/components/ui/ProgressBar.tsx` | 评分进度条 |

### 修改文件（10 个）

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `frontend/package.json` | +2 行 | 新增 tailwindcss + lucide-react 依赖 |
| `frontend/vite.config.ts` | +2 行 | 添加 tailwindcss 插件 |
| `frontend/src/main.tsx` | +1 行 | 引入 index.css |
| `frontend/src/App.tsx` | +2 行 | 挂载 ToastContainer |
| `frontend/src/pages/LoginPage.tsx` | 重构 | inline style → Tailwind |
| `frontend/src/pages/CaseListPage.tsx` | 重构 | inline style → Tailwind + DifficultyBadge |
| `frontend/src/pages/InterviewPage.tsx` | 重构 | inline style → Tailwind + Alert |
| `frontend/src/pages/AssessmentPage.tsx` | 重构 | inline style → Tailwind + ProgressBar |
| `frontend/src/components/ChatBubble.tsx` | 重构 | inline style → Tailwind + 动画光标 |
| `frontend/src/components/ChatInput.tsx` | 重构 | inline style → Tailwind |
| `frontend/src/components/DiagnosisForm.tsx` | 重构 | inline style → Tailwind |
| `frontend/src/components/ScoreCard.tsx` | 重构 | inline style → Tailwind + ProgressBar |

### 不改动的文件

| 文件 | 原因 |
|------|------|
| `frontend/src/types/index.ts` | TypeScript 类型无需变更 |
| `frontend/src/api/*.ts` | API 层纯逻辑，与样式无关 |
| `frontend/src/stores/authStore.ts` | 状态逻辑无需变更 |
| `frontend/src/stores/interviewStore.ts` | 状态逻辑无需变更 |
| `frontend/index.html` | 无需改动 |
| `frontend/tsconfig.json` | 无需改动 |

---

*本方案总预计工时：7-12 小时（单开发者）。建议按 Phase 1→2→3→4 顺序实施，每阶段结束做一次 commit。*
