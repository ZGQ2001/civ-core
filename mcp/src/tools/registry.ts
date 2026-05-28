/**
 * Tool 注册框架 —— 把一个 sidecar RPC 方法包成一个 MCP tool。
 *
 * 一个 ToolDef 描述：
 *   - rpcMethod  sidecar 端 JSON-RPC method 名（带点：`anchor.run`）
 *   - mcpName    MCP tool 名（不能含点；下划线分隔：`anchor_run`）
 *   - description 给 agent 看的「做什么 + 入参口径」（agent 选 tool 的依据）
 *   - inputSchema zod raw shape（可选；空对象等价无入参）
 *
 * 错误映射策略（对齐 civ-core「问题在哪 + 怎么修」）：
 *   - SidecarRpcError → MCP `isError: true` + 原始 message（业务级，agent 看得到，能继续）
 *   - SidecarFatalError → 抛出去（致命，让 transport 关闭，agent 知道 server 死了）
 *   - 其他 Error → `isError: true` 兜底（理论上不该到这里）
 *
 * 结果格式：result 序列化成 JSON text 放进 `content[0].text`。
 * 后续可以加 structuredContent 字段（MCP 1.x 支持，给 agent 结构化拿值），先 text 一把梭。
 */

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { ZodRawShape } from "zod";
import { SidecarFatalError, SidecarRpcError } from "../sidecar.js";
import type { SidecarRouter } from "../router.js";

export interface ToolDef {
  rpcMethod: string;
  mcpName: string;
  description: string;
  inputSchema?: ZodRawShape;
}

/** sanity check：MCP tool 名必须 `[a-zA-Z0-9_-]+`（不允许 `.`）。 */
function validateMcpName(name: string): void {
  if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
    throw new Error(
      `MCP tool 名非法：${name}（只允许 [a-zA-Z0-9_-]+，不能含点/空格）`,
    );
  }
}

/** 转发 + 错误映射的核心，给两种 callback 签名共用。 */
async function invokeAndWrap(
  router: SidecarRouter,
  rpcMethod: string,
  params: Record<string, unknown>,
): Promise<{ content: Array<{ type: "text"; text: string }>; isError?: boolean }> {
  try {
    const result = await router.call(rpcMethod, params);
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  } catch (err) {
    if (err instanceof SidecarFatalError) throw err;
    const msg =
      err instanceof SidecarRpcError
        ? err.message
        : err instanceof Error
          ? err.message
          : String(err);
    return {
      content: [{ type: "text", text: msg }],
      isError: true,
    };
  }
}

export function registerSidecarTool(
  server: McpServer,
  router: SidecarRouter,
  def: ToolDef,
): void {
  validateMcpName(def.mcpName);

  // SDK 的 callback 签名取决于 inputSchema 有无：
  //   - 有 schema：(args, extra) => result   ← 第一个参数是验证后的 args
  //   - 无 schema：(extra) => result          ← 只有 extra（含 signal 等元数据）
  // 这两种必须分支注册，否则无 schema 时把 extra 当 args 转发 → 把 AbortSignal
  // 当 RPC 入参塞给 sidecar，Python 端 list_presets() 收到非法 kw 报错。
  if (def.inputSchema) {
    server.registerTool(
      def.mcpName,
      { description: def.description, inputSchema: def.inputSchema },
      async (args: Record<string, unknown>) =>
        invokeAndWrap(router, def.rpcMethod, args ?? {}),
    );
  } else {
    server.registerTool(
      def.mcpName,
      { description: def.description },
      async () => invokeAndWrap(router, def.rpcMethod, {}),
    );
  }
}
