---
name: civ-core-anchor-calc
description: 锚杆抗拔（GB 50086-2015）计算逻辑工作指引。涉及锚杆抗拔 / GB 50086 / 弹性位移量 / 0.1Nt / 1.2Nt / 判定上下限 / Q < δ < R / AnchorCalculator / AnchorMath 等 civ-core 锚杆相关计算代码时触发。
---

# 锚杆抗拔计算工作指引

## 计算来源单一原则

**所有判定公式、阈值、条件**走 [[civil-codes-vault]] 里 GB 50086-2015 的笔记 + 该笔记里的 `calc_xxx 伪代码` 块。**禁止在代码注释或本 skill 里独立维护一份公式**——双重维护就是 bug 源头。

工作流程：
1. 查 `D:\CodeProjects\civil-codes-vault\10_检测项目\锚杆抗拔.md`（或类似命名）
2. 看 `calc_anchor_pullout 伪代码` 块（如存在）→ 直译成 C#
3. 不存在伪代码 → 跟用户确认要不要先在 vault 里建（避免代码先于规范知识）
4. 实现完成 → 在测试里引用 vault 笔记的具体条文号（如「GB 50086-2015 条文 G.0.6」）

## civ-core 内已落地的位置

| 文件 | 干啥 |
|------|-----|
| [AnchorMath.cs](dotnet/civ-doc/Calc/Anchor/AnchorMath.cs) | 公式底座（Q / R / 弹性位移量 / 各级位移） |
| [AnchorCalculator.cs](dotnet/civ-doc/Calc/Anchor/AnchorCalculator.cs) | 主入口（输入 workbook → 输出 result） |
| [AnchorFieldCatalog.cs](dotnet/civ-doc/Calc/Anchor/AnchorFieldCatalog.cs) | catalog 字段（49 字段）+ 中文名 + 别名 |
| [AnchorColumns.cs](dotnet/civ-doc/Calc/Anchor/AnchorColumns.cs) | Excel 输入列名常量（`批次` / `锚杆编号` / `0.1Nt` / ...） |
| [AnchorStandards.cs](dotnet/civ-doc/Calc/Anchor/AnchorStandards.cs) | 支持规范常量 |
| [AnchorAnalysisSheet.cs](dotnet/civ-doc/ReportTables/AnchorAnalysisSheet.cs) | 输出 sheet 写入 |

## 关键概念（**最容易踩**的领域陷阱）

### 1. 单位
- **P（轴向拉力设计值，Nt）** → 输入用 N，模板里显示 kN（`axial_design_load_kn` 派生字段，alias「轴向拉力设计值」）
- **位移读数** → 输入 mm
- **E（弹性模量）** → N/mm²（钢筋取 2.0×10⁵）
- **截面积 A** → mm²

输入单位错了会导致 Q / R 阈值差几个数量级，肉眼难发现。**xUnit 必须有单位回归用例**。

### 2. 判定公式（GB 50086-2015 G.0.6）

```
Q < 弹性位移量 < R   →  合格
其中：
  弹性位移量 = δ(1.2Nt-5min) - δ(卸载0.1Nt)
  Q = 0.9 · P · Lf / (E · A)       # 下限：游离段必须充分受力
  R = (Lf + La/3) · P / (E · A)    # 上限：锚固段不能滑移过大
```

**单位一致性**：P [N], Lf/La [mm], A [mm²], E [N/mm²] → Q/R [mm]，跟弹性位移量同单位才能比。

### 3. 输入数据格式
锚杆每根 13 列位移读数：
- 加载阶段：0.1Nt / 0.4Nt / 0.7Nt / 1.0Nt / 1.2Nt-1min / 1.2Nt-3min / 1.2Nt-5min
- 卸载阶段：卸载1.0Nt / 卸载0.7Nt / 卸载0.4Nt / 卸载0.1Nt

**列名定死，是契约**（[AnchorColumns.cs](dotnet/civ-doc/Calc/Anchor/AnchorColumns.cs)），改名会破前端模板 + 用户 Excel。

### 4. 批次 vs 锚杆维度
同一批锚杆共享一组工程参数（P/Lf/La/A/E）。前端 [anchorParamsForm.tsx](frontend/src/tools/_shared/anchorParamsForm.tsx) 按批次填，传 `params_by_batch: { batchId: AnchorParams }`。

batch 级 user_input 字段（如 `grouting_date`）走 `batch_user_inputs`，参考 [[civ-core-make-template]] 的批次维度模板说明。

### 5. anchor_index 跨批次全局递增
报告里 `{{锚杆序号}}` 占位符的值是**全局**的（批次 A 有 3 根 → A: 1,2,3；批次 B 有 2 根 → B: 4,5），不是批次内。

在 [AnchorHandlers.Run](dotnet/civ-doc/Handlers/AnchorHandlers.cs) 里 `anchorIndex++` 在批次循环外累加。

## 测试套路

每个公式 / 判定路径都有 xUnit 覆盖：

```csharp
[Fact]
public void 弹性位移量_合格样例_应判合格()
{
    var input = new AnchorRowInput(...);  // 一组实测数据
    var p = AnchorParams.Create(P:180000, Lf:500, La:7500, A:804.25, E:200000);
    var result = AnchorCalculator.CalcRow(input, p);
    Assert.True(result.IsQualified);
    Assert.Equal(2.05, result.ElasticDisplacement, precision: 2);
}
```

**完整覆盖**：合格 + 不合格（Q 边界）+ 不合格（R 边界）+ 单位异常 + 缺列数据。

## 跟 catalog 字段对照

模板里写 `{{弹性位移量}}` 命中 catalog `elastic_displacement`；写 `{{允许值上限}}` 命中 `r_upper`。完整列表见 [AnchorFieldCatalog.cs](dotnet/civ-doc/Calc/Anchor/AnchorFieldCatalog.cs)。

不确定字段名时去模板助手工具看「按层级」分组，比翻代码快。

## 常见错误

| 现象 | 原因 |
|------|-----|
| Q 跟 R 数量级差 1000× | P 单位用了 kN 没换算成 N |
| 弹性位移量算出来 -X.XX | 拿错列（卸载列减加载列反了） |
| 判定结果全合格 / 全不合格 | A 或 E 拿错（A 是 mm² 不是 cm²） |
| 报告里 `{{允许值上限}}` 不替换 | catalog 别名网没覆盖。查 catalog R_upper / 上限 等别名 |

## 相关 skill

- [[civ-core-dev]] — 项目工作流入口
- [[civil-codes-vault]] — 规范知识库（公式源头）
- [[civ-core-add-detection-type]] — 加新检测类型时参考锚杆作为范本
- [[civ-core-make-template]] — 报告填充配套
