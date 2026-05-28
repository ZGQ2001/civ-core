import { describe, expect, it } from "vitest";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  JsonRpcSidecar,
  SidecarFatalError,
  SidecarRpcError,
  spawnSidecar,
} from "../src/sidecar.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixturePath = join(__dirname, "fixtures", "echo-rpc.mjs");

function spawnEcho(): JsonRpcSidecar {
  // process.execPath = 当前 node 二进制，跨平台稳
  return spawnSidecar("echo", process.execPath, [fixturePath]);
}

describe("JsonRpcSidecar", () => {
  it("call → result（基本回环）", async () => {
    const s = spawnEcho();
    try {
      const r = await s.call("echo.hello", { x: 1 });
      expect(r).toEqual({ echoed: "echo.hello", params: { x: 1 } });
    } finally {
      s.kill();
    }
  });

  it("并发 call 串行化，按顺序返回", async () => {
    const s = spawnEcho();
    try {
      const results = await Promise.all([
        s.call("echo.a", { i: 1 }),
        s.call("echo.b", { i: 2 }),
        s.call("echo.c", { i: 3 }),
      ]);
      expect(results).toEqual([
        { echoed: "echo.a", params: { i: 1 } },
        { echoed: "echo.b", params: { i: 2 } },
        { echoed: "echo.c", params: { i: 3 } },
      ]);
    } finally {
      s.kill();
    }
  });

  it("sidecar 返回 error → 抛 SidecarRpcError（业务级，可继续调）", async () => {
    const s = spawnEcho();
    try {
      await expect(s.call("echo.bad", {})).rejects.toBeInstanceOf(SidecarRpcError);
      // 业务级错误不影响后续调用
      const r = await s.call("echo.after_bad", { y: 2 });
      expect(r).toEqual({ echoed: "echo.after_bad", params: { y: 2 } });
    } finally {
      s.kill();
    }
  });

  it("进程崩了 → SidecarFatalError，后续 call fast-fail", async () => {
    const s = spawnEcho();
    try {
      await s.call("echo.exit", {});
      // 等 'exit' 事件 propagate（child.on('exit')）
      await new Promise((r) => setTimeout(r, 100));
      expect(s.isAlive()).toBe(false);
      await expect(s.call("echo.anything", {})).rejects.toBeInstanceOf(
        SidecarFatalError,
      );
    } finally {
      s.kill();
    }
  });
});
