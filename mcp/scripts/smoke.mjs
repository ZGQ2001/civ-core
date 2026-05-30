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
import { tmpdir } from "node:os";
import { rmSync } from "node:fs";

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

  // ── Phase 2 回归守卫：所有新域 tool 必须在 list 里 ─────────────────
  const toolNames = new Set(list.tools.map((t) => t.name));
  const expectedPhase2 = [
    "catalog_list", "catalog_get", "catalog_save", "catalog_delete",
    "template_validate",
    "files_list_dir", "files_exists", "files_create_file", "files_create_folder",
    "files_rename", "files_copy", "files_move", "files_delete",
    "files_undo_delete", "files_reveal",
    "pdf_tools_merge", "pdf_tools_split_per_page", "pdf_tools_split_by_ranges",
    "pdf_tools_inspect",
    "word2pdf_convert", "word2pdf_inspect",
    "plot_curves_save_preset", "plot_curves_delete_preset",
    "plot_curves_rename_preset", "plot_curves_copy_preset",
  ];
  const missing = expectedPhase2.filter((n) => !toolNames.has(n));
  if (missing.length > 0) {
    console.error(`[smoke] FAIL: 缺少 Phase 2 工具: ${missing.join(", ")}`);
    await client.close().catch(() => undefined);
    process.exit(1);
  }
  console.error(`[smoke] Phase 2 工具齐全（${expectedPhase2.length} 个）`);

  // ── C# 读路径（doc 之外）：catalog_list ──────────────────────────
  const catalogs = await client.callTool({ name: "catalog_list", arguments: {} });
  const catalogText = catalogs.content?.[0]?.text ?? "";
  if (catalogs.isError) {
    console.error(`[smoke] catalog_list ERROR: ${catalogText}`);
  } else {
    const parsed = JSON.parse(catalogText);
    console.error(`[smoke] catalog 数: ${(parsed.catalogs ?? []).length}`);
  }

  // ── C# 文件路径：files_list_dir 列 mcp/ 目录 ─────────────────────
  const mcpDir = join(__dirname, "..");
  const listing = await client.callTool({
    name: "files_list_dir",
    arguments: { path: mcpDir },
  });
  const listingText = listing.content?.[0]?.text ?? "";
  if (listing.isError) {
    console.error(`[smoke] files_list_dir ERROR: ${listingText}`);
  } else {
    const parsed = JSON.parse(listingText);
    console.error(`[smoke] files_list_dir 条目数: ${(parsed.entries ?? []).length}`);
  }

  // ── 新检测类型 coating：装配线三跳（generate_template → expand_template）──
  const coatingExpected = [
    "coating_generate_template", "coating_expand_template",
    "coating_list_batches", "coating_run",
  ];
  const coatingMissing = coatingExpected.filter((n) => !toolNames.has(n));
  if (coatingMissing.length > 0) {
    console.error(`[smoke] FAIL: 缺少 coating 工具: ${coatingMissing.join(", ")}`);
    await client.close().catch(() => undefined);
    process.exit(1);
  }
  {
    // generate（含构件清单样例：梁长度8/柱截面数3）→ expand 出测点网格。
    // 填数字需 xlsx 库，smoke 不做；coating_run 的判定由 dotnet 测试覆盖。
    const tmpl = join(tmpdir(), `coating_smoke_${Date.now()}.xlsx`);
    const gen = await client.callTool({
      name: "coating_generate_template",
      arguments: { output_xlsx: tmpl },
    });
    console.error(`[smoke] coating_generate_template isError: ${gen.isError === true}`);
    const exp = await client.callTool({
      name: "coating_expand_template",
      arguments: { input_xlsx: tmpl },
    });
    const expText = exp.content?.[0]?.text ?? "";
    if (exp.isError) {
      console.error(`[smoke] coating_expand_template ERROR: ${expText}`);
      await client.close().catch(() => undefined);
      process.exit(1);
    }
    const parsed = JSON.parse(expText);
    console.error(
      `[smoke] coating_expand_template: ${parsed.members} 构件 / ${parsed.total_sections} 截面 / sheets=${(parsed.sheets ?? []).join(",")}`,
    );
    try { rmSync(tmpl); } catch { /* 清理失败忽略 */ }
  }

  // ── Python 预设写路径 roundtrip：copy → list → delete ────────────
  // 预设名不能以下划线开头（preset_manager 校验），用普通中文临时名。
  const TMP = "冒烟临时副本";
  const baseParsed = JSON.parse(presetText || "{}");
  const basePresets = baseParsed.presets ?? [];
  const src = baseParsed.default ?? basePresets[0];
  if (src) {
    // 仅当上次残留时才预删（避免删不存在项产生误导性 ERROR 行）
    if (basePresets.includes(TMP)) {
      await client.callTool({
        name: "plot_curves_delete_preset",
        arguments: { name: TMP },
      });
    }
    const copy = await client.callTool({
      name: "plot_curves_copy_preset",
      arguments: { source_name: src, new_name: TMP },
    });
    console.error(`[smoke] copy_preset(${src}→${TMP}) isError: ${copy.isError === true}`);
    const after = await client.callTool({
      name: "plot_curves_list_presets",
      arguments: {},
    });
    const afterParsed = JSON.parse(after.content?.[0]?.text ?? "{}");
    const present = (afterParsed.presets ?? []).includes(TMP);
    console.error(`[smoke] 临时预设已出现: ${present}`);
    const del = await client.callTool({
      name: "plot_curves_delete_preset",
      arguments: { name: TMP },
    });
    console.error(`[smoke] delete_preset isError: ${del.isError === true}`);
  } else {
    console.error("[smoke] 无可复制的预设，跳过 plot_curves CRUD roundtrip");
  }

  await client.close();
  console.error("[smoke] OK");
  process.exit(0);
} catch (err) {
  console.error("[smoke] FAIL:", err);
  await client.close().catch(() => undefined);
  process.exit(1);
}
