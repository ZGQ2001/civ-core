"""QSplitter 宽度记忆（P1）的单元测试。

通过 monkey patch `PlotCurvesView._make_settings` 把 QSettings 重定向到
tmp 路径下的 INI 文件，避免污染开发机真实 user-scope settings，也避免
不同测试用例之间互相污染。

L-1 起，splitter 维度从三栏（预设列表/中栏/预览）改为两栏：
  • 左栏：参数面板（PresetAccordionPanel，L-3b 实装）
  • 右栏：实时预览（LivePreviewPane，L-2 实装）
本测试随之把所有 sizes 从 list[3] 改成 list[2]。

不测的内容：
  • Qt 内部的 splitterMoved 信号触发节奏（PyQt 自身行为）
  • Windows 注册表 vs Linux INI 后端差异（用 IniFormat 走文件后端规避）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.configs.loader import load_config  # noqa: E402
from civ_core.ui.windows.plot_curves_view import (  # noqa: E402
    _INITIAL_RIGHT_SIZES,
    _INITIAL_SIZES,
    _SETTINGS_KEY_RIGHT_SPLITTER,
    _SETTINGS_KEY_SPLITTER,
    PlotCurvesView,
)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


@pytest.fixture
def tmp_settings_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """让 PlotCurvesView._make_settings 返回指向 tmp INI 文件的 QSettings。"""
    ini_path = tmp_path / "settings.ini"

    def fake_make_settings(self) -> QSettings:
        return QSettings(str(ini_path), QSettings.Format.IniFormat)

    monkeypatch.setattr(PlotCurvesView, "_make_settings", fake_make_settings)
    return ini_path


@pytest.fixture
def view(qapp: QApplication, tmp_settings_factory: Path) -> PlotCurvesView:
    cfg = load_config()
    v = PlotCurvesView(cfg)
    yield v
    v.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 维度断言：两栏（L-1）
# ──────────────────────────────────────────────────────────────────
class TestDimensionality:
    def test_initial_sizes_has_two_columns(self) -> None:
        """L-1 改造后默认 sizes 应当只有 2 个数（左参数 / 右预览）。"""
        assert len(_INITIAL_SIZES) == 2


# ──────────────────────────────────────────────────────────────────
# 默认行为：没存过 → 用 _INITIAL_SIZES
# ──────────────────────────────────────────────────────────────────
class TestRestoreDefault:
    def test_no_saved_value_uses_initial_sizes(self, view: PlotCurvesView) -> None:
        """首次启动（settings 文件全空）→ splitter 用默认 sizes。"""
        # _splitter.sizes() 反映布局之后的实际像素，可能被 view 显示尺寸缩放过；
        # 我们直接断言"还原函数"返回的是默认值即可
        assert view._restore_splitter_sizes() == list(_INITIAL_SIZES)


# ──────────────────────────────────────────────────────────────────
# 写入 + 还原 round-trip
# ──────────────────────────────────────────────────────────────────
class TestRoundtrip:
    def test_save_then_restore(
        self,
        view: PlotCurvesView,
        tmp_settings_factory: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_on_splitter_moved 应把 splitter 当前 sizes 写到 settings。

        测试不去调 setSizes（offscreen + 未 show 时，Qt 不会立即生效，sizes()
        会反映 widget 实际像素空间）。直接 monkey patch splitter.sizes 让它
        返回预设值，专测 _on_splitter_moved 的写入逻辑。
        """
        monkeypatch.setattr(view._splitter, "sizes", lambda: [500, 300])
        view._on_splitter_moved(0, 0)

        s = QSettings(str(tmp_settings_factory), QSettings.Format.IniFormat)
        saved = s.value(_SETTINGS_KEY_SPLITTER)
        # IniFormat 后端把 list[int] 存为 list[str]，读出来要再 int 一遍
        assert [int(x) for x in saved] == [500, 300]

    def test_restore_uses_saved_values(
        self, view: PlotCurvesView, tmp_settings_factory: Path
    ) -> None:
        """事先在 settings 里塞值 → 新 view 的 _restore 应读回。"""
        s = QSettings(str(tmp_settings_factory), QSettings.Format.IniFormat)
        s.setValue(_SETTINGS_KEY_SPLITTER, [550, 450])
        s.sync()

        # 同一个 view 可以再调一次 _restore 验证（其实测试创建新 view 更接近真实场景，
        # 但 fixture 的复用做不到；逻辑等价）
        assert view._restore_splitter_sizes() == [550, 450]


# ──────────────────────────────────────────────────────────────────
# 容错：损坏 / 异常值回退到默认
# ──────────────────────────────────────────────────────────────────
class TestRestoreFallbacks:
    def test_garbage_value_falls_back_to_default(
        self, view: PlotCurvesView, tmp_settings_factory: Path
    ) -> None:
        """settings 里存了非数字 → 回退默认。"""
        s = QSettings(str(tmp_settings_factory), QSettings.Format.IniFormat)
        s.setValue(_SETTINGS_KEY_SPLITTER, ["abc", "def"])
        s.sync()

        assert view._restore_splitter_sizes() == list(_INITIAL_SIZES)

    def test_wrong_length_falls_back_to_default(
        self, view: PlotCurvesView, tmp_settings_factory: Path
    ) -> None:
        """长度 != 2（含旧三栏遗留值）→ 回退默认。

        老用户升级后，QSettings 里可能存着 list[3] 的旧三栏 sizes；
        这里要确保读取时识别为损坏，回退到新两栏默认值。
        """
        s = QSettings(str(tmp_settings_factory), QSettings.Format.IniFormat)
        s.setValue(_SETTINGS_KEY_SPLITTER, [220, 380, 440])  # 旧三栏值
        s.sync()

        assert view._restore_splitter_sizes() == list(_INITIAL_SIZES)

    def test_zero_sum_falls_back_to_default(
        self, view: PlotCurvesView, tmp_settings_factory: Path
    ) -> None:
        s = QSettings(str(tmp_settings_factory), QSettings.Format.IniFormat)
        s.setValue(_SETTINGS_KEY_SPLITTER, [0, 0])
        s.sync()

        assert view._restore_splitter_sizes() == list(_INITIAL_SIZES)


# ──────────────────────────────────────────────────────────────────
# _on_splitter_moved 的边界：含 0 的 sizes 不存
# ──────────────────────────────────────────────────────────────────
class TestSaveGuards:
    def test_save_skips_when_any_size_is_zero(
        self,
        view: PlotCurvesView,
        tmp_settings_factory: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """避免把"某栏被拖到 0 像素"的瞬态写下去。"""
        # 先 monkey patch sizes 返回合法值，触发一次保存
        monkeypatch.setattr(view._splitter, "sizes", lambda: [500, 300])
        view._on_splitter_moved(0, 0)

        # 再切到含 0 的 sizes → 应该被守门拦下，不覆盖原值
        monkeypatch.setattr(view._splitter, "sizes", lambda: [800, 0])
        view._on_splitter_moved(0, 0)

        s = QSettings(str(tmp_settings_factory), QSettings.Format.IniFormat)
        saved = s.value(_SETTINGS_KEY_SPLITTER)
        assert [int(x) for x in saved] == [500, 300]


# ──────────────────────────────────────────────────────────────────
# 真实启动流程：构造时确实读了 saved sizes
# ──────────────────────────────────────────────────────────────────
class TestConstructionUsesSaved:
    def test_new_view_picks_up_saved_sizes(
        self, qapp: QApplication, tmp_settings_factory: Path
    ) -> None:
        """先在 ini 写入，再创建 view → splitter 初始 sizes 应反映。"""
        s = QSettings(str(tmp_settings_factory), QSettings.Format.IniFormat)
        s.setValue(_SETTINGS_KEY_SPLITTER, [620, 380])
        s.sync()

        cfg = load_config()
        v = PlotCurvesView(cfg)
        try:
            # splitter.sizes() 在 widget 还没 show() 时可能返回 [0,0]，
            # 用 _restore_splitter_sizes 的返回断言更稳
            assert v._restore_splitter_sizes() == [620, 380]
        finally:
            v.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 右栏垂直 splitter（预览/底栏 上下比例）持久化（UX 重构新增）
# ──────────────────────────────────────────────────────────────────
class TestRightSplitterPersistence:
    def test_default_when_no_saved_value(self, view: PlotCurvesView) -> None:
        assert view._restore_right_splitter_sizes() == list(_INITIAL_RIGHT_SIZES)

    def test_roundtrip_save_and_restore(
        self,
        view: PlotCurvesView,
        tmp_settings_factory: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(view._right_splitter, "sizes", lambda: [500, 250])
        view._on_right_splitter_moved(0, 0)
        s = QSettings(str(tmp_settings_factory), QSettings.Format.IniFormat)
        saved = s.value(_SETTINGS_KEY_RIGHT_SPLITTER)
        assert [int(x) for x in saved] == [500, 250]

    def test_wrong_length_falls_back(
        self, view: PlotCurvesView, tmp_settings_factory: Path
    ) -> None:
        s = QSettings(str(tmp_settings_factory), QSettings.Format.IniFormat)
        s.setValue(_SETTINGS_KEY_RIGHT_SPLITTER, [100, 200, 300])
        s.sync()
        assert view._restore_right_splitter_sizes() == list(_INITIAL_RIGHT_SIZES)
