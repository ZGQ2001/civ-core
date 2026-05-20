"""标准化日志系统（彩色控制台 / 滚动文件）+ 独立审计日志。

设计要点：
  1. 以 stdlib logging 为根，第三方库日志都汇合到这里
  2. 两个 handler：控制台默认 INFO（彩色 ANSI），文件 DEBUG
  3. setup_logging() 幂等 —— 重复调用不叠加 handler
  4. 审计日志独立 logger civ_core.audit / 独立文件 audit.jsonl
     一行一个事件，便于机器解析；不流到 root，不污染 app.log

说明：原 QtLogBridge（PySide6 信号桥）已删 —— 旧 Qt UI 在 2026-05-20
Tauri 转型时已弃用；新前端通过 RPC 取日志，不需要 Qt 信号通道。
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

if TYPE_CHECKING:
    from civ_core.configs.loader import LoggingConfig


# ──────────────────────────────────────────────────────────────────
# 彩色控制台 Formatter（ANSI 转义，无第三方依赖）
# ──────────────────────────────────────────────────────────────────
class _AnsiColorFormatter(logging.Formatter):
    _COLORS = {
        logging.DEBUG: "\x1b[37m",
        logging.INFO: "\x1b[36m",
        logging.WARNING: "\x1b[33m",
        logging.ERROR: "\x1b[31m",
        logging.CRITICAL: "\x1b[1;91m",
    }
    _RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        color = self._COLORS.get(record.levelno, "")
        return f"{color}{base}{self._RESET}" if color else base


# ──────────────────────────────────────────────────────────────────
# 顶层 API
# ──────────────────────────────────────────────────────────────────
_INSTALLED = False

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
) -> None:
    """挂载控制台 + 滚动文件 handler 到 root logger。幂等。"""
    global _INSTALLED

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(_to_level(level))

    if _INSTALLED:
        return

    formatter = logging.Formatter(DEFAULT_FMT, DEFAULT_DATEFMT)
    color_formatter = _AnsiColorFormatter(DEFAULT_FMT, DEFAULT_DATEFMT)

    # 控制台
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(_to_level(console_level))
    console.setFormatter(color_formatter)
    root.addHandler(console)

    # 滚动文件
    file_handler = RotatingFileHandler(
        log_dir / file_name,
        maxBytes=max_file_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(_to_level(file_level))
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # 审计日志（独立 logger / 独立文件 / 不挂 root）
    setup_audit_logger(log_dir)

    _INSTALLED = True
    logging.getLogger(__name__).info(
        "Logging initialized. dir=%s console=%s file=%s",
        log_dir,
        console_level,
        file_level,
    )


def setup_from_config(cfg: LoggingConfig, log_dir: Path | str) -> None:
    """从 LoggingConfig 直接初始化。"""
    setup_logging(
        log_dir=log_dir,
        level=cfg.level,
        console_level=cfg.console_level,
        file_level=cfg.file_level,
        max_file_mb=cfg.max_file_mb,
        backup_count=cfg.backup_count,
    )


def get_logger(name: str = "civ_core") -> logging.Logger:
    """业务代码统一拿 logger 的入口。"""
    return logging.getLogger(name)


def _to_level(name: str | int) -> int:
    if isinstance(name, int):
        return name
    return getattr(logging, str(name).upper(), logging.INFO)


# ──────────────────────────────────────────────────────────────────
# 审计日志（独立 logger / 独立文件 / JSONL）
# ──────────────────────────────────────────────────────────────────
# 字段约定（最小集，工具可在 extra= 里附加自己的字段）：
#   ts            ISO8601，带 Asia/Shanghai 时区
#   tool          工具名，如 "plot_curves"
#   status        ok | partial | failed
#   input_path    输入文件绝对路径（可选）
#   input_sha256  输入文件 SHA256（可选；流式计算，大文件友好）
#   output_dir    输出目录（可选）

_AUDIT_LOGGER_NAME = "civ_core.audit"
_AUDIT_FILENAME = "audit.jsonl"
_AUDIT_TZ = ZoneInfo("Asia/Shanghai")


def compute_file_sha256(path: Path | str, *, chunk_size: int = 1 << 20) -> str:
    """流式计算文件 SHA256，返回 64 字符小写 hex。"""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def setup_audit_logger(log_dir: Path | str) -> logging.Logger:
    """初始化审计 logger（独立文件 audit.jsonl，不流到 root）。幂等。"""
    d = Path(log_dir)
    d.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(_AUDIT_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = RotatingFileHandler(
        d / _AUDIT_FILENAME,
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
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
    """写一条审计条目（一行 JSON）。"""
    logger = logging.getLogger(_AUDIT_LOGGER_NAME)
    if not logger.handlers:
        logging.getLogger(__name__).warning(
            "审计 logger 未初始化，条目降级写入主日志。"
            "请在程序启动时调 setup_logging() 或 setup_audit_logger()。"
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
        entry.update(extra)

    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"), default=str)
    logger.info(line)
