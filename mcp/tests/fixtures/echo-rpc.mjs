#!/usr/bin/env node
/**
 * 测试 fixture：一个最小 JSON-RPC echo server。
 * 协议跟真 sidecar 一致：stdin 一行 request → stdout 一行 response，stderr 自由。
 *
 * 特殊 method（给测试用）：
 *   - `echo.bad`  → 返回 JSON-RPC error
 *   - `echo.exit` → 返回 result 后立刻 process.exit(0)（模拟 sidecar 主动崩）
 *   - 其余        → 返回 { echoed: method, params }
 */

process.stdin.setEncoding("utf8");
let buf = "";
process.stdin.on("data", (chunk) => {
  buf += chunk;
  let nl;
  while ((nl = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, nl);
    buf = buf.slice(nl + 1);
    if (!line.trim()) continue;
    let req;
    try {
      req = JSON.parse(line);
    } catch {
      continue; // 真 sidecar 会回 -32700，本 fixture 简化为吞掉
    }
    if (req.method === "echo.bad") {
      process.stdout.write(
        JSON.stringify({
          jsonrpc: "2.0",
          id: req.id,
          error: { code: -32602, message: "故意制造的错误：参数不对" },
        }) + "\n",
      );
    } else if (req.method === "echo.exit") {
      process.stdout.write(
        JSON.stringify({
          jsonrpc: "2.0",
          id: req.id,
          result: { ok: true },
        }) + "\n",
      );
      process.exit(0);
    } else {
      process.stdout.write(
        JSON.stringify({
          jsonrpc: "2.0",
          id: req.id,
          result: { echoed: req.method, params: req.params },
        }) + "\n",
      );
    }
  }
});
process.stderr.write("echo server ready\n");
