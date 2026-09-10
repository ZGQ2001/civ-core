---
name: civ-core-mcp-tools
description: 做 civ-core 下一步候选 #1（把 sidecar 30+ RPC 暴露成 MCP server）的方法论。涉及 MCP server 建设、把 anchor.* / doc.* / pdf_tools.* / word2pdf.* / workspace.* / files.* / xlsx.* / plot_curves.* 任何 RPC 包成 MCP tool 时触发。给出 schema 推导、错误格式映射、进度通知、stdio vs SSE 选型。
---

# civ-core MCP server 建设

把 civ-core 的双 sidecar 30+ JSON-RPC 方法暴露成标准 MCP server，让 Claude / Codex / Cursor 等 agent 原生调用。

## 出发点

civ-core 已有 JSON-RPC over stdin/stdout 协议层。MCP 协议设计上跟它**90% 同构**：

| JSON-RPC（civ-core 现状） | MCP |
|--------------------------|-----|
| `method: "anchor.run"` | `tool.call("anchor.run", ...)` |
| `params: {input_xlsx, ...}` | `arguments: {input_xlsx, ...}` |
| `result: {batches, anchors_total, ...}` | `content: [{type: "text", text: "..."}]` |
| JSON-RPC error code | MCP error 格式 |
| `Console.Error.WriteLine` 日志 | MCP `notifications/message` |

所以**架构上是一个薄薄的协议适配层**，不重写业务。

## 选型决策

| 维度 | 推荐 | 理由 |
|------|------|------|
| 语言 | C# / TypeScript / Python | C# 复用 dispatcher，零跨语言；TS 单独 server 进程，弱耦合；Python sidecar 已存在但小 |
| 协议 | stdio | 跟 civ-core sidecar 风格一致，agent 启动一个子进程就用 |
| 入口位置 | 新加 `dotnet/civ-mcp/`（独立项目） | 不污染 sidecar；future Tauri 可选启动 |
| RPC 复用 | 进程内调 `Dispatcher` | 不要再起 sidecar 子进程，性能 + 错误传播都好 |

## 实施步骤（每步可独立 commit）

### Step 1：建项目骨架
```
dotnet/
├── civ-doc/                 # 现有 sidecar
└── civ-mcp/                 # 新 MCP server
    ├── civ-mcp.csproj       # net9.0, 引 ModelContextProtocol NuGet
    ├── Program.cs           # stdio loop + MCP handshake
    └── McpServer.cs         # tool list + tool call dispatch
```

`civ-mcp.csproj` 引用 `civ-doc.csproj`（复用 Dispatcher / Handlers）。

### Step 2：tool list 注册
每个 sidecar RPC 包成一个 MCP tool。schema 从 handler 入参手动写：

```csharp
new Tool {
    Name = "anchor_run",                              // MCP 用下划线
    Description = "运行锚杆抗拔计算（GB 50086-2015），输入 Excel + 工程参数 → 出数据分析 + 可选 Word 报告",
    InputSchema = new {
        type = "object",
        properties = new {
            input_xlsx = new { type = "string", description = "锚杆数据 Excel 绝对路径" },
            standard = new { type = "string", @enum = new[] { "GB 50086-2015" } },
            params_by_batch = new { type = "object", description = "..." },
            // ...
        },
        required = new[] { "input_xlsx", "params_by_batch" }
    }
}
```

### Step 3：tool call dispatch
调到现有 `Dispatcher`：

```csharp
async Task<CallToolResult> HandleToolCall(string name, JsonElement args) {
    var rpcMethod = name.Replace('_', '.');  // anchor_run → anchor.run
    try {
        var result = await dispatcher.InvokeAsync(rpcMethod, args);
        return new CallToolResult {
            Content = new[] { new TextContent { Text = JsonSerializer.Serialize(result) } }
        };
    } catch (ArgumentException e) {
        // 用户级错误 → MCP isError = true，但不抛
        return new CallToolResult { IsError = true, Content = new[] { new TextContent { Text = e.Message } } };
    }
}
```

### Step 4：进度通知
sidecar 现在的 `Console.Error.WriteLine` 日志映射到 MCP `notifications/message`，agent 能看到进度。

### Step 5：测试 + 接 Claude Code
- 单元测试用 ModelContextProtocol SDK 的 test client
- 端到端：写一个 `claude_mcp.json` 配置，让本地 Claude Code 连上跑 anchor.run

## 错误格式标准（对齐 civ-core 原则）

civ-core 的「错误信息告诉用户问题在哪 + 怎么修」 → MCP 里也要遵守：

❌ 不好：`ArgumentException: 'input_xlsx' 必须是字符串`
✅ 好：`找不到输入 Excel 文件：D:\xxx.xlsx — 请检查路径是否拼写正确、文件是否存在`

## 跟内置 mcp-builder skill 的关系

`anthropic-skills:mcp-builder` 是通用方法论，本 skill 是 civ-core 专属落地。两个一起激活：mcp-builder 给「怎么写 MCP server」通用规范，本 skill 给「civ-core 具体怎么对接」。

## 相关 skill

- `anthropic-skills:mcp-builder` — 通用 MCP server 规范
- [[civ-core-dev]] — 项目架构
- [[civ-core-debug-rpc]] — 协议层调试
- [[dotnet-io-pipelines]] — stdio 高性能 I/O
