#!/usr/bin/env bash
# 筑核 (civ-core) 快速启动脚本
# 双击或在终端运行: bash run.sh

set -e
cd "$(dirname "$0")"

# 激活虚拟环境并启动
source .venv/Scripts/activate
uv run python -m civ_core.main
