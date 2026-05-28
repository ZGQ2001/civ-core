#!/usr/bin/env node
/**
 * civ-core MCP server 入口。
 *
 * 进程模型（参考 frontend/src-tauri/src/sidecar.rs）：
 *   1. 启动时 spawn 两个 sidecar 子进程
 *      - civ-doc（C# .NET 9）       — anchor / leeb / xlsx / files / pdf_tools / word2pdf ...
 *      - civ_core.api（Python 3.12）— plot_curves（matplotlib 无可替代）
 *   2. 创建 McpServer，按 ToolDef 注册 MCP tools；每个 tool 转发到 SidecarRouter
 *      （前缀路由：plot_curves.* → Python，其余 → C#）
 *   3. 用 StdioServerTransport 连 agent；本进程 stdout = MCP 协议流，stderr = 日志
 *
 * 当前进度（commit 3）：只注册探活 doc_ping / doc_version；commit 4-5 起逐步补 18 个工具。
 *
 * 仓库根定位：环境变量 CIV_CORE_REPO_ROOT 优先，否则从 dist/ 向上推断（见 lib/repoRoot.ts）。
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { resolveRepoRoot } from "./lib/repoRoot.js";
import { SidecarRouter } from "./router.js";
import { spawnCsharpDev, spawnPythonDev } from "./sidecar.js";
import { allAnchorTools } from "./tools/anchor.js";
import { allDocTools } from "./tools/doc.js";
import { registerSidecarTool } from "./tools/registry.js";
import { allWorkspaceTools } from "./tools/workspace.js";

const SERVER_NAME = "civ-core-mcp";
const SERVER_VERSION = "0.1.0";

async function main(): Promise<void> {
  const repoRoot = resolveRepoRoot();
  process.stderr.write(`[${SERVER_NAME}] repo root: ${repoRoot}\n`);

  // 起两个 sidecar。任一进程崩了 → JsonRpcSidecar 内置 stderr drain 会写出原因；
  // 路由到该 sidecar 的后续 tool 调用会 SidecarFatalError → MCP 致命错。
  const csharp = spawnCsharpDev(repoRoot);
  const python = spawnPythonDev(repoRoot);
  const router = new SidecarRouter(python, csharp);

  const server = new McpServer({
    name: SERVER_NAME,
    version: SERVER_VERSION,
  });

  // Phase 1 工具注册
  const phase1Tools = [...allDocTools, ...allWorkspaceTools, ...allAnchorTools];
  for (const def of phase1Tools) {
    registerSidecarTool(server, router, def);
  }

  // 优雅退出：杀子进程，否则会变成孤儿
  const cleanup = (): void => {
    process.stderr.write(`[${SERVER_NAME}] shutting down, killing sidecars...\n`);
    csharp.kill();
    python.kill();
  };
  process.on("SIGINT", () => {
    cleanup();
    process.exit(0);
  });
  process.on("SIGTERM", () => {
    cleanup();
    process.exit(0);
  });
  process.on("exit", cleanup);

  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write(
    `[${SERVER_NAME}] ready (stdio, ${phase1Tools.length} tools)\n`,
  );
  // 详细 tool 清单也写一份方便排查
  for (const t of phase1Tools) {
    process.stderr.write(`  - ${t.mcpName} → ${t.rpcMethod}\n`);
  }
}

main().catch((err: unknown) => {
  const detail = err instanceof Error ? err.stack ?? err.message : String(err);
  process.stderr.write(`[${SERVER_NAME}] fatal: ${detail}\n`);
  process.exit(1);
});
