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
import type { ZodType } from 'zod';

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

/**
 * 调 sidecar RPC。
 *
 * @param schema 可选 zod schema：传入则对返回值做运行时校验（核心方法用，见 lib/rpcSchemas.ts）。
 *   校验失败抛「后端返回格式异常」——把契约漂移在边界显式化，而非渲染时静默炸 / 出错报告。
 *   不传则沿用 `as T`（无运行时校验，适合非关键方法）。
 */
export async function rpc<T = unknown>(
  method: string,
  params: Record<string, unknown> | unknown[] = {},
  schema?: ZodType<T>,
): Promise<T> {
  let raw: unknown;
  try {
    raw = await invoke('rpc_call', { method, params });
  } catch (e) {
    throw new Error(translateError(e), { cause: e });
  }
  if (!schema) return raw as T;
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    const detail = parsed.error.issues
      .map((i) => `${i.path.join('.') || '(根)'}: ${i.message}`)
      .join('；');
    throw new Error(
      `后端返回格式异常（${method}，可能 sidecar 版本不匹配）：${detail}`,
    );
  }
  return parsed.data;
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
