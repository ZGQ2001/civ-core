# 工作上下文

> **角色**：当前焦点、UX 缺口、用户偏好。**每会话更新**，时效性强。
> **维护**：AI 每次会话结束时更新。里程碑级变动记 PROGRESS.md，这里不重复。
> **配套**：`CLAUDE.md`（宪法）| `RULES.md`（规范）| `PROGRESS.md`（里程碑）

---

## 当前焦点（2026-06-03 续）— 换价值主张(D)去黑盒 + 7 目标推进（分支 `claude/magical-cori-a9T8w`，PR #22 draft）

> Claude Code on the web 会话。负责人定方向 **D**（数据透明可验证为主线，Word 报告降为可选），并下 7 条目标。本 web 环境**装不了 dotnet、前端依赖也没装、网络锁死** → C#/前端均靠 CI 验（dotnet + 前端 (TS) job 已绿）。

**已做（已 push PR #22，CI 验证）**

- **修前端编译断**：`report_generator` 报告类型三选一 radio → 检测类型多选 checkbox（`ReportType`→`DetectionType`/`selectedTypes`，杀 `'multi'` 硬编码）。→ #1 能编译、#3 前后端对应（编译层）。
- **防火两截面**（#2）：`CoatingTemplateExpander.ResolveSections` 显式截面数<2 报错、按长度算兜底到 `CoatingStandards.MinSections=2`；国标膨胀型 5处×3点走 FiveLocationCount 天然豁免。
- **去黑盒(D)**：① 机读 sheet `_批次参数`/`_结果数据` VeryHidden→Hidden；② 两处 `catch{}` 静默吞错→`Console.Error` 显形；③ 锚杆补「判定依据」演算稿 sheet（公式+GB条款，拉齐防火已有 footer）。
- **去重(#5)**：`AnchorColumns`/`CoatingColumns` 各抄的 NormalizeHeader 公共核心抽到 `Calc/HeaderNormalizer.Core`（二者不全等——防火多剥单位括注，保行为组合不盲并）。

**卡点 / 交接**

- **#6「每个模块都是大框架」（通用 pipeline 抽象 = `docs/plans/2026-06-02-detection-pipeline-abstraction.md`）**：负责人已显式推翻 6-02「暂缓」决定、要做。
  - **Phase 0（去重地基）本会话已完成**：`Calc/HeaderNormalizer.Core`（NormalizeHeader 公共核心）+ `Handlers/HandlerUtil.ParseStringMap`（user_inputs 解析公共核心）（+ 上会话 SafeSheetName→`Calc/SheetNameUtil`）。剩 `RequireColumn` 近似×2 未并（低价值，待并需先 diff）。
  - **Phase 2（`DetectionDescriptor` + 通用 handler 脚手架 + 显式 `DetectionCatalog`，按文档 §4/§6 迁移顺序 Leeb→Coating→Anchor）待做**——大重构，文档要求**每步 `dotnet test` 绿**当安全网；但本会话末 **MCP/CI 断连 + 本环境装不了 dotnet → 无法验证**，故未盲推（不在不可验证的 base 上堆大重构留烂尾）。下个能跑 dotnet/CI 的会话按文档落地，先拿 Leeb 试水。
- **#4 企业级前端 / #7 深度解耦**：剩余多为前端改动，本环境装不了依赖无法本地验，建议能 `npm ci` 的环境续做。
- 输入 reader 的 `continue` 多为结构性跳行（空行/汇总行/辅助 sheet），非静默吞错，按手术刀未动。

---

## 当前焦点（2026-06-03）— 整治"割裂"（分支 `claude/laughing-keller-uuZ7S`，PR #21 draft）

> 一次 Claude Code on the web 会话的产出。代码 + 方案都在该分支/PR。本 web 环境网络白名单装不了 dotnet，C# 的下一步需在能跑 `dotnet test` 的机器上接着做。

**已做（已 push 到分支）**

- 删 3 个零引用 Python 死代码模块（`data_cache` / `steel_presets` + 其测试；本地 pytest 226 绿）。
- C# 合并 4 份逐字相同的 `SafeSheetName` → `Calc/SheetNameUtil.cs`（本机无 dotnet，靠 CI 验）。
- 纠正 codicons 误报：`.ai/RULES.md` 图标清单标注"非穷举、以 @vscode/codicons 包为准"。
- 两份方案：`docs/plans/2026-06-02-整治割裂-大白话路线.md`（总路线 + 决策）、`docs/plans/2026-06-02-detection-pipeline-abstraction.md`（后端统一骨架，**已暂缓**）。

**负责人拍板三条（详见大白话路线第六节）**

1. **出报告不重算**：各类型出报告都读"数据处理"已算好的结果。锚杆已是（`AnchorResultReader`），**防火在重算**（缺 `CoatingResultReader`）→ 要补。
2. **录入向防火看齐**：信息全在数据表里；锚杆去掉多余 UI 参数表单（参数进"批次信息"sheet）。
3. **短期不加新检测类型** → 暂缓通用 pipeline 大抽象（不为"以后可能用"过度设计）。

**下一步（需 dotnet 环境）**：给防火补 `CoatingResultReader`，让 `report.assemble` / `coating.report` 出报告读结果、不重算，配往返测试（read==compute）。后续：报告类型改多选、检测项目下拉补齐、锚杆录入向防火收敛。

---

## 当前焦点（2026-05-31）

**防火涂层补齐「薄型/超薄型（膨胀型）」判定（GB 50205-2020 §13.4.3 膨胀型）** —— 之前只厚型出
判定、薄/超薄一律「待判定」，本轮接入膨胀型判定 + 国标 5 处×3 点布点。分支 `feat/coating-thin-ultrathin`
（基于 main，4 commit + 1 个顺手修 logo lint blocker），**未 push**。C# 255 测试绿、前端 tsc/lint/fmt 绿、MCP 7 测+typecheck 绿。

- **判定（用户拍板，各规范各算法）**：厚型 GB 50205「80% 测点 + 最薄×0.85」**原样不动**；膨胀型（薄/超薄）
  **构件均值 ≥ 设计×0.95（偏差−5%）且 ≥ 设计−0.2mm（−200µm 兜底，取较严 max）**。地标国标都按 −5%。
- **布点（标准×涂层类型）**：国标 + 薄/超薄 → **5 处×3 点**（参照 GB/T 50621 §12 防腐，sheet「测点数据-<类型>-膨胀型」，
  列 点1/点2/点3，截面号=处号 1~5，固定 5 处）；国标厚型 / 地标任意 → 截面×面（现状）。同类型混涂层类型拆两张 sheet。
- **范围**：只做梁/柱（桁架/网架/檩条/顶板少见，本轮不做）。`待判定` 链路保留置 0（梁柱已全判）。
- **宽表**：统一一套列服务厚/膨胀；加「本段均值（每行）/判定下限」列，「平均值」改名「构件均值」；合格率膨胀型「—」；
  footer 按出现的涂层类型分别标判定依据。精度沿用 `ThicknessDecimals`（厚2位/薄超薄3位 mm）。
- **未做**：Layer 5（报告填充/Word）仍缺防火涂层 Word 模板，待后续。

