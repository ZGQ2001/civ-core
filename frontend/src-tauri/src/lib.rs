//! Tauri 主进程入口。
//!
//! 启动时 spawn 两个 sidecar 子进程：
//!   - Python (`civ_core.api`) — 业务计算/IO 主力
//!   - C# (`civ-doc`) — Word/Excel 重资产场景（OpenXML SDK）
//!
//! 注册 rpc_call command 给前端调用；SidecarRouter 按 method 前缀路由。

mod sidecar;
mod watcher;

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use serde_json::Value;
use sidecar::{spawn_csharp_dev, spawn_python_dev, SidecarRouter};
use tauri::{async_runtime::block_on, Manager};

/// 从 cwd 向上查找含 `pyproject.toml` 的目录作为仓库根。
/// dev 模式 cwd 可能是 frontend/src-tauri 也可能是 frontend，靠 marker 判断比 parent 计数稳。
fn find_repo_root() -> PathBuf {
    let start = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut cur = start.as_path();
    loop {
        if cur.join("pyproject.toml").is_file() {
            return cur.to_path_buf();
        }
        match cur.parent() {
            Some(p) => cur = p,
            None => return start,
        }
    }
}

/// 启动对 `path` 的文件系统监控；新路径会自动替换旧监控。
#[tauri::command]
async fn watch_workspace(
    app: tauri::AppHandle,
    state: tauri::State<'_, watcher::WatcherState>,
    path: String,
) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    *guard = None; // drop 旧 watcher（停止旧监控）
    *guard = Some(watcher::start_watch(app, &path).map_err(|e| e.to_string())?);
    Ok(())
}

/// 停止文件系统监控。
#[tauri::command]
async fn unwatch_workspace(state: tauri::State<'_, watcher::WatcherState>) -> Result<(), String> {
    state.0.lock().map_err(|e| e.to_string())?.take();
    Ok(())
}

/// 把 method+params 转发到对应 sidecar（按前缀路由），返回 RPC result 或错误字符串。
#[tauri::command]
async fn rpc_call(
    router: tauri::State<'_, Arc<SidecarRouter>>,
    method: String,
    params: Value,
) -> Result<Value, String> {
    router
        .call(&method, params)
        .await
        .map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(
            tauri_plugin_log::Builder::default()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .setup(|app| {
            // dev 模式：沿 cwd 向上找 pyproject.toml 定位仓库根。
            // resource_dir 在 dev 模式指向 target/debug，parent 计数容易错；
            // 用 marker 文件判断稳得多。生产打包（T6）改走 externalBin，不再用 repo_root。
            let repo_root = find_repo_root();

            log::info!("启动 sidecar，仓库根 = {}", repo_root.display());

            // 串行启两个 sidecar；任一失败应用直接退出（前端没 backend 也跑不了）
            let router = block_on(async {
                let python = spawn_python_dev(&repo_root).await?;
                let csharp = spawn_csharp_dev(&repo_root).await?;
                Ok::<_, anyhow::Error>(SidecarRouter::new(Arc::new(python), Arc::new(csharp)))
            })
            .expect("启动 sidecar 失败");

            app.manage(Arc::new(router));
            app.manage(watcher::WatcherState(Mutex::new(None)));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            rpc_call,
            watch_workspace,
            unwatch_workspace
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
