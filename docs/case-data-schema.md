# 病例数据范本（v2.2）

> **这是什么**：病例数据的**唯一结构约定**。切分现有 30 例、将来医院提供新病例，都按这个来。
> **为什么单独成文件**：它是"引擎"与"内容"的接缝（P3）——结构变了，代码要跟着改；内容变了，代码不动。
> **配套阅读**：[data-requirements.md](data-requirements.md)（为什么需要这些字段）·
> [case-data-structure.md](case-data-structure.md)（医院原文档的编号体系）
>
> 版本：`2.2`（2026-10-11 加入检查子项层）。`2.1` 及以前只有患者侧四块，检查项是扁平的。

---

## 0. 文件布局

一例病例 = **两个文件**，按权限层切开（见 data-requirements §2）：

```
data/cases/en01.patient.json     ← 患者侧：学生通过对话能问出来的
data/cases/en01.exam.json        ← 检查侧：学生申请检查后返回的
```

教师侧（`D`/`DD`/`T`/`G`/`R`/`K`/`V`）**当前不入库**，将来单独成文件，永不与上面两个混放。

---

## 1. `patient.json`

```jsonc
{
  "case_id": "EN01",
  "group": "牙体牙髓",
  "difficulty": "基础",
  "identity": { "gender": "女", "age": 28 },
  "opening": "左下后牙喝冰水、吃甜的会酸痛，差不多两个星期了。",
  "facts": {
    "H01": { "label": "主诉部位与时间", "text": "…" },
    "H02": { "label": "发展经过",       "text": "…" },
    "H03": { "label": "鉴别性症状",     "text": "…" },
    "H04": { "label": "全身及危险征象", "text": "…" },
    "H05": { "label": "既往诊疗与用药", "text": "…" },
    "H06": { "label": "健康/过敏与相关风险", "text": "…" },
    "H07": { "label": "习惯及其他相关情况",  "text": "…" }
  },
  "psychology": {
    "P01": { "label": "担忧",       "text": "…" },
    "P02": { "label": "偏好",       "text": "…" },
    "P03": { "label": "理解与反应", "text": "…" }
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `case_id` | string | ✅ | `EN01`。**中性编号，永不改**；也是列表页标题 |
| `group` | string | ✅ | 主题分组：牙体牙髓 / 牙周 / 修复 / 黏膜 / 颌面外科 |
| `difficulty` | string | ✅ | 医院原值（基础/中等/高级），入库时映射为英文枚举 |
| `identity.gender` / `.age` | string / int | ✅ | 患者身份。生成器直接引用 |
| `opening` | string | ✅ | **开场白，逐字原文**。不调 LLM，每位学生看到同一句 |
| `facts` | object | ✅ | 固定 7 槽 `H01`–`H07`。**槽位语义固定**（主诉/发展/鉴别/危险征象/既往/全身/习惯），换科室时槽位名不变 |
| `facts[*].label` | string | ✅ | 槽位名。**选择器要读它**（只读标签认不出"咬合痛"） |
| `facts[*].text` | string | ✅ | **原文，逐字不可改** |
| `psychology` | object | ✅ | 固定 3 槽 `P01`–`P03`：担忧 / 偏好 / 理解与反应 |
| `psychology[*].text` | string | ✅ | `P03` 是**行为规则**（"不新增价格、剂量、保证治愈"），不是病情 |

**禁止**：任何 `D`/`DD`/`T`/`G`/`R` 内容出现在此文件（P4——边界靠数据缺失，不靠提示词）。

---

## 2. `exam.json`

```jsonc
{
  "case_id": "EN01",
  "schema_version": "2.2",
  "exams": {
    "E02": {
      "label": "36及对照牙冷测、叩诊",
      "level": "关键",
      "result": "36冷测痛约3秒消失；35、37对照反应短暂。36叩诊阴性，松动度0。",
      "boundary": "…相关子项请求仅返回该项结果，不可返回整个E02（如仅询问冷诊，不可同时返回叩诊结果）。",
      "split_verified": true,

      "aliases": ["冷诊", "冷测", "…"],          // 全部子项别名的并集，兼容扁平匹配

      "subitems": [
        {
          "key": "cold",
          "label": "冷测",
          "aliases": ["冷诊", "冷测", "冷刺激试验", "冷热诊", "温度测试", "…"],
          "result_fragments": ["36冷测痛约3秒消失；35、37对照反应短暂。"],
          "source": "derived"
        },
        {
          "key": "percussion",
          "label": "叩诊",
          "aliases": ["叩诊", "叩痛检查", "牙齿叩诊", "…"],
          "result_fragments": ["36叩诊阴性"],
          "source": "derived"
        },
        {
          "key": "mobility",
          "label": "松动度",
          "aliases": ["检查松动度", "牙齿活动度检查"],
          "result_fragments": ["松动度0。"],
          "source": "derived"
        },
        {
          "key": "pulp",
          "label": "牙髓活力",
          "aliases": ["牙髓检查", "牙髓活力测试", "…"],
          "result_fragments": [],               // 伞形子项（空数组）：问它返回整包
          "source": "derived"
        }
      ],
      "split_note": "4 个别名组，其中 1 组为伞形"       // 可选：说明为何这样切/为何不切
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `case_id` | string | ✅ | 与 patient.json 一致 |
| `schema_version` | string | ✅ | 本文件遵循的范本版本 |
| `exams` | object | ✅ | 键为 `E01`…`E0n`，**顺序即学生列表展示顺序** |
| `exams[*].label` | string | ✅ | 项名，医院原文 |
| `exams[*].level` | string | ✅ | `关键` / `条件性` / `补充` / `未提供` |
| `exams[*].result` | string \| null | ✅ | 检查结果**原文，永不改动**。`未提供` 项为 `null` |
| `exams[*].boundary` | string | ✅ | 医院写的规则说明。**不给学生看**，是给系统的约束 |
| `exams[*].split_verified` | bool | ✅ | 子项切分是否通过全部机器校验。`false` = 未切分、整包返回 |
| `exams[*].split_note` | string | — | 可选：说明为何这样切 / 为何不切（如"单一别名组"） |
| `exams[*].aliases` | string[] | ✅ | 所有子项别名的并集（兼容扁平匹配逻辑） |
| `exams[*].subitems` | object[] | ✅ | 子项列表。**整项无分组或只有 1 个组时为空数组**（整项即子项） |
| `subitems[*].key` | string | ✅ | 稳定英文 ID（`cold` / `percussion`…）。**进披露轨迹，永不改** |
| `subitems[*].label` | string | ✅ | 子项名。医院写的或我们补的 |
| `subitems[*].aliases` | string[] | ✅ | 该子项的别名（医院的 `；` 分组即子项划分） |
| `subitems[*].result_fragments` | string[] | ✅ | **每段都必须是 `result` 的逐字连续子串**。**数组**，因为一个子项可以拥有多段不连续的结果。**空数组 `[]` = 伞形**（问它返回整包） |
| `subitems[*].source` | string | ✅ | `authored`（医院写的）/ `derived`（我们补的） |

**关于 `result_fragments` 是数组**：医院的结果常常是"甲；乙；丙"，而子项划分可能是"【A】= 甲 + 丙；【B】= 乙"。
所以一个子项可以拥有**多段**。跨子项拼回原文时必须**按各段在原文中的位置排序**再拼——
按 `subitems` 列表顺序拼是错的（校验器就是被这个坑过一次）。

---

## 3. 校验规则（机器强制）

写数据时按下表自检；`scripts/` 里的校验器会强制执行，不过就拒绝。

| # | 规则 | 违反后果 |
|---|---|---|
| V1 | 每个 `result_fragments[*]` 是 `result` 的**逐字连续子串**（**且不得取自 `boundary`**） | 拒绝：说明切分时改写了原文 |
| V2 | 所有片段**按其在原文中的位置排序**后拼接，去空白标点必须**完整覆盖** `result`，且**互不重叠** | 拒绝：说明有句子被丢了或被两个子项同时占用 |
| V3 | `subitems[*].label` 必须能在**该子项的 aliases 里**找到出处；自补的名**不得超过 12 字、不得含分隔符** | 拒绝：说明模型自创名词，或把整串别名抄成了名字 |
| V4 | 同一 `subitems[*].key` 在**全库唯一**；`aliases` 不跨子项重复 | 拒绝：匹配会歧义 |
| V5 | `result` 为 `null` ⟺ `level == "未提供"` | 拒绝：状态自相矛盾 |
| V6 | `patient.json` 不含任何 `D`/`DD`/`T`/`G`/`R` 键 | 拒绝：越权（P4） |
| V7 | **只有 1 个别名组的 E 项不切分**（`subitems: []`，整项即子项） | 拒绝：无依据的切分＝编造结构 |

**校验失败 → `split_verified: false`、该项退回整包、记入清单，并带反馈重试（最多 3 次）。**
不通过也要留在数据里看得见；**不允许静默降级**。

**任一项校验失败 → `split_verified: false`，该 E 项退回整包返回，并记入待人工清单。**
不通过也要留在数据里，让问题可见；**不允许静默降级**。

---

## 4. 子项切分的界线（P1）

| ✅ 允许 | ❌ 禁止 |
|---|---|
| 给已有别名组起名（名字要有出处） | 发明检查、结果、数值 |
| 决定"哪一句属于哪个子项" | 改写 / 润色 / 合并 / 精简结果文字 |
| 标 `source: derived` | 丢掉任何一句 |
| `result_fragment: null`（拿不准就不切） | 硬切一个可能错的分法 |

**关键**：片段逐字就是原文，我们补的是**结构**（哪句属于哪一小项），不是医学内容。
所以这不违反 P1，但**必须靠 V1/V2 机器保证**，不能靠模型自觉。

---

## 5. 与医院原文档的对应

| 范本字段 | 医院 docx 的哪一行 |
|---|---|
| `exams[*].label` / `.level` / `.result` | `E02 [关键] 36及对照牙冷测、叩诊 <结果>` |
| `exams[*].subitems[*].aliases` | `可接受表达：` 一行，**按 `；` 分组、`【】` 取名** |
| `exams[*].boundary` | `实际返回：` 一行 |
| `subitems[*].label` | 该组前的 `【组名】`；**缺失时由我们补并标 `derived`** |
| `subitems[*].result_fragment` | 医院没写，由我们按 V1/V2 切分 |

`facts` / `psychology` / `opening` 来自 docx 的 A1 段（患者资料与 SP 行为）。

---

## 6. 版本历史

| 版本 | 变更 |
|---|---|
| 2.0 | 首版：`identity` / `opening` / `facts`(H01–H07) / `psychology`(P01–P03) |
| 2.1 | 难度改中文原值；`exam.json` 独立成文件；E 项加 `level` 枚举（原 `critical` 布尔表达不了"条件性/未提供"） |
| **2.2** | **`exam.json` 加 `subitems` 层**（`key`/`label`/`aliases`/`result_fragments`/`source`）+ `split_verified`/`split_note`；确立 V1–V7 校验规则。首个版本用单段 `result_fragment`，跑 5 例时发现**一个子项可能拥有多段不连续结果**（MU01 E02：「其他部位检查」= 第1句+第3句），改为数组 |
