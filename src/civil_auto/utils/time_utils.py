"""带时区的时间处理工具（手册 §4.4 强制要求）。

所有业务代码需要当前时间时，统一调这里的函数。
禁止在业务模块里直接 `datetime.now()` —— 那会产生 naive datetime（无时区信息）。

时区策略：
    显示/存储 = Asia/Shanghai（UTC+8）
    内部比较  = 两端都带时区即可，无需转 UTC
    审计日志  = ISO-8601 格式（含时区偏移）：2026-01-02T15:04:05+08:00
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# 项目标准时区（全模块复用，不要各处自造 ZoneInfo("Asia/Shanghai")）
try:
    _TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    # Windows 无 tzdata 时 fallback 到固定偏移 UTC+8（功能等价，不含 DST 信息）
    from datetime import timedelta
    _TZ_SHANGHAI = timezone(timedelta(hours=8))  # type: ignore[assignment]


def now_shanghai() -> datetime:
    """返回当前 Asia/Shanghai 时间（带时区，非 naive）。

    是全项目「获取当前时间」的唯一入口。
    """
    return datetime.now(tz=_TZ_SHANGHAI)


def now_utc() -> datetime:
    """返回当前 UTC 时间（带时区）。"""
    return datetime.now(tz=timezone.utc)


def to_iso8601(dt: datetime) -> str:
    """把 datetime 格式化为 ISO-8601 字符串（含时区偏移）。

    示例：``2026-05-04T15:30:00+08:00``

    用于：审计日志（P0-8）、文件名时间戳等。
    """
    if dt.tzinfo is None:
        raise ValueError(
            f"to_iso8601 不接受 naive datetime：{dt!r}。"
            "请使用 now_shanghai() 或 now_utc() 获取带时区的时间。"
        )
    return dt.isoformat(timespec="seconds")


def timestamp_tag(dt: Optional[datetime] = None) -> str:
    """生成适合嵌入文件名的时间戳（不含冒号和时区偏移）。

    示例：``20260504_1530``（年月日_时分）

    若不传 dt，默认用当前上海时间。
    """
    t = dt or now_shanghai()
    return t.strftime("%Y%m%d_%H%M")


def timestamp_tag_with_seconds(dt: Optional[datetime] = None) -> str:
    """带秒的文件名时间戳：``20260504_153005``。"""
    t = dt or now_shanghai()
    return t.strftime("%Y%m%d_%H%M%S")


def ensure_tz_aware(dt: datetime) -> datetime:
    """若传入 naive datetime，附上 Asia/Shanghai 时区后返回；已带时区则原样返回。

    用于：处理 openpyxl 读出来的日期列（可能是 naive）。
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_TZ_SHANGHAI)
    return dt
