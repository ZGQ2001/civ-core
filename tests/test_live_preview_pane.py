"""LivePreviewPane（L-2.3）单元测试。

测试目标：
  • 防抖：300ms 内连发多次 request_redraw 只触发一次渲染
  • 串行：渲染期间收到新请求 → 当前完成后自动追加一次
  • 占位提示：缺预设 / 缺数据源时不启动 worker，只更新提示

不测的内容：
  • 真实 matplotlib 渲染输出（已在 test_chart_writer_bytes 覆盖）
  • QPixmap 像素正确性（依赖 Qt 自身渲染）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


@pytest.fixture
def patched_worker(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """把 _PreviewWorker.run 替换成"立即 emit ready 假 PNG"的桩。

    这样可以专注测防抖 / 串行调度逻辑，不依赖真 matplotlib（慢且重）。
    返回的 dict 用来统计真实 worker 启动次数。
    """
    from civ_core.ui.components import live_preview_pane as lpp

    stats = {"runs": 0}

    real_signals_cls = lpp._PreviewWorkerSignals

    class _StubWorker(lpp._PreviewWorker):  # type: ignore[misc]
        def run(self) -> None:  # noqa: D401
            stats["runs"] += 1
            # 假 PNG header + 一些字节 —— QPixmap.loadFromData 会失败但不影响
            # 流程统计；signals 仍然 emit 出去触发主线程回调
            fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
            try:
                self.signals.ready.emit(self._gen, fake_png)
            except RuntimeError:
                pass

    # 把模块里的类替换掉，让 _launch_worker 走 stub
    monkeypatch.setattr(lpp, "_PreviewWorker", _StubWorker)
    monkeypatch.setattr(lpp, "_PreviewWorkerSignals", real_signals_cls)
    return stats


def _make_preset() -> dict[str, Any]:
    """造一个最低限度的预设字典，让 build_jobs 不会因缺字段早抛。

    但因为我们 stub 了 worker，run 不真跑 build_jobs，preset 内容其实无关；
    保留这个 helper 是为了将来想"半 stub"时复用。
    """
    return {
        "id_column": "X",
        "filename_template": "{id}.png",
        "title_template": "{id}",
        "x_axis": {"label": "x", "range": None},
        "y_axis": {"label": "y", "range": None},
        "curves": [],
    }


# ──────────────────────────────────────────────────────────────────
# 占位提示：缺预设 / 缺数据源 → 不启动 worker
# ──────────────────────────────────────────────────────────────────
class TestPlaceholderHints:
    def test_initial_hint_visible(self, qapp: QApplication) -> None:
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            assert "请先" in pane._hint_label.text()
        finally:
            pane.deleteLater()

    def test_no_preset_does_not_launch_worker(
        self,
        qapp: QApplication,
        patched_worker: dict[str, int],
        tmp_path: Path,
        qtbot: Any,
    ) -> None:
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.set_data_source(tmp_path / "x.xlsx")  # 触发防抖
            qtbot.wait(500)
            assert patched_worker["runs"] == 0
            assert "预设" in pane._hint_label.text()
        finally:
            pane.deleteLater()

    def test_no_data_source_does_not_launch_worker(
        self,
        qapp: QApplication,
        patched_worker: dict[str, int],
        qtbot: Any,
    ) -> None:
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.set_preset(_make_preset())
            qtbot.wait(500)
            assert patched_worker["runs"] == 0
            assert "Excel" in pane._hint_label.text() or "数据源" in pane._hint_label.text()
        finally:
            pane.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 防抖：连发多次 → 只触发一次 worker
# ──────────────────────────────────────────────────────────────────
class TestDebounce:
    def test_five_calls_in_window_trigger_one_worker(
        self,
        qapp: QApplication,
        patched_worker: dict[str, int],
        tmp_path: Path,
        qtbot: Any,
    ) -> None:
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            # 先把数据源设齐（这些调用本身会触发防抖，等它一次后清零）
            pane.set_preset(_make_preset())
            pane.set_data_source(tmp_path / "x.xlsx")
            qtbot.wait(500)
            patched_worker["runs"] = 0  # 重置统计窗口

            # 在 300ms 内连发 5 次 —— 应当合并成 1 次实际 worker 启动
            for _ in range(5):
                pane.request_redraw()
                qtbot.wait(30)  # 每 30ms 一发，5 发共 150ms < 300ms 防抖窗口

            qtbot.wait(500)  # 等防抖触发完 + worker 跑完
            assert patched_worker["runs"] == 1
        finally:
            pane.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 串行：渲染期间收到新请求 → 当前完成后自动补一次
# ──────────────────────────────────────────────────────────────────
class TestSerialPending:
    def test_pending_path_followup_render(
        self,
        qapp: QApplication,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        qtbot: Any,
    ) -> None:
        """渲染期间主动调 _do_redraw 触发 pending 分支：
        当前 worker emit ready 后应自动补一次新 worker。

        策略：直接调 pane._do_redraw() 让 worker 真启动；启动后立刻把
        _is_rendering 视作 True（手动设 _pending=True 模拟），断言 emit ready
        回到主线程时 _is_rendering 复位 + 又起了一次 worker。
        """
        from civ_core.ui.components import live_preview_pane as lpp

        stats = {"runs": 0}

        class _Stub(lpp._PreviewWorker):  # type: ignore[misc]
            def run(self) -> None:  # noqa: D401
                stats["runs"] += 1
                fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
                try:
                    self.signals.ready.emit(self._gen, fake_png)
                except RuntimeError:
                    pass

        monkeypatch.setattr(lpp, "_PreviewWorker", _Stub)

        pane = lpp.LivePreviewPane()
        try:
            pane._preset = _make_preset()
            pane._data_source = tmp_path / "x.xlsx"

            # 启动第一次 worker（绕过防抖直接 _do_redraw）
            pane._do_redraw()
            # 立刻把 pending 置上，模拟"渲染中又来一次请求"
            pane._pending = True

            # 等主线程事件循环消费 ready 信号 → 回调里发现 pending → 补一次
            qtbot.waitUntil(lambda: stats["runs"] >= 2, timeout=2000)
            assert stats["runs"] == 2
            # runs+=1 在 worker.run() 入口；它和 ready 信号回主线程之间还有一段
            # 跨线程队列投递，再等一轮 _is_rendering 复位（CI 慢机时序敏感）
            qtbot.waitUntil(lambda: not pane._is_rendering, timeout=2000)
            assert pane._is_rendering is False
            assert pane._pending is False
        finally:
            pane.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 接口形态：set_preset/set_data_source/request_redraw 都存在
# ──────────────────────────────────────────────────────────────────
class TestPublicInterface:
    def test_has_required_methods(self, qapp: QApplication) -> None:
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            assert callable(pane.set_preset)
            assert callable(pane.set_data_source)
            assert callable(pane.request_redraw)
        finally:
            pane.deleteLater()


# ──────────────────────────────────────────────────────────────────
# P1.5-Step1：highlight_row 切换 _current_row_idx + 触发重绘
# ──────────────────────────────────────────────────────────────────
class TestHighlightRowSwitchesPreview:
    """P1.5 Step 1：highlight_row(idx) 不再只是占位，
    应该真切换预览到第 idx 行的图。"""

    def test_initial_row_idx_is_zero(self, qapp: QApplication) -> None:
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            assert pane._current_row_idx == 0
        finally:
            pane.deleteLater()

    def test_highlight_row_updates_idx(self, qapp: QApplication) -> None:
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.highlight_row(3)
            assert pane._current_row_idx == 3
        finally:
            pane.deleteLater()

    def test_highlight_row_triggers_redraw(
        self,
        qapp: QApplication,
        patched_worker: dict[str, int],
        tmp_path: Path,
        qtbot: Any,
    ) -> None:
        """数据已齐备时，highlight_row 应触发 worker 跑一次（重绘新行）。"""
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.set_preset(_make_preset())
            pane.set_data_source(tmp_path / "x.xlsx")
            qtbot.wait(500)
            patched_worker["runs"] = 0  # 重置

            pane.highlight_row(2)
            qtbot.wait(500)  # 等防抖 + worker
            assert patched_worker["runs"] == 1
        finally:
            pane.deleteLater()

    def test_set_preset_resets_row_idx(self, qapp: QApplication) -> None:
        """切预设时，原 row_idx 在新数据集可能越界 → 重置 0。"""
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.highlight_row(5)
            assert pane._current_row_idx == 5
            pane.set_preset(_make_preset())
            assert pane._current_row_idx == 0
        finally:
            pane.deleteLater()

    def test_set_data_source_resets_row_idx(self, qapp: QApplication, tmp_path: Path) -> None:
        """切数据源同理：原 idx 对新文件无意义 → 重置 0。"""
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.highlight_row(5)
            pane.set_data_source(tmp_path / "x.xlsx")
            assert pane._current_row_idx == 0
        finally:
            pane.deleteLater()

    def test_highlight_negative_or_huge_is_ignored(self, qapp: QApplication) -> None:
        """负数 / 极端值不应崩 —— 负数视为"不切换"。"""
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.highlight_row(4)
            pane.highlight_row(-1)  # 忽略
            assert pane._current_row_idx == 4
        finally:
            pane.deleteLater()


# ──────────────────────────────────────────────────────────────────
# P1.5-Step1：_pick_job_index 纯函数（越界回退 0；空列表回退 -1）
# ──────────────────────────────────────────────────────────────────
class TestPickJobIndex:
    """worker 内 jobs[row_idx] 的越界回退策略 —— 抽成纯函数便于单测。"""

    def test_normal_in_range(self) -> None:
        from civ_core.ui.components.live_preview_pane import _pick_job_index

        assert _pick_job_index(5, 2) == 2
        assert _pick_job_index(5, 0) == 0
        assert _pick_job_index(5, 4) == 4

    def test_out_of_range_falls_back_to_zero(self) -> None:
        from civ_core.ui.components.live_preview_pane import _pick_job_index

        assert _pick_job_index(5, 5) == 0  # 上界外
        assert _pick_job_index(5, 100) == 0
        assert _pick_job_index(5, -1) == 0

    def test_empty_jobs_returns_negative(self) -> None:
        """空 jobs：返回 -1，调用方据此走"无可用图"分支。"""
        from civ_core.ui.components.live_preview_pane import _pick_job_index

        assert _pick_job_index(0, 0) == -1
        assert _pick_job_index(0, 3) == -1


# ──────────────────────────────────────────────────────────────────
# P1.5-Step2：叠加对比模式开关
# ──────────────────────────────────────────────────────────────────
class TestOverlayMode:
    """LivePreviewPane.set_overlay_mode 切换单行/叠加渲染模式。"""

    def test_initial_overlay_mode_is_false(self, qapp: QApplication) -> None:
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            assert pane._overlay_mode is False
        finally:
            pane.deleteLater()

    def test_set_overlay_mode_updates_state(self, qapp: QApplication) -> None:
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.set_overlay_mode(True)
            assert pane._overlay_mode is True
            pane.set_overlay_mode(False)
            assert pane._overlay_mode is False
        finally:
            pane.deleteLater()

    def test_set_overlay_mode_triggers_redraw(
        self,
        qapp: QApplication,
        patched_worker: dict[str, int],
        tmp_path: Path,
        qtbot: Any,
    ) -> None:
        """切模式应触发一次重绘（叠加 vs 单行渲染目标不同）。"""
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.set_preset(_make_preset())
            pane.set_data_source(tmp_path / "x.xlsx")
            qtbot.wait(500)
            patched_worker["runs"] = 0

            pane.set_overlay_mode(True)
            qtbot.wait(500)
            assert patched_worker["runs"] == 1
        finally:
            pane.deleteLater()

    def test_set_same_mode_does_not_redraw(
        self,
        qapp: QApplication,
        patched_worker: dict[str, int],
        tmp_path: Path,
        qtbot: Any,
    ) -> None:
        """重复设置相同模式应是 no-op，不重绘。"""
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.set_preset(_make_preset())
            pane.set_data_source(tmp_path / "x.xlsx")
            qtbot.wait(500)
            patched_worker["runs"] = 0

            pane.set_overlay_mode(False)  # 与初始相同
            qtbot.wait(500)
            assert patched_worker["runs"] == 0
        finally:
            pane.deleteLater()

    def test_worker_accepts_overlay_mode_kw(self, qapp: QApplication) -> None:
        """_PreviewWorker.__init__ 接受 overlay_mode 关键字参数。"""
        import inspect

        from civ_core.ui.components.live_preview_pane import _PreviewWorker

        sig = inspect.signature(_PreviewWorker.__init__)
        assert "overlay_mode" in sig.parameters

    def test_highlight_in_overlay_mode_does_not_reset_idx(self, qapp: QApplication) -> None:
        """叠加模式下 highlight_row 应保留 idx 用于"高亮哪根"。"""
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pane.set_overlay_mode(True)
            pane.highlight_row(3)
            assert pane._current_row_idx == 3
            assert pane._overlay_mode is True
        finally:
            pane.deleteLater()


# ──────────────────────────────────────────────────────────────────
# P1.5-Step3b：_pixel_to_data + _find_nearest_row 纯函数
# ──────────────────────────────────────────────────────────────────
class TestPixelToData:
    """PNG 像素 → data 坐标 反算（线性 / log / 越界）。"""

    def test_inside_box_linear(self) -> None:
        from civ_core.ui.components.live_preview_pane import _pixel_to_data

        # axes 在 PNG 中占 (100, 50) - (500, 350)，即 400×300 像素
        bbox = (100.0, 50.0, 500.0, 350.0)
        # 左下角 (100, 350) → (0, 0)
        r = _pixel_to_data(100.0, 350.0, axes_bbox_px=bbox, xlim=(0.0, 10.0), ylim=(0.0, 100.0))
        assert r is not None
        assert abs(r[0] - 0.0) < 1e-9
        assert abs(r[1] - 0.0) < 1e-9
        # 右上角 (500, 50) → (10, 100)
        r = _pixel_to_data(500.0, 50.0, axes_bbox_px=bbox, xlim=(0.0, 10.0), ylim=(0.0, 100.0))
        assert r is not None
        assert abs(r[0] - 10.0) < 1e-9
        assert abs(r[1] - 100.0) < 1e-9
        # 中心
        r = _pixel_to_data(300.0, 200.0, axes_bbox_px=bbox, xlim=(0.0, 10.0), ylim=(0.0, 100.0))
        assert r is not None
        assert abs(r[0] - 5.0) < 1e-9
        assert abs(r[1] - 50.0) < 1e-9

    def test_outside_returns_none(self) -> None:
        from civ_core.ui.components.live_preview_pane import _pixel_to_data

        bbox = (100.0, 50.0, 500.0, 350.0)
        assert (
            _pixel_to_data(99.0, 200.0, axes_bbox_px=bbox, xlim=(0.0, 1.0), ylim=(0.0, 1.0)) is None
        )
        assert (
            _pixel_to_data(501.0, 200.0, axes_bbox_px=bbox, xlim=(0.0, 1.0), ylim=(0.0, 1.0))
            is None
        )
        assert (
            _pixel_to_data(200.0, 49.0, axes_bbox_px=bbox, xlim=(0.0, 1.0), ylim=(0.0, 1.0)) is None
        )
        assert (
            _pixel_to_data(200.0, 351.0, axes_bbox_px=bbox, xlim=(0.0, 1.0), ylim=(0.0, 1.0))
            is None
        )

    def test_log_axis_uses_log10_interp(self) -> None:
        """log 轴：像素中心 → 10**((log10(min)+log10(max))/2)。"""
        import math

        from civ_core.ui.components.live_preview_pane import _pixel_to_data

        bbox = (0.0, 0.0, 100.0, 100.0)
        # x: log 轴 1..1000；中心像素 50 应映射到 10**1.5 ≈ 31.62
        r = _pixel_to_data(
            50.0,
            50.0,
            axes_bbox_px=bbox,
            xlim=(1.0, 1000.0),
            ylim=(0.0, 1.0),
            x_log=True,
            y_log=False,
        )
        assert r is not None
        assert math.isclose(r[0], 10**1.5, rel_tol=1e-6)

    def test_degenerate_bbox_returns_none(self) -> None:
        from civ_core.ui.components.live_preview_pane import _pixel_to_data

        # x1 == x0：退化
        r = _pixel_to_data(
            50.0, 50.0, axes_bbox_px=(100.0, 50.0, 100.0, 350.0), xlim=(0.0, 1.0), ylim=(0.0, 1.0)
        )
        assert r is None


class TestLabelToPngPixel:
    """QLabel 坐标 → PNG 像素（KeepAspectRatio 居中显示）。"""

    def test_exact_fit_no_letterbox(self) -> None:
        from civ_core.ui.components.live_preview_pane import _label_to_png_pixel

        # label 和 pixmap 同比例：无留白，scale = 1
        r = _label_to_png_pixel(150.0, 100.0, label_size=(300, 200), pixmap_size=(300, 200))
        assert r is not None
        assert abs(r[0] - 150.0) < 1e-9
        assert abs(r[1] - 100.0) < 1e-9

    def test_horizontal_letterbox(self) -> None:
        """pixmap 比 label 更宽：上下留白。"""
        from civ_core.ui.components.live_preview_pane import _label_to_png_pixel

        # pixmap 400×200 → label 400×300：scale = min(1.0, 1.5) = 1.0
        # shown 400×200，上下各留 50。中心 (200, 150) → pixmap (200, 100)
        r = _label_to_png_pixel(200.0, 150.0, label_size=(400, 300), pixmap_size=(400, 200))
        assert r is not None
        assert abs(r[0] - 200.0) < 1e-9
        assert abs(r[1] - 100.0) < 1e-9

    def test_vertical_letterbox(self) -> None:
        """pixmap 比 label 更高：左右留白。"""
        from civ_core.ui.components.live_preview_pane import _label_to_png_pixel

        # pixmap 200×400 → label 300×400：scale = min(1.5, 1.0) = 1.0
        # shown 200×400，左右各留 50。点 (150, 200) → pixmap (100, 200)
        r = _label_to_png_pixel(150.0, 200.0, label_size=(300, 400), pixmap_size=(200, 400))
        assert r is not None
        assert abs(r[0] - 100.0) < 1e-9
        assert abs(r[1] - 200.0) < 1e-9

    def test_in_letterbox_returns_none(self) -> None:
        """落在留白区返回 None。"""
        from civ_core.ui.components.live_preview_pane import _label_to_png_pixel

        # pixmap 400×200 → label 400×300，上下各 50 留白
        # 点 (200, 25) 在顶部留白
        r = _label_to_png_pixel(200.0, 25.0, label_size=(400, 300), pixmap_size=(400, 200))
        assert r is None
        # 点 (200, 275) 在底部留白
        r = _label_to_png_pixel(200.0, 275.0, label_size=(400, 300), pixmap_size=(400, 200))
        assert r is None

    def test_scaling_inversed_correctly(self) -> None:
        """label 比 pixmap 大 → scale>1，反算除以 scale。"""
        from civ_core.ui.components.live_preview_pane import _label_to_png_pixel

        # pixmap 200×100 → label 600×300：scale = min(3.0, 3.0) = 3.0
        # shown 600×300（无留白）。label 中心 (300, 150) → pixmap (100, 50)
        r = _label_to_png_pixel(300.0, 150.0, label_size=(600, 300), pixmap_size=(200, 100))
        assert r is not None
        assert abs(r[0] - 100.0) < 1e-9
        assert abs(r[1] - 50.0) < 1e-9

    def test_zero_size_returns_none(self) -> None:
        from civ_core.ui.components.live_preview_pane import _label_to_png_pixel

        assert _label_to_png_pixel(10.0, 10.0, label_size=(0, 100), pixmap_size=(100, 100)) is None
        assert _label_to_png_pixel(10.0, 10.0, label_size=(100, 100), pixmap_size=(100, 0)) is None


# ──────────────────────────────────────────────────────────────────
# P1.5-Step3c：LivePreviewPane.point_hovered 信号 + _on_image_hover
# ──────────────────────────────────────────────────────────────────
class TestPointHoveredSignal:
    """叠加模式下，hover 预览图 → emit point_hovered(row_idx)。"""

    def test_signal_exists(self, qapp: QApplication) -> None:
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            # point_hovered 信号应存在并可 connect
            assert hasattr(pane, "point_hovered")
            seen: list[int] = []
            pane.point_hovered.connect(seen.append)
            pane.point_hovered.emit(7)
            assert seen == [7]
        finally:
            pane.deleteLater()

    def test_no_meta_no_emit(self, qapp: QApplication) -> None:
        """meta=None（单行 / 未渲染）→ _on_image_hover 不 emit。"""
        from PySide6.QtCore import QPoint

        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            seen: list[int] = []
            pane.point_hovered.connect(seen.append)
            pane._hit_test_meta = None  # 显式（默认就是）
            pane._on_image_hover(QPoint(100, 100))
            assert seen == []
        finally:
            pane.deleteLater()

    def test_hover_emits_correct_row_idx(self, qapp: QApplication) -> None:
        """构造已知 meta + pixmap，hover label 内一点应 emit 最近曲线的 row_idx。"""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPixmap

        from civ_core.infra_io.chart_writer import HitTestMeta
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            # 模拟一次叠加渲染：pixmap 600×400，axes 占满（无留白）
            pix = QPixmap(600, 400)
            pix.fill()
            pane._current_pixmap = pix
            pane._image_label.resize(600, 400)
            pane._image_label.setPixmap(pix)

            # 三根试件，row 0 在 x=1 / row 1 在 x=5 / row 2 在 x=9（y=50）
            pane._hit_test_meta = HitTestMeta(
                png_width=600,
                png_height=400,
                axes_bbox_px=(0.0, 0.0, 600.0, 400.0),
                xlim=(0.0, 10.0),
                ylim=(0.0, 100.0),
                points=[
                    (0, [1.0], [50.0]),
                    (1, [5.0], [50.0]),
                    (2, [9.0], [50.0]),
                ],
            )

            seen: list[int] = []
            pane.point_hovered.connect(seen.append)
            # label 中点 (300, 200) → pixmap (300, 200) → data (5, 50) → row 1
            pane._on_image_hover(QPoint(300, 200))
            assert seen == [1]
        finally:
            pane.deleteLater()

    def test_hover_in_letterbox_no_emit(self, qapp: QApplication) -> None:
        """落在 letterbox 留白区 → _label_to_png_pixel 返 None → 不 emit。"""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPixmap

        from civ_core.infra_io.chart_writer import HitTestMeta
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            # pixmap 400×200 → label 400×300：上下各 50 留白
            pix = QPixmap(400, 200)
            pix.fill()
            pane._current_pixmap = pix
            pane._image_label.resize(400, 300)
            pane._image_label.setPixmap(pix)

            pane._hit_test_meta = HitTestMeta(
                png_width=400,
                png_height=200,
                axes_bbox_px=(0.0, 0.0, 400.0, 200.0),
                xlim=(0.0, 10.0),
                ylim=(0.0, 100.0),
                points=[(0, [1.0], [50.0])],
            )

            seen: list[int] = []
            pane.point_hovered.connect(seen.append)
            pane._on_image_hover(QPoint(200, 25))  # 顶部留白
            assert seen == []
        finally:
            pane.deleteLater()

    def test_hoverable_label_emits_hover_at(self, qapp: QApplication) -> None:
        """_HoverableLabel 启用 mouseTracking 且能 emit hover_at。"""
        from PySide6.QtCore import QPoint

        from civ_core.ui.components.live_preview_pane import _HoverableLabel

        lab = _HoverableLabel()
        try:
            assert lab.hasMouseTracking() is True

            seen: list[QPoint] = []
            lab.hover_at.connect(seen.append)
            lab.hover_at.emit(QPoint(42, 17))
            assert len(seen) == 1
            assert seen[0].x() == 42 and seen[0].y() == 17
        finally:
            lab.deleteLater()


# ──────────────────────────────────────────────────────────────────
# P1.5-① 单行 hover tooltip
# ──────────────────────────────────────────────────────────────────
class TestFindNearestCurvePoint:
    """单行 hover 用：找最近 (curve_name, x, y)。"""

    def test_returns_nearest(self) -> None:
        from civ_core.ui.components.live_preview_pane import (
            _find_nearest_curve_point,
        )

        curves = [
            ("加载", [0.0, 2.0, 5.0], [0.0, 20.0, 50.0]),
            ("卸载", [5.0, 3.0, 0.0], [50.0, 25.0, 0.0]),
        ]
        # 查询点 (2.1, 20) → 加载.第二点 (2, 20)
        r = _find_nearest_curve_point(2.1, 20.0, curves, xlim=(0.0, 10.0), ylim=(0.0, 100.0))
        assert r is not None
        name, x, y = r
        assert name == "加载"
        assert x == 2.0 and y == 20.0

    def test_empty_returns_none(self) -> None:
        from civ_core.ui.components.live_preview_pane import (
            _find_nearest_curve_point,
        )

        assert _find_nearest_curve_point(0.0, 0.0, [], xlim=(0.0, 1.0), ylim=(0.0, 1.0)) is None


class TestFormatHoverTooltip:
    def test_basic_format(self) -> None:
        from civ_core.ui.components.live_preview_pane import (
            _format_single_hover_tooltip,
        )

        s = _format_single_hover_tooltip(
            curve_name="加载",
            x_label="位移",
            x_value=5.123,
            y_label="荷载",
            y_value=60.0,
        )
        assert "曲线: 加载" in s
        assert "位移: 5.123" in s
        assert "荷载: 60" in s  # 去尾随零

    def test_handles_empty_axis_label(self) -> None:
        from civ_core.ui.components.live_preview_pane import (
            _format_single_hover_tooltip,
        )

        s = _format_single_hover_tooltip(
            curve_name="A", x_label="", x_value=1.0, y_label="", y_value=2.0
        )
        # 空 label 回退到 "X" / "Y"
        assert "X: 1" in s
        assert "Y: 2" in s


class TestSingleRowHoverTooltip:
    """LivePreviewPane 单行 hover 设 tooltip 集成测试。"""

    def test_single_meta_hover_sets_tooltip(self, qapp: QApplication) -> None:
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPixmap

        from civ_core.infra_io.chart_writer import SingleRowHitTestMeta
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pix = QPixmap(600, 400)
            pix.fill()
            pane._current_pixmap = pix
            pane._image_label.resize(600, 400)
            pane._image_label.setPixmap(pix)

            pane._single_hit_test_meta = SingleRowHitTestMeta(
                png_width=600,
                png_height=400,
                axes_bbox_px=(0.0, 0.0, 600.0, 400.0),
                xlim=(0.0, 10.0),
                ylim=(0.0, 100.0),
                x_label="位移",
                y_label="荷载",
                curves=[
                    ("加载", [1.0, 5.0, 9.0], [10.0, 50.0, 90.0]),
                ],
            )

            # 中点 (300, 200) → data (5, 50) → 最近"加载".第二点 (5, 50)
            pane._on_image_hover(QPoint(300, 200))
            tip = pane._image_label.toolTip()
            assert "加载" in tip
            assert "5" in tip
            assert "50" in tip
        finally:
            pane.deleteLater()

    def test_overlay_meta_present_skips_single_path(self, qapp: QApplication) -> None:
        """同时有两类 meta（理论不该出现）时 overlay 优先，单行 tooltip 不设。"""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPixmap

        from civ_core.infra_io.chart_writer import (
            HitTestMeta,
            SingleRowHitTestMeta,
        )
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pix = QPixmap(600, 400)
            pix.fill()
            pane._current_pixmap = pix
            pane._image_label.resize(600, 400)
            pane._image_label.setPixmap(pix)

            pane._hit_test_meta = HitTestMeta(
                png_width=600,
                png_height=400,
                axes_bbox_px=(0.0, 0.0, 600.0, 400.0),
                xlim=(0.0, 10.0),
                ylim=(0.0, 100.0),
                points=[(0, [5.0], [50.0])],
            )
            pane._single_hit_test_meta = SingleRowHitTestMeta(
                png_width=600,
                png_height=400,
                axes_bbox_px=(0.0, 0.0, 600.0, 400.0),
                xlim=(0.0, 10.0),
                ylim=(0.0, 100.0),
                curves=[("X", [5.0], [50.0])],
            )

            pane._image_label.setToolTip("")
            seen: list[int] = []
            pane.point_hovered.connect(seen.append)

            pane._on_image_hover(QPoint(300, 200))
            assert seen == [0]  # overlay 路径走了
            assert pane._image_label.toolTip() == ""  # 单行没走
        finally:
            pane.deleteLater()

    def test_invalidate_clears_tooltip_and_meta(self, qapp: QApplication) -> None:
        """切预设 / 数据源 / 模式 → meta + tooltip 都清空。"""
        from PySide6.QtGui import QPixmap

        from civ_core.infra_io.chart_writer import SingleRowHitTestMeta
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            pix = QPixmap(600, 400)
            pix.fill()
            pane._current_pixmap = pix
            pane._single_hit_test_meta = SingleRowHitTestMeta(
                png_width=600,
                png_height=400,
                axes_bbox_px=(0.0, 0.0, 600.0, 400.0),
                xlim=(0.0, 1.0),
                ylim=(0.0, 1.0),
                curves=[("a", [0.5], [0.5])],
            )
            pane._image_label.setToolTip("旧 tooltip")

            pane.set_preset(_make_preset())
            assert pane._single_hit_test_meta is None
            assert pane._hit_test_meta is None
            assert pane._image_label.toolTip() == ""
        finally:
            pane.deleteLater()

    def test_worker_single_hittest_signal_exists(self, qapp: QApplication) -> None:
        from civ_core.ui.components.live_preview_pane import (
            _PreviewWorkerSignals,
        )

        sigs = _PreviewWorkerSignals()
        # 信号对象存在且能 emit / connect
        assert hasattr(sigs, "single_hittest_ready")
        seen: list[tuple[int, bytes, object]] = []
        sigs.single_hittest_ready.connect(lambda g, b, m: seen.append((g, b, m)))
        sigs.single_hittest_ready.emit(1, b"abc", "fake")
        assert seen == [(1, b"abc", "fake")]


class TestFindNearestRow:
    """从多曲线点里找离查询点最近的，返回 row_idx。"""

    def test_returns_nearest_row(self) -> None:
        from civ_core.ui.components.live_preview_pane import _find_nearest_row

        # 三根试件：row 0 在 x=1 / row 1 在 x=5 / row 2 在 x=9
        pts = [
            (0, [1.0], [50.0]),
            (1, [5.0], [50.0]),
            (2, [9.0], [50.0]),
        ]
        r = _find_nearest_row(5.1, 50.0, pts, xlim=(0.0, 10.0), ylim=(0.0, 100.0))
        assert r is not None
        assert r[0] == 1

    def test_returns_none_for_empty(self) -> None:
        from civ_core.ui.components.live_preview_pane import _find_nearest_row

        assert _find_nearest_row(0.0, 0.0, [], xlim=(0.0, 1.0), ylim=(0.0, 1.0)) is None

    def test_uses_normalized_distance(self) -> None:
        """量纲悬殊时，归一化距离能让"两轴等重要"。"""
        from civ_core.ui.components.live_preview_pane import _find_nearest_row

        # row 0 离查询点 x 偏 0.5 / y 偏 0；row 1 x 偏 0 / y 偏 5
        # 归一化前：欧氏 0.5 vs 5（row 0 近）
        # 归一化后（xlim 0..10、ylim 0..100）：row 0=0.05、row 1=0.05（接近）
        # 取再近 1 步：让 row 1 略近，验证归一化生效
        pts = [
            (0, [0.5], [50.0]),  # x 偏 0.5（归 0.05），y 偏 0
            (1, [0.0], [49.0]),  # x 偏 0，y 偏 1（归 0.01）
        ]
        # 查询点 (0, 50)：row 1 归一化距离 0.01，row 0 归一化 0.05 → row 1 近
        r = _find_nearest_row(0.0, 50.0, pts, xlim=(0.0, 10.0), ylim=(0.0, 100.0))
        assert r is not None
        assert r[0] == 1
