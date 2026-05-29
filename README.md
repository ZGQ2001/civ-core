<h1 align="center">筑核 · civ-core</h1>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square" alt="Platform: Windows">
  <img src="https://img.shields.io/badge/license-Apache--2.0-green?style=flat-square" alt="License: Apache-2.0">
  <img src="https://img.shields.io/badge/status-source--only-orange?style=flat-square" alt="Status: source-only (no binary release yet)">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Rust-Tauri_2.11-orange?style=flat-square" alt="Rust">
  <img src="https://img.shields.io/badge/C%23-.NET_9-purple?style=flat-square" alt="C#">
  <img src="https://img.shields.io/badge/TS-React_19-blue?style=flat-square" alt="TypeScript">
  <img src="https://img.shields.io/badge/Python-3.12-yellow?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/MCP-server-pink?style=flat-square" alt="MCP server">
</p>

---

**筑核** 是面向土木工程检测行业的桌面端内业报告自动化工具：Excel/CSV 拖入 → 自动评定 → Word 报告 + 曲线图。

> 内部自用为主；同时对外提供 MCP server，给 Claude Code / Codex / Cursor 等 AI agent 原生调用入口。

---

## 项目定位（先讲清楚再用）

- **当前状态**：源码运行；尚未打包二进制 release。`Releases` 页为空。T6 打包（PyInstaller + dotnet publish + Tauri externalBin + MCP Node bundle）做完后才会提供 `.exe` 安装包。
- **运行入口有两个**：
  1. **桌面 GUI**（Tauri 2 + React 19）—— 非编程用户日常操作的主入口。
  2. **MCP server**（Node + TS）—— 给 AI agent 用的入口，跟 GUI 共享同一组 sidecar 但各起独立子进程。
- **平台**：当前装配线（计算 / Excel / Word / SQLite）跨平台；只有 `word2pdf` 走 Windows COM（dynamic）的 `Word.Application`，非 Windows 抛 `PlatformNotSupported`。
- **依赖（从源码运行时）**：
  - .NET 9 SDK（C# sidecar）
  - Python 3.12 + [uv](https://docs.astral.sh/uv/)（matplotlib 图表引擎）
  - Node 20+（前端 + MCP server）
  - Rust toolchain（Tauri 主进程）
  - 无需 Microsoft Office（Excel/Word 读写走 OpenXML SDK；仅 `word2pdf` 需要 Word/WPS）

---

## 功能

### 装配线（一条流水线，工序之间显式串接）

| 工序                                | 输入 → 输出                                                 | 状态                                                    |
| ----------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------- |
| 数据处理 · 锚杆抗拔 (GB 50086-2015) | 锚杆 Excel → 结果 xlsx（含数据分析 + `_批次参数` metadata） | ✅                                                      |
| 数据处理 · 里氏硬度推定 (INSP-001)  | 里氏硬度 Excel → `_里氏硬度推定结果.xlsx`                   | ✅                                                      |
| 数据处理 · 钻芯法 (INSP-002)        | 芯样 Excel → 结果 xlsx                                      | 🚧 骨架                                                 |
| 数据处理 · 回弹法 (INSP-003)        | 回弹 Excel → 结果 xlsx                                      | 🚧 骨架                                                 |
| 绘曲线图 (plot_curves)              | Excel + 预设 → 高清 PNG                                     | ✅                                                      |
| 报告填充                            | 结果 xlsx + Word 模板 + 用户输入 → docx                     | ✅（含 [[检测项目]]>[[批次]]>[[每根锚杆]] 三层 marker） |
| 模板助手                            | docx 模板字段校验 + catalog 4 级字段管理                    | ✅                                                      |

### 工具

- **报告预设**：整份 user_inputs 存 `~/.civ-core/report_presets/<id>.json`，跨报告复用 + 字段历史值下拉
- **PDF 工具**：合并 / 按页拆 / 按范围拆（PDFsharp，原子写）
- **Word → PDF**：仅 Windows（dynamic COM 调 Word/WPS）

---

## 架构

```
GUI 入口                             Agent 入口
🖥 Tauri 2 主进程 (Rust)            🤖 MCP server (Node + TS)
   ├── SidecarRouter                  ├── SidecarRouter
   │   ├── 默认 → 🔧 C# (.NET 9)     │   ├── 默认 → 🔧 C# (.NET 9)
   │   │   计算 / Excel / Word /      │   │   （独立子进程，不共享）
   │   │   SQLite / 模板 / 预设       │   └── 白名单 → 📊 Python 3.12
   │   └── 白名单 → 📊 Python 3.12   │       (matplotlib 出图)
   │       (matplotlib 出图)          └── 25 MCP tools 暴露给 agent
   └── React 19 + Vite 前端
   ↓                                   ↓
   📁 工作区目录                       💾 ~/.civ-core/
                                          standards.db / report_presets/ / catalogs/
```

**双客户端 / 双 sidecar**：GUI 和 MCP server 是平级入口，各自 spawn 一组 sidecar 子进程（不共享内存状态，共享文件系统）。所有业务逻辑在 sidecar 里，入口层只做 JSON-RPC 转发。Python sidecar 只承载 `plot_curves.*`（matplotlib 无可替代），其余全 C#。

详见 [`CLAUDE.md`](CLAUDE.md)（架构宪法）和 [`.ai/RULES.md`](.ai/RULES.md)（RPC 全表 + 编码规范）。

---

## 技术栈

| 层         | 选型                                                           |
| ---------- | -------------------------------------------------------------- |
| 前端 UI    | React 19 · TypeScript · Tailwind v4 · @vscode/codicons         |
| 桌面壳     | Tauri 2.11 · Rust                                              |
| Agent 入口 | MCP server（Node 20+ · TS · `@modelcontextprotocol/sdk` 1.29） |
| 计算引擎   | C# · .NET 9 · ClosedXML · OpenXML SDK · PDFsharp               |
| 图表引擎   | Python 3.12 · matplotlib（仅此一处用 Python）                  |
| 通信协议   | JSON-RPC 2.0 over stdin/stdout 行协议                          |
| 数据库     | SQLite (Microsoft.Data.Sqlite)                                 |
| 测试       | xUnit (C#) · vitest (MCP) · pytest (Python) · ruff             |

---

## 从源码运行

### 前置依赖

| 工具     | 版本                                                |
| -------- | --------------------------------------------------- |
| .NET SDK | 9.0+                                                |
| Python   | 3.12+（推荐用 [uv](https://docs.astral.sh/uv/) 管） |
| Node     | 20+                                                 |
| Rust     | stable（Tauri 2 要求）                              |

### 启动 GUI

```bash
# 一次性
cd dotnet/civ-doc && dotnet build
uv sync
cd frontend && npm install

# 跑
cd frontend && npm run tauri:dev
```

### 启动 MCP server（接 Claude Code）

```bash
cd mcp && npm install && npm run build
# 在 ~/.claude/mcp_servers.json 配置 node dist/index.js，详见 mcp/CLAUDE.md
```

---

## 测试 / 静态检查

```bash
# C#
cd dotnet/civ-doc && dotnet format style --verify-no-changes && dotnet build && dotnet test

# 前端
cd frontend && npx tsc -b --noEmit && npm run lint && npm run format:check

# MCP server
cd mcp && npm run typecheck && npm test

# Python
uv run --frozen ruff format --check . && uv run --frozen ruff check . && uv run --frozen pytest -q
```

---

## License

[Apache License 2.0](LICENSE)
