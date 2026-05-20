#!/usr/bin/env bash
# civ-core 开发模式一键启动（Tauri + Vite + Python sidecar）
#
# 用法：
#   bash run.sh         # Git Bash / WSL
#   ./run.sh            # 如果有可执行权限（chmod +x）
#
# 行为：
#   1. 切到脚本所在目录（仓库根）
#   2. 确保 cargo 在 PATH（首次装 Rust 后当前 shell 可能 PATH 没刷新）
#   3. cd frontend && npm run tauri:dev
#      Tauri 会自动起 Vite + 编译 Rust + spawn Python sidecar（一键三个进程）

set -euo pipefail

cd "$(dirname "$0")"

# rustup 默认装 cargo 到 ~/.cargo/bin；当前 shell PATH 没刷新就手动补上
if [ -d "$HOME/.cargo/bin" ] && ! command -v cargo >/dev/null 2>&1; then
    export PATH="$HOME/.cargo/bin:$PATH"
fi

cd frontend
exec npm run tauri:dev
