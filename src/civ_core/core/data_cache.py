"""Excel 数据缓存（L-2 实时渲染管线的依赖之一）。

为什么需要：
  • LivePreviewPane 防抖后频繁请求重绘，每次都重读 Excel 太浪费
    （仪器导出几万行也常见，单次读 ≈ 几百 ms，连点 5 次参数就 1~2 秒卡顿）
  • 切预设时只重读"映射规则"，不重读 Excel —— 因为 Excel 内容没变

缓存键设计：
  (resolved_path, sheet_name, header_row, mtime_ns)
  • resolved_path：用 Path.resolve() 把符号链接和相对路径都归一化
  • mtime_ns：纳秒精度，避免文件系统 1s 精度抖动；用户重新保存 xlsx 后
    mtime 一定会变，缓存自动失效
  • 不做内容 hash：几万行算 sha256 也慢，mtime 已经足够

对外暴露：
  • ExcelDataCache 类（测试可独立实例化）
  • EXCEL_DATA_CACHE 全局单例（生产用，跨 view / pane 共享）

CLAUDE.md 合规性：
  • 用纯 dict 列表存（不引 pandas）
  • Path 全部走 pathlib
  • 异常透传 ExcelReadError，不吞
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from civ_core.infra_io.excel_reader import read_rows
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# 缓存键：四元组覆盖所有"影响读取结果"的输入
# (str(resolved_path), sheet_name, header_row, mtime_ns)
# sheet_name 用 str | None，但 None 不可哈希 → 这里允许 None（tuple 元素是 None 时仍可 hash）
_CacheKey = tuple[str, str | None, int, int]


class ExcelDataCache:
    """按 (path, mtime, sheet, header_row) 缓存 read_rows 的结果。

    LRU 策略：暂不引（CLAUDE.md 风格上倾向"够用即可"，外面调 clear() 主动管理）。
    实际使用中条目数 ≈ 用户切过的 (Excel, sheet, header_row) 组合数，通常 < 10。
    """

    def __init__(self) -> None:
        self._cache: dict[_CacheKey, list[dict[str, Any]]] = {}

    def get_rows(
        self,
        path: Path | str,
        sheet_name: str | None,
        header_row: int,
    ) -> list[dict[str, Any]]:
        """读 Excel 行；命中缓存直接返回同一 list 对象。

        返回值约定：调用方不要 mutate 返回的 list / dict，否则会污染缓存。
        生产场景调用方都是只读使用（喂给 build_jobs / 列名联动），不存在 mutate 需求。
        """
        p = Path(path).resolve()

        # stat 必须在缓存查找之前算，因为 mtime 是 key 的一部分；
        # 文件不存在 → stat() 抛 FileNotFoundError → 下游 read_rows 也会抛
        # ExcelReadError，统一让 read_rows 抛（带 hint）
        if not p.is_file():
            # 这里不直接 raise，交给 read_rows 抛带 hint 的 ExcelReadError
            return read_rows(p, sheet_name, header_row=header_row)

        # stat_result.st_mtime_ns 纳秒精度，避免 1s 抖动
        mtime_ns = p.stat().st_mtime_ns
        key: _CacheKey = (str(p), sheet_name, header_row, mtime_ns)

        cached = self._cache.get(key)
        if cached is not None:
            log.debug(
                "ExcelDataCache 命中：%s [%s] header_row=%d (%d 行)",
                p.name,
                sheet_name or "<默认>",
                header_row,
                len(cached),
            )
            return cached

        # 未命中：真读盘
        rows = read_rows(p, sheet_name, header_row=header_row)
        self._cache[key] = rows
        log.debug(
            "ExcelDataCache 写入：%s [%s] header_row=%d → %d 行",
            p.name,
            sheet_name or "<默认>",
            header_row,
            len(rows),
        )
        return rows

    def clear(self) -> None:
        """清空全部缓存。测试用，生产几乎不调（mtime 自动失效已够）。"""
        n = len(self._cache)
        self._cache.clear()
        if n:
            log.debug("ExcelDataCache 已清空 %d 条缓存", n)

    def size(self) -> int:
        """当前缓存条目数（调试用）。"""
        return len(self._cache)


# 全局单例：view / pane / 任何下游都用这一份
# 大写 + 模块级常量风格，告知调用方"这是单例，别自己 new"
EXCEL_DATA_CACHE = ExcelDataCache()
