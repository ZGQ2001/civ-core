/**
 * files.* —— 工作区文件管理：列目录 / 存在性 / 增删改 / 复制移动 / 在系统打开。
 *
 * 让经 MCP 连进来的 agent（自身可能没有文件系统访问）也能管理工作区文件，
 * 跑完整装配线不用绕 Tauri / 本地 shell。
 *
 * 入参 schema 跟 dotnet/civ-doc/Handlers/FilesHandlers.cs 一一对照。
 * 平台说明：delete / undo_delete / reveal 仅 Windows（C# 端按 OS 条件注册 + 抛
 * PlatformNotSupported）；其余跨平台。
 */

import { z } from "zod";
import type { ToolDef } from "./registry.js";

export const filesListDir: ToolDef = {
  rpcMethod: "files.list_dir",
  mcpName: "files_list_dir",
  description:
    "列目录内容。返回 {entries: [{name, path, is_dir, size, mtime}]}（目录排前 + 自然排序）。" +
    "缺省隐藏 .开头的项与 .civ-core 元目录。",
  inputSchema: {
    path: z.string().describe("目录绝对路径"),
    show_hidden: z
      .boolean()
      .optional()
      .describe("是否显示隐藏项（.开头 / .civ-core），缺省 false"),
  },
};

export const filesExists: ToolDef = {
  rpcMethod: "files.exists",
  mcpName: "files_exists",
  description:
    "检查路径是否存在及类型。返回 {exists, is_dir, is_file}。",
  inputSchema: {
    path: z.string().describe("待检查的绝对路径"),
  },
};

export const filesCreateFile: ToolDef = {
  rpcMethod: "files.create_file",
  mcpName: "files_create_file",
  description:
    "在已存在的父目录下创建一个空文件。返回 {path}。" +
    "父目录不存在 / 同名已存在 / 文件名非法（Windows 名校验）会报错。",
  inputSchema: {
    parent: z.string().describe("父目录绝对路径（必须已存在）"),
    name: z.string().describe("新文件名（含扩展名，如 '数据.xlsx'）"),
  },
};

export const filesCreateFolder: ToolDef = {
  rpcMethod: "files.create_folder",
  mcpName: "files_create_folder",
  description:
    "在已存在的父目录下创建文件夹。返回 {path}。同名已存在 / 名称非法会报错。",
  inputSchema: {
    parent: z.string().describe("父目录绝对路径（必须已存在）"),
    name: z.string().describe("新文件夹名"),
  },
};

export const filesRename: ToolDef = {
  rpcMethod: "files.rename",
  mcpName: "files_rename",
  description:
    "同目录内改名（文件或文件夹）。返回 {path}（改名后绝对路径）。" +
    "目标名已存在会报错；新名等于旧名直接返回原路径。",
  inputSchema: {
    path: z.string().describe("待改名的绝对路径"),
    new_name: z.string().describe("新名称（仅文件名，不含目录）"),
  },
};

export const filesCopy: ToolDef = {
  rpcMethod: "files.copy",
  mcpName: "files_copy",
  description:
    "复制文件或文件夹（文件夹递归）到目标目录。返回 {path}（实际落地路径）。" +
    "目标目录已有同名时自动追加 (2)/(3)，不覆盖。",
  inputSchema: {
    src: z.string().describe("源文件/文件夹绝对路径"),
    dst_parent: z.string().describe("目标父目录绝对路径（必须已存在）"),
  },
};

export const filesMove: ToolDef = {
  rpcMethod: "files.move",
  mcpName: "files_move",
  description:
    "移动文件或文件夹到目标目录。返回 {path}（移动后绝对路径）。" +
    "同名自动追加 (2)/(3)；源父目录==目标目录时直接返回原路径（空操作）。",
  inputSchema: {
    src: z.string().describe("源文件/文件夹绝对路径"),
    dst_parent: z.string().describe("目标父目录绝对路径（必须已存在）"),
  },
};

export const filesDelete: ToolDef = {
  rpcMethod: "files.delete",
  mcpName: "files_delete",
  description:
    "把文件/文件夹发送到回收站（不是永久删除，可在 5 分钟内用 files_undo_delete 还原）。返回 {ok}。" +
    "\n\n⚠️ 仅 Windows——其它平台该方法未注册，调用会报方法不存在。",
  inputSchema: {
    path: z.string().describe("待删除的绝对路径"),
  },
};

export const filesUndoDelete: ToolDef = {
  rpcMethod: "files.undo_delete",
  mcpName: "files_undo_delete",
  description:
    "从回收站还原最近一次 files_delete 删掉的项（5 分钟内有效，走 Shell COM）。" +
    "返回 {restored_path, parent}。" +
    "\n\n⚠️ 仅 Windows。无入参。",
};

export const filesReveal: ToolDef = {
  rpcMethod: "files.reveal",
  mcpName: "files_reveal",
  description:
    "在 Windows 资源管理器里定位并选中该文件/文件夹（explorer /select）。返回 {ok}。" +
    "\n\n⚠️ 仅 Windows，且是给「旁边有人盯着屏幕」用的——纯无头 agent 看不到弹出的窗口。",
  inputSchema: {
    path: z.string().describe("要定位的绝对路径"),
  },
};

export const allFilesTools: readonly ToolDef[] = [
  filesListDir,
  filesExists,
  filesCreateFile,
  filesCreateFolder,
  filesRename,
  filesCopy,
  filesMove,
  filesDelete,
  filesUndoDelete,
  filesReveal,
];
