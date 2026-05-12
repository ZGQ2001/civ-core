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
            # 最终状态应回到 idle，pending 被清掉
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
