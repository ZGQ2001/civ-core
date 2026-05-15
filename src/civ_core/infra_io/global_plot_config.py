"""全局绘图配置的 QSettings I/O 包装（2026-05-14 去预设化重构）。

设计上下文
==========
用户原话"预设=曲线列表"。重构前每个预设打包了"环境字段（坐标轴/样式/输出
模板）+ 曲线列表"，导致改坐标轴标签被迫存为新预设、UI 双层概念混淆。

重构后：
  • 预设 JSON 只存"曲线列表"（每个 key = 一条曲线）
  • 环境字段成为唯一一份全局配置，走 QSettings 自动保存（每台机器独立）
  • UI 上字段改一次 → 自动落 QSettings，下次启动即恢复

本模块职责
==========
单向函数式 API：
  • load_global_plot_config() -> GlobalPlotConfig   读 QSettings 还原全局配置
  • save_global_plot_config(cfg)                    写 QSettings 持久化
  • DEFAULT_GLOBAL_CONFIG                           出厂默认（不带任何用户偏好）

为什么走 QSettings 不写 config.toml
==================================
  • config.toml 是项目级（git 维护）的"出厂默认"
  • QSettings 是用户级（每台机器独立）的"覆盖层"
  • 全局绘图配置属于"用户在 UI 上反复调节"的字段，频繁写 toml 既慢又会
    污染 git 工作树。沿用本项目其他 UI 偏好（如主题、splitter sizes）的
    QSettings 持久化模式
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from civ_core.domain.schema import GlobalPlotConfig
from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# QSettings 组织/应用名（与项目其他 UI 偏好一致）
_SETTINGS_ORG = "ZGQ"
_SETTINGS_APP = "CivCore"

# QSettings key 前缀：plot_curves/global/*
# 与 plot_curves/splitter_sizes 等已有 key 同 prefix，便于工具页归类
_KEY_PREFIX = "plot_curves/global/"

# 出厂默认（不带任何用户偏好）—— 用作 fallback + 单测基线
DEFAULT_GLOBAL_CONFIG = GlobalPlotConfig()


def _make_settings() -> QSettings:
    """工厂方法 —— 单测里可 monkey-patch 重定向到 tmp ini。"""
    return QSettings(_SETTINGS_ORG, _SETTINGS_APP)


# ──────────────────────────────────────────────────────────────────
# 私有：QSettings 值类型容错（与项目其他 _restore_* 一致）
# ──────────────────────────────────────────────────────────────────
def _as_bool(v: object, default: bool) -> bool:
    """QSettings 各后端返回类型不同：bool / "true"/"false" / int。"""
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return bool(v)
    return str(v).lower() in {"true", "1", "yes"}


def _as_int(v: object, default: int) -> int:
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _as_str(v: object, default: str) -> str:
    if v is None:
        return default
    return str(v)


def _as_range(v: object) -> tuple[float, float, float] | None:
    """读 [min, max, step] 三元组；None / 损坏 → None。"""
    if v is None:
        return None
    try:
        parts = [float(x) for x in v]  # type: ignore[union-attr]
    except (TypeError, ValueError):
        return None
    if len(parts) != 3:
        return None
    return (parts[0], parts[1], parts[2])


def _as_legend(v: object) -> str | None:
    """图例位置：'' / None → None（不显示）；其他原样。"""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# ──────────────────────────────────────────────────────────────────
# 公共 API
# ──────────────────────────────────────────────────────────────────
def load_global_plot_config() -> GlobalPlotConfig:
    """从 QSettings 还原全局绘图配置；缺失字段走 DEFAULT_GLOBAL_CONFIG 的值。"""
    s = _make_settings()

    def k(key: str) -> object:
        return s.value(_KEY_PREFIX + key)

    return GlobalPlotConfig(
        id_column=_as_str(k("id_column"), DEFAULT_GLOBAL_CONFIG.id_column),
        filename_template=_as_str(k("filename_template"), DEFAULT_GLOBAL_CONFIG.filename_template),
        title_template=_as_str(k("title_template"), DEFAULT_GLOBAL_CONFIG.title_template),
        dpi=_as_int(k("dpi"), DEFAULT_GLOBAL_CONFIG.dpi),
        x_label=_as_str(k("x_label"), DEFAULT_GLOBAL_CONFIG.x_label),
        y_label=_as_str(k("y_label"), DEFAULT_GLOBAL_CONFIG.y_label),
        x_range=_as_range(k("x_range")),
        y_range=_as_range(k("y_range")),
        x_log=_as_bool(k("x_log"), DEFAULT_GLOBAL_CONFIG.x_log),
        y_log=_as_bool(k("y_log"), DEFAULT_GLOBAL_CONFIG.y_log),
        y2_enabled=_as_bool(k("y2_enabled"), DEFAULT_GLOBAL_CONFIG.y2_enabled),
        y2_label=_as_str(k("y2_label"), DEFAULT_GLOBAL_CONFIG.y2_label),
        y2_range=_as_range(k("y2_range")),
        y2_log=_as_bool(k("y2_log"), DEFAULT_GLOBAL_CONFIG.y2_log),
        grid=_as_bool(k("grid"), DEFAULT_GLOBAL_CONFIG.grid),
        legend_loc=_as_legend(k("legend_loc")),
    )


def save_global_plot_config(cfg: GlobalPlotConfig) -> None:
    """把 GlobalPlotConfig 全量写入 QSettings（覆盖前一次值）。

    实现为"全量覆盖"而非"diff 写"：QSettings 写一个 key 性能极低成本，全量
    覆盖代码更简单且没有"漏写半边字段"的风险。
    """
    s = _make_settings()

    def w(key: str, value: object) -> None:
        s.setValue(_KEY_PREFIX + key, value)

    w("id_column", cfg.id_column)
    w("filename_template", cfg.filename_template)
    w("title_template", cfg.title_template)
    w("dpi", int(cfg.dpi))
    w("x_label", cfg.x_label)
    w("y_label", cfg.y_label)
    w("x_range", list(cfg.x_range) if cfg.x_range is not None else None)
    w("y_range", list(cfg.y_range) if cfg.y_range is not None else None)
    w("x_log", bool(cfg.x_log))
    w("y_log", bool(cfg.y_log))
    w("y2_enabled", bool(cfg.y2_enabled))
    w("y2_label", cfg.y2_label)
    w("y2_range", list(cfg.y2_range) if cfg.y2_range is not None else None)
    w("y2_log", bool(cfg.y2_log))
    w("grid", bool(cfg.grid))
    w("legend_loc", cfg.legend_loc if cfg.legend_loc is not None else "")
    s.sync()


__all__ = [
    "DEFAULT_GLOBAL_CONFIG",
    "load_global_plot_config",
    "save_global_plot_config",
]
