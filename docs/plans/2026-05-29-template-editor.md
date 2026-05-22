# Built-in Template Editor – Technical Plan Summary

**Goal:** Users import a Word document containing one table, bind data fields visually in a front-end editor, generate a template config file; report generation auto-fills values by template.

**Architecture:** C# OpenXML parses Word table → React front-end editor (click cell to bind field) → save JSON template file → on report generation, C# loads template + data → fills output.

**Tech Stack:** C# .NET 9 + OpenXML SDK 3.x, React 19 + TypeScript, Zustand (editor state) + zundo (undo/redo middleware), Tauri invoke (JSON-RPC).

## Architecture Overview

```
User Word file (single table)
  ↓ upload (tauri file dialog → absolute path → invoke)
┌─ C# Template Parser ────────────────────┐
│  OpenXML: find anchor → next Table      │
│  TableRow → Cell → Text/Style           │
│  MergeInfo → rowSpan/colSpan            │
│  Calculate tableSignature (hash)        │
│  Output: TemplateTable JSON             │
└─────────────┬─────────────────────────────┘
              ↓
┌─ Frontend Editor Page ──────────────────┐
│  HTML table (click cell to highlight)   │
│  Right panel: field list                │
│  Repeat strategy / format               │
│  Save → TemplateConfig JSON             │
└─────────────┬─────────────────────────────┘
              ↓ RPC: template.save
┌─ File Storage ──────────────────────────┐
│  ~/.civ-core/templates/                 │
│    anchor-report-template/              │
│      source.docx  ← original Word file  │
│      config.json   ← binding config     │
└─────────────┬─────────────────────────────┘
              ↓ RPC: report.generate
┌─ C# Report Generator ───────────────────┐
│  Load source.docx + config.json         │
│  Verify tableSignature match            │
│  For each anchor:                       │
│    Clone table paragraph                │
│    Traverse bindings → fill values      │
│    (Run-level: preserve rPr, replace t) │
│  Merge into final .docx report          │
└──────────────────────────────────────────┘
```

## Data Structures

### Template Configuration (JSON)

```json
{
  "version": 1,
  "projectType": "anchor",
  "displayName": "锚杆抗拔试验报告",
  "tableSignature": "rows:15_cols:6_hash:A8F9C2",
  "repeat": {
    "strategy": "per_anchor",
    "tableInterval": 1
  },
  "bindings": [
    {
      "cell": { "row": 2, "col": 2 },
      "fieldKey": "anchor_id",
      "format": null
    },
    {
      "cell": { "row": 11, "col": 3 },
      "fieldKey": "elastic_displacement",
      "format": "0.00"
    },
    {
      "cell": { "row": 11, "col": 4 },
      "fieldKey": "judgement_result",
      "format": null
    }
  ],
  "merges": [
    {
      "groupName": "委托方参数区",
      "cells": [
        { "row": 1, "col": 1 },
        { "row": 1, "col": 2 },
        { "row": 2, "col": 1 }
      ]
    }
  ]
}
```

> **tableSignature** 由 C# 解析 Word 时计算：`rows:{N}_cols:{M}_hash:{前100单元格内容MD5前6位}`。生成报告时先比对，不匹配则抛异常阻断，要求用户重新绑定模板。

### Available Field List (C#)

```csharp
public static class TemplateFields
{
    public static readonly FieldDef[] AnchorFields = new[]
    {
        // 委托方参数
        new("anchor_id",              "锚杆编号",       FieldSource.Calculated, "string"),
        new("bar_material_spec",      "杆体材料规格",    FieldSource.UserInput,  "string"),
        // ... (杆体弹模, 自由段长度, 锚固段长度, 轴向拉力设计值, 锁定荷载, 钻孔直径, etc.)
        // 试验结果
        new("elastic_displacement",   "弹性位移量",      FieldSource.Calculated, "double", "0.00"),
        new("upper_limit",            "上限值",          FieldSource.Calculated, "double", "0.00"),
        new("lower_limit",            "下限值",          FieldSource.Calculated, "double", "0.00"),
        new("judgement_result",       "判定结果",        FieldSource.Calculated, "string"),
        // 位移读数 (0.1Nt位移 … 1.2Nt位移) ×5
        // 荷载等级 (0.1Nt荷载 … 1.2Nt荷载) ×5
    };
}

/// <summary>
/// Key 是字段唯一主键，绝不因规范改名而变动。
/// Name 仅用于前端显示。
/// </summary>
public record FieldDef(
    string Key,           // 唯一主键，如 "elastic_displacement"
    string Name,          // 中文显示名，如 "弹性位移量"
    FieldSource Source,   // Calculated | UserInput
    string ValueType,     // string | double
    string? DefaultFormat = null
);
```

### Frontend Zustand Store

```typescript
interface TemplateEditorState {
    table: ParsedTable | null;
    bindings: Record<string, { fieldKey: string; format?: string }>; // key = "r-c"
    selectedCell: { row: number; col: number } | null;
    availableFields: FieldDef[];
    repeatStrategy: "per_anchor" | "per_batch";
    tableInterval: number;
}
```

> **Undo/Redo**: 使用 zundo 中间件包裹 Zustand store，自动记录每次 binding 变更，以最小成本实现 Ctrl+Z 防误触。

## C# Engine Design

### File Structure

```
dotnet/civ-doc/
├── Template/
│   ├── TemplateParser.cs    # Word → ParsedTable（锚点定位 + 合并解析 + 签名计算）
│   ├── TemplateConfig.cs    # JSON config read/write
│   ├── ReportGenerator.cs   # Template + data → output report（签名校验 + Run级填值）
│   └── TemplateFields.cs    # Field definitions（Key/Name双字段）
```

### RPC Methods

- `template.parse` – 接收 **docx 绝对路径字符串** → 返回 `ParsedTable` JSON + `tableSignature`
- `template.fields` – return available fields (含 Key + Name)
- `template.save` – receive config JSON → store under `~/.civ-core/templates/`
- `template.list` – list saved templates
- `template.load` – load config + original file by name
- `report.generate` – template name + computed data → output .docx path

> **IPC 优化**：`template.parse` 前端只传绝对路径（如 `C:\templates\xxx.docx`），C# 直接读本地磁盘。不通过 Tauri invoke 传递 byte[]，避免大文件内存开销。

### Core Logic Highlights (pseudocode)

**TemplateParser.cs**

```csharp
public ParsedTable Parse(string docxPath)
{
    using var doc = WordprocessingDocument.Open(docxPath, false);
    var body = doc.MainDocumentPart.Document.Body;

    // 1. 定位模板锚点
    //    要求用户在目标表格前的段落中写入 [[数据绑定区]]
    //    程序寻找该段落后第一个 Table
    var anchorPara = body.Descendants<Paragraph>()
        .FirstOrDefault(p => p.InnerText.Contains("[[数据绑定区]]"));
    if (anchorPara == null)
        throw new InvalidOperationException("模板缺少锚点：请在目标表格前插入段落 [[数据绑定区]]");

    var table = anchorPara.ElementsAfter()
        .OfType<Table>()
        .FirstOrDefault();
    if (table == null)
        throw new InvalidOperationException("锚点 [[数据绑定区]] 之后未找到表格");

    // 2. 解析表格
    var result = new ParsedTable();
    int rowIdx = 0;
    foreach (var row in table.Descendants<TableRow>())
    {
        int colIdx = 0;
        foreach (var cell in row.Descendants<TableCell>())
        {
            if (result.IsMergedInto(rowIdx, colIdx)) { colIdx++; continue; }

            result.Cells[rowIdx][colIdx] = new ParsedCell
            {
                Text = cell.InnerText,
                RowSpan = GetRowSpan(cell),    // GridSpan / VerticalMerge
                ColSpan = GetColSpan(cell),
                Bold = cell.Descendants<Bold>().Any(),
                FontSize = GetFontSize(cell),
            };

            if (result.Cells[rowIdx][colIdx].RowSpan > 1 ||
                result.Cells[rowIdx][colIdx].ColSpan > 1)
                result.MarkMerged(rowIdx, colIdx);

            colIdx++;
        }
        rowIdx++;
    }

    // 3. 计算表格签名（行数_列数_前100格MD5前6位）
    result.TableSignature = ComputeSignature(table);

    return result;
}

private string ComputeSignature(Table table)
{
    var rows = table.Descendants<TableRow>().Count();
    var cells = table.Descendants<TableCell>().Take(100)
        .Select(c => c.InnerText);
    var cols = table.Descendants<TableRow>().First()
        .Descendants<TableCell>().Count();
    var hash = Convert.ToHexString(
        MD5.HashData(Encoding.UTF8.GetBytes(string.Join("", cells)))
    )[..6];
    return $"rows:{rows}_cols:{cols}_hash:{hash}";
}
```

> **测试要求**：阶段 1 测试 TemplateParser.cs 时，必须使用包含 `gridSpan`（横跨多列）和 `vMerge`（纵跨多行）的**真实复杂 Word 报表**作为单元测试用例，严禁仅用简单 n×n 表格测试。

**ReportGenerator.cs 伪代码：**

```csharp
public string Generate(string templateName, AnchorBatchResult data, UserInputValues inputs)
{
    var config = TemplateConfig.Load(templateName);
    using var doc = WordprocessingDocument.Open(config.SourceDocxPath, true);

    var body = doc.MainDocumentPart.Document.Body;

    // 1. 签名校验 —— 第一步，不匹配直接阻断
    var anchorPara = body.Descendants<Paragraph>()
        .FirstOrDefault(p => p.InnerText.Contains("[[数据绑定区]]"));
    var templateTable = anchorPara?.ElementsAfter().OfType<Table>().FirstOrDefault()
        ?? throw new InvalidOperationException("模板锚点或表格缺失");

    var currentSignature = ComputeSignature(templateTable);
    if (currentSignature != config.TableSignature)
        throw new InvalidOperationException(
            $"模板已修改！当前签名 {currentSignature} 与保存时 {config.TableSignature} 不一致，" +
            "请重新打开模板编辑器绑定字段。");

    if (config.Repeat.Strategy == "per_anchor")
    {
        foreach (var (input, result) in data.RowsWithResults)
        {
            var clonedTable = (Table)templateTable.CloneNode(true);
            templateTable.InsertAfterSelf(clonedTable);

            foreach (var binding in config.Bindings)
            {
                var cell = GetCell(clonedTable, binding.Cell.Row, binding.Cell.Col);
                string value = ResolveValue(binding.FieldKey, input, result, inputs);
                ReplaceCellTextAtRunLevel(cell, value, binding.Format);
            }
        }
        templateTable.Remove();
    }

    string outputPath = GetOutputPath(templateName);
    doc.MainDocumentPart.Document.Save();
    return outputPath;
}

// ============================================
// 字段解析：基于 FieldKey，不再用中文 switch
// ============================================
private string ResolveValue(string fieldKey, AnchorRowInput input,
    AnchorRowResult result, UserInputValues inputs)
{
    return fieldKey switch
    {
        "anchor_id"             => input.AnchorId,
        "elastic_displacement"  => result.ElasticDisplacement.ToString("0.00"),
        "upper_limit"           => result.UpperLimit.ToString("0.00"),
        "lower_limit"           => result.LowerLimit.ToString("0.00"),
        "judgement_result"      => result.Qualified ? "合格" : "不合格",
        _ when inputs.TryGetValue(fieldKey, out var v) => v,
        _ => "«未知字段»"
    };
}

// ============================================
// Run 级替换 —— 保留样式，只换文本
// ============================================
private void ReplaceCellTextAtRunLevel(TableCell cell, string value, string? format)
{
    string display = format != null && double.TryParse(value, out var d)
        ? d.ToString(format) : value;

    var paragraphs = cell.Descendants<Paragraph>().ToList();
    // 定位第一个 Run：保留 rPr（样式），只替换 t（文本）
    var firstRun = paragraphs.SelectMany(p => p.Descendants<Run>()).FirstOrDefault();
    if (firstRun != null)
    {
        // 保留 <w:rPr> 不动；只替换 <w:t> 的 Text
        var textElement = firstRun.Descendants<Text>().FirstOrDefault();
        if (textElement != null)
        {
            textElement.Text = display;
        }
    }

    // 其余 Run（含多余 Text 节点）全部删除，防止残留旧字符
    foreach (var para in paragraphs)
    {
        var runs = para.Descendants<Run>().ToList();
        if (runs.Count > 1)
        {
            for (int i = 1; i < runs.Count; i++)
                runs[i].Remove();
        }
    }
}
```

---

## 三、前端组件设计

### 3.1 路由和页面

```
/templates             模板列表页
/templates/editor      编辑器页（新建）
/templates/editor/:id  编辑器页（编辑已有）
```

### 3.2 组件树

```
<TemplateEditorPage>
  <ToolBar>
    <ImportWordButton />     // 上传 Word → RPC template.parse（传路径，不传 byte[]）
    <RepeatStrategySelect /> // per_anchor | per_batch
    <SaveButton />           // RPC template.save
  </ToolBar>
  <SplitPane>
    <TableView />            // 左：HTML 表格渲染
    <BindingPanel />         // 右：字段列表 + 绑定信息
  </SplitPane>
</TemplateEditorPage>
```

### 3.3 TableView 组件

- 用 HTML `<table>` 渲染 ParsedTable JSON
- 行高列宽按比例还原（不追求像素级）
- 已绑定格子显示浅蓝底色 + 字段名小标签
- 点击格子 → 红框高亮 → selectedCell 更新
- 合并单元格正确跨行跨列

```tsx
function TableView({ table, bindings, selectedCell, onCellClick }: Props) {
  return (
    <table className="template-table">
      <tbody>
        {table.rows.map((row, r) => (
          <tr key={r}>
            {row.cells.map((cell, c) => {
              if (cell.isHidden) return null; // 被合并覆盖
              const bound = bindings[`${r}-${c}`];
              const selected = selectedCell?.row === r && selectedCell?.col === c;

              return (
                <td
                  key={c}
                  rowSpan={cell.rowSpan}
                  colSpan={cell.colSpan}
                  className={clsx(
                    'template-cell',
                    bound && 'bound',
                    selected && 'selected'
                  )}
                  onClick={() => onCellClick(r, c)}
                >
                  {cell.text}
                  {bound && <span className="field-tag">{bound}</span>}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

### 3.4 BindingPanel 组件

- 显示可用字段列表（按类型分组：委托方参数 / 试验结果 / 位移读数）
- **字段显示中文名（`f.name`），内部绑定用 Key（`f.key`）**
- 未选中格子时灰色不可用
- 选中格子后：点击字段名 → 绑定到该格子（存储 fieldKey）
  - 如果该字段 Key 已绑到其他格子 → 旧绑定自动解除
  - 如果该格子已有绑定 → 替换
- 已绑定字段旁显示格子位置（如 B3）
- 「清除绑定」按钮

```tsx
function BindingPanel({ fields, bindings, selectedCell, onBind }: Props) {
  return (
    <div className="binding-panel">
      <h3>数据字段</h3>
      {selectedCell ? (
        <div className="selected-info">
          已选中: 第{selectedCell.row + 1}行 第{selectedCell.col + 1}列
        </div>
      ) : (
        <div className="hint">点击左侧表格中的格子开始绑定</div>
      )}

      {Object.entries(groupedFields).map(([group, fields]) => (
        <div key={group} className="field-group">
          <h4>{group}</h4>
          {fields.map(f => {
            // 用 Key 查找绑定（内部主键），显示 Name
            const boundCell = findBindingByKey(f.key, bindings);
            return (
              <div
                key={f.key}
                className={clsx('field-item', boundCell && 'used')}
                onClick={() => selectedCell && onBind(selectedCell, f.key)}
              >
                {f.name}
                {boundCell && <span className="bound-to">{boundCell}</span>}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
```

---

## 四、实施步骤

### 阶段 1：C# 核心引擎（3-5 天）

| 任务 | 内容 |
|------|------|
| 1.1 | `TemplateFields.cs` — 字段清单定义（`FieldDef` 含 Key + Name 双字段） |
| 1.2 | `TemplateParser.cs` — Word 表格解析（锚点定位 + 合并单元格 + 签名计算）<br>**测试必须用含 gridSpan/vMerge 的真实复杂 Word 报表** |
| 1.3 | `TemplateConfig.cs` — JSON 序列化/反序列化（含 tableSignature） + 测试 |
| 1.4 | `TemplateHandlers.cs` — RPC 路由接入（parse 接收路径字符串 / fields / save / list / load） |
| 1.5 | `ReportGenerator.cs` — 签名校验 + Run 级填值 + 测试 |

### 阶段 2：前端编辑器（4-6 天）

| 任务 | 内容 |
|------|------|
| 2.1 | `useTemplateEditor` Zustand store + **zundo 中间件**（Ctrl+Z 防误触） |
| 2.2 | `TableView` 组件 — 解析结果渲染 + 格子选中高亮 |
| 2.3 | `BindingPanel` 组件 — 字段列表（中文显示/Key 绑定） + 点击绑定 |
| 2.4 | `ToolBar` — 导入 Word（取本地路径传 C#） / 重复策略选择 / 保存 |
| 2.5 | 异常状态处理 — 加载中 / 解析失败 / 签名不匹配 / 保存失败 |

### 阶段 3：集成与善后（3-4 天）

| 任务 | 内容 |
|------|------|
| 3.1 | 联调前后端完整流程（含签名校验阻断场景） |
| 3.2 | 删除 `AnchorReportTable.cs` 硬编码（改成走模版引擎） |
| 3.3 | 用户输入字段的前端表单（前端收集 `UserInputValues`） |
| 3.4 | `report.generate` 与现有计算流程对接 |

---

## 五、与现有代码的关系

- **保留**：`AnchorCalculator.cs`、`AnchorMath.cs`、`AnchorStandards.cs` 等计算层不变
- **保留**：`AnchorTemplateWriter.cs`（输入 Excel 模板生成）不变
- **替换**：`AnchorReportTable.cs` 220 行硬编码 → 模版引擎
- **新增**：`dotnet/civ-doc/Template/` 目录
- **新增**：`frontend/src/pages/TemplateEditor/` 目录

---

## 六、风险与边界

| 风险 | 应对 |
|------|------|
| OpenXML 复杂合并单元格（横向+纵向同时） | 先支持最常见情况；极端合并 fallback 提示用户简化模版 |
| 用户私自编辑已绑定的 Word 模板（增删行列） | **tableSignature 强校验**：生成时比对签名，不匹配则阻断并提示重新绑定 |
| 规范改名导致存量模板报废 | **FieldKey 解耦**：Key 不变，Name 可随时换，绑定永不失效 |
| 表格后跟文字段落处理 | MVP 假设用户只上传纯表文件，无尾巴段落 |
| 前端 HTML 表格无法还原 Word 行高绝对值 | 按比例渲染，够看清结构即可；不追求像素级 |
| 多批次的表间合并（如"所有锚杆共用委托方参数表"） | 第一期不做，config.merges 预留字段 |