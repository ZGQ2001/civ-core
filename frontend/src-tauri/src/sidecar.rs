//! Python sidecar 子进程管理。
//!
//! 启动 `uv run python -m civ_core.api`，stdin/stdout 行协议 JSON-RPC 通信。
//! 单 Mutex 串行调用就够：内业小工具 RPC 并发量低，避免做复杂 id 匹配。
//!
//! 开发时 cwd 是仓库根（src-tauri 的祖父目录 -> ../../..）；生产打包后
//! sidecar 是嵌入的 PyInstaller 单文件 exe（T6 阶段配 Tauri externalBin）。

use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};

use anyhow::{Context, Result, anyhow};
use serde_json::{Value, json};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tokio::sync::Mutex;

pub struct PythonSidecar {
    stdin: Mutex<ChildStdin>,
    stdout: Mutex<BufReader<ChildStdout>>,
    next_id: AtomicU64,
    _child: Child, // 持有避免 drop 杀进程
}

impl PythonSidecar {
    /// 开发模式：在仓库根目录跑 `uv run python -m civ_core.api`。
    /// 生产模式：调 `sidecar_civ_core_api`（PyInstaller exe，T6 阶段接）。
    pub async fn spawn_dev(repo_root: &std::path::Path) -> Result<Self> {
        let mut cmd = Command::new("uv");
        cmd.args(["run", "python", "-m", "civ_core.api"])
            .current_dir(repo_root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        let mut child = cmd
            .spawn()
            .with_context(|| format!("启动 Python sidecar 失败 (cwd={})", repo_root.display()))?;
        let stdin = child.stdin.take().ok_or_else(|| anyhow!("拿不到 sidecar stdin"))?;
        let stdout = child.stdout.take().ok_or_else(|| anyhow!("拿不到 sidecar stdout"))?;
        log::info!("Python sidecar 启动 (pid={:?})", child.id());
        Ok(Self {
            stdin: Mutex::new(stdin),
            stdout: Mutex::new(BufReader::new(stdout)),
            next_id: AtomicU64::new(1),
            _child: child,
        })
    }

    /// JSON-RPC 调用：method + params(JSON) → result(JSON) | 错误。
    pub async fn call(&self, method: &str, params: Value) -> Result<Value> {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let req = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        });
        let req_line = format!("{}\n", req);

        // 串行：拿到 stdin lock 再拿 stdout lock，保证一次完整 round-trip 不被打断
        let mut stdin = self.stdin.lock().await;
        stdin
            .write_all(req_line.as_bytes())
            .await
            .context("写 sidecar stdin 失败")?;
        stdin.flush().await.context("flush sidecar stdin 失败")?;
        drop(stdin); // 早释放 stdin，让 sidecar 处理时其他 caller 可以排队

        let mut stdout = self.stdout.lock().await;
        let mut line = String::new();
        let n = stdout.read_line(&mut line).await.context("读 sidecar stdout 失败")?;
        if n == 0 {
            return Err(anyhow!("sidecar 关闭了 stdout (进程崩溃?)"));
        }

        let resp: Value = serde_json::from_str(line.trim())
            .with_context(|| format!("解析 sidecar 响应失败: {}", line.trim()))?;

        if let Some(err) = resp.get("error") {
            let msg = err
                .get("message")
                .and_then(|m| m.as_str())
                .unwrap_or("未知错误");
            return Err(anyhow!("RPC error: {}", msg));
        }

        Ok(resp.get("result").cloned().unwrap_or(Value::Null))
    }
}
