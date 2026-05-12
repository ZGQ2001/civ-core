"""实时预览面板（L-2 实装）。

职责
====
  • 持有当前预设数据 + Excel 数据源
  • 接收"请重绘"请求 → 300ms 防抖 → 启动渲染 worker → 显示 PNG

接口（与 PROGRESS.md L-2 一致）
================================
  • set_preset(preset: dict | None)         —— 由 PresetAccordionPanel(L-3b) 调
  • set_data_source(path: Path | None)      —— 由数据源分组(L-3b)调
  • request_redraw()                        —— 由参数面板任意 valueChanged 调

防抖策略
========
  request_redraw() → QTimer.singleShot(300ms)；timer 在 300ms 内被反复调用
  会被持续 reset，最终只触发一次 _do_redraw —— 避免连点滑块时狂渲染。

Worker 串行
===========
  pyplot 全局状态多线程不安全，因此 worker 串行执行：
    • _is_rendering=True 期间收到的 _do_redraw 只标记 _pending=True
    • 当前 worker 跑完后检查 _pending，如有则立即再起一个
  这保证 last-write-wins：用户最后改的那次参数终会反映到画面，
  期间的中间状态被合并丢弃。

渲染失败的友善处理
==================
  缺数据源 / 缺预设 / 列名不匹配 / Excel 读不到 → QLabel 显示提示文字，
  不弹 InfoBar（实时预览频繁触发，弹窗会刷屏）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel

from civ_core.core.data_cache import EXCEL_DATA_CACHE
from civ_core.core.plot_curves import (
    PlotCurvesError,
    build_jobs,
)
from civ_core.infra_io.chart_writer import render_plot_to_bytes
from civ_core.infra_io.excel_reader import ExcelReadError
from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 防抖窗口：连续 valueChanged 在此时间窗内合并成一次重绘
_DEBOUNCE_MS = 300

# 预览 figure 尺寸：宽高 / dpi 偏小一些，屏显已够清晰，省 CPU
_PREVIEW_FIGSIZE = (7.0, 4.0)
_PREVIEW_DPI = 100


class LivePreviewPane(QWidget):
    """实时预览面板：参数变化 → 300ms 防抖 → 重绘当前预设的代表行。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("livePreviewPane")

        # 当前数据源
        self._preset: dict[str, Any] | None = None
        self._data_source: Path | None = None
        self._sheet_name: str | None = None
        # L-4 高亮行索引（占位，P1.5 才在图上画标记）
        self._highlight_row_idx: int = -1

        # Worker 串行：is_rendering 期间收到的请求仅置 pending
        self._is_rendering: bool = False
        self._pending: bool = False
        # generation token：worker 启动时分配，回来时若 gen 不匹配（用户已要新数据）则丢弃
        self._render_gen: int = 0

        # 防抖 timer：start() 会 reset 计时
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_redraw)

        # 全局线程池：渲染 worker 投递到这里
        self._pool = QThreadPool.globalInstance()

        self._build_layout()
        self._update_hint("请先在左栏选择数据源与预设")

    # ── UI 骨架 ──────────────────────────────────────────────────
    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # 图像区：QLabel + setPixmap；alignment 居中，避免缩放后偏左上
        self._image_label = QLabel(self)
        self._image_label.setObjectName("livePreviewImage")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 不强制 minimum size，让窗口可以无限缩小（缩小时图按比例 KeepAspectRatio）
        # scaledContents=False：用我们自己的 _scaled_pixmap 控制缩放，
        # 不让 QLabel 拉伸（拉伸会失真）
        self._image_label.setScaledContents(False)
        layout.addWidget(self._image_label, 1)

        # 状态/提示行：在 image 上方时占用图位置；改为下方"小字"提示更轻
        self._hint_label = BodyLabel("", self)
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet("color: #888;")
        self._hint_label.setWordWrap(True)
        layout.addWidget(self._hint_label)

        # 缓存的原图 pixmap —— resize 时按当前 size 重新缩放
        self._current_pixmap: QPixmap | None = None

    def resizeEvent(self, event: Any) -> None:  # noqa: D401
        """容器变化时按比例重缩当前图（不重新渲染）。"""
        super().resizeEvent(event)
        if self._current_pixmap is not None and not self._current_pixmap.isNull():
            self._image_label.setPixmap(self._scaled_pixmap())

    def _scaled_pixmap(self) -> QPixmap:
        assert self._current_pixmap is not None
        return self._current_pixmap.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _update_hint(self, text: str) -> None:
        self._hint_label.setText(text)

    # ── 对外接口 ─────────────────────────────────────────────────
    def set_preset(self, preset: dict[str, Any] | None) -> None:
        """设置当前预设（dict 结构，与 curve_presets.json 单条预设字段一致）。

        切预设视为"内容变化"，立刻触发防抖重绘。
        """
        self._preset = preset
        self.request_redraw()

    def set_data_source(
        self, path: Path | str | None, sheet: str | None = None
    ) -> None:
        """设置 Excel 数据源路径 + sheet。None = 未选。

        切数据源或 sheet → 触发防抖重绘（缓存按 (path, mtime, sheet, header)
        命中，切回来零成本）。
        """
        if path is None:
            self._data_source = None
        else:
            self._data_source = Path(path)
        self._sheet_name = sheet
        self.request_redraw()

    def request_redraw(self) -> None:
        """请求一次防抖重绘。可被高频调用（每次 valueChanged）。"""
        # singleShot 模式下，start 会重置剩余时间 —— 这就是"防抖"
        self._debounce_timer.start(_DEBOUNCE_MS)

    def highlight_row(self, idx: int) -> None:
        """L-4：让预览图上突出第 idx 行对应的曲线点。

        L-4 简化版：仅更新状态指示文字 + 记内部索引，不在图上画突出标记。
        真正的"在曲线上标记圆圈"留待 P1.5（需要把 idx → 曲线坐标的反向映射
        和单独的 highlight worker，工作量足够单独立项）。

        加这个方法是为了让 DataSourcePane.row_highlighted 信号有挂载点，
        view 层的连线在 L-4 完整通过；后续 P1.5 只需要把渲染逻辑补齐。
        """
        self._highlight_row_idx = idx
        log.debug("LivePreview highlight_row idx=%d（P1.5 起在图上画标记）", idx)
        self._update_hint(
            f"高亮第 {idx + 1} 行 · 图上突出标记由 P1.5 实装"
        )

    # ── 渲染主流程 ───────────────────────────────────────────────
    def _do_redraw(self) -> None:
        """防抖 timer 触发：检查 worker 占用 → 启动 / 排队。"""
        # 数据源未齐备：直接更新提示，不启动 worker
        if self._preset is None:
            self._update_hint("请先选择预设")
            return
        if self._data_source is None:
            self._update_hint("请先选择 Excel 数据源")
            return

        # worker 串行：进行中只置 pending，等回调里再起新 worker
        if self._is_rendering:
            self._pending = True
            return

        self._launch_worker()

    def _launch_worker(self) -> None:
        assert self._preset is not None
        assert self._data_source is not None
        self._is_rendering = True
        self._render_gen += 1
        gen = self._render_gen
        self._update_hint("渲染中…")

        worker = _PreviewWorker(
            preset=self._preset,
            data_source=self._data_source,
            sheet_name=self._sheet_name,
            generation=gen,
        )
        worker.signals.ready.connect(self._on_worker_ready)
        worker.signals.failed.connect(self._on_worker_failed)
        # 保活：测试场景下 worker 一旦超出 _launch_worker 作用域可能被 GC
        self._active_worker = worker
        self._pool.start(worker)
        log.debug("LivePreview 启动渲染 worker gen=%d", gen)

    def _on_worker_ready(self, gen: int, png_bytes: bytes) -> None:
        """worker 回主线程：仅当 gen 仍是最新代时接受结果。"""
        self._is_rendering = False
        if gen != self._render_gen:
            log.debug(
                "LivePreview 丢弃过期 worker 结果 gen=%d (当前 gen=%d)",
                gen,
                self._render_gen,
            )
        else:
            pix = QPixmap()
            pix.loadFromData(png_bytes, "PNG")
            self._current_pixmap = pix
            self._image_label.setPixmap(self._scaled_pixmap())
            self._update_hint(f"已渲染（{len(png_bytes) // 1024} KB）")

        # pending 兜底：渲染过程中收到的新请求需补一次
        if self._pending:
            self._pending = False
            self._launch_worker()

    def _on_worker_failed(self, gen: int, reason: str) -> None:
        self._is_rendering = False
        if gen != self._render_gen:
            log.debug("LivePreview 丢弃过期 worker 错误 gen=%d", gen)
        else:
            self._update_hint(f"预览失败：{reason}")

        if self._pending:
            self._pending = False
            self._launch_worker()


# ──────────────────────────────────────────────────────────────────
# Worker：在线程池里跑"读缓存 → build_jobs 取首张 → render_plot_to_bytes"
# ──────────────────────────────────────────────────────────────────
class _PreviewWorkerSignals(QObject):
    # 信号带 generation：让主线程能识别"这是哪一代请求"，过期就丢
    ready = Signal(int, bytes)
    failed = Signal(int, str)


class _PreviewWorker(QRunnable):
    """渲染一次预览的 QRunnable。

    流程：
      1. 从 EXCEL_DATA_CACHE 拿 rows（mtime 内自动复用）
      2. build_jobs(preset, rows) 取第一个有效 PlotJob 作为代表
      3. render_plot_to_bytes → emit ready(gen, png_bytes)
    任意环节异常 → emit failed(gen, 友善文字)，不抛到 worker 线程外。
    """

    def __init__(
        self,
        *,
        preset: dict[str, Any],
        data_source: Path,
        sheet_name: str | None,
        generation: int,
    ) -> None:
        super().__init__()
        self._preset = preset
        self._data_source = data_source
        self._sheet_name = sheet_name
        self._gen = generation
        self.signals = _PreviewWorkerSignals()

    def run(self) -> None:  # noqa: D401
        try:
            rows = EXCEL_DATA_CACHE.get_rows(
                self._data_source, self._sheet_name, 1
            )
            if not rows:
                self._safe_emit_failed("Excel 没有可用的数据行")
                return

            # 预览只取第一个 PlotJob（一行 = 一张图）作为代表
            # output_dir 传 /tmp 占位 —— build_jobs 只用它拼路径，render_plot_to_bytes 忽略它
            jobs, _summary = build_jobs(
                self._preset, rows, output_dir=Path(".")
            )
            if not jobs:
                self._safe_emit_failed("数据行都无法生成有效曲线（详见日志）")
                return

            png = render_plot_to_bytes(
                jobs[0],
                figsize=_PREVIEW_FIGSIZE,
                dpi=_PREVIEW_DPI,
            )
            self._safe_emit_ready(png)

        except PlotCurvesError as e:
            # 业务异常（缺列等）：把 hint 也带上，让用户看到怎么修
            msg = str(e)
            if e.hint:
                msg = f"{msg}\n{e.hint}"
            self._safe_emit_failed(msg)
        except ExcelReadError as e:
            msg = str(e)
            if getattr(e, "hint", ""):
                msg = f"{msg}\n{e.hint}"
            self._safe_emit_failed(msg)
        except Exception as e:
            # 兜底：任何意料外异常都不要把 worker 线程拖崩
            log.error("LivePreview worker 意外异常", exc_info=e)
            self._safe_emit_failed(f"{type(e).__name__}: {e}")

    def _safe_emit_ready(self, png: bytes) -> None:
        try:
            self.signals.ready.emit(self._gen, png)
        except RuntimeError:
            # 主窗口已销毁 —— signals 对象 C++ 部分被回收，忽略
            pass

    def _safe_emit_failed(self, reason: str) -> None:
        try:
            self.signals.failed.emit(self._gen, reason)
        except RuntimeError:
            pass
