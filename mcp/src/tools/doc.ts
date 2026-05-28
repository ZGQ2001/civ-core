/**
 * 探活类 MCP tool —— 给 agent 一个最便宜的链路自检入口。
 *
 * `doc.ping` / `doc.version` 是 C# sidecar 的自检方法（见 dotnet/civ-doc/Handlers/DocHandlers.cs）。
 * agent 刚连上 MCP server 时调一遍，确认链路（agent → MCP server → sidecar）三跳全通。
 */

import type { ToolDef } from "./registry.js";

export const docPing: ToolDef = {
  rpcMethod: "doc.ping",
  mcpName: "doc_ping",
  description:
    "C# sidecar 链路探活（无入参）。返回 sidecar 自报状态（pong 字段）。" +
    "用于在调用业务工具前确认 MCP server → C# sidecar 链路畅通。",
};

export const docVersion: ToolDef = {
  rpcMethod: "doc.version",
  mcpName: "doc_version",
  description:
    "C# sidecar 版本信息（无入参）。返回 sidecar 自报 {name, version, dotnet}。" +
    "排查环境/依赖问题时用。",
};

export const allDocTools: readonly ToolDef[] = [docPing, docVersion];
