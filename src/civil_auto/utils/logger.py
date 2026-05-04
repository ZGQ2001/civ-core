"""标准化日志系统（三 sink：彩色控制台 / 滚动文件 / Qt 信号桥）。

设计要点：
  1. 以 stdlib logging 为根，所有第三方库的日志都自然汇合到这里。
  2. 三个 handler 各自独立级别 —— 控制台默认 INFO，文件 DEBUG，UI 用 INFO。
  3. QtLogBridge 把 LogRecord（不是字符串）发送到 UI，UI 端可按 level 上色、
     按 logger 名称过滤、点击跳源码。
  4. setup_logging() 幂等 —— 重复调用不会叠加 handler。
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from civil_auto.config.loader import LoggingConfig


# ──────────────────────────────────────────────────────────────────
# 1. 彩色控制台 Formatter（ANSI 转义，无第三方依赖）
# ──────────────────────────────────────────────────────────────────
class _AnsiColorFormatter(logging.Formatter):
    _COLORS = {
        logging.DEBUG: "\x1b[37m",  # gray
        logging.INFO: "\x1b[36m",  # cyan
        logging.WARNING: "\x1b[33m",  # yellow
        logging.ERROR: "\x1b[31m",  # red
        logging.CRITICAL: "\x1b[1;91m",  # bold bright red
    }
    _RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        color = self._COLORS.get(record.levelno, "")
        return f"{color}{base}{self._RESET}" if color else base


# ──────────────────────────────────────────────────────────────────
# 2. Qt 信号桥（跨线程安全：worker thread 也能 logger.info(...)）
# ──────────────────────────────────────────────────────────────────
class QtLogBridge(QObject):
    """logging.Handler 子类的信号载体。

    发射的是 LogRecord 对象本身，UI 端可拆出 levelno / msg / module / lineno
    / created（时间戳）来分别处理 —— 不只是一根字符串。
    """

    record_emitted = Signal(object)  # logging.LogRecord


class _QtSignalHandler(logging.Handler):
    def __init__(self, bridge: QtLogBridge):
        super().__init__()
        self._bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._bridge.record_emitted.emit(record)
        except Exception:
            self.handleError(record)


# ──────────────────────────────────────────────────────────────────
# 3. 顶层 API
# ──────────────────────────────────────────────────────────────────
_INSTALLED = False
_BRIDGE: QtLogBridge | None = None

DEFAULT_FMT = "[%(asctime)s] %(levelname)-5s  %(name)-22s — %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_dir: Path | str = "./logs",
    level: str = "INFO",
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    max_file_mb: int = 10,
    backup_count: int = 5,
    *,
    file_name: str = "app.log",
) -> QtLogBridge:
    """挂载三个 handler 到 root logger，返回 Qt 信号桥。

    重复调用安全（幂等）。UI 拿到 bridge 后调用：
        bridge.record_emitted.connect(my_log_panel.on_record)
    """
    global _INSTALLED, _BRIDGE

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(_to_level(level))

    if _INSTALLED and _BRIDGE is not None:
        return _BRIDGE

    formatter = logging.Formatter(DEFAULT_FMT, DEFAULT_DATEFMT)
    color_formatter = _AnsiColorFormatter(DEFAULT_FMT, DEFAULT_DATEFMT)

    # ── ① 控制台 ──
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(_to_level(console_level))
    console.setFormatter(color_formatter)
    root.addHandler(console)

    # ── ② 滚动文件 ──
    file_handler = RotatingFileHandler(
        log_dir / file_name,
        maxBytes=max_file_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(_to_level(file_level))
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # ── ③ Qt 信号桥 ──
    _BRIDGE = QtLogBridge()
    qt_handler = _QtSignalHandler(_BRIDGE)
    qt_handler.setLevel(_to_level(level))
    qt_handler.setFormatter(formatter)
    root.addHandler(qt_handler)

    _INSTALLED = True
    logging.getLogger(__name__).info(
        "Logging initialized. dir=%s console=%s file=%s",
        log_dir,
        console_level,
        file_level,
    )
    return _BRIDGE


def setup_from_config(cfg: LoggingConfig, log_dir: Path | str) -> QtLogBridge:
    """从 LoggingConfig (Pydantic) 直接初始化。"""
    return setup_logging(
        log_dir=log_dir,
        level=cfg.level,
        console_level=cfg.console_level,
        file_level=cfg.file_level,
        max_file_mb=cfg.max_file_mb,
        backup_count=cfg.backup_count,
    )


def get_qt_bridge() -> QtLogBridge | None:
    """UI 启动后取信号桥；setup_logging 未调用前返回 None。"""
    return _BRIDGE


def get_logger(name: str = "civil_auto") -> logging.Logger:
    """业务代码统一拿 logger 的入口。"""
    return logging.getLogger(name)


# ──────────────────────────────────────────────────────────────────
def _to_level(name: str | int) -> int:
    if isinstance(name, int):
        return name
    return getattr(logging, str(name).upper(), logging.INFO)
