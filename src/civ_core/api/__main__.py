"""api server 入口：`python -m civ_core.api`。

Tauri sidecar 会启动这个进程，通过 stdin/stdout JSON-RPC 与之通信。

关键约束：
  - stdout 是 JSON-RPC 协议流，绝对不能被 logger 污染
  - 所以本入口自己挂"只走文件 + stderr"的 logger，不调通用 setup_logging（那个默认挂 stdout console）
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from civ_core.api import handlers
from civ_core.api.server import Dispatcher, serve

# 日志目录：~/.civ-core/logs（不依赖当前工作目录权限）
_LOG_DIR = Path("~/.civ-core/logs").expanduser()
_LOG_FMT = "[%(asctime)s] %(levelname)-5s  %(name)-22s — %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _setup_api_logger() -> None:
    """只挂文件 handler + stderr handler，绝不动 stdout（JSON-RPC 协议流独占）。"""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 清掉可能被其他模块意外挂的 handler，避免重复输出 + stdout 污染
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(_LOG_FMT, _LOG_DATEFMT)

    # 文件 handler：持久化
    fh = RotatingFileHandler(
        _LOG_DIR / "api.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # stderr handler：Tauri 调试时能看到，不影响 stdout 协议流
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    root.addHandler(sh)


def build_dispatcher() -> Dispatcher:
    """注册所有内置 handler 模块；新增工具时在这里加一行 register_module。"""
    d = Dispatcher()
    d.register_module("workspace", handlers.workspace)
    d.register_module("files", handlers.files)
    d.register_module("plot_curves", handlers.plot_curves)
    d.register_module("leeb", handlers.leeb)
    d.register_module("pdf_tools", handlers.pdf_tools)
    d.register_module("word2pdf", handlers.word2pdf)
    # ping/version 用于桥联测试
    d.register("ping", lambda: "pong")
    d.register("version", lambda: {"app": "civ-core", "api": 1})
    return d


def main() -> int:
    _setup_api_logger()
    log = logging.getLogger(__name__)
    log.info("civ-core api server 启动")
    dispatcher = build_dispatcher()
    log.info("已注册方法：%s", dispatcher.methods())
    return serve(dispatcher)


if __name__ == "__main__":
    sys.exit(main())
