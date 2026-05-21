#!/usr/bin/env bash
# civ-core 开发模式一键启动（Tauri + Vite + Python sidecar + C# sidecar）
#
# 用法：
#   bash run.sh         # Git Bash / WSL
#   ./run.sh            # 如果有可执行权限（chmod +x）
#
# 行为：
#   1. 切到脚本所在目录（仓库根）
#   2. 确保 cargo 在 PATH（首次装 Rust 后当前 shell 可能 PATH 没刷新）
#   3. 预 build C# sidecar（civ-doc）—— Rust 端用 `dotnet exec dll` 启动，
#      避免 `dotnet run` 的 build 输出污染 JSON-RPC stdout 协议流
#   4. cd frontend && npm run tauri:dev
#      Tauri 会自动起 Vite + 编译 Rust + spawn Python + C# 两个 sidecar

set -euo pipefail

cd "$(dirname "$0")"

# rustup 默认装 cargo 到 ~/.cargo/bin；当前 shell PATH 没刷新就手动补上
if [ -d "$HOME/.cargo/bin" ] && ! command -v cargo >/dev/null 2>&1; then
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# 预 build C# sidecar（incremental build，首次约 3 秒，之后毫秒）
echo "[run.sh] 预 build C# sidecar..."
(cd dotnet/civ-doc && dotnet build --nologo --verbosity quiet)

cd frontend
exec npm run tauri:dev
