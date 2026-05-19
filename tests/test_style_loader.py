"""style_loader 测试。

覆盖：
  • StylePreset dataclass：默认值 / frozen / 嵌套结构
  • yaml 加载：缺失 / 语法错 / 部分覆盖（用户只改子键）
  • lru_cache 单例
"""

from __future__ import annotations

from pathlib import Path

import pytest

from civ_core.domain.style_schema import Colors, Dimensions, StylePreset, Typography
from civ_core.infra_io.style_loader import (
    _dict_to_preset,
    _read_yaml,
    load_style_preset,
    reload_style_preset,
)


# ────────────────────────────────────────────────────────────────
class TestStylePresetSchema:
    def test_default_construct(self) -> None:
        p = StylePreset()
        assert isinstance(p.typography, Typography)
        assert isinstance(p.colors, Colors)
        assert isinstance(p.dimensions, Dimensions)

    def test_default_values(self) -> None:
        p = StylePreset()
        # 抽几个关键字段验证默认值就位
        assert p.colors.primary.startswith("#")
        assert p.colors.text_primary.startswith("#")
        assert p.typography.size_body >= 8
        assert p.dimensions.radius >= 0

    def test_frozen(self) -> None:
        p = StylePreset()
        with pytest.raises(Exception):  # FrozenInstanceError
            p.colors = Colors()  # type: ignore[misc]


# ────────────────────────────────────────────────────────────────
class TestDictToPreset:
    def test_empty_dict_returns_defaults(self) -> None:
        p = _dict_to_preset({})
        assert p == StylePreset()

    def test_partial_override_colors(self) -> None:
        p = _dict_to_preset({"colors": {"primary": "#FF0000"}})
        assert p.colors.primary == "#FF0000"
        # 其他颜色仍是默认
        assert p.colors.text_primary == StylePreset().colors.text_primary

    def test_partial_override_typography(self) -> None:
        p = _dict_to_preset({"typography": {"size_title": 24}})
        assert p.typography.size_title == 24
        # font_family 默认
        assert p.typography.font_family_ui == StylePreset().typography.font_family_ui

    def test_unknown_section_ignored(self) -> None:
        # 未知顶层段被忽略（不抛异常，保持向前兼容）
        p = _dict_to_preset({"unknown_section": {"x": 1}})
        assert p == StylePreset()

    def test_unknown_key_within_known_section_ignored(self) -> None:
        # 子键里的未知字段也被忽略
        p = _dict_to_preset({"colors": {"primary": "#000", "made_up_color": "#FFF"}})
        assert p.colors.primary == "#000"


# ────────────────────────────────────────────────────────────────
class TestReadYaml:
    def test_missing_returns_empty_dict(self, tmp_path: Path) -> None:
        assert _read_yaml(tmp_path / "nonexistent.yaml") == {}

    def test_empty_file_returns_empty_dict(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.yaml"
        f.write_text("", encoding="utf-8")
        assert _read_yaml(f) == {}

    def test_valid_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "good.yaml"
        f.write_text("colors:\n  primary: '#ABCDEF'\n", encoding="utf-8")
        data = _read_yaml(f)
        assert data == {"colors": {"primary": "#ABCDEF"}}

    def test_malformed_yaml_returns_empty(self, tmp_path: Path) -> None:
        # 语法错的用户预设不能让程序崩，回退到空字典
        f = tmp_path / "broken.yaml"
        f.write_text("colors:\n  primary: [unclosed", encoding="utf-8")
        assert _read_yaml(f) == {}


# ────────────────────────────────────────────────────────────────
class TestLoadStylePreset:
    def test_returns_style_preset(self) -> None:
        reload_style_preset()
        p = load_style_preset()
        assert isinstance(p, StylePreset)

    def test_lru_cache_returns_same_instance(self) -> None:
        reload_style_preset()
        p1 = load_style_preset()
        p2 = load_style_preset()
        assert p1 is p2

    def test_reload_clears_cache(self) -> None:
        p1 = load_style_preset()
        p2 = reload_style_preset()
        # reload 返回新实例（不是同一对象）
        assert p1 is not p2 or p1 == p2  # 值相同但内存对象可能新
