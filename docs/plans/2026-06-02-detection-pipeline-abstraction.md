# 重构方案：检测类型统一 Pipeline 抽象（消硅仓）

**Date:** 2026-06-02
**Scope:** `dotnet/civ-doc/` 的 Anchor / Coating / Leeb 三检测类型。不动 Python sidecar、前端、MCP（仅 §8 列影响面）。
**Status:** 草案，待评审 —— 对应 `.ai/RULES.md` B1「架构级 backlog，需先出方案再动手」。本文只出方案，**不含任何代码改动**。
**关联:** 与 `docs/plans/refactor-service-layer.md`（Python plot_curves 服务层）正交，那是 Python 侧、这是 C# 侧。

---

## 1. 问题

CLAUDE.md 立身原则：「这个产品不是工具箱……它是**一条装配线**」。但这条比喻**只在单个检测类型内成立**（数据→结构化→曲线→表格→报告），**跨检测类型时不成立**：Anchor / Coating / Leeb 是三套并排的独立实现，没有共享骨架。

加一个检测类型的官方姿势（`.claude/skills/civ-core-add-detection-type/SKILL.md`）原话是「**找一个最相似的已有检测类型从头到尾对照，每一层加自己的同位件**」——也就是把 copy-paste 写成了 SOP。一个新类型今天要跨 4 种语言铺开：

| 层 | 今天要新增/改 |
| --- | --- |
| C# Calc | `Columns` / `Params` / `Standards` / `Math` / `Calculator` / `FieldCatalog`（≈6 文件） |
| C# 基建 | `ExcelReader` / `TemplateWriter` / `AnalysisSheet`（≈3 文件） |
| C# RPC | `XxxHandlers.cs` + `JsonRpcServer.RunAsync()` 注册一行 |
| 前端 | `data_processing/types.ts`（CalcType union）/ `controller.tsx` 派发 / `XxxSubForm.tsx` |
| MCP | `mcp/src/tools/<type>.ts` 写 N 个 ToolDef + `index.ts` 注册 |
| 报告 | catalog 字段 + 模板 docx |

而且**同一份入参契约被手写三遍**：C# handler 手解 `JsonElement` + MCP `zod` + 前端 `zod`（`lib/rpcSchemas.ts`）。

### 已固化的重复代码（精确位置）

| 逻辑 | 重复处 | 状态 |
| --- | --- | --- |
| `SafeSheetName` | `AnchorHandlers.cs:347` / `CoatingHandlers.cs:207` / `LeebHandlers.cs:223` / `CoatingTemplateExpander.cs:247` | 字节级相同 ×4 |
| `ParseUserInputs` | `AnchorHandlers.cs:298` / `CoatingHandlers.cs:185` | 相同 ×2 |
| `NormalizeHeader` | `AnchorColumns.cs:34` / `CoatingColumns.cs:47` | 近似 ×2 |
| `RequireColumn` | `AnchorExcelReader.cs:223`（private）/ `CoatingSheetUtil.cs:30`（public） | 近似 ×2 |
| 表头 map 读取 | `CoatingSheetUtil.ReadHeaderMap` 有；`AnchorExcelReader` 各自内联 | 模式相同未共用 |

> 结论：用户感受到的「每个功能都很割裂」，根因是**缺少跨检测类型的共享骨架**，且这个缺失被 SOP 制度化了。

---

## 2. 现状盘点（基于精确签名，as of 2026-06-02）

### 三条管线对照

| 维度 | Anchor | Coating | Leeb |
| --- | --- | --- | --- |
| RPC 方法 | `generate_template` `list_batches` `read_batch_info` `run`（4） | `generate_template` `expand_template` `list_batches` `run` `report`（5） | `run` `preview_excel`（2） |
| Calculator | `Calc(AnchorWorkbookInput) → AnchorWorkbookResult` | `Calc(CoatingWorkbookInput) → CoatingWorkbookResult` | `CalcWorkbook(LeebHardnessWorkbook, **StandardsDb**) → ...Result` |
| 规范库依赖 | 无（阈值硬编在 `AnchorMath`） | 无 | **必需** `StandardsDb`（查厚度/角度/强度三表） |
| ExcelReader | `ReadRows → List<BatchRows>` + `ListBatchIds` | `ReadRows → List<BatchMembers>` + `ListBatchIds` | `ReadWorkbook → LeebHardnessWorkbook`（**无 ListBatchIds**） |
| 结果落表 | `AnchorAnalysisSheet.Write(ws, batch)` | `CoatingAnalysisSheet.Write(ws, batch, standard)` | `LeebReportTable.Write(ws, batch)` |
| Word 报告 | `AnchorWordTable.GenerateReport(...)`（用 `IFieldResolver`） | `CoatingDocxReport.Generate(...)` | **无** —— 出 `report_table_data`，前端调 `xlsx.write_leeb_report_table` 收尾 |
| 字段目录 | `AnchorFieldCatalog.All`（120+ 字段，仍在变=B1） | 无 | 无 |
| 类型专属件 | `RowResolver`(IFieldResolver) / `BatchInfoSheet` / `ResultReader` | `TemplateExpander` / `SheetUtil` | —（最薄，4 文件） |

### 已经存在的共享件（说明这仓库不排斥抽象，只是没用在管线上）

- `ReportTables/WordTableStyle.cs` —— 5 个 static 样式方法（字体/边框/行/格），`AnchorWordTable` + `CoatingWordTable` + `DocxReportAssembler` 共用。
- `Template/IFieldResolver.cs` —— `AnchorRowResolver` 已实现这个接口。**Word 填充层早有接口，检测管线层却没有。**

### 调度（关键：决定"加类型要不要改调度代码"）

`Server/JsonRpcServer.cs:150-167` 里**显式手动**逐行注册，无反射、无约定：

```csharp
Handlers.LeebHandlers.RegisterAll(dispatcher);
Handlers.AnchorHandlers.RegisterAll(dispatcher);
Handlers.CoatingHandlers.RegisterAll(dispatcher);
// ...
```

每个 handler 内部 `d.Register("anchor.run", Run)`。这是刻意的——契合 CLAUDE.md「程序不能是黑盒，每一步可追溯」+ dotnet/CLAUDE.md「入参手解，不用反射」。**任何方案都必须保持"显式可 grep"，不能引入反射魔法。**

---

## 3. 设计目标 / 非目标

**目标**
1. 加检测类型 ≈ 实现少量接口 + 在**一处显式清单**登记，不再"照葫芦画瓢"全链 copy。
2. 消掉 §1 那批 util 重复（一处定义，处处调）。
3. 调度保持显式可追溯（**不引反射**）。
4. 共性走骨架，分歧走能力接口——不强塞。

**非目标（同样重要，防过度设计）**
1. **不**强行统一三者天生不同的部分：`AnchorMath` / `CoatingTemplateExpander` / 各自 domain record / `FieldCatalog`。
2. **不**冻结仍在变动的字段目录 —— B1 原话「字段目录还在变」，本方案刻意**不**抽象 `AnchorFieldCatalog` / `IFieldResolver` 这层。
3. **不**在本轮统一三层参数契约三写（C# 手解 / MCP zod / 前端 zod）——那是另一个独立大题（codegen），见 §7 备注。
4. **不**为"以后可能有的第 5、第 6 个类型"预留扩展点（CLAUDE.md：单次调用不做抽象）。当前 3 个类型，抽象只服务"让第 4 个变便宜"。

---

## 4. 方案（分阶段，每阶段独立可验收、可单独叫停）

按风险从低到高排。**Phase 0 几乎纯赚，Phase 2 才是降本主菜，Phase 1 可选可跳。**

### Phase 0 — 抽公共 util（纯去重，零行为变更，零接口）

把 §1 表里的重复函数收敛到共享处。**这一步不引入任何抽象、不改任何签名语义，只是把 copy-paste 合并。** 单独做就能消掉用户看到的大半"重复造轮子"。

```
dotnet/civ-doc/
├── Handlers/HandlerUtil.cs   (新)  SafeSheetName / ParseUserInputs / ParseBatchUserInputs
└── Calc/ColumnText.cs        (新)  NormalizeHeader / ReadHeaderMap / RequireColumn / RequireAnyColumn
                                     （CoatingSheetUtil 现有实现升级为唯一来源）
```

- `AnchorHandlers` / `CoatingHandlers` / `LeebHandlers` / `CoatingTemplateExpander` 的 4 份 `SafeSheetName` → 删，改调 `HandlerUtil.SafeSheetName`。
- 2 份 `ParseUserInputs` → 删，改调 `HandlerUtil`。
- `AnchorColumns.NormalizeHeader` / `CoatingColumns.NormalizeHeader` → 收敛到 `ColumnText.NormalizeHeader`（若两者去括号规则有细微差异，**保留差异参数化**，不擅自统一行为）。
- `AnchorExcelReader` 的 private `RequireColumn` + `CoatingSheetUtil.RequireColumn` → 收敛。

**验收：** `dotnet test` 全绿（行为零变更，纯重定向调用）。每个函数一个 commit。

> ⚠️ 合并 `NormalizeHeader` 前必须 diff 两份实现确认是否**真的等价**——Coating 那份"多去尾部单位"。若不等价，则共享函数带选项参数，**不能**把一个类型的行为悄悄套到另一个（出错代价是工程事故）。

### Phase 1 —（可选）薄契约，仅在三者真正对齐处

老实说：收益有限，因为三者签名有真实分歧（见 §5）。**只在能干净对齐的地方**加接口，否则跳过。候选：

```csharp
// 落表写入：三者都是 void Write(ws, 单批结果[, 额外])
public interface IAnalysisSheetWriter<TBatchResult>
{
    void Write(IXLWorksheet ws, TBatchResult batch);
}
```

`Calculator` 想抽 `IDetectionCalculator<TIn,TOut>` 也行，但 **Leeb 的 `StandardsDb` 入参会破坏统一签名**——硬塞需要 DI/能力接口（见 §5），得不偿失。**建议：Phase 1 只做 `IAnalysisSheetWriter`，Calculator 接口暂缓或跳过。**

### Phase 2 — 检测描述符 + 通用 handler 脚手架（真正降低加类型成本）

核心：把"读 Excel → 算 → 写分析表 → (可选)出 Word"的**共性 80% 写成一份脚手架**，类型专属的 20% 通过**显式描述符 + 能力接口**插入。调度仍显式可 grep。

```csharp
// 一个检测类型 = 一个显式描述符（不是反射扫描！）
public sealed record DetectionDescriptor(
    string Type,                       // "anchor" / "coating" / "leeb"
    IReadOnlyList<string> Standards,   // 支持的规范
    IDetectionPipeline Pipeline);      // 读→算→落表的实现

// 共性脚手架：给定描述符，统一注册 <type>.generate_template / list_batches / run
public static class DetectionHandlers
{
    public static void RegisterAll(Dispatcher d, DetectionDescriptor desc) { /* run() 公共骨架 */ }
}

// 显式清单（加类型只动这一处 + 实现 Pipeline）——保持可 grep、无反射
public static class DetectionCatalog
{
    public static readonly DetectionDescriptor[] All =
    [
        AnchorDetection.Descriptor,
        CoatingDetection.Descriptor,
        LeebDetection.Descriptor,
    ];
}
```

`JsonRpcServer.RunAsync()` 里检测类的注册从"3 个手写 RegisterAll"变成"遍历 `DetectionCatalog.All`"——仍是一段显式代码，加类型时**这里零改动**。

**加一个检测类型 = 实现 `IDetectionPipeline`（读/算/落表）+ 往 `DetectionCatalog.All` 加一行 + 写 Math/Domain 计算本体。** 不再 copy handler / 不再改 `JsonRpcServer`。

---

## 5. 处理三者的"不对齐"（本方案的关键难点）

绝不能用一个刚性接口把三者削足适履。分歧点逐个给策略：

| 分歧 | 策略 |
| --- | --- |
| Leeb 需 `StandardsDb`，Anchor/Coating 不需要 | `IDetectionPipeline` 的 calc 入口统一接收一个 `PipelineContext`（内含按需打开的 `StandardsDb` 句柄）；不需要的类型忽略它。**不**把 `StandardsDb` 塞进公共 calc 签名。 |
| Leeb 无 Word（甩前端），Anchor/Coating 有 | 可选能力接口 `IWordReportable`。脚手架 run() 检测到描述符实现了它才走 Word 分支；Leeb 不实现，自然走"返回 report_table_data"分支。 |
| Coating 独有 `expand_template`，Anchor 独有 `read_batch_info` | **不**进通用脚手架。保留为类型专属 handler，描述符里加可选 `ExtraMethods` 钩子登记。共性归脚手架，个性归专属。 |
| Leeb 无 `list_batches`（sheet 即批） | 脚手架的 list_batches 设为可选能力；Leeb 描述符不挂。 |
| `FieldCatalog` / `RowResolver`（仅 Anchor，且**在变**） | **整层不纳入抽象**（B1 非目标）。Word 填充继续用现有 `IFieldResolver`，类型自管。 |

原则：**共性 80% 进脚手架，分歧 20% 走"可选能力接口 / 类型专属 handler"**，宁可留个性，不可强统一。

---

## 6. 迁移顺序与验证

每步独立 commit + `dotnet test` 绿（C# 侧有近 30 个测试文件，几乎每类一对一覆盖，是安全网）。

1. **Phase 0 全做**（最低风险、立竿见影）。逐函数收敛，逐个验收。
2. Phase 2 **先拿 Leeb 试水**（最薄、依赖最少、无 Word），把脚手架 + 描述符跑通；`LeebHandlersTests` 必须仍绿。
3. 再迁 **Coating**，验证 `expand_template`/`report` 的"专属 handler"钩子机制。
4. 最后迁 **Anchor**（最重、有 Word + Catalog），验证 `IWordReportable` 能力接口。
5. Phase 1（若决定做）穿插在 2-4 之间，纯属顺手。

> 任一步若发现抽象在"对抗代码"而非"简化代码"，**立即停在上一个绿色 commit**，把结论写回本文档。抽象是手段不是目的。

---

## 7. 风险与权衡

- **过度抽象**：CLAUDE.md 明令「单次调用不做抽象，200 行能缩到 50 就缩」。本方案对策：Phase 0 纯去重无争议；Phase 1 标"可选可跳"；Phase 2 只服务"让第 4 个类型变便宜"，不为臆想的扩展点铺路。**当前只有 3 个类型，若团队判断短期不会加第 4 个，可以只做 Phase 0、永远不做 Phase 2。**
- **字段目录在变（B1）**：方案刻意把 `FieldCatalog`/`IFieldResolver` 划在抽象之外，避免冻结仍在迭代的契约。
- **削足适履**：§5 用能力接口/专属 handler 兜住分歧，但仍有"脚手架反而更绕"的风险——靠 §6 的"对抗即叫停"红线控制。
- **行为漂移（出错=工程事故）**：Phase 0 合并 `NormalizeHeader` 等必须先证等价，差异参数化，绝不悄悄改判定相关行为。
- **反射诱惑**：子方案里"assembly 扫描自动发现 handler"虽省一行注册，但违背"无黑盒/可追溯/不用反射"——**本方案明确否决，改用显式 `DetectionCatalog.All` 清单**。

> 备注（范围外，仅记录）：参数契约三写（C# 手解 / MCP zod / 前端 zod）是另一条更大的去重线（如从单一 schema codegen），不在本方案内，避免一次吞太多。

---

## 8. 影响面（本方案动 C#，但这些地方要知会）

- **MCP**：`mcp/src/tools/*.ts` 是 thin ToolDef，**RPC 方法名/入参不变则零改动**。Phase 2 不改对外协议。
- **前端**：同理，RPC 契约不变则不动。
- **Python sidecar**：不涉及。
- **测试**：C# 测试是验收闸，预期全程保持绿；不为重构改测试断言（除非函数搬家改 namespace）。

---

## 9. 留给你拍板的决策点

（按 CONTEXT.md「业务/架构判断不让 AI 替用户拍板」，以下需你定，再动手）

1. **走到哪个 Phase？**
   - A. 只做 **Phase 0**（消重复 util）——风险最低，立刻见效，**推荐至少做到这里**。
   - B. Phase 0 + **Phase 2**（描述符+脚手架）——真正降低"加第 4 个类型"的成本，工作量大。
   - C. 全做（含 Phase 1 薄契约）。
2. **短期会不会加第 4 个检测类型**（钻芯/回弹/拉拔…）？会 → Phase 2 性价比高；不会 → 可能只值 Phase 0。
3. **先迁哪个类型试水**？（建议 Leeb）
4. 参数契约三写要不要单开一个方案？（本轮范围外）
5. 命名：`DetectionDescriptor` / `IDetectionPipeline` / `DetectionCatalog` 是否合适？

---

## 10. Before / After（加一个检测类型的 C# 侧成本）

```
BEFORE（照葫芦画瓢）                      AFTER（Phase 0 + 2 之后）
==========================               ==========================
复制 Anchor 全链：                         实现计算本体：
  Columns/Params/Standards/Math/            <类型>Math + Domain record   ← 真正的业务
  Calculator/FieldCatalog                  实现一个 IDetectionPipeline   ← 读/算/落表
  ExcelReader/TemplateWriter/AnalysisSheet （读 util、SafeSheetName 等全部复用）
  XxxHandlers.cs（含 copy 来的           往 DetectionCatalog.All 加一行 ← 唯一登记点
    SafeSheetName/ParseUserInputs）        JsonRpcServer：零改动
  改 JsonRpcServer 加注册行                能力接口按需挂：
                                            有 Word → 实现 IWordReportable
≈ 9 文件 + 多处 copy-paste util              无 Word → 不挂，自动走数据返回分支
```

- **调度改动**：1 行 → 0 行
- **util copy-paste**：每类重抄一遍 → 0（共享）
- **新增文件**：≈9 → 计算本体 + 1 个 Pipeline 实现 + 1 行登记
- **行为变更**：零（全程测试护栏）
