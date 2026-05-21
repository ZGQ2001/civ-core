//! JSON-RPC sidecar 子进程管理（Python + C# 通用）。
//!
//! 一行协议：stdin 一行 JSON-RPC 请求 → stdout 一行 JSON-RPC 响应。
//! 单 Mutex 串行调用：内业小工具 RPC 并发量低，避免做复杂 id 匹配。
//!
//! 两个 sidecar：
//!   - PythonSidecar：`uv run python -m civ_core.api` — 业务计算/IO 主力
//!   - CSharpSidecar：`dotnet exec dotnet/civ-doc/bin/Debug/net9.0/civ-doc.dll` —
//!     Word/Excel 重资产场景（doc.* / xlsx.* 方法走 OpenXML SDK 原生）
//!
//! C# 端**假设已经 dotnet build 过**（run.sh 启动前会先 build），sidecar 直接 `dotnet exec` dll
//! 跑 —— 避免 `dotnet run` 的 build 信息混进 stdout 污染协议流。
//! 生产打包 T6 阶段切到 PyInstaller exe + dotnet publish 出来的 self-contained exe，
//! Tauri externalBin 同时引两个。
//!
//! SidecarRouter 按 method 前缀路由：`doc.*` / `xlsx.*` → C#，其余 → Python。

use std::process::Stdio;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use anyhow::{Context, Result, anyhow};
use serde_json::{Value, json};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tokio::sync::Mutex;

/// 通用 JSON-RPC sidecar。Python / C# 共用同一份调用逻辑。
pub struct JsonRpcSidecar {
    name: &'static str,
    stdin: Mutex<ChildStdin>,
    stdout: Mutex<BufReader<ChildStdout>>,
    next_id: AtomicU64,
    _child: Child, // 持有避免 drop 杀进程
}

impl JsonRpcSidecar {
    /// 从已配置好的 Command spawn。调用方负责设置 cwd / args / pipe / kill_on_drop。
    pub async fn spawn(name: &'static str, mut cmd: Command) -> Result<Self> {
        cmd.stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        let mut child = cmd
            .spawn()
            .with_context(|| format!("启动 sidecar 失败: {name}"))?;
        let stdin = child.stdin.take().ok_or_else(|| anyhow!("{name}: 拿不到 stdin"))?;
        let stdout = child.stdout.take().ok_or_else(|| anyhow!("{name}: 拿不到 stdout"))?;
        log::info!("{name} sidecar 启动 (pid={:?})", child.id());
        Ok(Self {
            name,
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
            .with_context(|| format!("{}: 写 stdin 失败", self.name))?;
        stdin.flush().await.with_context(|| format!("{}: flush stdin 失败", self.name))?;
        drop(stdin); // 早释放 stdin，让 sidecar 处理时其他 caller 可以排队

        let mut stdout = self.stdout.lock().await;
        let mut line = String::new();
        let n = stdout.read_line(&mut line).await
            .with_context(|| format!("{}: 读 stdout 失败", self.name))?;
        if n == 0 {
            return Err(anyhow!("{}: stdout 关闭（进程崩溃?）", self.name));
        }

        let resp: Value = serde_json::from_str(line.trim())
            .with_context(|| format!("{}: 解析响应失败: {}", self.name, line.trim()))?;

        if let Some(err) = resp.get("error") {
            let msg = err
                .get("message")
                .and_then(|m| m.as_str())
                .unwrap_or("未知错误");
            return Err(anyhow!("{} RPC error: {}", self.name, msg));
        }

        Ok(resp.get("result").cloned().unwrap_or(Value::Null))
    }
}

/// 开发模式：仓库根目录跑 `uv run python -m civ_core.api`。
pub async fn spawn_python_dev(repo_root: &std::path::Path) -> Result<JsonRpcSidecar> {
    let mut cmd = Command::new("uv");
    cmd.args(["run", "python", "-m", "civ_core.api"]).current_dir(repo_root);
    JsonRpcSidecar::spawn("python", cmd).await
}

/// 开发模式：跑 `dotnet exec dotnet/civ-doc/bin/Debug/net9.0/civ-doc.dll`。
/// 假设已 `dotnet build`（run.sh 启动前会预 build）；用 `dotnet exec` 而不是 `dotnet run`
/// 是为了避免 build 信息（"已成功生成"等）走 stdout 污染协议流。
pub async fn spawn_csharp_dev(repo_root: &std::path::Path) -> Result<JsonRpcSidecar> {
    let dll = repo_root
        .join("dotnet")
        .join("civ-doc")
        .join("bin")
        .join("Debug")
        .join("net9.0")
        .join("civ-doc.dll");
    if !dll.is_file() {
        return Err(anyhow!(
            "civ-doc.dll 不存在（{}）；请先 `cd dotnet/civ-doc && dotnet build`",
            dll.display()
        ));
    }
    let mut cmd = Command::new("dotnet");
    cmd.arg("exec").arg(&dll).current_dir(repo_root);
    JsonRpcSidecar::spawn("csharp", cmd).await
}

/// 按 method 路由到对应 sidecar。
///
/// **策略：默认 C#，白名单 Python**（按用户「以后代码都用 C#」方向）。
/// Python 白名单：工作区/文件系统 + 已交付的 Python 工具（plot_curves / pdf_tools / word2pdf）+ 顶层探活方法。
/// 其他全 → C#（新加 calcType 不用改这里）。
///
/// 两个 sidecar 各自一个 Arc 持有，互不阻塞（Mutex 在各自 struct 里）。
pub struct SidecarRouter {
    python: Arc<JsonRpcSidecar>,
    csharp: Arc<JsonRpcSidecar>,
}

impl SidecarRouter {
    pub fn new(python: Arc<JsonRpcSidecar>, csharp: Arc<JsonRpcSidecar>) -> Self {
        Self { python, csharp }
    }

    pub async fn call(&self, method: &str, params: Value) -> Result<Value> {
        if Self::is_python_method(method) {
            self.python.call(method, params).await
        } else {
            self.csharp.call(method, params).await
        }
    }

    /// Python 白名单：仅这些前缀走 Python，其他全 C#。
    /// 顶层 `ping` / `version` 算 Python 探活方法（C# 端也有 doc.ping 单独探活）。
    fn is_python_method(method: &str) -> bool {
        method == "ping"
            || method == "version"
            || method.starts_with("workspace.")
            || method.starts_with("files.")
            || method.starts_with("plot_curves.")
            || method.starts_with("pdf_tools.")
            || method.starts_with("word2pdf.")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_whitelist_routes_to_python() {
        // 工作区 / 文件系统 + 顶层探活
        assert!(SidecarRouter::is_python_method("ping"));
        assert!(SidecarRouter::is_python_method("version"));
        assert!(SidecarRouter::is_python_method("workspace.last"));
        assert!(SidecarRouter::is_python_method("files.list_dir"));
        // 已交付 Python 工具
        assert!(SidecarRouter::is_python_method("plot_curves.run"));
        assert!(SidecarRouter::is_python_method("pdf_tools.merge"));
        assert!(SidecarRouter::is_python_method("word2pdf.convert"));
    }

    #[test]
    fn default_csharp_for_everything_else() {
        // 已切 C#
        assert!(!SidecarRouter::is_python_method("doc.ping"));
        assert!(!SidecarRouter::is_python_method("xlsx.write_leeb_report_table"));
        // 本轮切 C#（Step 4）
        assert!(!SidecarRouter::is_python_method("leeb.run"));
        assert!(!SidecarRouter::is_python_method("leeb.preview_excel"));
        // 未来加的（不用改路由）
        assert!(!SidecarRouter::is_python_method("calc.core_drilling.run"));
        assert!(!SidecarRouter::is_python_method("rebound.run"));
    }
}
