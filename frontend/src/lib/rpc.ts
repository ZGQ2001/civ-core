/**
 * RPC client：前端通过 Tauri `rpc_call` command 转发到 Python sidecar。
 *
 * 用法：
 *   const { path } = await rpc<{ path: string | null }>("workspace.last");
 *   const { entries } = await rpc<{ entries: FileEntry[] }>("files.list_dir", { path });
 *
 * 错误：sidecar 抛错时 Promise reject，message 由 Rust 端拼好。
 */
import { invoke } from '@tauri-apps/api/core';

export async function rpc<T = unknown>(
  method: string,
  params: Record<string, unknown> | unknown[] = {},
): Promise<T> {
  return (await invoke('rpc_call', { method, params })) as T;
}

// 文件树用的 entry 类型（与 Python files.list_dir 返回对齐）
export interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  mtime: number | null;
}

// workspace.last 返回
export interface WorkspaceLast {
  path: string | null;
}
