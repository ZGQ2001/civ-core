"""标准化日志系统（三 sink：彩色控制台 / 滚动文件 / Qt 信号桥）+ 审计日志。

设计要点：
  1. 以 stdlib logging 为根，所有第三方库的日志都自然汇合到这里。
  2. 三个 handler 各自独立级别 —— 控制台默认 INFO，文件 DEBUG，UI 用 INFO。
  3. QtLogBridge 把 LogRecord（不是字符串）发送到 UI，UI 端可按 level 上色、
     按 logger 名称过滤、点击跳源码。
  4. setup_logging() 幂等 —— 重复调用不会叠加 handler。
  5. 审计日志独立成 civil_auto.audit logger，独立文件 logs/audit.jsonl：
     JSONL 一行一个事件，便于机器解析 / grep / tail；不流到主 app.log，
     避免和调试输出混在一起。每次工具运行都应在出口处写一条。
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

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

    # ── ④ 审计日志（独立 logger，不挂 root，独立文件）──
    setup_audit_logger(log_dir)

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


# ──────────────────────────────────────────────────────────────────
# 4. 审计日志（独立 logger / 独立文件 / JSONL）
# ──────────────────────────────────────────────────────────────────
#
# 设计动机：
#   • 普通 app.log 是给开发看 traceback / 调试的，每次跑都几千行
#   • 审计要回答"谁、什么时候、对哪个文件、跑出了什么"——这是合规 / 排查 / 复现的
#     单一事实源，不能淹没在调试输出里
#   • JSONL 比纯文本好处：
#       - 一行一个完整事件，tail/grep/awk 都好用
#       - 字段可以 jq 解析，长期可以喂到 SQLite/DuckDB 做统计
#       - 时间戳带时区，避免日后时区改动后历史记录失真
#
# 字段约定（最小集，工具可在 extra= 里附加自己的字段）：
#   ts            ISO8601，带 Asia/Shanghai 时区
#   tool          工具名，如 "plot_curves"
#   status        ok | partial | failed
#   input_path    输入文件绝对路径（可选）
#   input_sha256  输入文件 SHA256 全量摘要（可选；流式计算，大文件友好）
#   output_dir    输出目录（可选）

_AUDIT_LOGGER_NAME = "civil_auto.audit"
_AUDIT_FILENAME = "audit.jsonl"
_AUDIT_TZ = ZoneInfo("Asia/Shanghai")


def compute_file_sha256(path: Path | str, *, chunk_size: int = 1 << 20) -> str:
    """流式计算文件 SHA256，返回 64 字符小写 hex。

    chunk_size 默认 1 MiB —— 仪器导出的几十万行 Excel 也只占常数内存。
    文件不存在时抛 FileNotFoundError，不静默吞掉（审计场景必须忠实反映）。
    """
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def setup_audit_logger(log_dir: Path | str) -> logging.Logger:
    """初始化审计 logger（独立文件 audit.jsonl，不流到 root）。

    幂等：重复调用不会叠加 handler。
    与 setup_logging 联动：setup_logging 内部会自动调一次，因此 UI 启动后无需额外初始化；
    但脚本场景（test / CLI 直接调 run_plot_curves）也可单独调本函数。
    """
    d = Path(log_dir)
    d.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(_AUDIT_LOGGER_NAME)
    if logger.handlers:
        return logger  # 已初始化

    logger.setLevel(logging.INFO)
    # propagate=False —— 审计条目不流到 root，否则会同时出现在 console 和 app.log
    logger.propagate = False

    handler = RotatingFileHandler(
        d / _AUDIT_FILENAME,
        maxBytes=10 * 1024 * 1024,  # 10 MiB / 文件
        backupCount=10,  # 留 10 个历史文件 ≈ 100 MiB 上限
        encoding="utf-8",
    )
    # 审计是 JSONL：每条 message 已经是合法 JSON，formatter 只透传
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def write_audit_entry(
    tool: str,
    *,
    status: str,
    input_path: Path | str | None = None,
    input_sha256: str | None = None,
    output_dir: Path | str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """写一条审计条目（一行 JSON）。

    需先调过 setup_audit_logger（或 setup_logging）。若审计 logger 未初始化，
    降级写到主 logger 的 WARNING 级别——保证条目不会被静默丢失。
    """
    logger = logging.getLogger(_AUDIT_LOGGER_NAME)
    if not logger.handlers:
        logging.getLogger(__name__).warning(
            "审计 logger 未初始化，条目降级写入主日志。请在程序启动时调 setup_logging() / setup_audit_logger()。"
        )
        logger = logging.getLogger(__name__)

    entry: dict[str, Any] = {
        "ts": datetime.now(_AUDIT_TZ).isoformat(timespec="seconds"),
        "tool": tool,
        "status": status,
    }
    if input_path is not None:
        entry["input_path"] = str(input_path)
    if input_sha256 is not None:
        entry["input_sha256"] = input_sha256
    if output_dir is not None:
        entry["output_dir"] = str(output_dir)
    if extra:
        # extra 中允许放任意 JSON 可序列化对象；Path 等非内置类型在下方 default 兜底
        entry.update(extra)

    # ensure_ascii=False 让中文不转 \uXXXX；separators 去多余空格压缩行长
    line = json.dumps(
        entry, ensure_ascii=False, separators=(",", ":"), default=str
    )
    logger.info(line)
