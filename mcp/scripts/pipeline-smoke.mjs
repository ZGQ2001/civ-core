#!/usr/bin/env node
/** 样例端到端验收：MCP → 双 sidecar → Excel → PNG → 混合 Word 报告。 */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../..");
const output = process.argv[2] ? resolve(process.argv[2]) : mkdtempSync(join(tmpdir(), "civ-pipeline-"));
// 显式路径必须是新目录，防止覆盖已有业务文件。
if (process.argv[2]) mkdirSync(output);
const file = (name) => join(output, name);
const client = new Client({ name: "pipeline-smoke", version: "1.0.0" });
const transport = new StdioClientTransport({
  command: process.execPath,
  args: [join(here, "../dist/index.js")],
  stderr: "inherit",
});
const evidence = { kind: "synthetic-fixture", output, steps: {} };

async function call(name, args = {}) {
  const result = await client.callTool({ name, arguments: args });
  assert.ok(!result.isError, `${name}: ${JSON.stringify(result.content)}`);
  const data = JSON.parse(result.content[0].text);
  evidence.steps[name] = data;
  console.error(`[pipeline] ${name}: OK`);
  return data;
}

function fixtures(mode) {
  const r = spawnSync("uv", ["run", "--frozen", "python", join(here, "pipeline-fixtures.py"), mode, output], {
    cwd: repo, encoding: "utf8", timeout: 60_000,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  assert.equal(r.status, 0, `${mode}: ${r.error ?? ""}\n${r.stderr}\n${r.stdout}`);
  if (r.stdout) console.error(r.stdout.trim());
}

try {
  await client.connect(transport);
  assert.equal(await call("doc_ping"), "pong");
  await call("anchor_generate_template", { output_xlsx: file("anchor-input.xlsx") });
  const anchor = await call("anchor_run", {
    input_xlsx: file("anchor-input.xlsx"), output_xlsx: file("anchor-result.xlsx"),
  });
  assert.equal(anchor.anchors_total, 3);
  assert.equal(anchor.anchors_qualified, 1);

  const columns = ["0.1Nt", "0.4Nt", "0.7Nt", "1.0Nt", "1.2Nt-5min", "卸载1.0Nt", "卸载0.7Nt", "卸载0.4Nt", "卸载0.1Nt"];
  const loads = [18, 72, 126, 180, 216, 180, 126, 72, 18];
  const preset = {
    id_column: "锚杆编号", filename_template: "{id}.png", title_template: "锚杆{id} 荷载-位移曲线",
    x_axis: { label: "位移 / mm", range: null }, y_axis: { label: "荷载 / kN", range: null },
    curves: [{ name: "加载-卸载", points: columns.map((column, i) => ({ var_column: column, fixed_axis: "y", fixed_value: loads[i] })) }],
  };
  const available = await call("plot_curves_list_presets");
  assert.ok(available.presets.length > 0, "至少需要一个系统曲线预设");
  const curves = await call("plot_curves_run", {
    excel_path: file("anchor-input.xlsx"), preset: available.default ?? available.presets[0], preset_override: preset,
    output_dir: file("curves"), filename_prefix: "批次1_", output_format: "png",
  });
  assert.equal(curves.failed.length, 0);
  assert.equal(curves.written.length, 3);
  for (const png of curves.written) assert.equal(readFileSync(png).subarray(0, 8).toString("hex"), "89504e470d0a1a0a");

  await call("coating_generate_template", { output_xlsx: file("coating-input.xlsx") });
  await call("coating_expand_template", { input_xlsx: file("coating-input.xlsx") });
  fixtures("prepare");
  const coating = await call("coating_run", {
    input_xlsx: file("coating-input.xlsx"), output_xlsx: file("coating-result.xlsx"),
  });
  assert.equal(coating.members_total, 2);
  assert.equal(coating.members_qualified, 2);
  const report = await call("report_assemble", {
    word_template_path: file("template.docx"), output_docx: file("combined-report.docx"),
    user_inputs: { project_name: "自动化验收工程" },
    sections: [
      { type: "anchor", result_xlsx: file("anchor-result.xlsx"), curve_image_dir: file("curves") },
      { type: "coating", result_xlsx: file("coating-result.xlsx") },
    ],
  });
  assert.equal(report.tables, 5);
  assert.deepEqual(report.unknown_keys, []);
  assert.deepEqual(report.missing_images, []);
  fixtures("verify");
  evidence.status = "passed";
  console.error(`[pipeline] PASS: ${output}`);
} catch (error) {
  evidence.status = "failed";
  evidence.error = String(error);
  console.error(`[pipeline] FAIL: ${error.stack ?? error}`);
  process.exitCode = 1;
} finally {
  writeFileSync(file("evidence.json"), JSON.stringify(evidence, null, 2));
  await client.close();
}
