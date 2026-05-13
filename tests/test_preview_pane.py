"""PreviewPane 的单元测试。

测试策略：
  • 用 QPixmap.save 在 tmp_path 造几张真 PNG 当输入（不依赖 matplotlib，
    保持单测轻量）
  • 验证 set_results / clear / 选中切换 / 加载失败兜底

不测的内容：
  • QLabel 的实际渲染像素（Qt 内部）
  • resize 时缩放质量（视觉，由 SmoothTransformation 保证）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.ui.components.preview_pane import PreviewPane  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


@pytest.fixture
def pane(qapp: QApplication) -> PreviewPane:
    p = PreviewPane()
    yield p
    p.deleteLater()


def _make_test_png(path: Path, color: Qt.GlobalColor = Qt.GlobalColor.red) -> None:
    """在 path 写一张 32×32 纯色 PNG。"""
    pix = QPixmap(32, 32)
    pix.fill(QColor(color))
    saved = pix.save(str(path), "PNG")
    assert saved, f"测试 fixture 写 PNG 失败：{path}"


# ──────────────────────────────────────────────────────────────────
# 初始 / 空态
# ──────────────────────────────────────────────────────────────────
class TestInitialState:
    def test_initial_thumb_list_empty(self, pane: PreviewPane) -> None:
        assert pane._thumb_list.count() == 0

    def test_initial_label_shows_hint(self, pane: PreviewPane) -> None:
        """构造完成后大图区应显示空态提示。"""
        assert "运行批量出图后" in pane._big_label.text()

    def test_initial_no_pixmap(self, pane: PreviewPane) -> None:
        """空态时 pixmap 应为空。"""
        pix = pane._big_label.pixmap()
        assert pix is None or pix.isNull()


# ──────────────────────────────────────────────────────────────────
# set_results：填充 + 自动选中第一张
# ──────────────────────────────────────────────────────────────────
class TestSetResults:
    def test_populates_thumb_list(self, pane: PreviewPane, tmp_path: Path) -> None:
        files = [tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"]
        for f in files:
            _make_test_png(f)

        pane.set_results(files)

        assert pane._thumb_list.count() == 3
        # 文件名作为 item 文字
        names = {pane._thumb_list.item(i).text() for i in range(3)}
        assert names == {"a.png", "b.png", "c.png"}

    def test_auto_selects_first_item(self, pane: PreviewPane, tmp_path: Path) -> None:
        files = [tmp_path / "a.png", tmp_path / "b.png"]
        for f in files:
            _make_test_png(f)

        pane.set_results(files)

        assert pane._thumb_list.currentRow() == 0

    def test_first_image_loaded_as_big(self, pane: PreviewPane, tmp_path: Path) -> None:
        """选中第一张后，大图区应已加载 pixmap（非空、非空文字）。"""
        f = tmp_path / "a.png"
        _make_test_png(f)

        pane.set_results([f])

        # 文字应被清掉，pixmap 应非空
        assert pane._big_label.text() == ""
        pix = pane._big_label.pixmap()
        assert pix is not None and not pix.isNull()
        # _current_pixmap 已缓存原图（用于 resize 重缩放）
        assert pane._current_pixmap is not None
        assert not pane._current_pixmap.isNull()

    def test_empty_paths_falls_back_to_empty_state(self, pane: PreviewPane) -> None:
        """set_results 传空 list → 等价于 clear。"""
        pane.set_results([])
        assert pane._thumb_list.count() == 0
        assert "运行批量出图后" in pane._big_label.text()

    def test_replaces_old_results(self, pane: PreviewPane, tmp_path: Path) -> None:
        """新一轮出图 → 列表不应留旧条目。"""
        old1 = tmp_path / "old1.png"
        old2 = tmp_path / "old2.png"
        new1 = tmp_path / "new1.png"
        for f in (old1, old2, new1):
            _make_test_png(f)

        pane.set_results([old1, old2])
        assert pane._thumb_list.count() == 2

        pane.set_results([new1])
        assert pane._thumb_list.count() == 1
        assert pane._thumb_list.item(0).text() == "new1.png"


# ──────────────────────────────────────────────────────────────────
# 切换缩略图 → 大图刷新
# ──────────────────────────────────────────────────────────────────
class TestSelectionChange:
    def test_select_other_thumb_updates_big_image(self, pane: PreviewPane, tmp_path: Path) -> None:
        red = tmp_path / "red.png"
        blue = tmp_path / "blue.png"
        _make_test_png(red, Qt.GlobalColor.red)
        _make_test_png(blue, Qt.GlobalColor.blue)

        pane.set_results([red, blue])
        first_pix = pane._current_pixmap
        assert first_pix is not None

        # 切到 blue
        pane._thumb_list.setCurrentRow(1)
        second_pix = pane._current_pixmap
        assert second_pix is not None
        # 不同图 → cacheKey 不同
        assert first_pix.cacheKey() != second_pix.cacheKey()


# ──────────────────────────────────────────────────────────────────
# clear()
# ──────────────────────────────────────────────────────────────────
class TestClear:
    def test_clear_resets_to_empty_state(self, pane: PreviewPane, tmp_path: Path) -> None:
        f = tmp_path / "a.png"
        _make_test_png(f)
        pane.set_results([f])
        assert pane._thumb_list.count() == 1

        pane.clear()

        assert pane._thumb_list.count() == 0
        assert pane._current_pixmap is None
        assert "运行批量出图后" in pane._big_label.text()
        # pixmap 应清掉
        pix = pane._big_label.pixmap()
        assert pix is None or pix.isNull()


# ──────────────────────────────────────────────────────────────────
# 加载失败兜底
# ──────────────────────────────────────────────────────────────────
class TestLoadFailures:
    def test_missing_file_does_not_crash(self, pane: PreviewPane, tmp_path: Path) -> None:
        """文件不存在 → 列表条目仍创建（标 tooltip），后续条目不受影响。"""
        good = tmp_path / "good.png"
        _make_test_png(good)
        bad = tmp_path / "missing.png"  # 不创建文件

        pane.set_results([bad, good])  # 故意把坏的放前面

        # 两条 item 都在
        assert pane._thumb_list.count() == 2
        # 默认选中第一项 → 坏文件 → 大图区应显示"无法加载"
        assert "无法加载" in pane._big_label.text()
        # 切到 good → 大图正常显示
        pane._thumb_list.setCurrentRow(1)
        assert pane._current_pixmap is not None
        assert not pane._current_pixmap.isNull()


# ──────────────────────────────────────────────────────────────────
# UserRole 上挂的 Path
# ──────────────────────────────────────────────────────────────────
class TestPathStorage:
    def test_path_attached_to_item_user_role(self, pane: PreviewPane, tmp_path: Path) -> None:
        """每个列表项的 UserRole 应挂原 Path（供 _on_current_changed 取用）。"""
        f = tmp_path / "x.png"
        _make_test_png(f)
        pane.set_results([f])

        item = pane._thumb_list.item(0)
        stored = item.data(Qt.ItemDataRole.UserRole)
        assert isinstance(stored, Path)
        assert stored == f

    def test_tooltip_shows_full_path(self, pane: PreviewPane, tmp_path: Path) -> None:
        """tooltip 应是完整路径（让用户看到落到哪个目录）。"""
        f = tmp_path / "x.png"
        _make_test_png(f)
        pane.set_results([f])

        assert pane._thumb_list.item(0).toolTip() == str(f)
