# MCP server 域规则

> **角色**：仅在 AI 操作 `mcp/` 目录时加载。MCP server 专属编码规范。
> **主宪法**：`../CLAUDE.md`（架构 / 路由 / 不可变规则）

---

## 项目定位

把 civ-core 双 sidecar 的 JSON-RPC 方法包成标准 MCP tools，让 Claude Code /
Codex / Cursor 等 agent 原生调用 —— **不绕 Tauri 也能跑完整装配线**。

进程模型：本进程作为 MCP server，spawn 两个 sidecar 子进程（C# + Python），
把 MCP tool call → JSON-RPC over stdin/stdout 转发过去。所有业务逻辑只在
sidecar 里；本目录只做**协议适配 + 错误映射**。

## 目录结构

```text
mcp/
├── CLAUDE.md                  本文件
├── package.json               @modelcontextprotocol/sdk + zod
├── tsconfig.json              NodeNext + strict + noUncheckedIndexedAccess
├── src/
│   ├── index.ts               入口：spawn sidecar + 注册 tools + 连 stdio
│   ├── sidecar.ts             JsonRpcSidecar 客户端（对照 sidecar.rs）
│   ├── router.ts              SidecarRouter 前缀路由（同 Rust 端策略）
│   ├── lib/
│   │   └── repoRoot.ts        解析仓库根（env / sentinel 推断）
│   └── tools/             共 52 tool（基本与 sidecar RPC 全表对齐）
│       ├── registry.ts        ToolDef 接口 + registerSidecarTool 帮手
│       ├── doc.ts             doc 2 tool（ping / version 探活）
│       ├── workspace.ts       workspace 4 tool
│       ├── anchor.ts          anchor 4 tool
│       ├── leeb.ts            leeb 2 tool
│       ├── xlsx.ts            xlsx 1 tool
│       ├── template.ts        template 2 tool（fields / validate）
│       ├── report.ts          report 2 tool
│       ├── reportPreset.ts    report_preset 5 tool
│       ├── catalog.ts         catalog 4 tool（字段目录 CRUD）
│       ├── files.ts           files 10 tool（文件管理；delete/undo/reveal 仅 Win）
│       ├── pdfTools.ts        pdf_tools 4 tool
│       ├── word2pdf.ts        word2pdf 2 tool（convert 仅 Win）
│       └── plot_curves.ts     plot_curves 10 tool（走 Python sidecar；含预设 CRUD）
├── tests/                     vitest 单测 + echo fixture
└── scripts/
    └── smoke.mjs              端到端冒烟：用 MCP Client SDK 驱动本 server
```

## 加一个 MCP tool（SOP）

复用现有 sidecar RPC 方法时（绝大多数情况）：

1. **写 ToolDef**：在 `src/tools/<domain>.ts` 加一个 `ToolDef` 常量：

   ```ts
   export const fooBar: ToolDef = {
     rpcMethod: "foo.bar", // sidecar 端的 JSON-RPC method（带点）
     mcpName: "foo_bar", // MCP tool 名（点改下划线，[a-zA-Z0-9_-]+）
     description: "做什么 / 什么时候用 / 入参约束。", // agent 选 tool 的依据
     inputSchema: {
       // 可选；无入参就不传
       path: z.string().describe("文件绝对路径"),
       limit: z.number().int().optional().describe("最多返回多少行"),
     },
   };
   ```

2. **挂进域 export**：在同文件末尾 `allXxxTools` 数组里加上它。

3. **挂进 index.ts**：在 `phase1Tools` 数组里加上 `...allXxxTools`（如果是新域）。

4. **跑全链**：`npm run typecheck && npm test`。

5. **冒烟**：`npm run build && node scripts/smoke.mjs`，看 tool 是否在 list
   里 + 调用一次确认结果正确。

## 编码约定

- **TypeScript strict + NodeNext**：所有 import 必须带 `.js` 后缀（NodeNext ESM 要求）。
- **stdout 是 MCP 协议流**：日志只往 `process.stderr.write(...)`，绝不 `console.log`。
- **parameter properties 防 TS2565**：构造里有 IIFE / 异步回调引用字段时，
  用 `constructor(private readonly name: string, ...)` 而非「先声明后赋值」。
- **错误映射策略**：
  - `SidecarRpcError`（业务级）→ MCP `isError: true` + sidecar 原 message（保留「问题在哪 + 怎么修」）
  - `SidecarFatalError`（进程死了）→ 抛出去让 transport 关闭，agent 立刻知道
- **inputSchema 是 zod raw shape**（`{key: z.string()}`），**不是** `z.object({...})`。
  每个字段挂 `.describe(...)`，agent 在选 tool / 填参时能看到。
- **MCP tool 名不允许 `.`**：MCP 规范 `[a-zA-Z0-9_-]+`。约定：RPC `foo.bar` →
  tool `foo_bar`。`validateMcpName` 启动时校验，违规直接抛。
- **SDK callback 两种签名**：有 `inputSchema` 是 `(args, extra) => result`，
  没 `inputSchema` 是 `(extra) => result`。`registerSidecarTool` 已按 `inputSchema`
  有无分支注册——别绕过它直接 `server.registerTool(...)`。

## 启动 / 调试

### Dev 模式（仓库内跑）

前提：

- `dotnet build` 跑过（dll 在 `dotnet/civ-doc/bin/Debug/net9.0/`）
- `uv` 装好且 `uv sync` 跑过

启动：

```bash
cd mcp
npm install              # 首次
npm run build            # 编译到 dist/
node dist/index.js       # 跑（stdio 等 MCP client）
```

冒烟自检：

```bash
node scripts/smoke.mjs   # 用 MCP Client SDK 跑一遍 list + ping + plot_curves
```

### 接 Claude Code

`~/.claude/mcp_servers.json`（或仓库的 `.claude/`）加：

```json
{
  "mcpServers": {
    "civ-core": {
      "command": "node",
      "args": ["D:\\CodeProjects\\civ-core\\mcp\\dist\\index.js"],
      "env": {
        "CIV_CORE_REPO_ROOT": "D:\\CodeProjects\\civ-core"
      }
    }
  }
}
```

环境变量 `CIV_CORE_REPO_ROOT` 显式指仓库根；不给的话会从 `dist/` 向上推断 sentinel。

### 排查

- **`无法定位 civ-core 仓库根`**：检查 `CIV_CORE_REPO_ROOT` 或确保 `dist/` 在仓库内。
- **`civ-doc.dll 不存在`**：`cd dotnet/civ-doc && dotnet build`。
- **`python RPC error: ... 'signal'`**：之前 registry callback 签名 bug，已修；如果再
  出现说明 SDK 升级又改了签名约定，查 `registerSidecarTool` 的分支。
- **MCP tool 没在 list 里**：检查 `index.ts` 的 `phase1Tools` 数组有没加进去。
- **stderr 里 sidecar 报错但本 MCP 没异常**：注意 `[csharp]` / `[python]` 前缀的行——
  那是 sidecar 自己打的日志，可能业务报错但当前 tool 没调它。

## 测试

```bash
npm test                 # vitest，跑 7 个单测（router + sidecar 客户端）
npm run typecheck        # tsc --noEmit
```

单测覆盖：路由前缀策略 + sidecar 客户端的回环 / 串行 / SidecarRpcError /
SidecarFatalError。MCP 协议层暂无单测——靠 `smoke.mjs` 端到端兜底。

## 不在本目录做

- **写业务逻辑**：所有计算 / IO 在 sidecar 里。本目录只做协议适配。
- **改 sidecar 进程模型**：spawn 方式跟 sidecar.rs 对齐，要改两边一起改。
- **加新 RPC 方法**：先在 sidecar 加 handler（C# 或 Python），再来这里包 MCP tool。
