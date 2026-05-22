# civ-core（筑核）

土木检测内业报告自动化工具。接收 Excel/CSV/Word，自动完成数据格式化、规范评定、报告填充。
Windows 平台，内部自用，非编程人员操作。

**角色**：本文件是 AI 的宪法级上下文。放不可变的架构规则和边界。≤4000 字。每次会话必读。
**配套文件**：`.ai/RULES.md`（编码规范+清单）| `.ai/PROGRESS.md`（里程碑）| `.ai/CONTEXT.md`（当前焦点）
**子域规则**：`dotnet/CLAUDE.md` | `frontend/CLAUDE.md`（仅在操作对应目录时加载）

---

## 架构

```mermaid
graph TB
    subgraph Frontend ["前端 (Vite + React 19 + TS + Tailwind v4)"]
        UI["VSCode 风格布局<br/>TitleBar / SideBar / Editor / StatusBar"]
        RPC_Client["rpc.ts (JSON-RPC 2.0 客户端)"]
        UI --> RPC_Client
    end

    subgraph Tauri ["Tauri 2 主进程 (Rust)"]
        IPC_Cmd["rpc_call (tauri::command)"]
        Router["SidecarRouter<br/>前缀路由分发"]
        RPC_Client -- "invoke('rpc_call')" --> IPC_Cmd
        IPC_Cmd --> Router
    end

    subgraph CSharp ["C# Sidecar (.NET 9 · civ-doc)"]
        CS_RPC["JsonRpcServer.RunAsync()"]
        CS_Handlers["Handlers<br/>Doc / Leeb / Anchor / Xlsx<br/>word2pdf（待迁）"]
        CS_Calc["Calc 计算<br/>LeebMath / AnchorCalculator"]
        CS_CL["ClosedXML / OpenXML<br/>Excel/Word 读写 + docx→PDF"]
        CS_SQL["Microsoft.Data.Sqlite<br/>SQLite 只读查询"]
        CS_RPC --> CS_Handlers
        CS_Handlers --> CS_Calc
        CS_Handlers --> CS_CL
        CS_Handlers --> CS_SQL
    end

    subgraph Python ["Python Sidecar (3.12 · civ_core.api)"]
        Py_RPC["server.serve() / Dispatcher"]
        Py_Handlers["Handlers<br/>Workspace / Files / Plot / PDF"]
        Py_Core["Core 业务<br/>matplotlib 绘图"]
        Py_Infra["Infra IO<br/>file_manager / pdf_io / standards_db"]
        Py_RPC --> Py_Handlers
        Py_Handlers --> Py_Core
        Py_Handlers --> Py_Infra
    end

    subgraph Storage ["外部存储"]
        DB["~/.civ-core/standards.db<br/>规范数据库"]
        Disk["工作区目录"]
    end

    Router -- "默认路由<br/>leeb.* doc.* xlsx.* anchor.*<br/>word2pdf.*（待迁）" --> CS_RPC
    Router -- "白名单路由<br/>workspace.* files.* plot_curves.* pdf_tools.*" --> Py_RPC

    CS_SQL -- "只读查询" --> DB
    Py_Infra -- "Seed 写入" --> DB
    Py_Infra -- "读写" --> Disk
    CS_CL -- "读写" --> Disk

    style Frontend fill:#1e1e2e,stroke:#cba6f7,color:#cdd6f4
    style Tauri fill:#11111b,stroke:#89b4fa,color:#cdd6f4
    style CSharp fill:#181825,stroke:#a6e3a1,color:#cdd6f4
    style Python fill:#181825,stroke:#f9e2af,color:#cdd6f4
    style Storage fill:#313244,stroke:#f5c2e7,color:#cdd6f4
```

**双 sidecar 通过 stdin/stdout JSON-RPC 2.0 行协议通信。同协议、同错误码。前端不感知 sidecar 边界。Python 负责 standards.db 初始化写入，C# 以只读方式查询。**

## 技术栈

- Python 3.12+, `uv` 管理，禁 pip install
- C# .NET 9, ClosedXML 0.105, Microsoft.Data.Sqlite 10.0
- 前端 Vite + React 19 + TypeScript + Tailwind v4 + @vscode/codicons
- 主进程 Tauri 2.11 (Rust)
- JSON-RPC 2.0 over stdin/stdout，行协议

## RPC 路由

**策略：默认 C#，白名单 Python。** 未来新 calc 类型不加 Rust 代码。

| sidecar | 方法前缀 |
|---------|---------|
| **C#（默认）** | `leeb.*` `doc.*` `xlsx.*` `calc.*` `word2pdf.*`（待迁）— 及所有未列出的新方法 |
| **Python（白名单）** | `ping` `version` `workspace.*` `files.*` `plot_curves.*` `pdf_tools.*` |

## 不可变规则

1. **依赖方向**：`frontend → Tauri → sidecar → core/infra_io/domain`。禁反向 import。禁跨 sidecar 共享内存状态。

2. **handler `__all__`**：每个 `api/handlers/*.py` 顶部显式写 `__all__`。不写会把 `import Path` 暴露成 RPC 方法。

3. **`run()` 必须 return 值**：前端工具 controller 的 `run()` 签名必须是 `Promise<RunRes | null>`，不准靠闭包读 `this.state`。

4. **图标**：只用 @vscode/codicons 真实存在的名字。`calculator` 不存在→用 `symbol-method`。

5. **stdout 是协议流**：Python `api/__main__.py` 只挂 file+stderr logger；C# `Program.cs` 只写 `Console.Error`。绝不动 stdout。

## 会话自检（每次开工前回答）

- [ ] 这个功能走 Python 还是 C#？前缀配对了吗？
- [ ] handler 写了 `__all__` 吗？
- [ ] 前端 `run()` 是 `return` 值还是读闭包？

## 工作流

1. 会话开始：`git add -A && git commit -m "chore: 会话检查点"` → 读本文件 + `.ai/CONTEXT.md` → 报告状态→确认后动手
2. 单步完成：`git add -A && git commit -m "feat: xxx"`（不用 emoji）
3. 改 Python：`uv run --frozen ruff check . && uv run --frozen pytest -q && uv run --frozen python scripts/healthcheck.py`
4. 改 C#：`cd dotnet/civ-doc && dotnet build && dotnet test`
5. 改 Rust：`cd frontend/src-tauri && cargo check && cargo test --lib`
6. 改前端：`cd frontend && npx tsc -b --noEmit`
7. 阶段结束→更新 `.ai/CONTEXT.md`；里程碑完成→更新 `.ai/PROGRESS.md`

## 边界

| 禁止 | 必须 |
|------|------|
| 没方案就改代码 | 先报告方案→确认→执行 |
| core/ 直接读写文件 | IO 全走 infra_io/ |
| api/handlers/ 直接做计算 | 调 core/ |
| stdout 写日志 | stderr 或文件 |
| pip install / 顶层 import pandas | uv add / lazy import |
| 跨 sidecar 共享全局变量 | 共享状态走 `~/.civ-core/` 文件 |
| 大文件 `f.read()` 一把梭 | generator / 流式 |
| 中国源直连 | 用镜像（见 `.ai/RULES.md`） |
