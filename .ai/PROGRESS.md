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
T6 ⏳ 打包（PyInstaller + dotnet publish + Tauri externalBin）
T7 ✅ 删旧 Qt UI
```

**当前**：装配线第 5 工序「报告填充」上线 —— 锚杆抗拔 数据处理 → 绘曲线图 → 报告填充 完整链路通；占位符引擎升级到 `{{}}` v2，新增 `{{img:xxx}}` 图片占位符。下一步候选见 CONTEXT.md。

---

## 已交付（倒序）

| commit | 日期 | 内容 |
|--------|------|------|
| `228b0cf` | 2026-05-26 | feat(template): 图片占位符 `{{img:xxx}}` 嵌入 OpenXML Drawing + ImageInjector helper + plot_curves 按 anchor_id 自动串接 |
| `a1c74ee` | 2026-05-26 | feat(anchor): catalog 字段单位优化（kN 派生）+ 报告填充与数据处理解耦（独立 own + 一键导入）+ 抽共享 anchorParamsForm |
| `a3e2eb9` | 2026-05-26 | feat: 删 template_editor，新建 report_generator 独立工具页（4 件套 + ActivityBar）+ FileTree 删除确认升级到 VSCode 同款 |
| `2b83c41` | 2026-05-26 | feat: 占位符 `{}`→`{{}}` + DefaultFormat 真生效 + ReportGenerator 成对 marker + catalog 49 字段 + 别名网 + Excel Round 2 位（+38 xUnit）|
| `401a625` | 2026-05-26 | feat(data_processing): 接通 anchor Word 报告生成前端（已被后续 commit 拆出独立工具）|
| `5afe5af` | 2026-05-22 | fix: 锚杆生成模板「点了没反应」根因 — Tauri capability 缺 dialog:allow-save |
| `b6433a9` | 2026-05-22 | fix: 4 个 UX bug — 参数表纵向卡片 / 文件树联动 / RightPanel 反馈 / 日志启动写入（新建 ShellContext） |
| `9bc472a` | 2026-05-22 | fix: 锚杆生成模板按钮加 ok/error 状态反馈 |
| `ae3c48b` | 2026-05-22 | feat: 前端 data_processing calcType=anchor 子 form |
| `2ebcf34` | 2026-05-22 | feat: anchor RPC handlers（run/list_batches/generate_template）+ JsonRpcServer 注册 |
| `4b804a8` | 2026-05-22 | feat: anchor Excel 读 + 模板生成 + 两个输出 sheet（数据分析 + 报告内插表）写入 |
| `b66aa43` | 2026-05-22 | feat: anchor 抗拔计算底座 GB 50086-2015（Domain/Math/Calculator/Standards）+ 11 xUnit |
| `b13761c` | 2026-05-22 | fix: audit 高风险 4 项 — C# 静默吞异常 / 空数据校验 / 前端类型绕过 |
| `395f05e` | 2026-05-22 | fix: 修 3 个 controller run() 陈旧闭包 — handleRun 永远拿不到结果 |
| `8e5365b` | 2026-05-22 | fix(sidecar): 修锁死风险 — read_line 超时 + stderr drain + 崩溃标记 |
| `8d0a0ca` | 2026-05-22 | fix(tauri): 修启动闪退 — repo_root 推断错导致 C# sidecar 找不到 dll |
| `733b18b` | 2026-05-22 | docs: 重构 AI 上下文文件体系 |
| `fb05230` | 2026-05-22 | T5.5 Step 4：C# leeb.run RPC + 路由默认 C#（Phase 5 删 Python 旧代码） |
| `a6c8cc0` | 2026-05-22 | Phase 3：C# ClosedXML 读 leeb 输入 |
| `fa11a07` | 2026-05-22 | Phase 2：C# 核心算法（查表/插值/截尾平均） |
| `8b8119d` | 2026-05-22 | Phase 1：C# SQLite + 数据契约 |
| `6e43586` | 2026-05-21 | refactor leeb 输出格式 |
| `885124a` | 2026-05-21 | T5.5 Step 2 文档同步 |
| `a6676c1` | 2026-05-21 | T5.5 Step 2：C# ClosedXML 写报告插入表 |
| `47de0e8` | 2026-05-21 | T5.5 Step 1：C# sidecar 链路通 |
| `1ae71f1` | 2026-05-21 | T5 完结：word2pdf 工具页 |
| `7175729` | 2026-05-21 | pdf_tools 工具页 |
| `94751e0` | 2026-05-21 | data_processing 模块改名 + calcType 下拉 |
| `c77d156` | 2026-05-21 | leeb 工具页对齐范式 |
| `ca9accf` | 2026-05-21 | 移 AI 文档到 .ai/ |
| `[大清理]` | 2026-05-20 | 删旧 Qt UI（30+ 文件）+ 重写 logger/main + 去 pyside6/qfluentwidgets |

<details><summary>更早的 commit（展开查看）</summary>

| commit | 日期 | 内容 |
|--------|------|------|
| `921e9bb` | 2026-05-20 | VSCode 风 TitleBar + run.sh + 中国镜像 |
| `dc1f53a` | 2026-05-20 | T3 Tauri 主进程 + sidecar.rs |
| `6af15b3` | 2026-05-20 | T2 前端骨架 |
| `084033e` | 2026-05-20 | T1 Python JSON-RPC server |
| `c731acc` | 2026-05-19 | 删旧项目看板（22 文件） |
| `7a8a076` | 2026-05-19 | 里氏硬度 Excel 格式固化 + 多批支持 |
| `0bac5aa` | 2026-05-19 | INSP-001 里氏硬度切到完整可用 |
| `47db417` | 2026-05-19 | INSP-002 钻芯法计算底座 |

</details>

---

## 关键架构决策

| 决策 | 原因 |
|------|------|
| UI：Tauri + Web 替代 Qt | Qt 视觉天花板不可弥补 |
| 后端：Python + C# 双 sidecar 渐进迁移 | Word/Excel 重资产 C# 原生强；Python 业务底座保留 |
| 协议：JSON-RPC 2.0 over stdin/stdout | 极简，绕开 IPC 复杂度 |
| 预设双路径：系统 `presets/` + 用户 `~/.civ-core/` | 防更新覆盖用户数据 |
| 数据契约：dataclass + `__post_init__` | 不引 pydantic，依赖轻量 |
| 路由反转默认 C# | 用户方向「以后代码都用 C#」；新 calc 类型不加 Rust 代码 |
| ShellContext 全局可观察性（appendOutput/activatedFile） | 旧 prop-drilling 让 RightPanel 拿不到 appendOutput；用户偏好「UI 任何操作可观察」要求每个 onClick 入口先打日志 |
| 工具列名按 Nt 倍数（0.1Nt/1.2Nt-5min）不绑 kN | 输入列名与 P 解耦；同代码处理任意 P；跟报告内插表占位符语义一致 |
| 占位符引擎 v2：`{{}}` + `{{img:xxx}}` 双语法；catalog DefaultFormat 控制数字格式；按段位置切 Run 支持文本+图片混排 | 用户模板都用 `{{}}`；裸 double 1.234567 必须按规范保留位数；图片占位符必须能跟文本同段共存（如 "曲线: {{img:曲线图}} 已记录"） |
| 报告填充工具完全独立 own state，不耦合数据处理 | 装配线连贯但每个工序能独立工作（拿别人 Excel 出报告也得能用）；保留"一键导入"按钮兜手动连贯场景 |
| 字段维度划分（项目/批次/锚杆级）让用户拍板，不让 AI 替代 | AI 不是业务人；现阶段先用"拆批次"绕过批次共享字段（如灌浆日期）问题 |
