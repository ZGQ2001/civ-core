"""全局样式预设加载器：yaml → StylePreset。

加载顺序：
  1. 读系统预设 presets/ui/style_preset.yaml（可缺失，缺失时全走 dataclass 默认值）
  2. 读用户预设 <user_presets_dir>/ui/style_preset.yaml（可缺失）
  3. 子键级合并：用户值覆盖系统值；缺失字段保留默认
  4. 通过 _dict_to_preset 重建为 StylePreset

兜底原则（与 preset_manager 一致）：
  • 文件不存在 → 当作空字典，不抛异常
  • yaml 语法错 → log warning + 当作空字典，不让用户改坏自己的配置文件让程序挂
"""

from __future__ import annotations

from dataclasses import fields
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from civ_core.configs.loader import find_project_root, load_config
from civ_core.domain.style_schema import Colors, Dimensions, StylePreset, Typography
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# 内部工具
# ──────────────────────────────────────────────────────────────────
def _read_yaml(path: Path) -> dict[str, Any]:
    """读 yaml 文件 → dict；失败一律回退到空字典（不抛异常）。"""
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as e:
        log.warning("样式预设读取失败 %s：%s（回退到默认值）", path, e)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _filter_known_keys(cls: type, raw: dict[str, Any]) -> dict[str, Any]:
    """只保留 dataclass 已声明字段；未知键被静默忽略（向前兼容）。"""
    valid = {f.name for f in fields(cls)}
    return {k: v for k, v in raw.items() if k in valid}


def _dict_to_preset(data: dict[str, Any]) -> StylePreset:
    """嵌套 dict → StylePreset。

    顶层键：typography / colors / dimensions（未知顶层键被忽略）
    子键：未知字段被忽略；缺失字段保留 dataclass 默认值
    """
    typography_data = _filter_known_keys(Typography, data.get("typography", {}) or {})
    colors_data = _filter_known_keys(Colors, data.get("colors", {}) or {})
    dimensions_data = _filter_known_keys(Dimensions, data.get("dimensions", {}) or {})

    return StylePreset(
        typography=Typography(**typography_data),
        colors=Colors(**colors_data),
        dimensions=Dimensions(**dimensions_data),
    )


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """两层合并：顶层段同名 → 子键并集（override 覆盖 base）。"""
    out: dict[str, Any] = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


# ──────────────────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def load_style_preset() -> StylePreset:
    """加载全局样式预设（lru_cache 单例）。

    系统 → 用户 → dataclass 默认值三层兜底。
    """
    project_root = find_project_root()
    system_path = project_root / "presets" / "ui" / "style_preset.yaml"

    system_data = _read_yaml(system_path)

    # 用户预设走 config.toml 决定的路径；config 加载失败也不让样式系统挂
    user_data: dict[str, Any] = {}
    try:
        cfg = load_config()
        user_path = cfg.paths.user_presets_dir / "ui" / "style_preset.yaml"
        user_data = _read_yaml(user_path)
    except Exception as e:
        log.warning("加载用户样式预设失败（保留系统/默认值）：%s", e)

    merged = _merge_dicts(system_data, user_data)
    return _dict_to_preset(merged)


def reload_style_preset() -> StylePreset:
    """清缓存重新加载（用户改完 yaml 想热更新时调）。"""
    load_style_preset.cache_clear()
    return load_style_preset()
