//! 工作区目录实时监控。
//!
//! 用 OS 原生 FS 事件（Windows: ReadDirectoryChangesW，macOS: FSEvents，Linux: inotify）。
//! 500 ms 防抖：短时间内的批量文件变化合并成一次 `workspace-files-changed` 事件发给前端。

use notify::{Config, Event, RecommendedWatcher, RecursiveMode, Watcher};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter};

pub struct WatcherState(pub Mutex<Option<RecommendedWatcher>>);

/// 启动对 `path` 的递归监控，返回 watcher（调用方负责持有，drop 即停止监控）。
pub fn start_watch(app: AppHandle, path: &str) -> anyhow::Result<RecommendedWatcher> {
    let (tx, rx) = std::sync::mpsc::channel::<notify::Result<Event>>();
    let mut watcher = RecommendedWatcher::new(tx, Config::default())?;
    watcher.watch(std::path::Path::new(path), RecursiveMode::Recursive)?;

    std::thread::spawn(move || {
        const DEBOUNCE: Duration = Duration::from_millis(500);
        let mut pending = false;
        let mut deadline = Instant::now();

        loop {
            // 有待发事件时用剩余防抖时间做 recv 超时；否则长 park 等新事件。
            let timeout = if pending {
                deadline
                    .saturating_duration_since(Instant::now())
                    .max(Duration::from_millis(1))
            } else {
                Duration::from_secs(60)
            };

            match rx.recv_timeout(timeout) {
                Ok(Ok(_)) => {
                    // 收到文件系统事件：更新防抖截止时间
                    pending = true;
                    deadline = Instant::now() + DEBOUNCE;
                }
                Ok(Err(_)) => {}
                Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                    // 防抖期满：发一次刷新信号
                    if pending {
                        pending = false;
                        let _ = app.emit("workspace-files-changed", ());
                    }
                }
                Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }
    });

    Ok(watcher)
}
