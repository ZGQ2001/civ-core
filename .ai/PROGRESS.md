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
T6 ⏳ 打包（PyInstaller + dotnet publish + Tauri externalBin）
T7 ✅ 删旧 Qt UI
```

**当前**：T5.5 完成 + 锚杆抗拔（GB 50086-2015）上线 + ShellContext 可观察性补齐 + FileTree VSCode 风重构。下一步候选见 CONTEXT.md。

---

## 已交付（倒序）

| commit | 日期 | 内容 |
|--------|------|------|
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
