# 真实病例数据集成方案 V2

> **状态**: 实施中 | **日期**: 2026-08-02 | **版本**: 经过讨论确认的最终方案

---

## 一、决策总结

经过对原始数据（`medical_records.csv` 2124条）和自动生成病例（`case_001~599.json`）的深入分析，结合讨论确认以下关键决策：

| # | 决策项 | 结论 | 理由 |
|---|--------|------|------|
| 1 | 病例数量 | **精选100个** | 现阶段开发测试足够，质量>数量 |
| 2 | 筛选标准 | **6字段全有值 + 内容充分** | 主诉≥10字、现病史≥50字、口腔检查≥30字、诊断非空、治疗方案≥20字、既往史≥10字 |
| 3 | 低质量病例 | **直接丢弃** | 字段不全的信息给Agent用体验差 |
| 4 | 翻译模型 | **千问 (DashScope)** | 已有百炼账号，OpenAI兼容接口 |
| 5 | 翻译策略 | **翻译Agent + 审校Agent串行** | 审校视角有距离感，比自检更可靠 |
| 6 | 数据结构 | **双结构（拆子项+保留full_text）** | Agent优先查子字段，回退到full_text兜底 |
| 7 | 既往史 | **不拆子项** | 信息稀疏，拆了全是"否认xxx"反而不自然 |
| 8 | ICD编码 | **正则提取 + 字典补全** | 原文混在诊断文本里 |
| 9 | 新病例ID | **从ID 4开始** | MVP保持1-3不动，历史会话不受影响 |
| 10 | 疾病类型 | **质量优先，自然覆盖** | 不预设均衡采样 |

---

## 二、目标数据结构

统一采用双结构设计——完整原文与结构化子字段并存：

```json
{
  "title": "病例004：左下后牙疼痛1周（急性根尖周炎）",
  "department": "口腔科",
  "difficulty": "beginner | intermediate | advanced",
  "status": "published",
  "visit_type": "首诊",
  "data": {
    "basic_info": {
      "gender": "男 | 女",
      "age_range": "0–12 | 13–20 | 21–40 | 41–60 | 60+",
      "visit_type": "首诊 | 复诊"
    },
    "chief_complaint": "中文主诉原文",
    "present_illness": {
      "full_text": "翻译后的完整现病史原文",
      "onset": "起病描述",
      "duration": "持续时间",
      "character": "症状特征",
      "aggravating_factors": ["加重因素"],
      "relieving_factors": ["缓解因素"],
      "radiation": "放射痛描述"
    },
    "past_history": {
      "full_text": "翻译后的完整既往史原文（不拆子项）"
    },
    "oral_examination": {
      "full_text": "翻译后的完整口腔检查原文",
      "inspection": "视诊所见",
      "percussion": "叩诊结果",
      "palpation": "触诊结果",
      "mobility": "松动度",
      "thermal": "温度测试结果",
      "periodontal": "牙周情况"
    },
    "auxiliary_examination": { "xray": "", "cbct": "" },
    "diagnosis": {
      "primary": "主诊断中文名",
      "secondary": [],
      "icd_code": "Kxx.xxx"
    },
    "treatment_plan": {
      "emergency": "急症处理",
      "definitive": "根治方案",
      "restoration": "修复方案",
      "notes": "医嘱备注"
    }
  }
}
```

**双结构设计原理**：
- `full_text`：翻译后的完整临床文本，Agent 兜底理解上下文
- 子字段：从 full_text 提取的结构化信息，Agent 精准查询
- 子字段为空 → Agent 回退到 full_text → LLM 自行理解
- 即使 LLM 拆分有误差，信息不丢失

---

## 三、实施流水线

```
data/raw/medical_records.csv (2124条)
    │
    │  scripts/clean_data_v2.py  ← Phase 2: 6字段筛选 + 去废 + HTML解码
    │  筛选出 ~80-120 个高质量病例
    ▼
data/cases/intermediate/case_XXX.json (中间格式, 英文原文)
    │
    │  scripts/enrich_cases.py  ← Phase 3: LLM翻译 + 审校
    │  Step A: 千问翻译 → 中文结构化JSON
    │  Step B: 千问审校 → 对照原文修正 → 最终JSON
    ▼
data/cases/case_004~103.json (统一Schema, 中文, 双结构)
    │
    │  scripts/seed_db.py  ← Phase 4: 导入数据库
    ▼
data/app.db → cases 表 103条 (3 MVP + 100 真实)
```

---

## 四、实施步骤

### Phase 2: 数据清洗 `scripts/clean_data_v2.py`

1. 读取 CSV（Tab分隔，自动检测）
2. 患者分组（按 Filename 去重多诊次）
3. 6字段筛选 + 内容长度过滤
4. 去废数据（截断文本、占位符、COVID模板）
5. HTML 实体解码
6. ICD 编码正则提取
7. 输出中间格式 JSON

### Phase 3: LLM增强 `scripts/enrich_cases.py`

- Step A 翻译: 英文原文 → 中文结构化 JSON
- Step B 审校: 对照原文逐项检查 → 修正 → 输出
- 批量处理：每10个一批，检查点保存
- 先试运行5个，人工确认质量后全量

### Phase 4-6: 入库 + 适配

- `seed_db.py` 改造：遍历导入全部 case JSON
- `case_service.py` 多路径兼容 `_safe_get()`
- 前端 CaseListPage 加滚动容器

---

## 五、相关文件

| 文件 | 说明 |
|------|------|
| [data-issues-analysis.md](data-issues-analysis.md) | V1方案：完整的问题诊断和原始分析 |
| [../scripts/clean_data_v2.py](../scripts/clean_data_v2.py) | 清洗脚本 v2 |
| [../scripts/enrich_cases.py](../scripts/enrich_cases.py) | LLM翻译+审校脚本 |
| [../scripts/seed_db.py](../scripts/seed_db.py) | 数据库种子脚本（改造后） |
