# 工作上下文

> **角色**：当前焦点、UX 缺口、用户偏好。**每会话更新**，时效性强。
> **维护**：AI 每次会话结束时更新。里程碑级变动记 PROGRESS.md，这里不重复。
> **配套**：`CLAUDE.md`（宪法）| `RULES.md`（规范）| `PROGRESS.md`（里程碑）

---

## 当前焦点（2026-05-29）

**MCP server Phase 2 收尾：剩余 25 个 sidecar RPC 全包成 MCP tools** —— 在 Phase 1 的
20 + report_preset 5 + anchor_read_batch_info 之外，补齐 catalog 4 / template.validate 1 /
files 10 / pdf_tools 4 / word2pdf 2 / plot_curves 预设 CRUD 4。MCP tool 总数 **52**，基本
与 sidecar RPC 全表对齐（仅剩「`leeb.preview_excel` 与 `plot_curves.list_sheets` 是否合并成
通用 `excel_preview`」待评估）。纯协议适配，零业务逻辑——每个 ToolDef 一份 zod schema 跟
C#/Python handler 入参一一对照；Windows-only / 破坏性的 files.delete/undo_delete/reveal 在
description 里显式标注（用户拍板「全 10 个都包」）。

- **冒烟扩展**：`scripts/smoke.mjs` 加 Phase 2 回归守卫（tools/list 必须含全部 25 新 tool）+
  `catalog_list`（C# 读路径）+ `files_list_dir`（C# 文件路径）+ plot_curves 预设
  `copy→list→delete` roundtrip（Python 写路径）。三跳全绿。
- **踩坑**：smoke 初版临时预设名取了 `__smoke_copy__`，被 `preset_manager` 校验拒（预设名
  不能以下划线开头）——这是校验在正常工作，不是 bug；改用合法中文名后 roundtrip 通过。

## 前一焦点（2026-05-28 晚）

**报告填充 + 模板助手 12 项 Bug 清单全清（P1→P4 一气推完）** —— 用户列了 12 条
bug + 3 条架构验收前提，按 P1 紧凑修复 → P2 共享/显性化 → P3 公共组件 →
P4 大型架构 顺序逐包 commit。

- **P1 [cf07e78]**：报告填充顶栏固定 + 生成按钮入顶栏；ReportGenerator 末步
  扫 mainPart.HeaderParts/FooterParts 让页眉/页脚也支持 `{{}}` 替换（之前
  validate 扫了 ReportGenerator 没填，语义不一致）；TemplateHandlers.
  CheckLevelMatch 删「外层字段写在内层 scope」的 warning（批次级写在
  [[每根锚杆]] 里就是想每根重复出现的预期行为）。
- **P2 [b2095f5]**：ShellContext 加 curveImageDir + setter；报告填充 / 模板
  助手共用一份占位图目录；模板助手顶部加 4 层级 chip 图例（hover 出说明 +
  marker 写法），LevelDot 升级为带文字 chip「[报告级] 委托单位」。
- **P3 [be2f027]**：抽 `tools/_shared/CatalogDrivenInputs.tsx`，删
  report_generator 硬编码 `USER_INPUT_GROUPS` 32 字段，启动调 catalog.get
  动态渲染——模板助手改字段，报告填充立刻同步。
- **P4-1 [a7f3920 + 0a06d8b]**：新增 `report.run_from_result` RPC。
  AnchorHandlers.Run 写结果 xlsx 时附 `_批次参数` 隐藏 sheet 持久化
  AnchorParams；AnchorResultReader 反序列化结果 xlsx → AnchorWorkbookResult；
  ReportHandlers.RunFromResult 复用 ReportGenerator 出 Word 不重算。
  前端 dataSource=raw/result 二分路径，一键从数据处理导入默认走 result +
  dp.outputPath（彻底解决用户 bug #2+#7）。
- **P4-2 [9e3ae4c]**：`report_preset.*` 5 个 RPC（list/get/save/delete/rename）
  - 前端 PresetBar UI（另存为对话框 / 载入下拉 / 删除）+ MCP 5 tool wrap。
    整份报告一套预设（用户拍板）；按 catalog_id 过滤；存
    `~/.civ-core/report_presets/<id>.json`。
- **P4-3 [d62f861]**：报告名称可改（reportName state，影响输出 .docx 文件名，
  自动补 .docx 扩展）+ 数据来源 radio（raw / result）+ 一键导入默认走 result。
- **P4-4 [937d31d]**：检测项目下拉接 catalog.list 动态填，用户可切换
  catalog_id；当前只 anchor 真正接 calc，其他 catalog 只影响 UI 字段渲染。
- **P4-5 [937d31d]**：每个字段右侧「历史值下拉」(默认关，主开关 checkbox
  控启停)，开启后并发拉同 catalog 所有 preset 聚合非空值，按 key 去重排序。
  关闭立刻清空，避免误覆盖用户当前输入。
- 模板助手 #3 误报降级（同 P1）。

**前一焦点（2026-05-28 早）**：MCP server Phase 1 上线 —— 把 civ-core 双 sidecar 的 20 个 RPC 包成标准 MCP tools，给 Claude Code / Codex / Cursor 等 agent 原生入口（2026-05-27 路线定调「主要操作者是 AI agent」的关键基础设施）。

- **架构**：新顶级目录 `mcp/`（与 `dotnet/` `frontend/` 平级），Node + TS + `@modelcontextprotocol/sdk` 1.29，独立第 3 进程；启动时 spawn C# + Python 两个 sidecar 子进程（同 `sidecar.rs` 口径），把 MCP tool call 转发成 JSON-RPC 行协议。Tauri / 前端零改动。
- **20 tools = 2 doc + 4 workspace + 3 anchor + 2 leeb + 1 xlsx + 1 template + 1 report + 6 plot_curves**。装配线 + 通用模板渲染 + 出图全路径打通。每 tool 一份 zod inputSchema，按 .describe() 写清单位 / 用法 / 触发条件。
- **错误映射两层**：业务级 `SidecarRpcError` → MCP `isError: true` + 原 message 保留（「问题在哪 + 怎么修」）；进程级 `SidecarFatalError` → 抛出去关 transport。
- **冒烟**：scripts/smoke.mjs 用 MCP Client SDK 跑端到端三跳——agent → MCP server → sidecar 全通；doc_ping 返 "pong"，plot_curves_list_presets 拿到 1 个用户预设。
- **5 commit 落地**：脚手架 / sidecar 客户端+路由+7 单测 / MCP transport+doc tools / workspace+anchor 7 tools / 装配线+plot_curves 13 tools + registry callback 签名 bug 修。
- **接入 Claude Code**：`mcp/CLAUDE.md` 写了 mcp_servers.json 配置范例，env `CIV_CORE_REPO_ROOT` 指仓库根。

**前一焦点（2026-05-27）**：批次维度模板（灌浆日期按批次）—— 装配线「报告填充」工序从「报告级单值」升级到「报告级 + 批次级」两层。模型重塑：报告级（31 字段，已在 P3 改为 catalog 驱动）+ 批次级（目前唯一字段 `grouting_date`，`Record<batchId, string>`）。

## 前一焦点（2026-05-27）

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

1. **钻芯/回弹切 C#** —— agent 调用 `anchor_run` 已通，下一种检测类型自然顺延；data_processing calcType 下拉再加项。MCP server 已就位，新 calc 只要在 C# 加 handler，`mcp/src/tools/` 加一份 ToolDef 即可。
2. **多检测内容混排**（启用第 3 层「检测项目级」）—— 一份报告含锚杆 + 钻芯 + 回弹等多个 section；catalog 已有 `detection_item` level 概念，等钻芯/回弹切 C# 后再 wire。agent 出综合报告时刚需。
3. ~~**MCP server Phase 2**~~ —— ✅ 已完成（2026-05-29）：catalog 4 / template.validate / files 10 / pdf_tools 4 / word2pdf 2 / plot_curves 预设 CRUD 4 全包，MCP 52 tool 与 sidecar RPC 全表对齐。agent 现在能做完整「文件管家」工作（不只是装配线）。
4. **MCP server 进度通知** —— anchor.run / plot_curves.run 长任务，sidecar stderr 日志透传 → MCP `notifications/message`，让 agent 看到进度。当前只返终态。
5. **真正"一键流水线" GUI 按钮**（数据处理 → 绘曲线图 → 报告填充 串起来）—— 给「人 review 长 agent 任务」用的便利路径，次优先级（agent 可直接调 MCP 串起来，不需要 GUI 按钮）。
6. **LaTeX 报告路线**（`templates/latex/template.tex` 已贴入，未定方向：替代 docx？只生成 data_table fragment？给 ReportGenerator 加 latex 后端？）
7. **T6 打包** —— PyInstaller + dotnet publish + Tauri externalBin + mcp Node bundle（4 个产物一起出）
8. **App.tsx 拆 useShellState hook** —— 当前 470+ 行嵌套 5 个 Provider

---

## 用户偏好

| 偏好                                                                               | 来源日期   |
| ---------------------------------------------------------------------------------- | ---------- |
| 不要 JSON 编辑器——用 form                                                          | 2026-05-21 |
| 中间预览区 + 右侧参数区，统一交互范式                                              | 2026-05-21 |
| 全局禁 emoji（UI/commit/AI 文档）                                                  | 2026-05-21 |
| 大需求分多次 commit，每次独立验收                                                  | 2026-05-21 |
| 以后代码都用 C#（Python 已交付的不动）                                             | 2026-05-22 |
| 文档对 AI 友好、易于维护、不需要用户写专业内容                                     | 2026-05-22 |
| UI 任何操作必须可观察，禁黑盒——每个 onClick 入口先 appendOutput 一行               | 2026-05-22 |
| 字段命名要让非编程用户看得懂——中文名 + 变量符号 + 单位 + 一句话 hint 同行展示      | 2026-05-22 |
| 工具间不要过度耦合 —— 装配线连贯但每个工序能独立工作（提供"一键导入"代替隐式继承） | 2026-05-26 |
| 程序不能是黑盒 —— 错误信息告诉用户"问题在哪 + 怎么修"，不只是抛异常                | 2026-05-26 |
| 业务判断不让 AI 替用户拍板（如字段维度划分）—— 留 TODO 让用户后续 PR 决定          | 2026-05-26 |
| 系统主要操作者是 AI agent，不是人 —— 新功能先评估 agent 体验，GUI 做兜底           | 2026-05-27 |

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
- ~~报告填充顶栏跟随内容滚动 / 生成按钮埋在中间~~ → P1 顶栏固定 + 生成按钮 + 就绪态徽章一并入顶栏（cf07e78）
- ~~报告填充页眉里写 {{委托单位}} 验证通过但出 Word 时留原文~~ → ReportGenerator 末步扫 HeaderParts/FooterParts（cf07e78）
- ~~模板助手批次级字段写在 [[每根锚杆]] 内被误报「重复填充」~~ → CheckLevelMatch 删该 warning 分支（cf07e78）
- ~~报告填充和模板助手用不同的占位图目录变量~~ → ShellContext 加 curveImageDir 跨工具共享（b2095f5）
- ~~模板助手 4 层级只有彩色圆点 / 用户看不懂~~ → 顶部加 4 chip 图例 + LevelDot 升级为带文字 chip（b2095f5）
- ~~报告填充 USER_INPUT_GROUPS 硬编码 32 字段、跟 catalog 漂移~~ → 抽 `_shared/CatalogDrivenInputs` 公共组件（be2f027）
- ~~报告填充会重复跑计算 + 重写结果 xlsx~~ → 新 RPC `report.run_from_result` 读结果 xlsx 出 Word，前端 dataSource=result 走它（0a06d8b）
- ~~无填充记录保存 / 复用功能~~ → `report_preset.*` 5 RPC + 前端 PresetBar UI（9e3ae4c）
- ~~报告文件名硬编码「锚杆抗拔报告.docx」~~ → reportName state + UI 输入框 + 后端按 report_name 取（d62f861）
- ~~检测项目无法切换~~ → catalogId state + 顶部下拉接 catalog.list（937d31d）
- ~~用户希望字段输入框旁有可开关的历史值下拉~~ → CatalogDrivenInputs.historyByKey + SettingsForm 主开关聚合（937d31d）
- ~~result 路径灌浆日期丢失（`_批次参数` 隐藏 sheet 只存工程参数无日期，走「结果数据」来源时日期仍靠 GUI/预设）~~ → `AnchorResultMetadataSheet` 加第 7 列「灌浆日期」；`anchor.run` 持久化各批 grouting_date；`AnchorResultReader.Read` 加 out 旁路；`report.run_from_result` 按 GUI/预设优先、结果 xlsx 兜底合并（与 anchor.run 的「批次信息」回退同口径）。result xlsx 现自带日期，旧文件无第 7 列向后兼容

---

## 会话历史

### [2026-05-29] MCP server Phase 2：补齐 25 tool，52 tool 与 RPC 全表对齐

Phase 1 留的「文件管家 + 配置 + 预设 CRUD」缺口一次补完。纯 ToolDef 声明，无业务逻辑。

- **新增 25 tool**：catalog 4（list/get/save/delete）+ template.validate 1 + files 10
  （含 Windows-only 的 delete/undo_delete/reveal，用户拍板全包）+ pdf_tools 4 + word2pdf 2 +
  plot_curves 预设 CRUD 4（save/delete/rename/copy）。新建 `catalog.ts` / `files.ts` /
  `pdfTools.ts` / `word2pdf.ts`，扩 `template.ts` / `plot_curves.ts`。
- **index.ts**：`phase1Tools` → `allTools`，注册全部 13 个域；修了「25 tools = 20 + 5」的
  陈旧注释（实际 anchor 早已 4 tool）。
- **每个 schema 跟 handler 入参对照**：照 `mcp/CLAUDE.md` SOP，逐字段读 C#/Python handler 的
  `RequireString`/`params.get` 确认 key 名（catalog.save 的 `FieldCatalogDto`、files 的
  `parent`/`name`/`src`/`dst_parent`、pdf 的 `inputs`/`expr`、plot_curves CRUD 的
  `source_name`/`new_name` 等），不靠猜。
- **冒烟**：scripts/smoke.mjs 加回归守卫 + 三条新探针（catalog_list / files_list_dir /
  plot_curves 预设 roundtrip），端到端 52 tool 全绿。
- **2 commit**：feat（tool 代码 + index 注册 + 冒烟）/ docs（RULES 工具表 + mcp CLAUDE 目录树 +
  CONTEXT + PROGRESS）。

### [2026-05-28] MCP server Phase 1 上线：20 tools agent 原生入口

5 个 commit 把 civ-core 双 sidecar 30+ RPC 中的 20 个包成 MCP tools。架构定调（用户拍板）：TS/Node + 独立第 3 进程转发 RPC（不走 C# 进程内嵌）+ Phase 分两步（先装配线后文件操作）。

- **Commit 1 `279e50f` (脚手架)**：`mcp/` 顶级目录，package.json + tsconfig（NodeNext strict noUncheckedIndexedAccess）+ 空 index.ts；@modelcontextprotocol/sdk 1.29 + zod 3.25 装上；npm install + tsc build 跑通。
- **Commit 2 `a1011d4` (客户端+路由)**：`sidecar.ts` Node 版 `JsonRpcSidecar`（对照 `sidecar.rs`）+ `router.ts` 同前缀策略 + 7 单测（fixture 用 node 跑 echo JSON-RPC 子进程，不依赖真 sidecar）。SidecarRpcError / SidecarFatalError 两类清晰分。`parameter properties` 防 TS2565（async IIFE 引用 this.name）。
- **Commit 3 `d2e5a38` (MCP transport)**：`StdioServerTransport` 接上；`lib/repoRoot.ts` 环境变量 / sentinel 推断双路径；`tools/registry.ts` ToolDef + registerSidecarTool 错误映射；`tools/doc.ts` doc_ping / doc_version 探活。冒烟实测 doc_ping 返 "pong"。
- **Commit 4 `b2002ba` (workspace+anchor)**：4 workspace + 3 anchor = 7 tools。anchor_run schema 嵌套 record + 每字段 .describe() 写清单位（N/mm/mm²/MPa）+ marker / curve_image_dir 命名约定的描述。
- **Commit 5 `3ce8d6d` (装配线 + plot_curves + bug fix)**：补 leeb 2 + xlsx 1 + template 1 + report 1 + plot_curves 6 = 13 tools，Phase 1 共 20。**修 registry 签名 bug**：SDK 对无 inputSchema 的工具 callback 签名是 `(extra) => result`（不是 `(args) => ...`），之前误把 `extra`（含 AbortSignal）当 args 转发到 sidecar——Python 端 `list_presets()` 严格 kwargs 校验立刻爆。修法：按 def.inputSchema 有无分支注册。冒烟双 sidecar 全过。
- **Commit 6 `<本提交>` (文档同步)**：CLAUDE.md 架构图加 MCP 节点 + 不可变规则 #6 加 MCP tool 命名 / 会话自检加「新 RPC 同步加 MCP tool」；RULES.md 加 mcp 目录 + 补 RPC 全表缺漏 catalog.\* / template.validate / list_headers + 加 MCP tools 表 + 测试命令补 mcp + 全链表格补一行；新建 `mcp/CLAUDE.md` 域规则（项目定位 / 加 tool SOP / 编码约定 / 启动调试 / 接 Claude Code 配置范例）；CONTEXT.md 更新当前焦点 + 下一步候选；PROGRESS.md 加里程碑 T8。

期间确立两条约定：① **MCP tool 名禁含 `.`**（MCP 规范 `[a-zA-Z0-9_-]+`，约定 RPC `foo.bar` → tool `foo_bar`）；② **stdout 是 MCP 协议流**（跟 sidecar 同口径，stderr 才是日志）。最终 mcp typecheck + 7 单测全过；agent → MCP server → C# sidecar + Python sidecar 双链路冒烟全通。

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

- **Commit 1 `3c21a1e` (workspace)**：4 RPC（last/set/clear/create*standard）；HomeDir 走 USERPROFILE env var 与 Python expanduser 对齐方便测试；8 xUnit。顺手修 pre-existing `TemplateHandlers.Fields*未知project_type` 用例失败：错误信息加可选目录提示（符合"程序不能是黑盒"）。
- **Commit 2 `c354f30` (files)**：10 RPC（list_dir/exists/create_file/folder/rename/copy/move/reveal/delete/undo_delete）；delete 走 Microsoft.VisualBasic.FileSystem 发回收站，undo_delete 用 Shell.Application COM dynamic 调 "undelete" verb；自然排序对齐 Python；26 xUnit（含实测回收站往返）。
- **Commit 3 `50b4684` (pdf_tools)**：4 RPC（merge/split_per_page/split_by_ranges/inspect）；PDFsharp 6.2 原子写；范围表达式 "1-3,5,7-9" 解析对齐 Python；20 xUnit；卸 pypdf Python 依赖。
- **Commit 4 `0cefda1` (word2pdf)**：2 RPC（convert/inspect）；convert 用 dynamic 调 Word.Application + 回退 KWPS（Windows 限定，对齐 Python pywin32 DispatchEx 语义）；inspect 跨平台走 OpenXML + ZipArchive 读 docProps/app.xml<Pages>；macOS/Linux 抛 PlatformNotSupported + 注释指引未来怎么补 Mac AppleScript 路径；6 xUnit。

期间确立原则[[feedback-avoid-com]]："能不调 COM 就不调"——大多数场景有非 COM 替代（OpenXML / PDFsharp / .NET BCL）就用；word2pdf 找不到不损失排版精度的非 COM 方案才保留 COM。最终 C# 测试 181 / Python 残留 232 / Rust 路由 2 全过。

### [2026-05-26] 装配线第 5 工序「报告填充」上线 + 占位符引擎 v2 + 图片占位符

3 个 commit 完成「报告填充」从无到有 + 已知 bug 全修：

- **Commit 1**：占位符 `{}` → `{{}}`；catalog DefaultFormat 真生效（弹性位移量 2 位小数）；ReportGenerator 成对 marker `[[每根锚杆]]...[[/每根锚杆]]` 克隆段+表；catalog 加 25 个 user_input + 别名网；AnchorRowResolver 引擎注入 `anchor_index`；AnchorAnalysisSheet Round 3→2。+38 个 xUnit 用例。
- **Commit 2**：拆 template_editor 工具（删 4 件套）；新建 report_generator 工具（独立 controller + Page + SettingsForm 按 7 组折叠 32 字段）；数据处理页删 AnchorWordReportSection；FileTree 删除确认升级到 VSCode 同款；ActivityBar 入口换名。
- **Commit 3**：catalog 单位调整（`axial_design_load_kn` 派生字段 alias「轴向拉力设计值」，模板默认 kN 输出）；合并 test*engineer/test_date 到 inspection*\*（保留旧别名）；解耦 report_generator 完全独立 own state，加「从数据处理一键导入」按钮（上游就绪态高亮）；抽 \_shared/anchorParamsForm.tsx 两工具复用；图片占位符 `{{img:xxx}}` 引擎 + ImageInjector OpenXML Drawing 嵌入 + AnchorRowResolver 接 curveImageDir 按 anchor_id 拼路径 + 前端加曲线图目录 picker + missingImages 警告渲染。+5 个图片用例。

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
