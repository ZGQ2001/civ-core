# 报告生成流程（锚杆 / 防火涂层）—— 现状 + 收口方向

> 用途：跨窗口/会话交接。说明两个检测类型「从数据到 Word 报告」的完整链路、当前两条路的差异、以及统一方向。
> 关联：方案 `docs/plans/2026-05-31-report-table-generator.md`（机制决策）；记忆 `project_coating_thickness_branch.md`（进度）。
> 分支：`feat/coating-report-table`（未 push）。日期：2026-05-31。

---

## 总览

| | 表怎么进报告 | 引擎 | RPC | 状态 |
|---|---|---|---|---|
| **锚杆** | 程序建逐根 表2.4（含曲线图）、插入 `{{表格:锚杆}}` 占位符 | `AnchorWordTable` + `DocxReportAssembler` | `report.run_from_result` / `anchor.run`(可选出 Word) | ④ 已迁（本分支）|
| **防火涂层** | 程序按规范格式建表、插入 `{{表格:防火涂层}}` 占位符 | `CoatingWordTable` + `DocxReportAssembler` | `coating.report` | 单类型一键已通 |
| **多类型组装** | 一份模板含多个 `{{表格:xxx}}`，按勾选填、没勾的清掉 | `DocxReportAssembler` | `report.assemble` | ④ 已通（本分支）|

两个核心硬约束（用户拍板）：**① 用户换模板零代码 ② 报告页一键出报告**。
方向：数据核心（计算+字段）后端无关；Word 是当前渲染后端；LaTeX 作未来可选 PDF 后端，不锁死。
**两条路已收口到同一机制**（程序建表 + `{{表格:xxx}}` 占位符 + `DocxReportAssembler`）。
marker 引擎 `ReportGenerator` + 三层模板 + 「锚杆专用模板」**已删除**（用户拍板：以后没有专用模板）。

---

## 一、锚杆出报告（新机制，与防火涂层同：程序建表 + `{{表格:锚杆}}` 占位符）

```
给数据(Excel) → 点计算 → [绘曲线图] → 报告填充 → Word 报告
```

1. **数据处理**（前端 `data_processing`，calcType=anchor）→ RPC `anchor.run`
   - AnchorCalculator 计算 → 写**结果 xlsx**（含 `AnchorAnalysisSheet` + 隐藏元数据 sheet `_批次参数`/`批次信息`，持久化工程参数 + 灌浆日期）。可选 `word_template_path` 同时出 Word（走下面同一机制）。
2. **绘曲线图**（前端 `plot_curves`）→ RPC `plot_curves.run`（可选）
   - 每根锚杆一张荷载-位移曲线 PNG/SVG，按 anchor_id 命名。
3. **报告填充**（前端 `report_generator`）→ RPC `report.run_from_result`
   - 读结果 xlsx（不重算）→ 填 docx 薄壳模板。
   - 模板：要放表处写一段 **`{{表格:锚杆}}`**；程序按规范建**逐根「表2.4 单根结果表」**（17 列网格 + 合并）插在该处，表内 `{{img:曲线图}}` 按 anchor_id 嵌图；项目信息写 `{{委托单位}}` 等 `{{}}` 占位符 → 走 `AnchorFieldCatalog`（中文名/别名解析）由 `user_inputs` 填。
   - 标题编号：单根→`表2.4`、多根→`表2.4-1/2/…`（全局连续，节号由 `section_no` 定、缺省 2.4）。各批灌浆日期出现在本批锚杆表的「灌浆日期」格。
   - 引擎：`AnchorWordTable.BuildSection`（建表+`PlaceholderRenderer.RenderInto` 填值嵌图）+ `DocxReportAssembler.Generate`（找占位符/插表/填薄壳/页眉页脚）。`anchor.run`/`report.run_from_result` 共用 `AnchorWordTable.GenerateReport`。

关键文件：`Calc/Anchor/*`、`ReportTables/AnchorWordTable.cs`、`ReportTables/DocxReportAssembler.cs`、`ReportTables/WordTableStyle.cs`、`Template/PlaceholderRenderer.cs`、`Template/ImageInjector.cs`、`Handlers/ReportHandlers.cs` + `Handlers/AnchorHandlers.cs`。

特点：**表是程序按规范现建的**（薄壳里只放 `{{表格:锚杆}}` 占位符）；换模板/换甲方只改薄壳，零代码——与防火涂层完全同机制。

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

## 三、两条路已收口（④ 已完成）

原来锚杆走 marker 克隆、防火涂层走占位符建表——两套机制。**④ 已把锚杆迁到同一机制**：
程序建逐根 表2.4 + 插 `{{表格:锚杆}}` 占位符（删了 marker 引擎 `ReportGenerator` + 三层模板 + 「锚杆专用模板」）。

**`report.assemble`（多检测类型组装）**：一份薄壳模板可同时含 `{{表格:锚杆}}` + `{{表格:防火涂层}}`；
入参 `sections:[{type:'anchor', result_xlsx, ...}, {type:'coating', input_xlsx, ...}]`，对每个 section 建对应表插入，
**模板里写了但本次没提供数据的 `{{表格:xxx}}` 占位符自动清掉**，其余 `{{}}` 按 `user_inputs` 填 → 一份报告多 section。
引擎 `DocxReportAssembler.Generate(template, output, sections, userInputs, catalog)`；coating 单类型 `coating.report` 也已改走它。

关键文件：`ReportTables/DocxReportAssembler.cs`、`ReportTables/AnchorWordTable.cs`、`ReportTables/WordTableStyle.cs`、`Handlers/ReportHandlers.cs`（`report.assemble`）、`mcp/src/tools/report.ts`（`report_assemble`）。

## 四、终态一键流程（⑤ 前端，未做）

```
报告生成页：勾检测类型(锚杆☑ 防火涂层☑ …多选) → 填项目信息(~30 字段) → 点[生成]
  → 调 report.assemble：对每个勾选类型 读结果/测点 xlsx + 建对应表 + 填进同一份模板 → 一份 Word
```

后端 `report.assemble` 已就绪；⑤ 只需前端报告页做「多选 + 收集项目信息 + 拼 sections 调用」。

---

## 接续指引

- 分支 `feat/coating-report-table`（未 push）：① 录入网格 5处×3点 → ② 膨胀型+厚型 Word 表 → ③ 单类型一键 Word 闭环 → **④ 锚杆迁 `{{表格:锚杆}}` + 删 marker 引擎 + `report.assemble` 多类型组装**（4 个 commit：A 装配引擎/共用样式 · B 锚杆 表2.4 builder · C 迁两 handler+删 marker · D report.assemble+MCP+文档）。
- **下一步 ⑤**：前端报告页多选检测类型 + 一键（调 `report.assemble`）。
- 验证：`cd dotnet/civ-doc.Tests && dotnet test`（当前 249 通过/1 skip）；mcp `cd mcp && npm run typecheck && npm test && node scripts/smoke.mjs`（58 tools，含 `report_assemble`）。
- 出报告需用户提供带 `{{表格:xxx}}` 占位符的 docx 薄壳模板；表内部格式在代码里固定（规范统一），薄壳甲方可改。**锚杆已无「专用模板」**——和防火涂层一样只需薄壳 + `{{表格:锚杆}}`。
- 注：`docs/template-placeholders-quickstart.md` 和 `.claude/skills/civ-core-make-template/SKILL.md` 仍含 `[[每根锚杆]]` marker 教学，**已过时待改**（marker 路已删）。
