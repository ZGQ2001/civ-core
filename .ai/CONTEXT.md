# 工作上下文

> **角色**：当前焦点、UX 缺口、用户偏好。**每会话更新**，时效性强。
> **维护**：AI 每次会话结束时更新。里程碑级变动记 PROGRESS.md，这里不重复。
> **配套**：`CLAUDE.md`（宪法）| `RULES.md`（规范）| `PROGRESS.md`（里程碑）

---

## 当前焦点（2026-05-27）

**批次维度模板（灌浆日期按批次）上线** —— 装配线「报告填充」工序从「报告级单值」升级到「报告级 + 批次级」两层。模型重塑：报告级（仪器/人员/检测时间/参建单位/委托方等 31 字段，扁平 `ReportUserInputs`）+ 批次级（目前唯一字段 `grouting_date`，`Record<batchId, string>`）。

- **前端**：`types.ts` 抽出 `ReportBatchUserInputs` + 白名单 `BATCH_DIM_KEYS = ['grouting_date']`；`controller.tsx` state 拆两半 + batchIds effect 同步 + setter（单批 / 广播）+ RPC 入参增 `batch_user_inputs`；`SettingsForm.tsx` 新增 `GroutingDateByBatchSection`，状态机对齐 `AnchorParamsSection`（excelReady/loading/error/空批次/有批次），UI 含「全部批次填同一日期」广播框 + N 行 date input。
- **后端 C#**：`AnchorHandlers.Run` 自动 detect 模板里有没有 `[[批次]]` 字符串 → 分发 `ReportGenerator.Generate`（旧模板单批，含 grouting_date fallback：从第一批 batch_user_inputs 注入项目级，旧模板里的 `{{灌浆日期}}` 仍可用）或 `GenerateMultiBatch`（新模板多批，每批 `BatchResolver` 注入本批 grouting_date + batch_id + 项目级）。`ReportGenerator.GenerateMultiBatch` 早就实现，本次只 wire。
- **测试**：AnchorHandlersTests +2（多批不同灌浆日期端到端 + 旧模板 fallback），全套 182/183（1 skip 是真实数据测试）。

**前一焦点（2026-05-27）**：T5.7 Python sidecar 收口——workspace/files/pdf_tools/word2pdf 4 个域全切 C#，Python sidecar 只剩 plot_curves（matplotlib 无可替代）。

## 前一焦点（2026-05-26）

（说明：今天先做完 T5.7 Python 收口，又做完批次维度模板。两次焦点参见上方两段。）

**装配线第 5 个工序「报告填充」上线** —— 锚杆抗拔走通 数据处理 → (可选)绘曲线图 → 报告填充 完整链路。

- **占位符引擎 v2**：`{{key}}` 语法（不再 `{}`）；按 catalog `DefaultFormat` 真正格式化数字；新增 `{{img:xxx}}` 图片占位符（OpenXML Drawing 嵌入，按 anchor_id 自动匹配 PNG）。错误信息全部可操作（缺锚点提示放哪段、缺图列 missingImages 详单）。
- **ReportGenerator 成对 marker**：`[[每根锚杆]]...[[/每根锚杆]]` 之间所有元素一起克隆（不再单 marker + 后接 1 表）。模板视觉零变化，用户改起来只加 2 段 marker + 1 个 `{{锚杆序号}}`。
- **catalog 49 字段 + 别名网**：覆盖锚杆模板里全部占位符（{{委托单位}} {{0.1Nt位移}} {{杆体弹模}} {{允许值上限}} 等都自动命中）。`axial_design_load_kn` 派生字段让模板写 kN（计算仍用 N）。
- **报告填充工具**：独立 controller（不耦合 data_processing），own 全套输入/参数/Word state；顶部「一键导入数据处理」可选。SettingsForm 按 7 组折叠卡片收 ~32 个 user_input；Page 显示输入摘要 + 缺图警告 + 字段对照表 + 模板格式 cheat sheet。
- **共享 anchor 参数 UI**：`tools/_shared/anchorParamsForm.tsx` 抽出，data_processing / report_generator 两个工具复用按批次参数表（一份维护点）。
- **删 template_editor**：原模板编辑工具完全删除（功能整合进报告填充的字段对照表 collapsible）。
- **FileTree 删除二次确认升级**：VSCode 同款 modal —— 标题 + 完整路径 + 文件夹时警示 + 主按钮「移到回收站」+ Backdrop 不可关 + Enter/Esc 快捷键。

**Python 剩余职责**：plot_curves（matplotlib 无可替代）+ seeds standards.db。其他全切 C#。

---

## 下一步候选（按价值排，agent-first）

> **方向定调（2026-05-27）**：系统主要操作者是 AI agent，不是人。GUI 退到「人 review agent 输出」位置。所有新功能优先评估 agent 体验，GUI 按钮做兜底。

1. **MCP server：把 sidecar RPC 暴露成 MCP tools** —— agent 原生入口。30+ RPC（`anchor.*` / `doc.*` / `pdf_tools.*` / `word2pdf.*` / `xlsx.*` / `workspace.*` / `files.*` / `plot_curves.*`）包成 MCP tools，含 `inputSchema` JSON 描述；进度通知走 JSON-RPC notification → MCP progress；错误对齐「问题在哪 + 怎么修」原则。复用全部现有 sidecar 业务逻辑，只加协议层。预计 2-3 天。
2. **钻芯/回弹切 C#** —— agent 调用 `data_processing.run` 时除 anchor 外还要能跑 leeb / 钻芯 / 回弹；data_processing calcType 下拉再加项。
3. **多检测内容混排**（启用第 3 层「检测项目级」）—— 一份报告含锚杆 + 钻芯 + 回弹等多个 section；catalog 已有 `detection_item` level 概念，等钻芯/回弹切 C# 后再 wire。agent 出综合报告时刚需。
4. **真正"一键流水线" GUI 按钮**（数据处理 → 绘曲线图 → 报告填充 串起来）—— 给「人 review 长 agent 任务」用的便利路径，次优先级（agent 可直接调 MCP 串起来，不需要 GUI 按钮）。
5. **LaTeX 报告路线**（`templates/latex/template.tex` 已贴入，未定方向：替代 docx？只生成 data_table fragment？给 ReportGenerator 加 latex 后端？）
6. **T6 打包** —— PyInstaller + dotnet publish + Tauri externalBin（MCP server 独立打包还是合入 sidecar 待定）
7. **App.tsx 拆 useShellState hook** —— 当前 470+ 行嵌套 5 个 Provider

---

## 用户偏好

| 偏好 | 来源日期 |
|------|---------|
| 不要 JSON 编辑器——用 form | 2026-05-21 |
| 中间预览区 + 右侧参数区，统一交互范式 | 2026-05-21 |
| 全局禁 emoji（UI/commit/AI 文档） | 2026-05-21 |
| 大需求分多次 commit，每次独立验收 | 2026-05-21 |
| 以后代码都用 C#（Python 已交付的不动） | 2026-05-22 |
| 文档对 AI 友好、易于维护、不需要用户写专业内容 | 2026-05-22 |
| UI 任何操作必须可观察，禁黑盒——每个 onClick 入口先 appendOutput 一行 | 2026-05-22 |
| 字段命名要让非编程用户看得懂——中文名 + 变量符号 + 单位 + 一句话 hint 同行展示 | 2026-05-22 |
| 工具间不要过度耦合 —— 装配线连贯但每个工序能独立工作（提供"一键导入"代替隐式继承） | 2026-05-26 |
| 程序不能是黑盒 —— 错误信息告诉用户"问题在哪 + 怎么修"，不只是抛异常 | 2026-05-26 |
| 业务判断不让 AI 替用户拍板（如字段维度划分）—— 留 TODO 让用户后续 PR 决定 | 2026-05-26 |
| 系统主要操作者是 AI agent，不是人 —— 新功能先评估 agent 体验，GUI 做兜底 | 2026-05-27 |

---

## UX 缺口

- ~~底部 Panel 关闭后无 toggle~~ → StatusBar「面板」按钮 + Ctrl+J
- ~~plot_curves 调曲线只能编辑 JSON~~ → RightPanel form + 实时预览
- ~~预设无法新建/重命名/删除~~ → CRUD 全套
- ~~leeb/pdf/word2pdf 工具页没用范式~~ → 已迁
- ~~3 个工具 handleRun 陈旧闭包~~ → 已修（395f05e）
- ~~data_processing calcType 下拉只 1 项~~ → 已加锚杆抗拔（2 项）；等加钻芯/回弹
- ~~锚杆参数表横排 + 裸字母 P/Lf/La/A/E~~ → 已改纵向卡片
- ~~RightPanel 内操作无日志反馈~~ → ShellContext + 入口 appendOutput
- ~~点击「生成模板」无反应~~ → 加 dialog:allow-save capability
- ~~文件树双击只 openPath~~ → 双击 xlsx/pdf/docx 自动灌给对应工具
- ~~报告填充强耦合数据处理~~ → 解耦完全独立 + 可选一键导入
- ~~Word 报告占位符 {} 跟用户模板 {{}} 不匹配~~ → 占位符引擎升级 {{}}
- ~~弹性位移量/上下限输出裸 double~~ → catalog DefaultFormat 真正生效，2 位小数
- ~~{{曲线图}} 没法嵌图~~ → {{img:曲线图}} 引擎 + plot_curves 输出按 anchor_id 命名串接
- ~~FileTree 删除确认朴素~~ → VSCode 同款 modal 升级
- `data_processing` OpenXML 切 C# 后合并单元格已解决；前端不变
- word2pdf pages 字段只在 Word 保存过的 docx 有——显示「N 段」即可
- 流式进度未做——协议升级方案：JSON-RPC notification → Tauri event
- `App.tsx` 比较胖（470+ 行）+ 嵌套 5 个 Provider——可考虑 `useShellState` hook
- 「新建标准结构」用 `window.prompt`——后续换自定义 modal+toast
- plot_curves 数据对照表格 cell 暂不能跳到曲线上对应点
- 报告填充与绘曲线图无显式串接——用户得手动配置 plot_curves "标识列=锚杆编号" + 记住输出目录粘贴到报告填充。未来可加"自动按 anchor_id 出图"快捷路径
- ~~批次共享字段（grouting_date 等）目前只支持项目级 user_input；多批不同值时需手动拆批输入~~ → 灌浆日期已升级为按批次维度（前端 `groutingDateByBatch` + 后端 `[[批次]]` marker dispatch）。其他批次级字段（如有需要）按相同范式扩展

---

## 会话历史

### [2026-05-27] 批次维度模板上线：灌浆日期按批次填 + 模板助手指引

2 个 commit，6 个文件，+503/−30 行。**层级模型重塑**：「报告级 + 批次级」两层（多检测内容混排留待钻芯/回弹切 C# 后再补「检测项目级」第三层）。

- **Commit `57cf1fb` (pdf_tools UX 微调)**：拆分模式选了源 PDF 后输出目录自动 derive 同目录（不覆盖用户已选）；调参面板 `p-4/space-y-4` → `p-3/space-y-3` 与 plot_curves 对齐；"文件名说明框"去 border/bg 防误读成输入框。
- **Commit `380540c` (批次维度模板)**：
  - 模型重塑前用户先纠了我一轮——「仪器证书是报告级的、人员也是、检测时间也是」（我之前误划为批次级），最终批次级只剩 `grouting_date` 一个字段。
  - 前端 types.ts 抽 `ReportBatchUserInputs` + 白名单 `BATCH_DIM_KEYS`；controller.tsx state 拆两半 + batchIds 同步 effect + 广播 setter；SettingsForm.tsx 新增 `GroutingDateByBatchSection`（复用 `AnchorParamsSection` 状态机：excelReady/loading/error/空批次/有批次），含「全部批次填同一日期」广播框 + N 行 date input + 黄条提示 `[[批次]]` 段必要性。
  - 后端 AnchorHandlers.Run 模板 detect 分发：`TemplateHasBatchMarker` 扫 `[[批次]]` → 选 `GenerateMultiBatch`（每批 BatchResolver 注入本批 grouting_date + batch_id + 项目级）/ `Generate`（旧模板兼容 fallback：从第一批 batch_user_inputs 注入项目级 grouting_date，旧模板里 `{{灌浆日期}}` 仍可用）。
  - 模板教学路径：Word 模板 picker hint 指向 ActivityBar「模板助手」；catalog 早就把 `grouting_date` 标为 `batch` 级（[CatalogStore.cs:130](dotnet/civ-doc/Catalog/CatalogStore.cs:130)）+ `template.validate` 已有 marker scope 嵌套感知 + level mismatch hint，本次只补**指引**让用户走过去。
  - 测试 AnchorHandlersTests +2（多批不同日期端到端 + 旧模板 fallback）；全套 182/183 通过。

### [2026-05-27] T5.7 Python sidecar 收口：4 个域全迁 C#

4 个 commit 把 Python sidecar 残留 RPC 全迁 C#，符合"路由默认 C#"方向。Python sidecar 最终只承载 plot_curves（matplotlib 无可替代）。

- **Commit 1 `3c21a1e` (workspace)**：4 RPC（last/set/clear/create_standard）；HomeDir 走 USERPROFILE env var 与 Python expanduser 对齐方便测试；8 xUnit。顺手修 pre-existing `TemplateHandlers.Fields_未知project_type` 用例失败：错误信息加可选目录提示（符合"程序不能是黑盒"）。
- **Commit 2 `c354f30` (files)**：10 RPC（list_dir/exists/create_file/folder/rename/copy/move/reveal/delete/undo_delete）；delete 走 Microsoft.VisualBasic.FileSystem 发回收站，undo_delete 用 Shell.Application COM dynamic 调 "undelete" verb；自然排序对齐 Python；26 xUnit（含实测回收站往返）。
- **Commit 3 `50b4684` (pdf_tools)**：4 RPC（merge/split_per_page/split_by_ranges/inspect）；PDFsharp 6.2 原子写；范围表达式 "1-3,5,7-9" 解析对齐 Python；20 xUnit；卸 pypdf Python 依赖。
- **Commit 4 `0cefda1` (word2pdf)**：2 RPC（convert/inspect）；convert 用 dynamic 调 Word.Application + 回退 KWPS（Windows 限定，对齐 Python pywin32 DispatchEx 语义）；inspect 跨平台走 OpenXML + ZipArchive 读 docProps/app.xml<Pages>；macOS/Linux 抛 PlatformNotSupported + 注释指引未来怎么补 Mac AppleScript 路径；6 xUnit。

期间确立原则[[feedback-avoid-com]]："能不调 COM 就不调"——大多数场景有非 COM 替代（OpenXML / PDFsharp / .NET BCL）就用；word2pdf 找不到不损失排版精度的非 COM 方案才保留 COM。最终 C# 测试 181 / Python 残留 232 / Rust 路由 2 全过。

### [2026-05-26] 装配线第 5 工序「报告填充」上线 + 占位符引擎 v2 + 图片占位符

3 个 commit 完成「报告填充」从无到有 + 已知 bug 全修：

- **Commit 1**：占位符 `{}` → `{{}}`；catalog DefaultFormat 真生效（弹性位移量 2 位小数）；ReportGenerator 成对 marker `[[每根锚杆]]...[[/每根锚杆]]` 克隆段+表；catalog 加 25 个 user_input + 别名网；AnchorRowResolver 引擎注入 `anchor_index`；AnchorAnalysisSheet Round 3→2。+38 个 xUnit 用例。
- **Commit 2**：拆 template_editor 工具（删 4 件套）；新建 report_generator 工具（独立 controller + Page + SettingsForm 按 7 组折叠 32 字段）；数据处理页删 AnchorWordReportSection；FileTree 删除确认升级到 VSCode 同款；ActivityBar 入口换名。
- **Commit 3**：catalog 单位调整（`axial_design_load_kn` 派生字段 alias「轴向拉力设计值」，模板默认 kN 输出）；合并 test_engineer/test_date 到 inspection_*（保留旧别名）；解耦 report_generator 完全独立 own state，加「从数据处理一键导入」按钮（上游就绪态高亮）；抽 _shared/anchorParamsForm.tsx 两工具复用；图片占位符 `{{img:xxx}}` 引擎 + ImageInjector OpenXML Drawing 嵌入 + AnchorRowResolver 接 curveImageDir 按 anchor_id 拼路径 + 前端加曲线图目录 picker + missingImages 警告渲染。+5 个图片用例。

最终：dotnet test 108 通过 + 1 skip，frontend tsc 通过。

### [2026-05-23] pdf_tools / word2pdf 接 ShellContext.activatedFile

两个 controller 加 `useShell` + activatedFile useEffect。pdf_tools 按 mode 分支（merge 追加去重、split 覆盖），mode 用 modeRef 防陈旧闭包；word2pdf 追加到 inputs 去重。每个入口先 `appendOutput` 写日志。锚杆数据 sheet 验收通过，模板填充归到「报告生成」阶段，计算阶段不再做。

### [2026-05-22] 锚杆抗拔上线 + UX 可观察性补齐

锚杆抗拔（GB 50086-2015）4 commit：C# 计算底座（11 xUnit）→ Excel 读/模板生成/报告表写入（+9 xUnit）→ 3 个 RPC（+4 xUnit）→ 前端 calcType=anchor 子 form。

UX 修复 3 commit：参数表纵向卡片重做、ShellContext 全局可观察性、文件树双击联动、`dialog:allow-save` capability 修复（根因：Tauri 2 显式白名单，saveDialog 未授权被静默拒）。

用户后续重构 FileTree 为 VSCode 风扁平渲染（980 行：右键菜单 + in-place 编辑 + 剪贴板 + 删除回收站 + 焦点 refetch + diff），SideBar 拆 refreshNonce/collapseNonce 双触发，App 默认工具改 data_processing 排首位。后端 `files.py` 加 create_file/create_folder/rename/delete（回收站，send2trash）/copy/move/reveal 共 7 个 RPC，Windows 文件名校验。App 全局拦截 webview 网页式行为：原生 contextmenu / F5 / Ctrl+R / Ctrl+P / Ctrl+S / 文件拖入导航，保留 F12 开发者工具。

### [2026-05-22] AI 上下文文件重构

将 CLAUDE.md（10846 字）砍到宪法级（3788 字节），新增 `.ai/RULES.md`（编码规范+技术债+RPC清单）、`dotnet/CLAUDE.md`（C# 域规则）、`frontend/CLAUDE.md`（前端域规则）。PROGRESS.md 和 CONTEXT.md 重写，职责明确分离，无过期内容。

### [2026-05-20] UI 技术栈转型 + 旧代码大清理

删旧 Qt UI（30+ 源文件 + 20 个 UI 测试 + pyside6/qfluentwidgets/pytest-qt 三个依赖）。保留全部业务底座。

### [2026-05-19] 删项目看板 + INSP-001/002 计算底座交付

### [2026-05-14] 主管线定调：画图✅ → 计算✅ → 数据生成✅ → 报告填充✅ → Word 报告✅
