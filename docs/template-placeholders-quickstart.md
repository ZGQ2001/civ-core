# 占位符模板速成

> 给报告模板填字段最简单的方式：在 Word 里写 `{字段名}`，程序自动替换成实际值。
> 不需要打开模板编辑器，不需要点格子，不需要 JSON 配置。

---

## 1. 怎么用

**步骤 1**：拿一份甲方给的 Word 报告模板（`.docx`）

**步骤 2**：在需要填值的位置打 `{中文字段名}` 或 `{snake_case_key}`，比如：

```
锚杆编号：{anchor_id}        ← 用 Key
弹性位移：{弹性位移量}        ← 用中文名（推荐 — 跟规范用词一致）
判定结果：{判定结果}
```

**步骤 3**：保存模板，调 `report.render_placeholder` RPC（前端入口建设中）

程序会扫整个 Word：每一段、每一个表格里的每一个段落里，把 `{xxx}` 替换成对应值。

---

## 2. 锚杆抗拔（anchor）可用字段

> 中文名也可以直接当占位符用，引擎按 catalog 反查 Key。

### 工程参数（同批次共享）

| Key | 中文名 | 类型 | 默认格式 |
|---|---|---|---|
| `axial_design_load` | 轴向拉力设计值 P (N) | double | `0.00` |
| `free_length` | 自由段长度 Lf (mm) | double | `0.0` |
| `anchor_length` | 锚固段长度 La (mm) | double | `0.0` |
| `steel_area` | 钢筋面积 A (mm²) | double | `0.00` |
| `elastic_modulus` | 弹性模量 E (N/mm²) | double | `0` |

### 单根锚杆原始数据

| Key | 中文名 | 类型 | 默认格式 |
|---|---|---|---|
| `anchor_id` | 锚杆编号 | string | — |
| `disp_01nt` | 0.1Nt 时位移 (mm) | double | `0.00` |
| `disp_04nt` | 0.4Nt 时位移 (mm) | double | `0.00` |
| `disp_07nt` | 0.7Nt 时位移 (mm) | double | `0.00` |
| `disp_10nt` | 1.0Nt 时位移 (mm) | double | `0.00` |
| `disp_12nt_1min` | 1.2Nt 持荷 1min (mm) | double | `0.00` |
| `disp_12nt_3min` | 1.2Nt 持荷 3min (mm) | double | `0.00` |
| `disp_12nt_5min` | 1.2Nt 持荷 5min (mm) | double | `0.00` |
| `disp_unload_10nt` | 卸载至 1.0Nt (mm) | double | `0.00` |
| `disp_unload_07nt` | 卸载至 0.7Nt (mm) | double | `0.00` |
| `disp_unload_04nt` | 卸载至 0.4Nt (mm) | double | `0.00` |
| `disp_unload_01nt` | 卸载至 0.1Nt (mm) | double | `0.00` |

### 计算结果

| Key | 中文名 | 类型 | 默认格式 |
|---|---|---|---|
| `elastic_displacement` | 弹性位移量 M (mm) | double | `0.00` |
| `lower_limit` | 判定下限 Q (mm) | double | `0.00` |
| `upper_limit` | 判定上限 R (mm) | double | `0.00` |
| `judgement_result` | 判定结果 | string | "合格" / "不合格" |

### 用户填写

| Key | 中文名 |
|---|---|
| `client_name` | 委托单位 |
| `project_name` | 工程名称 |
| `test_date` | 试验日期 |
| `test_engineer` | 试验人员 |

---

## 3. 容易踩的坑

### 跨 Run 拆分
Word 输入法（特别是切中英文时）会把一个占位符拆成多个 Run（内部存储单元）。比如肉眼看是 `{anchor_id}`，文档里可能是 `{` + `anchor_id` + `}` 三块。引擎会**段落级合并 Run 文本再替换**，所以跨 Run 拆分**不影响**结果。

### 同段落多个 Run 样式
引擎替换时只保留**段落里第一个 Run 的字体样式**（rPr）。如果你在同一段里混用粗体 / 斜体 / 不同字号，替换后整段都会用第一个 Run 的样式。

**对策**：占位符所在的段落保持单一样式；多样式段落不要塞占位符。

### 拼错字段名
找不到的字段会留**原文**（比如 `{anchor_idid}` 不动），同时引擎返回 `unknown_keys` 列表给前端提示。建议生成完打开报告检查一遍。

### 占位符之间不要换行
`{anchor_id}` 不能跨行。`{` 和 `}` 必须在同一段落里。

---

## 4. 跟可视化模板编辑器的关系

| 场景 | 推荐 |
|---|---|
| 模板就是塞值进固定位置 | **占位符模式**（主路径，本文档） |
| 模板需要按每根锚杆克隆整张表 | 可视化编辑器（设 `repeat: per_row` + 表格签名校验） |
| 甲方给的模板布局很怪需要细调 | 可视化编辑器（点格子绑定，避免靠用户手写占位符） |

**当前实现状态**：
- 占位符模式：✅ C# 引擎 + RPC + 测试齐
- 可视化编辑器：✅ C# 引擎 + RPC + 前端 UI，但 `report.generate` 尚未对接锚杆计算流程（Phase 3）

---

## 5. RPC 调用例

```typescript
// 前端
await rpc('report.render_placeholder', {
  docx_path: 'C:/templates/anchor.docx',
  project_type: 'anchor',
  values: {
    anchor_id: 'P-01',
    elastic_displacement: 1.23,
    judgement_result: '合格',
    // ... 其他字段
  },
  output_path: 'C:/output/P-01.docx',
});
// → { output_path, replaced: N, unknown_keys: ['xxx', ...] }
```

后端实现见 [PlaceholderRenderer.cs](../dotnet/civ-doc/Template/PlaceholderRenderer.cs)
+ [ReportHandlers.cs](../dotnet/civ-doc/Handlers/ReportHandlers.cs)。
