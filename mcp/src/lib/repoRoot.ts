/**
 * 解析 civ-core 仓库根目录。
 *
 * 优先级：
 *   1. 环境变量 `CIV_CORE_REPO_ROOT`（agent 配置 MCP server 时显式给）
 *   2. 从本文件位置向上找 `dotnet/civ-doc/civ-doc.csproj`（dev 模式直接跑 dist/ 时用）
 *
 * 失败时抛清晰错误——「问题在哪 + 怎么修」原则。
 */

import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SENTINEL = join("dotnet", "civ-doc", "civ-doc.csproj");
const MAX_LEVELS = 8;

export function resolveRepoRoot(): string {
  const envRoot = process.env["CIV_CORE_REPO_ROOT"];
  if (envRoot) {
    if (!existsSync(join(envRoot, SENTINEL))) {
      throw new Error(
        `CIV_CORE_REPO_ROOT=${envRoot} 不像 civ-core 仓库（找不到 ${SENTINEL}）。\n` +
          `请把它指向仓库根目录（包含 dotnet/ frontend/ mcp/ 那一层）。`,
      );
    }
    return envRoot;
  }

  const here = dirname(fileURLToPath(import.meta.url));
  let cur = here;
  for (let i = 0; i < MAX_LEVELS; i++) {
    if (existsSync(join(cur, SENTINEL))) return cur;
    const parent = dirname(cur);
    if (parent === cur) break; // 到磁盘根
    cur = parent;
  }
  throw new Error(
    `无法定位 civ-core 仓库根（向上找 ${SENTINEL} 失败）。\n` +
      `查找起点：${here}\n` +
      `请设置环境变量 CIV_CORE_REPO_ROOT 指向仓库根。`,
  );
}
