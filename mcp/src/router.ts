/**
 * 方法前缀路由 —— 对照 `frontend/src-tauri/src/sidecar.rs::SidecarRouter`。
 *
 * 策略：默认 C#，白名单 Python。
 * 与 Rust 端口径一致，新方法不用改这里。
 */

import type { JsonRpcSidecar } from "./sidecar.js";

export class SidecarRouter {
  constructor(
    private readonly python: JsonRpcSidecar,
    private readonly csharp: JsonRpcSidecar,
  ) {}

  async call(method: string, params: unknown = {}): Promise<unknown> {
    const target = SidecarRouter.isPythonMethod(method) ? this.python : this.csharp;
    return target.call(method, params);
  }

  /**
   * Python 白名单：仅 `ping` / `version` / `plot_curves.*` 走 Python，其余 C#。
   * matplotlib 无可替代 → plot_curves 长留 Python；其余全切 C#（T5.7 已完成）。
   */
  static isPythonMethod(method: string): boolean {
    return (
      method === "ping" ||
      method === "version" ||
      method.startsWith("plot_curves.")
    );
  }
}
