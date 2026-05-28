#!/usr/bin/env node
/**
 * civ-core MCP server 入口（脚手架阶段 — commit 1）。
 *
 * 设计参考 `frontend/src-tauri/src/sidecar.rs`：本进程作为 MCP server，
 * 通过 stdio 向 agent 暴露 tools；运行时 spawn 两个子 sidecar
 *   - civ-doc（C# .NET 9）       — anchor / leeb / xlsx / files / pdf_tools / word2pdf ...
 *   - civ_core.api（Python 3.12） — plot_curves（matplotlib 无可替代）
 * 并按方法前缀路由（默认 C#，白名单 Python）。
 *
 * 协议口径与 sidecar.rs 一致：stdin 一行 JSON-RPC 请求 / stdout 一行 JSON-RPC 响应；
 * stderr 透传到本进程 stderr（带 `[csharp]` / `[python]` 前缀）方便排查。
 *
 * 当前进度：commit 1 — 仅项目骨架 + tsc 跑通。
 * 下一步：commit 2 接入 JsonRpcSidecar 客户端；commit 3 起接入 MCP StdioServerTransport。
 */

function main(): void {
  // stdout 是 MCP 协议流（commit 3 起接 transport），脚手架阶段先不动 stdout。
  // 任何状态信息必须只走 stderr。
  process.stderr.write(
    "[civ-core-mcp] scaffold loaded (commit 1); sidecar wiring not yet implemented\n",
  );
}

main();
