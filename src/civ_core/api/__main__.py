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
    """注册所有内置 handler 模块；新增工具时在这里加一行 register_module。

    注：leeb.* 已迁 C# sidecar（civ-doc），Python 端不再注册。Tauri SidecarRouter
    按方法名「默认 C#，白名单 Python」路由（详见 frontend/src-tauri/src/sidecar.rs）。
    """
    d = Dispatcher()
    d.register_module("plot_curves", handlers.plot_curves)
    d.register_module("pdf_tools", handlers.pdf_tools)
    d.register_module("word2pdf", handlers.word2pdf)
    # ping/version 用于桥联测试
    d.register("ping", lambda: "pong")
    d.register("version", lambda: {"app": "civ-core", "api": 1})
    return d


def _ensure_standards_db_seeded() -> None:
    """启动时确保 ~/.civ-core/standards.db 已 seed —— C# sidecar (civ-doc) 读它做
    leeb 计算（C# 端只读不 seed）。Python 端继续承担规范库写入责任。"""
    from civ_core.infra_io.standards_db import init_standards_db

    log = logging.getLogger(__name__)
    try:
        _db, conn = init_standards_db()
        conn.close()
        log.info("规范库 standards.db 已就绪（供 C# sidecar 读）")
    except Exception as e:
        log.warning("规范库初始化失败：%s（C# leeb.* 调用可能挂）", e)


def _force_utf8_streams() -> None:
    """Windows 默认 sys.stdin/stdout/stderr 用 GBK（cp936），中文写入会变成
    非 UTF-8 字节流；Tauri 端按 UTF-8 读 stderr 时直接失败。
    跟 C# sidecar 一样在入口强制三个流都用 UTF-8，跨语言协议一致。
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> int:
    _force_utf8_streams()
    _setup_api_logger()
    log = logging.getLogger(__name__)
    log.info("civ-core api server 启动")
    _ensure_standards_db_seeded()
    dispatcher = build_dispatcher()
    log.info("已注册方法：%s", dispatcher.methods())
    return serve(dispatcher)


if __name__ == "__main__":
    sys.exit(main())
