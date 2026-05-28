#!/usr/bin/env node
/**
 * 端到端冒烟：用 MCP Client SDK 驱动本仓库的 MCP server，跑 tools/list +
 * doc_ping + doc_version，验证 agent → MCP server → C# sidecar 三跳通畅。
 *
 * 用法：
 *   1. 先 build：cd mcp && npm run build
 *   2. 先确保 C# sidecar 已编译：cd dotnet/civ-doc && dotnet build
 *   3. 跑本脚本：node mcp/scripts/smoke.mjs
 *
 * 成功条件：tools/list 返回 doc_ping + doc_version；doc_ping 调用 isError=false 且
 * content[0].text 解析出有 pong/ok 字段。
 */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const serverPath = join(__dirname, "..", "dist", "index.js");

const transport = new StdioClientTransport({
  command: process.execPath,
  args: [serverPath],
  stderr: "inherit", // 让 server 的 stderr 透传到本进程，方便看 sidecar 启动日志
});

const client = new Client({ name: "smoke-driver", version: "0.0.1" }, { capabilities: {} });

try {
  await client.connect(transport);
  console.error("[smoke] connected");

  const list = await client.listTools();
  console.error(`[smoke] tools/list 返回 ${list.tools.length} 个:`);
  for (const t of list.tools) {
    console.error(`  - ${t.name}: ${t.description?.slice(0, 60) ?? ""}`);
  }

  const pong = await client.callTool({ name: "doc_ping", arguments: {} });
  console.error("[smoke] doc_ping isError:", pong.isError === true);
  console.error("[smoke] doc_ping content:", JSON.stringify(pong.content));

  const ver = await client.callTool({ name: "doc_version", arguments: {} });
  console.error("[smoke] doc_version content:", JSON.stringify(ver.content));

  // 验证 Python sidecar 路由也通：plot_curves_list_presets 走 plot_curves.* 白名单 → Python
  const presets = await client.callTool({
    name: "plot_curves_list_presets",
    arguments: {},
  });
  const presetText = presets.content?.[0]?.text ?? "";
  if (presets.isError) {
    console.error(`[smoke] plot_curves_list_presets ERROR: ${presetText}`);
  } else {
    const parsed = JSON.parse(presetText);
    const presetNames = parsed.presets ?? [];
    console.error(
      `[smoke] plot_curves 预设数: ${presetNames.length}（前 3：${presetNames.slice(0, 3).join(", ")}）`,
    );
  }

  await client.close();
  console.error("[smoke] OK");
  process.exit(0);
} catch (err) {
  console.error("[smoke] FAIL:", err);
  await client.close().catch(() => undefined);
  process.exit(1);
}
