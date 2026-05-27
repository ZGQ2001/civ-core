---
name: civ-core-debug-rpc
description: civ-core 双 sidecar JSON-RPC 协议层 / dispatcher / handler 排查 SOP。涉及"未知 method"、sidecar 启动失败、stdin/stdout 协议被污染、前端按钮没反应、handler 入参解析失败、跨 sidecar 状态不一致时触发。
---

# sidecar / RPC 调试 SOP

civ-core 协议：JSON-RPC 2.0 over stdin/stdout，前缀路由（`SidecarRouter`），默认 C# / 白名单 Python。

## 三层诊断法（按这个顺序排）

### 第 1 层：路由
看 `frontend/src-tauri/src/sidecar.rs` 里 `is_python_method()` 函数对这个 method 返回 true/false 是否正确。

- 走 C# 默认路由的方法 → 返回 false
- 走 Python 白名单的方法（`ping` / `version` / `plot_curves.*`） → 返回 true

错配症状：method 被发到错的 sidecar，对方报"未知 method"。

### 第 2 层：注册
- **C# 端**：`Program.cs` 里有没有 `<X>Handlers.RegisterAll(dispatcher)`？handler 类里有没有 `dispatcher.Register("xxx.method", Method)`？
- **Python 端**：`api/__main__.py` 的 `build_dispatcher()` 里有没有 `d.register_module("xxx", handlers.xxx)`？

### 第 3 层：handler 实现
- **C# 端**：方法签名 `static object? Method(JsonElement? @params)`，入参解析对吗？必填字段缺了会抛 `ArgumentException`，看错误文案。
- **Python 端**：handler 模块顶部有 `__all__ = [...]` 吗？（CLAUDE.md 不可变规则 2）没写会把 `import Path` 之类暴露成 RPC。

## 最可能的根因（按概率排）

| 症状 | 最可能根因 | 验证方式 |
|------|---------|---------|
| "未知 method: xxx.yyy" | 第 2 层没注册 OR CI 跑的 commit 不是 main 最新 | grep `Register.*"xxx.yyy"`；看 CI log 的 commit SHA |
| 前端按钮点了没反应 | `run()` 没 return 值（HandleRun stale closure） | 看 `controller.tsx` 的 `run()` 末尾是不是 `return res` 而不是 `setResult(res)` |
| sidecar 启动后立刻退出 | stdout 被业务代码写日志了 | grep `Console.WriteLine` / `print(` 在非测试代码里——必须改成 stderr |
| 入参 `null` exception | 前端 `params` 没传或字段名拼错 | 后端先打日志 `Console.Error.WriteLine($"params: {@params}")`；前端查 `rpc(...)` 调用 |
| 中文路径报错 | Windows + 中文 + PowerShell 编码问题 | Bash 命令路径用单引号包；PowerShell 命令用 `-EncodedCommand` base64 |
| handler 返回但前端拿到 null | C# `return new {...}` 字段名 lowercase，前端 TS 期望 PascalCase | 检查 `JsonSerializer` 配置 / 前端类型 |

## 调试武器（按侵入度从低到高）

1. **stderr 日志**：handler 里加 `Console.Error.WriteLine($"...");`，跑 Tauri dev 看终端
2. **手动调 sidecar**：绕过 Tauri，直接 echo JSON 给 sidecar 进程
   ```bash
   echo '{"jsonrpc":"2.0","id":1,"method":"anchor.list_batches","params":{...}}' \
     | dotnet/civ-doc/bin/Debug/net9.0/civ-doc.exe
   ```
3. **xUnit handler 测试**：`dotnet test --filter "FullyQualifiedName~XxxHandlersTests"`，参考 [AnchorHandlersTests.cs](dotnet/civ-doc.Tests/AnchorHandlersTests.cs) 范式
4. **前端 RPC 拦截**：`frontend/src/lib/rpc.ts` 里临时 `console.log(method, params, result)`

## 常见陷阱（用户/我历史踩过的）

### 1. HandleRun stale closure（前端 controller）
**症状**：`appendOutput` 永远不触发，结果显示 null。

**根因**：`handleRun` 里 `await c.run()` 之后从 `c.result` 读结果。`c` 在 render closure 里捕获，state 更新异步，外部读永远是旧值。

**修复**：`run()` 必须 `return res`，不准靠 `setState`：
```tsx
// ❌ 错
async function handleRun() {
  await c.run();
  if (c.result) appendOutput(c.result);  // 永远 null
}

// ✅ 对
async function handleRun() {
  const res = await c.run();
  if (res) appendOutput(res);
}
```

### 2. CI 跑的是旧 commit
**症状**：本地代码看着对，CI 报错。

**根因**：CI auto-fix commit 顺序、PR 合并顺序、webhook 滞后。

**修复**：在 CI log 里找跑的 commit SHA，跟 `git log` 对照。

### 3. Prettier mismatch 大规模重排
**症状**：CI 自动 commit 重排 200+ 行格式。

**根因**：本地 prettier 版本/配置跟 CI 不一致。

**修复**：本地先跑 `npm run format:check`；pin prettier 版本。

### 4. word2pdf COM 在 Linux 起不来
**症状**：CI 在 Linux runner 跑 word2pdf 测试爆。

**根因**：COM 是 Windows-only。

**修复**：xUnit 用 `[Fact(Skip="Windows only")]` 跳过 Linux；或在 setup 里 `OSPlatform.IsWindows()` 判断。

### 5. stale test after refactor
**症状**：refactor 后 CI `ImportError`/`MissingMethodException`。

**根因**：源代码删了，测试没跟着删。

**修复**：refactor 删 symbol 后跑 `grep -rn "<symbol>" tests/`，清理 stale。

## 不要做

- 不要为绕过 CI 失败 commit `--no-verify`（CLAUDE.md 行为准则）
- 不要因为 sidecar 启动失败就重写——99% 是协议流被污染或注册没做
- 不要相信"代码看着对"——CI 报错就是真错，先看 CI 跑的 commit

## 相关 skill

- [[civ-core-dev]] — 项目工作流入口
- [[civ-core-mcp-tools]] — MCP server 协议层（类似 RPC 的扩展）
- [[anti-narrative-execution]] — 不要说"修好了"除非看到测试通过
