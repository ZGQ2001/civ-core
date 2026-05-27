---
name: civ-core-add-detection-type
description: 给 civ-core 装配线加新检测类型（钻芯法、回弹法、超声法、新规范的锚杆变体等）的端到端 SOP。涉及在 data_processing 工具加 calcType 下拉项 / 加新 RPC handler / 加新 Calculator / 加新 catalog 字段 / 加端到端测试时触发。
---

# 加新检测类型 SOP

照葫芦画瓢路径：**找一个最相似的已有检测类型（一般是锚杆抗拔 = anchor）从头到尾对照**，每一层加自己的同位件。

## 入手前先答 3 个问题

1. **依据哪本规范？** —— 先查 [[civil-codes-vault]] 看 vault 里有没有这本规范的笔记
2. **判定公式是什么？** —— vault 笔记里的 `calc_xxx 伪代码` 块直接翻译，没有就先在 vault 里建
3. **输入数据维度？** —— 一根构件多个测点？多批次？设计参数怎么传？

业务判断（如批次维度、字段层级）**不要 AI 替用户拍板**——列方案让用户选，参考 batch-dimension 工作（CONTEXT.md 用户偏好「业务判断不让 AI 替用户拍板」）。

## 添加层次（按依赖方向，从底层往上）

### Layer 1：领域 + 计算（C# domain + Calc）
```
dotnet/civ-doc/Calc/<新类型>/
├── <新类型>Columns.cs            # Excel 列名常量
├── <新类型>Params.cs             # 工程参数 record（带 Create 校验）
├── <新类型>Standards.cs          # 支持的规范常量
├── <新类型>Math.cs (可选)        # 公式底座 + xUnit 单测
├── <新类型>Calculator.cs         # 主入口（输入 workbook → 输出 result）
└── <新类型>FieldCatalog.cs       # FieldDef[] 字段清单（key/name/source/value_type/format/aliases）
```

**验收**：xUnit 跑 `Math` 单元测试通过 + Calculator 对小样本数据跑出预期结果。

### Layer 2：基础设施（Excel 读写 + 报告表）
```
dotnet/civ-doc/Calc/<新类型>/
├── <新类型>ExcelReader.cs        # 读输入 Excel（按列名）
└── <新类型>TemplateWriter.cs     # 生成空白模板 Excel

dotnet/civ-doc/ReportTables/
└── <新类型>AnalysisSheet.cs      # 写报告内插表 / 数据分析 sheet
```

### Layer 3：RPC handler
```
dotnet/civ-doc/Handlers/<新类型>Handlers.cs
```

- 注册 3 个 RPC：`<新类型>.generate_template` / `<新类型>.list_batches` / `<新类型>.run`
- `Program.cs` 里加一行 `<新类型>Handlers.RegisterAll(dispatcher)`
- Run() 入参解析参考 [AnchorHandlers.cs](dotnet/civ-doc/Handlers/AnchorHandlers.cs) 模式

**验收**：`AnchorHandlersTests.cs` 范式照抄到 `<新类型>HandlersTests.cs`，端到端跑通。

### Layer 4：前端 calcType 子表单
```
frontend/src/tools/data_processing/
├── types.ts                      # CalcType union 加新项
├── controller.tsx                # 派发到新的 calc handler
└── <新类型>SubForm.tsx (可选)    # 类型专属参数 UI
```

dropdown 下拉里出现新选项，选了之后 SettingsForm 渲染对应参数。

### Layer 5：报告填充（如果需要 Word 输出）
- catalog 字段挂上别名（中文名 / 简写）让模板占位符 `{{xxx}}` 命中
- 测试模板：`templates/<新类型>报告模板.docx`
- 如果按批次维度输出 → 参考 [[civ-core-make-template]] 的 `[[批次]]` 用法

## commit 拆分（每步独立验收，对应用户偏好）

| Commit | 范围 |
|--------|-----|
| 1 | Layer 1：计算底座 + xUnit |
| 2 | Layer 2：Excel + 报告表 + 端到端测试 |
| 3 | Layer 3：RPC + handler test |
| 4 | Layer 4：前端 calcType + UI smoke |
| 5 | Layer 5：报告填充 + catalog 字段 + 模板验证（如需要） |

## 检查清单

- [ ] catalog `FieldDef` 写全字段（Key/Name/Source/ValueType/DefaultFormat/Aliases）
- [ ] 字段中文名是用户用的术语，不是程序员叫法
- [ ] DefaultFormat 真的生效（数字带正确小数位）
- [ ] 多批次场景：参考 [[civ-core-make-template]] 决定哪些是批次级字段
- [ ] 错误信息按 CLAUDE.md「程序不能是黑盒」原则——告诉用户问题在哪 + 怎么修
- [ ] CONTEXT.md「下一步候选」标完成 + UX 缺口收尾

## 相关 skill

- [[civ-core-dev]] — 项目工作流入口
- [[civ-core-anchor-calc]] — 锚杆作为参考实现
- [[civ-core-make-template]] — 报告填充支持
- [[civ-core-debug-rpc]] — 联调时排查
- [[civil-codes-vault]] — 规范知识库
