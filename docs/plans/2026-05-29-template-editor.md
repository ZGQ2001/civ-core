# 内置模版制作器 技术方案

> **For Hermes:** 使用 subagent-driven-development 逐任务实现。

**目标：** 用户可以导入含一张表格的 Word 文档，通过前端可视化编辑器绑定数据字段，生成模版配置文件；报告生成时按模版自动填值输出。

**架构：** C# OpenXML 解析 Word 表格 → 前端 React 编辑器（点击格子绑定字段）→ 保存 JSON 模版文件 → 生成报告时 C# 加载模版 + 数据 → 填充输出。

**技术栈：** C# .NET 9 + OpenXML SDK 3.x, React 19 + TypeScript, Zustand（编辑器状态）, Tauri invoke (JSON-RPC)

---

## 架构概览

```
用户 Word 文件（单表）
        ↓ 上传 (tauri file dialog → bytes → invoke)
┌─ C# Template Parser ────────────────────┐
│  OpenXML 解析:                            │
│    TableRow → Cell → Text/Style/Size      │
│    MergeInfo → rowSpan/colSpan            │
│  输出: TemplateTable JSON                 │
└─────────────┬─────────────────────────────┘
              ↓
┌─ 前端编辑器页 ──────────────────────────┐
│  <TemplateEditor>                         │
│    <TableView>  HTML 表格（点格高亮）     │
│    <BindingPanel>  右侧字段列表            │
│    <TemplateSettings>  重复策略/格式      │
│  保存 → TemplateConfig JSON              │
└─────────────┬─────────────────────────────┘
              ↓ RPC: template.save
┌─ 文件存储 ──────────────────────────────┐
│  ~/.civ-core/templates/                   │
│    锚杆报告模板/                           │
│      source.docx   ← 原始 Word 文件       │
│      config.json   ← 绑定配置             │
└─────────────┬─────────────────────────────┘
              ↓ RPC: report.generate
┌─ C# Report Generator ───────────────────┐
│  加载 source.docx + config.json          │
│  For each 锚杆:                           │
│    克隆表格段落                            │
│    遍历 bindings → 填值                   │
│  合并为最终报告 .docx                     │
└──────────────────────────────────────────┘
```

---

## 一、数据结构定义

### 1.1 模版配置（JSON 文件格式）

```json
{
  "version": 1,
  "projectType": "anchor",
  "displayName": "锚杆抗拔试验报告",
  "repeat": {
    "strategy": "per_anchor",
    "tableInterval": 1
  },
  "bindings": [
    {
      "cell": { "row": 2, "col": 2 },
      "field": "锚杆编号",
      "format": null
    },
    {
      "cell": { "row": 11, "col": 3 },
      "field": "弹性位移量",
      "format": "0.00"
    },
    {
      "cell": { "row": 11, "col": 4 },
      "field": "判定结果",
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

### 1.2 可用字段清单（硬编码，按项目类型）

```csharp
// C# 侧
public static class TemplateFields
{
    public static readonly FieldDef[] AnchorFields = new[]
    {
        // 委托方参数
        new("锚杆编号",         FieldSource.Calculated, "string"),
        new("杆体材料规格",     FieldSource.UserInput,  "string"),
        new("杆体弹模",         FieldSource.Calculated, "double", "0"),
        new("自由段长度",       FieldSource.Calculated, "double", "0.00"),
        new("锚固段长度",       FieldSource.Calculated, "double", "0.00"),
        new("轴向拉力设计值",   FieldSource.Calculated, "double", "0.0"),
        new("锁定荷载",         FieldSource.UserInput,  "string"),
        new("钻孔直径",         FieldSource.UserInput,  "string"),
        new("钻孔倾角",         FieldSource.UserInput,  "string"),
        new("岩土性状",         FieldSource.UserInput,  "string"),
        new("注浆材料强度等级", FieldSource.UserInput,  "string"),
        new("注浆材料配合比",   FieldSource.UserInput,  "string"),
        new("注浆方式",         FieldSource.UserInput,  "string"),
        new("灌浆压力",         FieldSource.UserInput,  "string"),
        new("灌浆日期",         FieldSource.UserInput,  "string"),
        // 试验结果
        new("弹性位移量",       FieldSource.Calculated, "double", "0.00"),
        new("上限值",           FieldSource.Calculated, "double", "0.00"),
        new("下限值",           FieldSource.Calculated, "double", "0.00"),
        new("判定结果",         FieldSource.Calculated, "string"),
        // 位移读数
        new("0.1Nt位移",        FieldSource.Calculated, "double", "0.00"),
        new("0.4Nt位移",        FieldSource.Calculated, "double", "0.00"),
        new("0.7Nt位移",        FieldSource.Calculated, "double", "0.00"),
        new("1.0Nt位移",        FieldSource.Calculated, "double", "0.00"),
        new("1.2Nt位移",        FieldSource.Calculated, "double", "0.00"),
        // 荷载等级
        new("0.1Nt荷载",        FieldSource.Calculated, "double", "0.0"),
        new("0.4Nt荷载",        FieldSource.Calculated, "double", "0.0"),
        new("0.7Nt荷载",        FieldSource.Calculated, "double", "0.0"),
        new("1.0Nt荷载",        FieldSource.Calculated, "double", "0.0"),
        new("1.2Nt荷载",        FieldSource.Calculated, "double", "0.0"),
    };
}

public record FieldDef(
    string Name,
    FieldSource Source,        // Calculated | UserInput
    string ValueType,          // string | double
    string? DefaultFormat = null
);
```

### 1.3 前端编辑器状态（Zustand store）

```typescript
// frontend/src/stores/templateEditor.ts
interface TemplateEditorState {
  // 解析后的表格
  table: ParsedTable | null;

  // 格子 → 字段 绑定（key = "r-c"）
  bindings: Record<string, string | null>;

  // 当前选中的格子
  selectedCell: { row: number; col: number } | null;

  // 可用字段列表（从 C# 获取）
  availableFields: FieldDef[];

  // 重复策略
  repeatStrategy: "per_anchor" | "per_batch";

  // 表间距
  tableInterval: number;
}
```

---

## 二、C# 引擎设计

### 2.1 文件结构

```
dotnet/civ-doc/
├── Template/
│   ├── TemplateParser.cs       # Word → ParsedTable 解析
│   ├── TemplateConfig.cs       # JSON 配置读写
│   ├── ReportGenerator.cs      # 模版 + 数据 → 输出报告
│   └── TemplateFields.cs       # 字段清单定义
```

### 2.2 新增 RPC 方法

```
template.parse       → 上传 .docx 字节 → 返回 ParsedTable JSON
template.fields      → 返回可用字段清单
template.save        → 接收 config JSON → 存入 ~/.civ-core/templates/
template.list        → 返回已保存模版列表
template.load        → 按名加载 config + 原文
report.generate      → 模版名 + 计算数据 → 输出 .docx 路径
```

### 2.3 核心逻辑

**TemplateParser.cs 伪代码：**

```csharp
public ParsedTable Parse(byte[] docxBytes)
{
    using var doc = WordprocessingDocument.Open(stream, false);
    var table = doc.MainDocumentPart.Document.Body
        .Descendants<Table>().First();  // 取第一个表

    var result = new ParsedTable();
    int rowIdx = 0;
    foreach (var row in table.Descendants<TableRow>())
    {
        int colIdx = 0;
        foreach (var cell in row.Descendants<TableCell>())
        {
            // 跳过被合并覆盖的格子
            if (result.IsMergedInto(rowIdx, colIdx)) { colIdx++; continue; }

            result.Cells[rowIdx][colIdx] = new ParsedCell
            {
                Text = cell.InnerText,
                RowSpan = GetRowSpan(cell),    // GridSpan / VerticalMerge
                ColSpan = GetColSpan(cell),
                Bold = cell.Descendants<Bold>().Any(),
                FontSize = GetFontSize(cell),
                Width = GetColumnWidth(cell),   // TableGrid 或 cell-level
            };

            // 填充合并占位
            if (result.Cells[rowIdx][colIdx].RowSpan > 1 ||
                result.Cells[rowIdx][colIdx].ColSpan > 1)
                result.MarkMerged(rowIdx, colIdx);

            colIdx++;
        }
        rowIdx++;
    }
    return result;
}
```

**ReportGenerator.cs 伪代码：**

```csharp
public string Generate(string templateName, AnchorBatchResult data, UserInputValues inputs)
{
    var config = TemplateConfig.Load(templateName);
    using var doc = WordprocessingDocument.Open(config.SourceDocxPath, true);

    var templateTable = doc.MainDocumentPart.Document.Body
        .Descendants<Table>().First();

    // 找到表格在文档中的位置
    var tableElement = templateTable; // 实际要处理表格所在段落

    if (config.Repeat.Strategy == "per_anchor")
    {
        // 为每根锚杆克隆表格
        foreach (var (input, result) in data.RowsWithResults)
        {
            var clonedTable = (Table)templateTable.CloneNode(true);
            // 插入到模板表格之后
            tableElement.InsertAfterSelf(clonedTable);

            // 遍历 bindings，填值
            foreach (var binding in config.Bindings)
            {
                var cell = GetCell(clonedTable, binding.Cell.Row, binding.Cell.Col);
                string value = ResolveValue(binding.Field, input, result, inputs);
                ReplaceCellText(cell, value, binding.Format);
            }
        }
        // 删除原始模板表格（仅作模板用，不输出）
        templateTable.Remove();
    }

    // 保存
    string outputPath = GetOutputPath(templateName);
    doc.MainDocumentPart.Document.Save();
    return outputPath;
}

private string ResolveValue(string fieldName, AnchorRowInput input,
    AnchorRowResult result, UserInputValues inputs)
{
    return fieldName switch
    {
        "锚杆编号" => input.AnchorId,
        "弹性位移量" => result.ElasticDisplacement.ToString("0.00"),
        "判定结果" => result.Qualified ? "合格" : "不合格",
        "杆体材料规格" => inputs.GetOrDefault(fieldName, "«杆体材料规格»"),
        // ... 其他字段
        _ => "«未知字段»"
    };
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
    <ImportWordButton />     // 上传 Word → RPC template.parse
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
- 未选中格子时灰色不可用
- 选中格子后：点击字段名 → 绑定到该格子
  - 如果该字段已绑到其他格子 → 旧绑定自动解除
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
            const boundCell = findBinding(f.name, bindings);
            return (
              <div
                key={f.name}
                className={clsx('field-item', boundCell && 'used')}
                onClick={() => selectedCell && onBind(selectedCell, f.name)}
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
| 1.1 | `TemplateFields.cs` — 字段清单定义 |
| 1.2 | `TemplateParser.cs` — Word 表格解析 + 测试（准备一份测试用 .docx） |
| 1.3 | `TemplateConfig.cs` — JSON 序列化/反序列化 + 测试 |
| 1.4 | `TemplateHandlers.cs` — RPC 路由接入（parse / fields / save / list / load） |
| 1.5 | `ReportGenerator.cs` — 模版克隆填值引擎 + 测试（用简单模版验证） |

### 阶段 2：前端编辑器（4-6 天）

| 任务 | 内容 |
|------|------|
| 2.1 | `useTemplateEditor` Zustand store |
| 2.2 | `TableView` 组件 — 解析结果渲染 + 格子选中高亮 |
| 2.3 | `BindingPanel` 组件 — 字段列表 + 点击绑定 |
| 2.4 | `ToolBar` — 导入 Word / 重复策略选择 / 保存 |
| 2.5 | 异常状态处理 — 加载中 / 解析失败 / 保存失败 |

### 阶段 3：集成与善后（3-4 天）

| 任务 | 内容 |
|------|------|
| 3.1 | 联调前后端完整流程 |
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
| 表格后跟文字段落处理 | MVP 假设用户只上传纯表文件，无尾巴段落 |
| 前端 HTML 表格无法还原 Word 行高绝对值 | 按比例渲染，够看清结构即可；不追求像素级 |
| 多批次的表间合并（如"所有锚杆共用委托方参数表"） | 第一期不做，config.merges 预留字段 |
