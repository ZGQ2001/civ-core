"""GlobalPlotConfig + QSettings I/O 测试（2026-05-14 去预设化重构）。

覆盖：
  • dataclass 默认值合法
  • to_preset_overlay_dict 把 cfg + curves 拼成 build_jobs 兼容的"伪预设"
  • load/save round-trip（用 tmp QSettings ini，避免污染真实用户配置）
  • 类型容错：损坏 / 缺失值 fallback 到默认
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.domain.schema import GlobalPlotConfig  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


@pytest.fixture
def tmp_qsettings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把 _make_settings 重定向到 tmp ini，避免污染真实用户配置。"""
    ini = tmp_path / "settings.ini"

    from civ_core.infra_io import global_plot_config as gpc

    def fake() -> QSettings:
        return QSettings(str(ini), QSettings.Format.IniFormat)

    monkeypatch.setattr(gpc, "_make_settings", fake)
    return ini


# ──────────────────────────────────────────────────────────────────
# GlobalPlotConfig dataclass 本身
# ──────────────────────────────────────────────────────────────────
class TestGlobalPlotConfigDataclass:
    def test_default_values(self) -> None:
        cfg = GlobalPlotConfig()
        assert cfg.id_column == "编号"
        assert cfg.filename_template == "{id}.png"
        assert cfg.x_label == "X"
        assert cfg.y_label == "Y"
        assert cfg.x_range is None
        assert cfg.y_range is None
        assert cfg.x_log is False
        assert cfg.y_log is False
        assert cfg.y2_enabled is False
        assert cfg.grid is True
        assert cfg.legend_loc is None
        assert cfg.dpi == 150

    def test_to_preset_overlay_dict_shape(self) -> None:
        """与 build_jobs 期待的"完整预设 dict"结构一致。"""
        cfg = GlobalPlotConfig(
            id_column="编号",
            x_label="位移(mm)",
            y_label="荷载(KN)",
            y_range=(0.0, 200.0, 20.0),
            grid=True,
            legend_loc="best",
        )
        curves = [{"name": "加载", "color": "#1F4FE0", "points": []}]
        d = cfg.to_preset_overlay_dict(curves)

        assert d["id_column"] == "编号"
        assert d["x_axis"] == {"label": "位移(mm)", "range": None, "log": False}
        assert d["y_axis"] == {"label": "荷载(KN)", "range": [0.0, 200.0, 20.0], "log": False}
        assert d["y_axis2"] is None
        assert d["style"] == {"grid": True, "legend": "best"}
        assert d["curves"] is curves  # 同一引用（不深拷贝，调用方控制）

    def test_to_preset_overlay_dict_with_y2(self) -> None:
        cfg = GlobalPlotConfig(y2_enabled=True, y2_label="时间(s)", y2_log=True)
        d = cfg.to_preset_overlay_dict([])
        assert d["y_axis2"] == {"label": "时间(s)", "range": None, "log": True}


# ──────────────────────────────────────────────────────────────────
# QSettings round-trip
# ──────────────────────────────────────────────────────────────────
class TestQSettingsRoundtrip:
    def test_load_no_saved_returns_default(self, qapp: QApplication, tmp_qsettings: Path) -> None:
        """没存过任何东西时，load 返回出厂默认。"""
        from civ_core.infra_io.global_plot_config import (
            DEFAULT_GLOBAL_CONFIG,
            load_global_plot_config,
        )

        cfg = load_global_plot_config()
        assert cfg == DEFAULT_GLOBAL_CONFIG

    def test_save_then_load_roundtrip(self, qapp: QApplication, tmp_qsettings: Path) -> None:
        from civ_core.infra_io.global_plot_config import (
            load_global_plot_config,
            save_global_plot_config,
        )

        original = GlobalPlotConfig(
            id_column="试件编号",
            filename_template="{id}_曲线.png",
            title_template="{id}：荷载-位移",
            dpi=200,
            x_label="位移(mm)",
            y_label="荷载(KN)",
            x_range=(0.0, 50.0, 5.0),
            y_range=(0.0, 200.0, 20.0),
            x_log=False,
            y_log=True,
            y2_enabled=True,
            y2_label="时间",
            y2_range=(0.0, 100.0, 10.0),
            y2_log=False,
            grid=False,
            legend_loc="upper right",
        )
        save_global_plot_config(original)
        restored = load_global_plot_config()
        assert restored == original

    def test_partial_save_fields_kept(self, qapp: QApplication, tmp_qsettings: Path) -> None:
        """save 是全量覆盖：新值完全替换前一次。"""
        from civ_core.infra_io.global_plot_config import (
            load_global_plot_config,
            save_global_plot_config,
        )

        save_global_plot_config(GlobalPlotConfig(x_label="A"))
        save_global_plot_config(GlobalPlotConfig(x_label="B"))
        assert load_global_plot_config().x_label == "B"


# ──────────────────────────────────────────────────────────────────
# 类型容错（QSettings 各后端返回类型不同）
# ──────────────────────────────────────────────────────────────────
class TestTypeCoercion:
    def test_load_with_garbage_range_falls_back_to_none(
        self, qapp: QApplication, tmp_qsettings: Path
    ) -> None:
        """range 字段如果存的不是 3 元数字列表 → None。"""
        from civ_core.infra_io.global_plot_config import load_global_plot_config

        from civ_core.infra_io import global_plot_config as gpc

        s = gpc._make_settings()
        s.setValue(gpc._KEY_PREFIX + "x_range", "garbage")
        s.setValue(gpc._KEY_PREFIX + "y_range", [1.0, 2.0])  # 长度不对
        s.sync()

        cfg = load_global_plot_config()
        assert cfg.x_range is None
        assert cfg.y_range is None

    def test_legend_empty_string_returns_none(
        self, qapp: QApplication, tmp_qsettings: Path
    ) -> None:
        """legend_loc 存空串 → None（不显示图例）。"""
        from civ_core.infra_io.global_plot_config import load_global_plot_config

        from civ_core.infra_io import global_plot_config as gpc

        s = gpc._make_settings()
        s.setValue(gpc._KEY_PREFIX + "legend_loc", "")
        s.sync()
        cfg = load_global_plot_config()
        assert cfg.legend_loc is None

    def test_bool_int_string_variants_all_recognized(
        self, qapp: QApplication, tmp_qsettings: Path
    ) -> None:
        """QSettings 后端可能把 bool 存成 'true'/'false'/'1'/'0'。"""
        from civ_core.infra_io.global_plot_config import load_global_plot_config

        from civ_core.infra_io import global_plot_config as gpc

        s = gpc._make_settings()
        s.setValue(gpc._KEY_PREFIX + "x_log", "true")
        s.setValue(gpc._KEY_PREFIX + "y_log", 1)
        s.setValue(gpc._KEY_PREFIX + "grid", False)
        s.sync()
        cfg = load_global_plot_config()
        assert cfg.x_log is True
        assert cfg.y_log is True
        assert cfg.grid is False


# ──────────────────────────────────────────────────────────────────
# build_jobs 兼容性：确保拼出来的 dict 能被现有 build_jobs 接受
# ──────────────────────────────────────────────────────────────────
class TestBuildJobsCompatibility:
    def test_overlay_dict_has_all_keys_build_jobs_reads(self) -> None:
        """build_jobs 内部读 id_column / x_axis / y_axis / y_axis2 / style /
        curves / filename_template / title_template —— 全部都该有。"""
        cfg = GlobalPlotConfig()
        d = cfg.to_preset_overlay_dict([{"name": "x", "color": "#000000", "points": []}])
        for key in (
            "id_column",
            "filename_template",
            "title_template",
            "x_axis",
            "y_axis",
            "y_axis2",
            "style",
            "curves",
        ):
            assert key in d, f"build_jobs 需要 {key} 字段"
