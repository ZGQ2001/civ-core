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
 * 工具覆盖：Phase 1 装配线核心 + Phase 2（catalog / template.validate / files /
 * pdf_tools / word2pdf / plot_curves 预设 CRUD），基本与 sidecar RPC 全表对齐。
 *
 * 仓库根定位：环境变量 CIV_CORE_REPO_ROOT 优先，否则从 dist/ 向上推断（见 lib/repoRoot.ts）。
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { resolveRepoRoot } from "./lib/repoRoot.js";
import { SidecarRouter } from "./router.js";
import { spawnCsharpDev, spawnPythonDev } from "./sidecar.js";
import { allAnchorTools } from "./tools/anchor.js";
import { allCatalogTools } from "./tools/catalog.js";
import { allCoatingTools } from "./tools/coating.js";
import { allDocTools } from "./tools/doc.js";
import { allFilesTools } from "./tools/files.js";
import { allLeebTools } from "./tools/leeb.js";
import { allPdfToolsTools } from "./tools/pdfTools.js";
import { allPlotCurvesTools } from "./tools/plot_curves.js";
import { registerSidecarTool } from "./tools/registry.js";
import { allReportTools } from "./tools/report.js";
import { allReportPresetTools } from "./tools/reportPreset.js";
import { allTemplateTools } from "./tools/template.js";
import { allWord2PdfTools } from "./tools/word2pdf.js";
import { allWorkspaceTools } from "./tools/workspace.js";
import { allXlsxTools } from "./tools/xlsx.js";

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

  // 工具注册：与 sidecar RPC 全表对齐（除 calc 类型 stub）。
  // doc 2 / workspace 4 / anchor 4 / coating 4 / leeb 2 / xlsx 1 / template 2 / report 2 /
  // report_preset 5 / catalog 4 / files 10 / pdf_tools 4 / word2pdf 2 / plot_curves 10。
  const allTools = [
    ...allDocTools,
    ...allWorkspaceTools,
    ...allAnchorTools,
    ...allCoatingTools,
    ...allLeebTools,
    ...allXlsxTools,
    ...allTemplateTools,
    ...allReportTools,
    ...allReportPresetTools,
    ...allCatalogTools,
    ...allFilesTools,
    ...allPdfToolsTools,
    ...allWord2PdfTools,
    ...allPlotCurvesTools,
  ];
  for (const def of allTools) {
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
    `[${SERVER_NAME}] ready (stdio, ${allTools.length} tools)\n`,
  );
  // 详细 tool 清单也写一份方便排查
  for (const t of allTools) {
    process.stderr.write(`  - ${t.mcpName} → ${t.rpcMethod}\n`);
  }
}

main().catch((err: unknown) => {
  const detail = err instanceof Error ? err.stack ?? err.message : String(err);
  process.stderr.write(`[${SERVER_NAME}] fatal: ${detail}\n`);
  process.exit(1);
});
