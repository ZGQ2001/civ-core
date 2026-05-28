/**
 * workspace.* —— 工作区上下文 4 tool。
 *
 * agent 调任何装配线 tool 前应先确认 workspace 选好（workspace_last 拿到值
 * 或调 workspace_set 设一个）。输入输出文件最好放在工作区目录下，方便用户
 * 后续在 Tauri GUI 里 review 输出。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const workspaceLast: ToolDef = {
  rpcMethod: "workspace.last",
  mcpName: "workspace_last",
  description:
    "读取上次保存的工作区路径。无入参，返回 {path: string | null}。" +
    "null 表示从未设过——agent 应提示用户用 workspace_set 选一个工作区目录。",
};

export const workspaceSet: ToolDef = {
  rpcMethod: "workspace.set",
  mcpName: "workspace_set",
  description:
    "设置当前工作区路径。入参 path 必须是已存在的目录（绝对路径）。" +
    "返回 {ok, path}。后续装配线 tool 的输入输出文件建议放在工作区下。",
  inputSchema: {
    path: z.string().describe("工作区目录的绝对路径，必须已存在"),
  },
};

export const workspaceClear: ToolDef = {
  rpcMethod: "workspace.clear",
  mcpName: "workspace_clear",
  description:
    "清除已记忆的工作区。无入参，返回 {ok}。一般不用——除非要彻底重置或上次记的路径已删。",
};

export const workspaceCreateStandard: ToolDef = {
  rpcMethod: "workspace.create_standard",
  mcpName: "workspace_create_standard",
  description:
    "在 parent_dir 下新建一个标准 civ-core 项目骨架（4 个业务子目录 + .civ-core/）。" +
    "返回 {ok, path: 新建项目根目录}。name 不能含路径分隔符；目录必须不存在。" +
    "用户开新项目时调一次即可。",
  inputSchema: {
    parent_dir: z.string().describe("父目录绝对路径（必须已存在）"),
    name: z.string().describe("项目名（不含 / 和 \\）"),
  },
};

export const allWorkspaceTools: readonly ToolDef[] = [
  workspaceLast,
  workspaceSet,
  workspaceClear,
  workspaceCreateStandard,
];
