/**
 * Node 版 JsonRpcSidecar —— 对照 `frontend/src-tauri/src/sidecar.rs`。
 *
 * 协议口径与 Rust 端完全一致：
 *   stdin 一行 JSON-RPC 请求 → stdout 一行 JSON-RPC 响应。
 *   stderr 透传到本进程 stderr，前缀 `[<name>]`（sidecar 端只往 stderr 写日志）。
 *
 * 串行调用：一次 in-flight，避免多 caller 交错读 stdout 拿错响应。
 * 30s 超时：拿不到响应立刻让出，整条链路不被一次卡顿拖死；超时后标记 dead，后续调用 fast-fail。
 */

import { spawn, type ChildProcess, type SpawnOptions } from "node:child_process";
import { createInterface } from "node:readline";
import { join } from "node:path";

const RPC_TIMEOUT_MS = 30_000;

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params: unknown;
}

interface JsonRpcOk {
  jsonrpc: "2.0";
  id: number;
  result: unknown;
}

interface JsonRpcErr {
  jsonrpc: "2.0";
  id: number;
  error: { code: number; message: string; data?: unknown };
}

type JsonRpcResponse = JsonRpcOk | JsonRpcErr;

/** 标识一次 sidecar 报错来自 RPC 协议层（带原始 error 对象，方便上层映射 MCP isError）。 */
export class SidecarRpcError extends Error {
  constructor(
    message: string,
    public readonly rpcError: JsonRpcErr["error"],
  ) {
    super(message);
    this.name = "SidecarRpcError";
  }
}

/** 标识 sidecar 进程层故障（崩溃 / EOF / 超时）；调用方应拒绝后续调用并退出。 */
export class SidecarFatalError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SidecarFatalError";
  }
}

export class JsonRpcSidecar {
  private nextId = 1;
  private alive = true;
  /** 串行队列：每次 call 链到上一次完成之后。 */
  private inFlight: Promise<unknown> = Promise.resolve();
  /** stdout 按行 iterator，next() 返回下一行；done=true 即 EOF。 */
  private readonly stdoutLines: AsyncIterator<string>;

  // parameter properties：声明 + 构造时赋值同时发生，避开 TS2565
  // （async IIFE 内引用 `this.name` 时 TS 无法证明微任务序——这种写法直接给定）。
  constructor(
    private readonly name: string,
    private readonly child: ChildProcess,
  ) {
    if (!child.stdin || !child.stdout || !child.stderr) {
      throw new SidecarFatalError(
        `${name}: 子进程缺少 stdio 管道（spawn 必须 stdio:'pipe'）`,
      );
    }

    const rl = createInterface({ input: child.stdout, crlfDelay: Infinity });
    this.stdoutLines = rl[Symbol.asyncIterator]();

    // stderr drain：不读会让 sidecar 的 stderr buffer 满了阻塞写
    const errRl = createInterface({ input: child.stderr, crlfDelay: Infinity });
    void (async () => {
      for await (const line of errRl) {
        process.stderr.write(`[${this.name}] ${line}\n`);
      }
    })();

    child.on("exit", (code, signal) => {
      this.alive = false;
      process.stderr.write(
        `[${this.name}] sidecar exited code=${code} signal=${signal}\n`,
      );
    });
    child.on("error", (err) => {
      this.alive = false;
      process.stderr.write(`[${this.name}] sidecar process error: ${err.message}\n`);
    });
  }

  /**
   * 发起一次 JSON-RPC 调用。串行：等上一次完成才开始。
   *
   * 抛错类型：
   *   - SidecarRpcError：sidecar 返回了 `error` 字段（业务级错误，可继续调用）
   *   - SidecarFatalError：进程死了 / stdout 关 / 超时（不可恢复，请重启）
   */
  async call(method: string, params: unknown = {}): Promise<unknown> {
    if (!this.alive) {
      throw new SidecarFatalError(
        `${this.name} sidecar 已死（进程退出或崩溃），请重启 MCP server`,
      );
    }
    // 接到上一个 in-flight 之后再开始；忽略上一个的错误（call 的错误已抛给原 caller）
    const prev = this.inFlight.catch(() => undefined);
    const run = prev.then(() => this.callOnce(method, params));
    // 链上下一个 in-flight；errors 不污染下一次（catch 过了）
    this.inFlight = run.catch(() => undefined);
    return run;
  }

  private async callOnce(method: string, params: unknown): Promise<unknown> {
    const id = this.nextId++;
    const req: JsonRpcRequest = { jsonrpc: "2.0", id, method, params };
    const reqLine = `${JSON.stringify(req)}\n`;

    // 写 stdin（背压让 node 自己管；child.stdin 是 Writable）
    const stdin = this.child.stdin!;
    await new Promise<void>((resolve, reject) => {
      stdin.write(reqLine, "utf8", (err) => (err ? reject(err) : resolve()));
    });

    // 读一行，套 30s 超时
    let respLine: string;
    let timeoutId: NodeJS.Timeout | undefined;
    try {
      respLine = await new Promise<string>((resolve, reject) => {
        timeoutId = setTimeout(() => {
          this.alive = false;
          reject(
            new SidecarFatalError(
              `${this.name}: RPC 调用 ${method} 超过 ${RPC_TIMEOUT_MS / 1000}s 无响应`,
            ),
          );
        }, RPC_TIMEOUT_MS);
        this.stdoutLines.next().then(
          ({ value, done }) => {
            if (done) {
              this.alive = false;
              reject(new SidecarFatalError(`${this.name}: stdout 关闭（进程崩溃?）`));
              return;
            }
            resolve(value);
          },
          (err: unknown) => {
            this.alive = false;
            reject(
              new SidecarFatalError(
                `${this.name}: 读 stdout 失败 (${err instanceof Error ? err.message : String(err)})`,
              ),
            );
          },
        );
      });
    } finally {
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    }

    let resp: JsonRpcResponse;
    try {
      resp = JSON.parse(respLine) as JsonRpcResponse;
    } catch (e) {
      throw new SidecarFatalError(
        `${this.name}: 解析响应失败 (${e instanceof Error ? e.message : String(e)}): ${respLine.slice(0, 200)}`,
      );
    }

    if ("error" in resp && resp.error !== undefined) {
      const msg = resp.error.message || "未知错误";
      throw new SidecarRpcError(`${this.name} RPC error: ${msg}`, resp.error);
    }
    return (resp as JsonRpcOk).result;
  }

  /** 主动终止 sidecar；幂等。 */
  kill(): void {
    if (!this.alive) return;
    this.alive = false;
    if (!this.child.killed) {
      this.child.kill();
    }
  }

  isAlive(): boolean {
    return this.alive;
  }
}

/** spawn 一个子进程并包成 JsonRpcSidecar；stdio 强制 pipe。 */
export function spawnSidecar(
  name: string,
  command: string,
  args: readonly string[],
  options: SpawnOptions = {},
): JsonRpcSidecar {
  const child = spawn(command, args, {
    ...options,
    stdio: ["pipe", "pipe", "pipe"],
  });
  return new JsonRpcSidecar(name, child);
}

/**
 * Dev 模式起 C# sidecar：`dotnet exec dotnet/civ-doc/bin/Debug/net9.0/civ-doc.dll`。
 * 与 sidecar.rs::spawn_csharp_dev 口径一致——假设 build 过；用 `exec` 而不是 `run`
 * 避免 build 信息污染 stdout。
 */
export function spawnCsharpDev(repoRoot: string): JsonRpcSidecar {
  const dll = join(repoRoot, "dotnet", "civ-doc", "bin", "Debug", "net9.0", "civ-doc.dll");
  return spawnSidecar("csharp", "dotnet", ["exec", dll], { cwd: repoRoot });
}

/**
 * Dev 模式起 Python sidecar：`uv run python -m civ_core.api`。
 * 与 sidecar.rs::spawn_python_dev 口径一致。
 */
export function spawnPythonDev(repoRoot: string): JsonRpcSidecar {
  return spawnSidecar("python", "uv", ["run", "python", "-m", "civ_core.api"], {
    cwd: repoRoot,
  });
}
