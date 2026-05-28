# 开发日志

> **角色**：里程碑记录和已交付清单。粗粒度、历史视角。AI 在里程碑完成时更新。
> **配套**：`CLAUDE.md`（宪法）| `RULES.md`（规范）| `CONTEXT.md`（当前焦点）

---

## 里程碑

```
T1 ✅ Python JSON-RPC server (stdin/stdout)
T2 ✅ 前端骨架 (Vite + React + TS + Tailwind v4 + codicons)
T3 ✅ Tauri 主进程 + Python sidecar 桥 + VSCode 风顶栏
T4 ✅ 工作区 + 文件树端到端
T5 ✅ 4 个工具页全部 controller/Page/SettingsForm 范式
T5.5 ✅ C# sidecar + leeb 整套迁 C#（路由默认 C#）
T5.6 ✅ 装配线 anchor 走通（数据处理 → 绘曲线图 → 报告填充 出 docx + 嵌图）
T5.7 ✅ Python sidecar 收口：workspace/files/pdf_tools/word2pdf 全切 C#；Python 仅留 plot_curves
T6 ⏳ 打包（PyInstaller + dotnet publish + Tauri externalBin + mcp Node bundle）
T7 ✅ 删旧 Qt UI
T8 ✅ MCP server Phase 1：把 20 个 sidecar RPC 包成 MCP tools，agent 原生入口
```

**当前**：T8 MCP server Phase 1 完成。装配线 + 通用模板渲染 + 出图全路径都能让 agent 经 MCP 跑。Phase 2 待补 files/pdf_tools/word2pdf/catalog/preset CRUD 等约 25 个 tool。下一步候选见 CONTEXT.md（钻芯回弹切 C# / 多检测内容混排 / MCP Phase 2 / T6 打包 / LaTeX 路线）。

---

## 已交付（倒序）

| commit     | 日期       | 内容                                                                                                                                      |
| ---------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `<本系列>` | 2026-05-28 | feat(mcp): MCP server Phase 1（5 commit；20 tools；端到端三跳冒烟全通）                                                                   |
| `3ce8d6d`  | 2026-05-28 | feat(mcp): Phase 1 凑齐 20 tools + 修 registry callback 签名 bug（leeb/xlsx/template/report/plot_curves）                                 |
| `b2002ba`  | 2026-05-28 | feat(mcp): workspace 4 + anchor 3 = 7 装配线核心 tool                                                                                     |
| `d2e5a38`  | 2026-05-28 | feat(mcp): 接入 StdioServerTransport + doc_ping/doc_version 端到端跑通                                                                    |
| `a1011d4`  | 2026-05-28 | feat(mcp): sidecar 客户端 + 前缀路由 + 7 个单测                                                                                           |
| `279e50f`  | 2026-05-28 | feat(mcp): MCP server 脚手架（agent-first 路线起步）                                                                                      |
| `380540c`  | 2026-05-27 | feat(report_generator): 灌浆日期升级为批次维度字段（前端 groutingDateByBatch + 后端 [[批次]] marker dispatch；旧模板 fallback；+2 xUnit） |
| `57cf1fb`  | 2026-05-27 | fix(pdf_tools): 拆分输出目录默认与源 PDF 同目录 + 调参面板字号对齐 plot_curves + 文件名说明框去 border 防误读                             |
| `0cefda1`  | 2026-05-27 | refactor(word2pdf): 迁 C#（Windows COM dynamic + macOS/Linux stub；inspect 跨平台走 OpenXML）                                             |
| `50b4684`  | 2026-05-27 | refactor(pdf_tools): 迁 C#（PDFsharp 6.2，原子写）+ 20 xUnit；卸 pypdf Python 依赖                                                        |
| `c354f30`  | 2026-05-27 | refactor(files): 迁 C#（10 RPC，回收站 + 5min undo Shell COM）+ 26 xUnit                                                                  |
| `3c21a1e`  | 2026-05-27 | refactor(workspace): 迁 C#（4 RPC，~/.civ-core/workspace.json + 标准骨架）+ 8 xUnit；顺修 TemplateHandlers pre-existing 用例              |
| `228b0cf`  | 2026-05-26 | feat(template): 图片占位符 `{{img:xxx}}` 嵌入 OpenXML Drawing + ImageInjector helper + plot_curves 按 anchor_id 自动串接                  |
| `a1c74ee`  | 2026-05-26 | feat(anchor): catalog 字段单位优化（kN 派生）+ 报告填充与数据处理解耦（独立 own + 一键导入）+ 抽共享 anchorParamsForm                     |
| `a3e2eb9`  | 2026-05-26 | feat: 删 template_editor，新建 report_generator 独立工具页（4 件套 + ActivityBar）+ FileTree 删除确认升级到 VSCode 同款                   |
| `2b83c41`  | 2026-05-26 | feat: 占位符 `{}`→`{{}}` + DefaultFormat 真生效 + ReportGenerator 成对 marker + catalog 49 字段 + 别名网 + Excel Round 2 位（+38 xUnit）  |
| `401a625`  | 2026-05-26 | feat(data_processing): 接通 anchor Word 报告生成前端（已被后续 commit 拆出独立工具）                                                      |
| `5afe5af`  | 2026-05-22 | fix: 锚杆生成模板「点了没反应」根因 — Tauri capability 缺 dialog:allow-save                                                               |
| `b6433a9`  | 2026-05-22 | fix: 4 个 UX bug — 参数表纵向卡片 / 文件树联动 / RightPanel 反馈 / 日志启动写入（新建 ShellContext）                                      |
| `9bc472a`  | 2026-05-22 | fix: 锚杆生成模板按钮加 ok/error 状态反馈                                                                                                 |
| `ae3c48b`  | 2026-05-22 | feat: 前端 data_processing calcType=anchor 子 form                                                                                        |
| `2ebcf34`  | 2026-05-22 | feat: anchor RPC handlers（run/list_batches/generate_template）+ JsonRpcServer 注册                                                       |
| `4b804a8`  | 2026-05-22 | feat: anchor Excel 读 + 模板生成 + 两个输出 sheet（数据分析 + 报告内插表）写入                                                            |
| `b66aa43`  | 2026-05-22 | feat: anchor 抗拔计算底座 GB 50086-2015（Domain/Math/Calculator/Standards）+ 11 xUnit                                                     |
| `b13761c`  | 2026-05-22 | fix: audit 高风险 4 项 — C# 静默吞异常 / 空数据校验 / 前端类型绕过                                                                        |
| `395f05e`  | 2026-05-22 | fix: 修 3 个 controller run() 陈旧闭包 — handleRun 永远拿不到结果                                                                         |
| `8e5365b`  | 2026-05-22 | fix(sidecar): 修锁死风险 — read_line 超时 + stderr drain + 崩溃标记                                                                       |
| `8d0a0ca`  | 2026-05-22 | fix(tauri): 修启动闪退 — repo_root 推断错导致 C# sidecar 找不到 dll                                                                       |
| `733b18b`  | 2026-05-22 | docs: 重构 AI 上下文文件体系                                                                                                              |
| `fb05230`  | 2026-05-22 | T5.5 Step 4：C# leeb.run RPC + 路由默认 C#（Phase 5 删 Python 旧代码）                                                                    |
| `a6c8cc0`  | 2026-05-22 | Phase 3：C# ClosedXML 读 leeb 输入                                                                                                        |
| `fa11a07`  | 2026-05-22 | Phase 2：C# 核心算法（查表/插值/截尾平均）                                                                                                |
| `8b8119d`  | 2026-05-22 | Phase 1：C# SQLite + 数据契约                                                                                                             |
| `6e43586`  | 2026-05-21 | refactor leeb 输出格式                                                                                                                    |
| `885124a`  | 2026-05-21 | T5.5 Step 2 文档同步                                                                                                                      |
| `a6676c1`  | 2026-05-21 | T5.5 Step 2：C# ClosedXML 写报告插入表                                                                                                    |
| `47de0e8`  | 2026-05-21 | T5.5 Step 1：C# sidecar 链路通                                                                                                            |
| `1ae71f1`  | 2026-05-21 | T5 完结：word2pdf 工具页                                                                                                                  |
| `7175729`  | 2026-05-21 | pdf_tools 工具页                                                                                                                          |
| `94751e0`  | 2026-05-21 | data_processing 模块改名 + calcType 下拉                                                                                                  |
| `c77d156`  | 2026-05-21 | leeb 工具页对齐范式                                                                                                                       |
| `ca9accf`  | 2026-05-21 | 移 AI 文档到 .ai/                                                                                                                         |
| `[大清理]` | 2026-05-20 | 删旧 Qt UI（30+ 文件）+ 重写 logger/main + 去 pyside6/qfluentwidgets                                                                      |

<details><summary>更早的 commit（展开查看）</summary>

| commit    | 日期       | 内容                                   |
| --------- | ---------- | -------------------------------------- |
| `921e9bb` | 2026-05-20 | VSCode 风 TitleBar + run.sh + 中国镜像 |
| `dc1f53a` | 2026-05-20 | T3 Tauri 主进程 + sidecar.rs           |
| `6af15b3` | 2026-05-20 | T2 前端骨架                            |
| `084033e` | 2026-05-20 | T1 Python JSON-RPC server              |
| `c731acc` | 2026-05-19 | 删旧项目看板（22 文件）                |
| `7a8a076` | 2026-05-19 | 里氏硬度 Excel 格式固化 + 多批支持     |
| `0bac5aa` | 2026-05-19 | INSP-001 里氏硬度切到完整可用          |
| `47db417` | 2026-05-19 | INSP-002 钻芯法计算底座                |

</details>

---

## 关键架构决策

| 决策                                                                                                               | 原因                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| UI：Tauri + Web 替代 Qt                                                                                            | Qt 视觉天花板不可弥补                                                                                                                                                                                                                                                                                                                               |
| 后端：Python + C# 双 sidecar 渐进迁移                                                                              | Word/Excel 重资产 C# 原生强；Python 业务底座保留                                                                                                                                                                                                                                                                                                    |
| 协议：JSON-RPC 2.0 over stdin/stdout                                                                               | 极简，绕开 IPC 复杂度                                                                                                                                                                                                                                                                                                                               |
| 预设双路径：系统 `presets/` + 用户 `~/.civ-core/`                                                                  | 防更新覆盖用户数据                                                                                                                                                                                                                                                                                                                                  |
| 数据契约：dataclass + `__post_init__`                                                                              | 不引 pydantic，依赖轻量                                                                                                                                                                                                                                                                                                                             |
| 路由反转默认 C#                                                                                                    | 用户方向「以后代码都用 C#」；新 calc 类型不加 Rust 代码                                                                                                                                                                                                                                                                                             |
| ShellContext 全局可观察性（appendOutput/activatedFile）                                                            | 旧 prop-drilling 让 RightPanel 拿不到 appendOutput；用户偏好「UI 任何操作可观察」要求每个 onClick 入口先打日志                                                                                                                                                                                                                                      |
| 工具列名按 Nt 倍数（0.1Nt/1.2Nt-5min）不绑 kN                                                                      | 输入列名与 P 解耦；同代码处理任意 P；跟报告内插表占位符语义一致                                                                                                                                                                                                                                                                                     |
| 占位符引擎 v2：`{{}}` + `{{img:xxx}}` 双语法；catalog DefaultFormat 控制数字格式；按段位置切 Run 支持文本+图片混排 | 用户模板都用 `{{}}`；裸 double 1.234567 必须按规范保留位数；图片占位符必须能跟文本同段共存（如 "曲线: {{img:曲线图}} 已记录"）                                                                                                                                                                                                                      |
| 报告填充工具完全独立 own state，不耦合数据处理                                                                     | 装配线连贯但每个工序能独立工作（拿别人 Excel 出报告也得能用）；保留"一键导入"按钮兜手动连贯场景                                                                                                                                                                                                                                                     |
| 字段维度划分（报告/检测项目/检测批/构件级）让用户拍板                                                              | AI 不是业务人。最终模型 4 级：报告级（甲方/工程/参建单位）+ 检测项目级（仪器/人员/时间）+ 检测批级（灌浆日期等）+ 构件级（每根锚杆/钻芯/回弹），catalog metadata 在 `CatalogStore.InferLevel` 里硬编码、`template.validate` 据此给 level mismatch hint。当前实现只跑通报告 + 检测批两层（grouting_date 按批次），检测项目层留待多检测内容混排再启用 |
| 批次维度走「白名单 + 模板 marker dispatch」而非动 catalog                                                          | 前端 `BATCH_DIM_KEYS` 白名单决定 UI 渲染位置（按批次卡片 vs 项目级 input）；后端 `AnchorHandlers.Run` 扫模板有没有 `[[批次]]` 字符串决定走 `Generate` vs `GenerateMultiBatch`。catalog 的 `FieldDef` 不加 `Dimension` 属性——避免动 49 字段定义；后续字段从项目级挪到批次级只改 types.ts + 白名单                                                    |
| word2pdf 渲染：Windows COM + Mac stub，不用 LibreOffice/Pages 降级                                                 | 检测报告对甲方 Word 模板还原度要求高，~5% 排版差异不可接受；Mac 路径以后补 AppleScript 驱动 Word for Mac，精度跟 Windows 对齐                                                                                                                                                                                                                       |
| 「能不调 COM 就不调」但精度优先                                                                                    | 大多数场景（文件回收站除外）有非 COM 替代（OpenXML / PDFsharp / .NET BCL）就用；word2pdf 这种纯渲染场景找不到等价无 COM 方案，才保留 COM                                                                                                                                                                                                            |
| 主要面向 AI agent，GUI 退居次位（2026-05-27 定调）                                                                 | agent 经 MCP 协议拿 tool list + schema 直接调用 sidecar；人通过 GUI review agent 输出。后续候选评估 agent 体验优先，GUI 按钮做兜底（如「一键流水线」按钮对 agent 无价值，因为它能直接串 MCP tools）                                                                                                                                                 |
| MCP server 走独立 Node 进程转发 RPC，不进程内嵌 C# sidecar（2026-05-28）                                           | skill 推荐过 `dotnet/civ-mcp/` 进程内调 Dispatcher，用户拍板独立第 3 进程：① Tauri / sidecar 进程边界零改动 ② Node MCP SDK 生态最成熟 ③ TS 写 schema 比 C# 写 anonymous object 顺手 ④ 跟其他语言栈解耦，未来某种 sidecar 升级不需要改 MCP 层。代价是多一层 JSON 序列化（业务量小可忽略）+ 多一个 Node 运行时依赖（T6 打包时 bundle 成单文件解决）   |
