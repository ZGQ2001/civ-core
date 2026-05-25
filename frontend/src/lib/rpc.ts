/**
 * RPC client：前端通过 Tauri `rpc_call` command 转发到 Python sidecar。
 *
 * 用法：
 *   const { path } = await rpc<{ path: string | null }>("workspace.last");
 *   const { entries } = await rpc<{ entries: FileEntry[] }>("files.list_dir", { path });
 *
 * 错误：sidecar 抛错时 Promise reject，message 经 translateError 转为用户可读。
 */
import { invoke } from '@tauri-apps/api/core';

function translateError(raw: unknown): string {
  const msg = String(raw);
  if (msg.includes('sidecar 已死') || msg.includes('exited'))
    return '后台服务已断开，请重启应用';
  if (msg.includes('timeout') || msg.includes('超时'))
    return '操作超时，请重试';
  if (msg.includes('FileNotFoundException') || msg.includes('文件不存在'))
    return '文件不存在，请检查路径是否正确';
  if (
    msg.includes('FileFormatException') ||
    msg.includes('not a valid package')
  )
    return '该文件不是有效的 Excel 文件，请检查文件是否损坏';
  if (
    msg.includes('PermissionError') ||
    msg.includes('Access') ||
    msg.includes('被占用')
  )
    return '文件被占用，请关闭 Excel/Word 后重试';
  return msg;
}

export async function rpc<T = unknown>(
  method: string,
  params: Record<string, unknown> | unknown[] = {},
): Promise<T> {
  try {
    return (await invoke('rpc_call', { method, params })) as T;
  } catch (e) {
    throw new Error(translateError(e), { cause: e });
  }
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
