# 筑核（civ-core）

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Stars](https://img.shields.io/github/stars/ZGQ2001/civ-core?style=flat-square)
![Last Commit](https://img.shields.io/github/last-commit/ZGQ2001/civ-core?style=flat-square)
![Release](https://img.shields.io/github/v/release/ZGQ2001/civ-core?style=flat-square)
![Contributors](https://img.shields.io/github/contributors/ZGQ2001/civ-core?style=flat-square)
![CI](https://img.shields.io/github/actions/workflow/status/ZGQ2001/civ-core/ci.yml?style=flat-square&label=CI)
![Top Lang](https://img.shields.io/github/languages/top/ZGQ2001/civ-core?style=flat-square)
![Code Size](https://img.shields.io/github/languages/code-size/ZGQ2001/civ-core?style=flat-square)
![Rust](https://img.shields.io/badge/Rust-Tauri_2.11-orange?style=flat-square)
![C#](https://img.shields.io/badge/C%23-.NET_9-purple?style=flat-square)
![TypeScript](https://img.shields.io/badge/TS-React_19-blue?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.12-yellow?style=flat-square)

[![Star History Chart](https://api.star-history.com/svg?repos=ZGQ2001/civ-core&type=Date)](https://star-history.com/#ZGQ2001/civ-core&Date)

土木工程检测内业报告自动化工具。

输入 Excel/CSV/Word → 自动完成数据格式化、规范评定、图表生成、Word 报告填充。

---

## 📸 功能截图

### 曲线图工具
![曲线图](docs/plot_curves_demo.png)

### 数据处理（里氏硬度 / 锚杆抗拔）
![数据处理](docs/data_processing_demo.png)

---

## 🚀 快速上手

1. 从 [Releases](https://github.com/ZGQ2001/civ-core/releases) 下载最新版
2. 解压运行 `civ-core.exe`
3. 选择工具 → 导入数据 → 一键出报告

---

## 🧰 功能

| 工具 | 说明 |
|------|------|
| 📊 绘图工具 | 导入 Excel → 选曲线模板 → 批量出图 PNG |
| 🔩 里氏硬度 (INSP-001) | 钢材硬度 → 抗拉强度推定，多批/角度/厚度修正 |
| 🪨 钻芯法 (INSP-002) | 混凝土芯样抗压强度推定 |
| 🔄 回弹法 (INSP-003) | 混凝土回弹强度推定（骨架就绪） |
| ⚓ 锚杆抗拔 | GB 50086-2015 抗拔试验计算 |
| 📄 Word → PDF | 批量转换 |
| 📎 PDF 工具 | 合并 / 分拆 |
| 📁 工作区管理 | 自动创建项目文件夹结构 |

---

## 🛠 开发

### 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vite + React 19 + TypeScript + Tailwind v4 |
| 桌面壳 | Tauri 2.11 (Rust) |
| 主计算引擎 | C# .NET 9 + ClosedXML + OpenXML SDK |
| 图表引擎 | Python 3.12 + matplotlib |
| RPC 协议 | JSON-RPC 2.0 over stdin/stdout |
| 数据库 | SQLite (Microsoft.Data.Sqlite) |
| 测试 / Lint | pytest / ruff / xUnit |
| CI | GitHub Actions (Windows) |

### 架构

```mermaid
graph TB
    subgraph Frontend ["前端 (Vite + React 19 + TS)"]
        UI["VSCode 风格布局"]
        RPC_Client["rpc.ts"]
        UI --> RPC_Client
    end
    subgraph Tauri ["Tauri 2 (Rust)"]
        Router["SidecarRouter"]
        RPC_Client --> Router
    end
    subgraph CSharp ["C# Sidecar (.NET 9)"]
        CS["Doc / Leeb / Anchor / Xlsx / Workspace / Files / PDF"]
    end
    subgraph Python ["Python (3.12)"]
        Py["plot_curves · matplotlib"]
    end
    subgraph Storage ["存储"]
        DB["standards.db"] & Disk["工作区"]
    end
    Router -- "默认路由" --> CS
    Router -- "白名单" --> Py
    CS & Py --> Storage
```

### 启动开发环境

```bash
bash run.sh
# 或
cd frontend && npm run tauri:dev
```

### 命令行（脱壳模式）

```bash
uv run python -m civ_core.main --list-presets
uv run python -m civ_core.main --tool plot_curves --input data.xlsx --preset 预设名 --output ./输出/
uv run pytest
uv run ruff check .
```

### 目录结构

```
civ-core/
├── frontend/          React UI + Tauri 主进程
├── src/civ_core/      Python sidecar（api/core/infra_io/domain）
├── dotnet/civ-doc/    C# sidecar（Handlers/Calc/ReportTables）
├── docs/              土木知识库 + 开发日志
├── tests/             300+ pytest
├── presets/           系统预设
└── ~/.civ-core/       用户数据
```
