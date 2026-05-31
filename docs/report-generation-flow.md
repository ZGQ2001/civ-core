# 报告生成流程（锚杆 / 防火涂层）—— 现状 + 收口方向

> 用途：跨窗口/会话交接。说明两个检测类型「从数据到 Word 报告」的完整链路、当前两条路的差异、以及统一方向。
> 关联：方案 `docs/plans/2026-05-31-report-table-generator.md`（机制决策）；记忆 `project_coating_thickness_branch.md`（进度）。
> 分支：`feat/coating-report-table`（未 push）。日期：2026-05-31。

---

## 总览

| | 表怎么进报告 | 引擎 | RPC | 状态 |
|---|---|---|---|---|
| **锚杆** | 模板里 marker 克隆（一锚杆一张表）| `ReportGenerator` | `report.run_from_result` | 成熟·已交付 |
| **防火涂层** | 程序按规范格式建表、插入 `{{表格:防火涂层}}` 占位符 | `CoatingWordTable` + `CoatingDocxReport` | `coating.report` | 单类型一键已通（本分支）|

两个核心硬约束（用户拍板）：**① 用户换模板零代码 ② 报告页一键出报告**。
方向：数据核心（计算+字段）后端无关；Word 是当前渲染后端；LaTeX 作未来可选 PDF 后端，不锁死。

---

## 一、锚杆出报告（现状，老路：docx 模板 + marker 克隆）

```
给数据(Excel) → 点计算 → [绘曲线图] → 报告填充 → Word 报告
```

1. **数据处理**（前端 `data_processing`，calcType=anchor）→ RPC `anchor.run`
   - AnchorCalculator 计算 → 写**结果 xlsx**（含 `AnchorAnalysisSheet` + 隐藏元数据 sheet `_批次参数`/`批次信息`，持久化工程参数 + 灌浆日期）。
2. **绘曲线图**（前端 `plot_curves`）→ RPC `plot_curves.run`（可选）
   - 每根锚杆一张荷载-位移曲线 PNG，按 anchor_id 命名。
3. **报告填充**（前端 `report_generator`）→ RPC `report.run_from_result`
   - 读结果 xlsx（不重算）→ 填 Word 模板（`锚杆专用模板.docx`）。
   - 模板：项目信息写 `{{委托单位}}` 等；用成对 marker `[[检测项目]]`/`[[批次]]`/`[[每根锚杆]]` 包「表2.4 单根结果表」，引擎按锚杆**克隆 N 份**；曲线图 `{{img:曲线图}}` 嵌入。
   - 引擎 `ReportGenerator`（Generate / GenerateMultiBatch / GenerateMultiDetectionItem）；项目信息走 `AnchorFieldCatalog`。

关键文件：`Calc/Anchor/*`、`Template/ReportGenerator.cs`、`Template/PlaceholderRenderer.cs`、`Template/ImageInjector.cs`、`Handlers/ReportHandlers.cs`。

特点：**表是模板里画好的，引擎克隆填值**（一锚杆一张表）。

---

## 二、防火涂层出报告（现状，新路：薄壳占位符 + 程序建表）

```
生成模板 → 填构件清单 → 展开测点网格 → 填数字 → 点生成 → Word 报告
```

1. **`coating.generate_template`** → 出「类型预设 + 构件清单」xlsx。
2. 填**构件清单**（一构件一行：位置 / 类型 / 长度或截面数 / 设计厚度）。
3. **`coating.expand_template`** → 展开「测点数据-<类型>」网格。
   - 国标膨胀型(薄/超薄)=5 处×3 点（处号 1~5 × 测点1/2/3）；厚型 / 地标=截面×面（截面数=⌈长度/间距⌉，国标3m/地标1m）。
4. 填**实测数字**。
5. **`coating.report`** → 读测点数据 → 计算 → 填 docx 薄壳模板：
   - 模板放表处写一段 **`{{表格:防火涂层}}`**；程序在该处**按规范格式建表插入**（`CoatingWordTable.BuildAll` 分派：国标膨胀型→5处μm 表 `BuildExpansion`、厚型→截面×面 mm 表 `BuildThick`，按构件类型分张）。
   - 项目信息写 `{{委托单位}}`/`{{检测结论}}` 等 → `user_inputs` 填（`CoatingDocxReport.Generate` 调 `PlaceholderRenderer`）。
   - 另存 `coating.run`（出「<批>-数据分析」宽表，供核对/可追溯，不进最终报告）。

关键文件：`ReportTables/CoatingWordTable.cs`、`ReportTables/CoatingDocxReport.cs`、`Handlers/CoatingHandlers.cs`（`coating.report`）、`mcp/src/tools/coating.ts`（`coating_report`）。

特点：**表是程序按规范格式现建的**（薄壳里只放一个占位符）；换模板/换甲方只改薄壳，零代码。单位：厚型 mm（游标卡尺）/ 薄·超薄 μm（测厚仪）；厚型报告表照母版无设计/判定列。

---

## 三、两条路不一致（④ 要收口）

锚杆走 `report.run_from_result`（marker 克隆），防火涂层走 `coating.report`（占位符建表）——同一个「出表」动作两套机制。

**④ 多检测类型组装**：把锚杆也改成「`{{表格:锚杆}}` 占位符 + 程序建表」的同一机制，让**一份模板能同时含 `{{表格:锚杆}}` + `{{表格:防火涂层}}`**，勾了哪些类型填哪些、没勾的清掉 → 一份报告多 section。锚杆老的 marker 路保留不动，新机制并行接入。

## 四、终态一键流程（⑤ 前端）

```
报告生成页：勾检测类型(锚杆☑ 防火涂层☑ …多选) → 填项目信息(~30 字段) → 点[生成]
  → 程序：对每个勾选类型 跑计算/读结果 + 建对应表 + 填进同一份模板 → 一份 Word
```

---

## 接续指引

- 分支 `feat/coating-report-table`（5 commit，未 push）：① 录入网格 5处×3点 → ② 膨胀型+厚型 Word 表 → ③ 单类型一键 Word 闭环（RPC + MCP）。
- **下一步 ④**：锚杆接入 `{{表格:锚杆}}` 占位符机制（程序建锚杆 Word 表）+ 多占位符按勾选填。**再 ⑤**：前端报告页多选 + 一键。
- 验证：`cd dotnet/civ-doc.Tests && dotnet test`（当前 261/1skip）；mcp `cd mcp && npm run typecheck && npm test && node scripts/smoke.mjs`。
- 出报告需用户提供带 `{{表格:xxx}}` 占位符的 docx 薄壳模板（`coating.report` 的 `word_template_path`）；表内部格式在代码里固定（规范统一），薄壳甲方可改。
