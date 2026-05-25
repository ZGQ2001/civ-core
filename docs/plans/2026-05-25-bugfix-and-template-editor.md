# Bug 修复 + 模板编辑器启动计划

## 一、Bug 修复（前置，预计 2-3h）

### Bug 1：目录树自然排序

**现象**：文件名含数字时按字典序排列（"100" 排在 "2" 前面），应按自然数排序。

**根因**：`src/civ_core/api/handlers/files.py:126` 用 `e["name"].lower()` 做排序 key，纯字典序。

**修复**：

```python
import re

def _natural_sort_key(name: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]

# line 126
entries.sort(key=lambda e: (not e["is_dir"], _natural_sort_key(e["name"])))
```

**验证**：写 pytest，输入 `["file2", "file100", "file10"]` 期望输出 `["file2", "file10", "file100"]`。

---

### Bug 2：Excel 预览不显示合并单元格

**现象**：data_processing 的 Excel 预览表格不支持 rowSpan/colSpan，合并单元格被拆成多个独立格。

**根因**：
- C# `LeebHandlers.PreviewExcel` 返回的数据结构是 `{headers, rows}`——扁平 dict 列表，不含合并信息。
- 前端 `data_processing/Page.tsx:244-280` 渲染时没有 rowSpan/colSpan 逻辑。

**修复（C# 端）**：`LeebHandlers.PreviewExcel` 增加返回 `merges` 字段：

```json
{
  "merges": [
    {"sr": 0, "sc": 0, "er": 2, "ec": 0}
  ]
}
```

用 ClosedXML `ws.MergedRanges` 读取合并区域，转为 0-based 坐标。

**修复（前端）**：`data_processing/Page.tsx` 预计算 `mergeMap`（主格 → rowSpan/colSpan）+ `suppressedSet`（被合并覆盖的格），渲染时：
- 主格加 `rowSpan`/`colSpan` 属性
- 被覆盖格跳过 `return null`

**验证**：用含合并单元格的测试 xlsx 预览，确认跨行跨列正确。

---

### Bug 3：曲线对照数据表格列顺序错

**现象**：`RowDataStrip` 里的列不按预设定义顺序排列。

**根因**：`plot_curves/Page.tsx` 的 `RowDataStrip` 用 `Object.keys(rowData).filter(...)` 取列——顺序取决于 Excel 列序而非预设定义序。用户期望的是：id_column 在最前，然后按曲线定义顺序排。

**修复**：`RowDataStrip` 中用有序数组替代 `referenced` Set，按 preset 定义顺序构建：

```tsx
const orderedKeys: string[] = [];
const seen = new Set<string>();
if (c.effectivePreset) {
  const add = (k: string) => { if (k && !seen.has(k)) { seen.add(k); orderedKeys.push(k); } };
  add(c.effectivePreset.id_column);
  for (const curve of c.effectivePreset.curves) {
    for (const pt of curve.points) {
      add(pt.var_column);
    }
  }
}
const visibleKeys = orderedKeys.filter((k) => k in rowData);
```

**验证**：切换预设，确认列顺序与预设定义一致。

---

## 二、模板编辑器（新工具页）

### 位置

ActivityBar 排序：数据处理 → 绘曲线图 → **模板编辑** → PDF 工具 → Word→PDF

```tsx
// App.tsx TOP_TOOLS
const TOP_TOOLS: ActivityItem[] = [
  { id: 'data_processing', icon: 'symbol-method', tooltip: '数据处理' },
  { id: 'plot_curves', icon: 'graph-line', tooltip: '绘曲线图' },
  { id: 'template_editor', icon: 'table', tooltip: '模板编辑' },  // 新增
  { id: 'pdf_tools', icon: 'file-pdf', tooltip: 'PDF 工具' },
  { id: 'word2pdf', icon: 'file-binary', tooltip: 'Word → PDF' },
];
```

### Phase 1：C# 核心引擎（本次）

详细技术方案见 `docs/plans/2026-05-29-template-editor.md`。

| 步骤 | 文件 | 内容 |
|------|------|------|
| 1.1 | `dotnet/civ-doc/Template/TemplateFields.cs` | 字段清单定义（FieldDef: Key + Name + Source + ValueType） |
| 1.2 | `dotnet/civ-doc/Template/TemplateParser.cs` | Word 表格解析：锚点 `[[数据绑定区]]` 定位 → Table 遍历 → 合并单元格 → 签名计算 |
| 1.3 | `dotnet/civ-doc/Template/TemplateConfig.cs` | JSON 配置序列化/反序列化（含 tableSignature） |
| 1.4 | `dotnet/civ-doc/Handlers/TemplateHandlers.cs` | RPC 接入：template.parse / template.fields / template.save / template.list / template.load |
| 1.5 | `dotnet/civ-doc/Template/ReportGenerator.cs` | 签名校验 + Run 级填值（保留样式只换文本） |

**依赖**：OpenXML SDK（civ-doc.csproj 已有 ClosedXML，需确认是否额外需要 DocumentFormat.OpenXml）。

**RPC 路由**：`template.*` 前缀走 C# 默认路由，无需改 Rust/Tauri 端。

**测试**：必须用含 `gridSpan`（横跨多列）和 `vMerge`（纵跨多行）的真实复杂 Word 报表做 xUnit 测试。

### Phase 2：前端编辑器页（后续）

本次只搭空壳 + Provider：
- `frontend/src/tools/template_editor/` 目录：index.ts / types.ts / controller.tsx / Page.tsx / SettingsForm.tsx
- Page.tsx 先只显示"选择 Word 模板文件"按钮 + 空占位
- controller.tsx 注册 useEffect 联动 shell.activatedFile（.docx 文件）

### Phase 3：前端编辑器完整交互 + 联调（后续）

---

## 三、实施顺序

1. Bug 1：目录树自然排序（15min）
2. Bug 2：Excel 预览合并单元格（C# + 前端，1-2h）
3. 模板编辑器 Phase 1 C# 核心引擎（按 1.1-1.5 顺序）
4. 模板编辑器前端空壳（Phase 2 骨架，让工具页可见可点）
