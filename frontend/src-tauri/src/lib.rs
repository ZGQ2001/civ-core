//! Tauri 主进程入口。
//!
//! 启动时 spawn 两个 sidecar 子进程：
//!   - Python (`civ_core.api`) — 业务计算/IO 主力
//!   - C# (`civ-doc`) — Word/Excel 重资产场景（OpenXML SDK）
//!
//! 注册 rpc_call command 给前端调用；SidecarRouter 按 method 前缀路由。

mod sidecar;

use std::sync::Arc;

use serde_json::Value;
use sidecar::{SidecarRouter, spawn_csharp_dev, spawn_python_dev};
use tauri::{Manager, async_runtime::block_on};

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
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(
            tauri_plugin_log::Builder::default()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .setup(|app| {
            // 仓库根目录：src-tauri/ → frontend/ → civ-core/
            let repo_root = app
                .path()
                .resource_dir()
                .ok()
                .and_then(|p| p.parent().and_then(|q| q.parent()).map(|q| q.to_path_buf()))
                .unwrap_or_else(|| {
                    // dev 启动时 resource_dir 可能不指向仓库根，回退到 cwd 的祖父
                    std::env::current_dir()
                        .ok()
                        .and_then(|cwd| cwd.parent().map(|p| p.to_path_buf()))
                        .unwrap_or_else(|| std::path::PathBuf::from("."))
                });

            log::info!("启动 sidecar，仓库根 = {}", repo_root.display());

            // 串行启两个 sidecar；任一失败应用直接退出（前端没 backend 也跑不了）
            let router = block_on(async {
                let python = spawn_python_dev(&repo_root).await?;
                let csharp = spawn_csharp_dev(&repo_root).await?;
                Ok::<_, anyhow::Error>(SidecarRouter::new(
                    Arc::new(python),
                    Arc::new(csharp),
                ))
            })
            .expect("启动 sidecar 失败");

            app.manage(Arc::new(router));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![rpc_call])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
