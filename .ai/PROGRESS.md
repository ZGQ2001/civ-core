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

**当前**：T5.5 完成（5 commits，leeb 全线 C#，Python 端 6 文件删除，路由反转默认 C#）。下一步 T5.5 Step 3 报告生成 或 T6 打包。

---

## 已交付（倒序）

| commit | 日期 | 内容 |
|--------|------|------|
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
