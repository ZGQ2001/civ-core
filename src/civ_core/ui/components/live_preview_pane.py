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

from PySide6.QtCore import QObject, QPoint, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel

from civ_core.core.data_cache import EXCEL_DATA_CACHE
from civ_core.core.plot_curves import (
    PlotCurvesError,
    build_jobs,
)
from civ_core.infra_io.chart_writer import (
    HitTestMeta,
    render_overlay_with_hittest,
    render_plot_to_bytes,
)
from civ_core.infra_io.excel_reader import ExcelReadError
from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 防抖窗口：连续 valueChanged 在此时间窗内合并成一次重绘
_DEBOUNCE_MS = 300

# 预览 figure 尺寸：宽高 / dpi 偏小一些，屏显已够清晰，省 CPU
_PREVIEW_FIGSIZE = (7.0, 4.0)
_PREVIEW_DPI = 100


class _HoverableLabel(QLabel):
    """支持 mouseMove + leave 信号的 QLabel（P1.5-Step3c）。

    QLabel 默认 mouseTracking=False（按下才有 move 事件）；这里开启 tracking，
    把鼠标在 label 内的逐点位置和"离开"事件转成信号，方便父组件不重写
    eventFilter 也能监听。
    """

    hover_at = Signal(QPoint)
    hover_left = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 不按键也产生 mouseMoveEvent —— hover hit-testing 必备
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: D401
        # event.position() 返回 QPointF；.toPoint() 取整。
        # 注意：必须 emit "before" super，否则 super 可能消化 event 提前返回
        self.hover_at.emit(event.position().toPoint())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: object) -> None:  # noqa: D401
        # Qt 把 leave 单独立项；用 object 类型注解避免 PySide6 在不同 Qt 版本下
        # 的 QEvent 类型差异
        self.hover_left.emit()
        super().leaveEvent(event)  # type: ignore[arg-type]


class LivePreviewPane(QWidget):
    """实时预览面板：参数变化 → 300ms 防抖 → 重绘当前预设的代表行。"""

    # P1.5-Step3c：叠加模式下，鼠标 hover 曲线点 → 通知外部"对应第 row_idx 行"
    point_hovered = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("livePreviewPane")

        # 当前数据源
        self._preset: dict[str, Any] | None = None
        self._data_source: Path | None = None
        self._sheet_name: str | None = None
        # 当前预览的行索引（0-based）。
        # P1.5-Step1 起 highlight_row(idx) 不再只是占位，而是真切换到第 idx 行的图。
        # 切预设 / 切数据源时重置 0（旧 idx 对新数据集越界）。
        self._current_row_idx: int = 0
        # P1.5-Step2 叠加对比模式：True = 把所有 jobs 画到一张图上，
        # _current_row_idx 用来"高亮哪根"；False = 只画 jobs[_current_row_idx]。
        self._overlay_mode: bool = False
        # P1.5-Step3c：最近一次叠加渲染的 hit-test 元数据；
        # 单行模式 / 还没渲染时为 None —— hover 直接忽略
        self._hit_test_meta: HitTestMeta | None = None

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

        # 图像区：_HoverableLabel + setPixmap；alignment 居中，避免缩放后偏左上
        # P1.5-Step3c：用 _HoverableLabel 子类替代 QLabel，让 mouseMove 转信号
        self._image_label = _HoverableLabel(self)
        self._image_label.setObjectName("livePreviewImage")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 不强制 minimum size，让窗口可以无限缩小（缩小时图按比例 KeepAspectRatio）
        # scaledContents=False：用我们自己的 _scaled_pixmap 控制缩放，
        # 不让 QLabel 拉伸（拉伸会失真）
        self._image_label.setScaledContents(False)
        # 叠加模式下的 hover hit-testing
        self._image_label.hover_at.connect(self._on_image_hover)
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
        重置 _current_row_idx 为 0：旧预设下的行号对新预设可能无意义。
        """
        self._preset = preset
        self._current_row_idx = 0
        self.request_redraw()

    def set_data_source(
        self, path: Path | str | None, sheet: str | None = None
    ) -> None:
        """设置 Excel 数据源路径 + sheet。None = 未选。

        切数据源或 sheet → 触发防抖重绘（缓存按 (path, mtime, sheet, header)
        命中，切回来零成本）。
        重置 _current_row_idx 为 0：旧文件的行号在新文件可能越界。
        """
        if path is None:
            self._data_source = None
        else:
            self._data_source = Path(path)
        self._sheet_name = sheet
        self._current_row_idx = 0
        self.request_redraw()

    def request_redraw(self) -> None:
        """请求一次防抖重绘。可被高频调用（每次 valueChanged）。"""
        # singleShot 模式下，start 会重置剩余时间 —— 这就是"防抖"
        self._debounce_timer.start(_DEBOUNCE_MS)

    def highlight_row(self, idx: int) -> None:
        """切换预览到第 idx 行对应的图（P1.5-Step1 实装）。

        旧 L-4 版本只是占位（更新提示文字）；现在真正切换：
          1. 更新 _current_row_idx；负数 / 不变忽略
          2. 触发防抖重绘 —— 单行模式拿 jobs[idx]；叠加模式则高亮第 idx 根

        worker 端越界回退由 _pick_job_index 兜底；这里不做边界检查
        因为本方法不知道 jobs 总数（rows 在 worker 里才被读）。
        """
        if idx < 0:
            log.debug("highlight_row 忽略负数 idx=%d", idx)
            return
        if idx == self._current_row_idx:
            return
        self._current_row_idx = idx
        log.debug("LivePreview 切换到第 %d 行（0-based）", idx)
        self.request_redraw()

    def set_overlay_mode(self, enabled: bool) -> None:
        """切换"叠加对比图 / 单行图"渲染模式（P1.5-Step2）。

        叠加模式：所有 jobs 画到同一张图，每根试件一种颜色；
        _current_row_idx 决定哪根高亮（其他半透明）。
        单行模式（默认）：只画 jobs[_current_row_idx]。

        模式切换会重绘（两种渲染目标不同）；重复设置同值是 no-op。
        idx 不重置 —— 叠加模式下保留高亮、切回单行时仍是同一根的图。
        """
        if bool(enabled) == self._overlay_mode:
            return
        self._overlay_mode = bool(enabled)
        log.debug("LivePreview 叠加模式=%s", self._overlay_mode)
        self.request_redraw()

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
            row_idx=self._current_row_idx,
            overlay_mode=self._overlay_mode,
        )
        worker.signals.ready.connect(self._on_worker_ready)
        worker.signals.overlay_ready.connect(self._on_worker_overlay_ready)
        worker.signals.failed.connect(self._on_worker_failed)
        # 保活：测试场景下 worker 一旦超出 _launch_worker 作用域可能被 GC
        self._active_worker = worker
        self._pool.start(worker)
        log.debug("LivePreview 启动渲染 worker gen=%d", gen)

    def _on_worker_ready(self, gen: int, png_bytes: bytes) -> None:
        """worker 回主线程：仅当 gen 仍是最新代时接受结果。

        单行 ready 路径 → 清空 _hit_test_meta（叠加 meta 对单行无意义）。
        """
        self._is_rendering = False
        if gen != self._render_gen:
            log.debug(
                "LivePreview 丢弃过期 worker 结果 gen=%d (当前 gen=%d)",
                gen,
                self._render_gen,
            )
        else:
            self._hit_test_meta = None
            self._apply_png(png_bytes)

        # pending 兜底：渲染过程中收到的新请求需补一次
        if self._pending:
            self._pending = False
            self._launch_worker()

    def _on_worker_overlay_ready(
        self, gen: int, png_bytes: bytes, meta: object
    ) -> None:
        """叠加模式 worker 回主线程：除 png 外还带 hit-test meta。

        与 _on_worker_ready 的差异：保存 meta 供后续 hover 反算；
        渲染逻辑共用 _apply_png（避免两条 ready 路径重复代码）。
        """
        self._is_rendering = False
        if gen != self._render_gen:
            log.debug("LivePreview 丢弃过期 overlay worker gen=%d", gen)
        else:
            # meta 类型由 Signal(object) 跨线程传递，运行时确保是 HitTestMeta
            assert isinstance(meta, HitTestMeta)
            self._hit_test_meta = meta
            self._apply_png(png_bytes)

        if self._pending:
            self._pending = False
            self._launch_worker()

    def _apply_png(self, png_bytes: bytes) -> None:
        """把 PNG 字节流展示到 image_label，更新提示。两条 ready 路径共用。"""
        pix = QPixmap()
        pix.loadFromData(png_bytes, "PNG")
        self._current_pixmap = pix
        self._image_label.setPixmap(self._scaled_pixmap())
        self._update_hint(f"已渲染（{len(png_bytes) // 1024} KB）")

    def _on_image_hover(self, point: QPoint) -> None:
        """叠加模式下，鼠标在预览图上移动 → 反算 row idx → emit point_hovered。

        路径：
          label 像素 → _label_to_png_pixel → PNG 像素
                    → _pixel_to_data → data 坐标
                    → _find_nearest_row → row idx
        meta 为 None（单行模式 / 未渲染）→ 不做事，避免误 emit。
        """
        meta = self._hit_test_meta
        if meta is None or self._current_pixmap is None or self._current_pixmap.isNull():
            return

        label_size = (self._image_label.width(), self._image_label.height())
        pixmap_size = (self._current_pixmap.width(), self._current_pixmap.height())
        pix = _label_to_png_pixel(
            float(point.x()), float(point.y()),
            label_size=label_size, pixmap_size=pixmap_size,
        )
        if pix is None:
            return
        data_xy = _pixel_to_data(
            pix[0], pix[1],
            axes_bbox_px=meta.axes_bbox_px,
            xlim=meta.xlim, ylim=meta.ylim,
            x_log=meta.x_log, y_log=meta.y_log,
        )
        if data_xy is None:
            return
        found = _find_nearest_row(
            data_xy[0], data_xy[1], meta.points,
            xlim=meta.xlim, ylim=meta.ylim,
        )
        if found is None:
            return
        row_idx, _dist = found
        self.point_hovered.emit(row_idx)

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
    # P1.5-Step3c：叠加模式额外携带 HitTestMeta（用 object 避开 Qt 元类型注册）
    overlay_ready = Signal(int, bytes, object)
    failed = Signal(int, str)


def _label_to_png_pixel(
    lx: float,
    ly: float,
    *,
    label_size: tuple[int, int],
    pixmap_size: tuple[int, int],
) -> tuple[float, float] | None:
    """QLabel 内坐标 → 原 PNG 像素坐标。

    QLabel 用 KeepAspectRatio 居中显示 pixmap，所以 label 上会有 letterbox 留白。
    本函数反算出实际显示区在 label 中的偏移 / 缩放，再把 label 坐标映射回 pixmap。
    落在留白区（letterbox）时返回 None。
    """
    lw, lh = label_size
    pw, ph = pixmap_size
    if lw <= 0 or lh <= 0 or pw <= 0 or ph <= 0:
        return None

    # KeepAspectRatio：缩放到能完整 fit 进 label，取较小比例
    scale = min(lw / pw, lh / ph)
    shown_w = pw * scale
    shown_h = ph * scale
    offset_x = (lw - shown_w) / 2.0
    offset_y = (lh - shown_h) / 2.0
    dx = lx - offset_x
    dy = ly - offset_y
    if dx < 0 or dx > shown_w or dy < 0 or dy > shown_h:
        return None
    return dx / scale, dy / scale


def _pixel_to_data(
    px: float,
    py: float,
    *,
    axes_bbox_px: tuple[float, float, float, float],
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    x_log: bool = False,
    y_log: bool = False,
) -> tuple[float, float] | None:
    """PNG 像素坐标 → data 坐标（线性 / log 都支持）。

    像素原点左上、y 向下；matplotlib data 原点左下、y 向上。
    返回 (x_data, y_data)；像素落在 axes_bbox_px 外时返回 None。

    log 轴：把像素先线性插值到 log10 域，再 10**。
    """
    import math

    x0, y0, x1, y1 = axes_bbox_px
    if px < x0 or px > x1 or py < y0 or py > y1:
        return None
    if x1 <= x0 or y1 <= y0:
        return None  # 退化 bbox 防 0 除

    # 横向：x0 → xlim[0]，x1 → xlim[1]
    fx = (px - x0) / (x1 - x0)
    if x_log:
        lx0, lx1 = math.log10(xlim[0]), math.log10(xlim[1])
        x_data = 10 ** (lx0 + fx * (lx1 - lx0))
    else:
        x_data = xlim[0] + fx * (xlim[1] - xlim[0])

    # 纵向：注意 y 翻转 —— py=y0(顶) → ylim[1]（上）；py=y1(底) → ylim[0]（下）
    fy = (py - y0) / (y1 - y0)
    if y_log:
        ly0, ly1 = math.log10(ylim[0]), math.log10(ylim[1])
        # fy=0 顶 ⇒ ylim[1]；fy=1 底 ⇒ ylim[0]
        y_data = 10 ** (ly1 - fy * (ly1 - ly0))
    else:
        y_data = ylim[1] - fy * (ylim[1] - ylim[0])

    return x_data, y_data


def _find_nearest_row(
    x_data: float,
    y_data: float,
    points: list[tuple[int, list[float], list[float]]],
    *,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
) -> tuple[int, float] | None:
    """在所有曲线点里找离 (x_data, y_data) 最近的，返回 (row_idx, 归一化距离)。

    归一化：把每条曲线的 (xs, ys) 用 (xlim, ylim) 缩放到 [0,1]²，
    距离用欧氏。这样 x、y 量纲不同（位移 mm vs 荷载 kN）时不会被
    某一轴主导。

    空 points → None。
    """
    if not points:
        return None
    x_span = max(xlim[1] - xlim[0], 1e-12)
    y_span = max(ylim[1] - ylim[0], 1e-12)
    qx = (x_data - xlim[0]) / x_span
    qy = (y_data - ylim[0]) / y_span

    best_row = -1
    best_d2 = float("inf")
    for row_idx, xs, ys in points:
        for x, y in zip(xs, ys):
            nx = (x - xlim[0]) / x_span
            ny = (y - ylim[0]) / y_span
            d2 = (nx - qx) ** 2 + (ny - qy) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_row = row_idx
    if best_row < 0:
        return None
    return best_row, best_d2 ** 0.5


def _pick_job_index(jobs_count: int, requested: int) -> int:
    """从 jobs 列表里挑出 row_idx 对应的 job 下标。

    返回：
      • jobs_count <= 0          → -1（无可用图，调用方走"空"分支）
      • 0 <= requested < jobs_count → requested（正常命中）
      • 越界 / 负数                 → 0（回退第一张）

    抽成纯函数是为了单测（不依赖 Qt / matplotlib / Excel）。
    """
    if jobs_count <= 0:
        return -1
    if 0 <= requested < jobs_count:
        return requested
    return 0


class _PreviewWorker(QRunnable):
    """渲染一次预览的 QRunnable。

    流程：
      1. 从 EXCEL_DATA_CACHE 拿 rows（mtime 内自动复用）
      2. build_jobs(preset, rows) 得到所有 PlotJob
      3. 按 row_idx 选 jobs[row_idx]（越界回退 0），render_plot_to_bytes
      4. emit ready(gen, png_bytes)
    任意环节异常 → emit failed(gen, 友善文字)，不抛到 worker 线程外。
    """

    def __init__(
        self,
        *,
        preset: dict[str, Any],
        data_source: Path,
        sheet_name: str | None,
        generation: int,
        row_idx: int = 0,
        overlay_mode: bool = False,
    ) -> None:
        super().__init__()
        self._preset = preset
        self._data_source = data_source
        self._sheet_name = sheet_name
        self._gen = generation
        self._row_idx = row_idx
        self._overlay_mode = overlay_mode
        self.signals = _PreviewWorkerSignals()

    def run(self) -> None:  # noqa: D401
        try:
            rows = EXCEL_DATA_CACHE.get_rows(
                self._data_source, self._sheet_name, 1
            )
            if not rows:
                self._safe_emit_failed("Excel 没有可用的数据行")
                return

            # build_jobs 返回所有行的图；按 row_idx 选一张作为预览
            # output_dir 传 . 占位 —— render_plot_to_bytes 忽略它
            jobs, _summary = build_jobs(
                self._preset, rows, output_dir=Path(".")
            )
            picked = _pick_job_index(len(jobs), self._row_idx)
            if picked < 0:
                self._safe_emit_failed("数据行都无法生成有效曲线（详见日志）")
                return

            if self._overlay_mode:
                # 叠加模式：用 with_hittest 同时拿 PNG + 反算 meta
                png, meta = render_overlay_with_hittest(
                    jobs,
                    highlight_row_idx=picked,
                    figsize=_PREVIEW_FIGSIZE,
                    dpi=_PREVIEW_DPI,
                )
                self._safe_emit_overlay_ready(png, meta)
            else:
                # 单行模式：只画 jobs[picked]
                png = render_plot_to_bytes(
                    jobs[picked],
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

    def _safe_emit_overlay_ready(self, png: bytes, meta: HitTestMeta) -> None:
        try:
            self.signals.overlay_ready.emit(self._gen, png, meta)
        except RuntimeError:
            pass

    def _safe_emit_failed(self, reason: str) -> None:
        try:
            self.signals.failed.emit(self._gen, reason)
        except RuntimeError:
            pass
