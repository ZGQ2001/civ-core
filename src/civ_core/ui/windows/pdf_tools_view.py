"""PDF 工具视图：合并 + 拆分（P3 新工具接入）。

布局：
  ┌─────────────────────────────────────────────────────────┐
  │ [Tab: 合并]  [Tab: 拆分]                                  │
  │   合并: 文件列表 + 上下移 + 输出文件 + 「▶ 合并」              │
  │   拆分: 单文件 + 模式(单选: 每页 / 按范围) + 输出目录 + 「▶ 拆分」 │
  ├─────────────────────────────────────────────────────────┤
  │ 状态行 + 进度条                                            │
  └─────────────────────────────────────────────────────────┘

合规：
  • 不直接调 pypdf —— 全部走 infra_io/pdf_io.py
  • 异常通过 error_infobar 用三段式（定位 → 原因 → 建议）展示
  • 长任务投递到 QThreadPool，不卡 UI
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    RadioButton,
    StrongBodyLabel,
    TabBar,
)

from civ_core.configs.loader import AppConfig
from civ_core.infra_io.pdf_io import (
    PdfOpError,
    merge_pdfs,
    split_pdf_by_ranges,
    split_pdf_per_page,
)
from civ_core.ui.components.error_infobar import (
    show_error_infobar,
    show_success_infobar,
    show_warning_infobar,
)
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


class PdfToolsView(QWidget):
    """PDF 合并/拆分工具页（导航 routing key = pdfToolsPage）。"""

    def __init__(self, cfg: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pdfToolsPage")
        self._cfg = cfg
        self._pool = QThreadPool.globalInstance()
        self._active_worker: _BaseWorker | None = None

        # 合并 Tab 状态
        self._merge_inputs: list[Path] = []
        self._merge_out_path: Path | None = None

        # 拆分 Tab 状态
        self._split_input: Path | None = None
        self._split_out_dir: Path | None = None

        self._build_layout()

    # ── UI 骨架 ─────────────────────────────────────────────────
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(10)

        title = StrongBodyLabel("PDF 工具", self)
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        outer.addWidget(title)

        subtitle = BodyLabel(
            "合并多个 PDF · 按页拆分 · 按页号范围拆分。所有操作走原子写，"
            "失败不会留半截文件。",
            self,
        )
        subtitle.setStyleSheet("color: #888;")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        # ── Tab 切换 ──
        # qfluentwidgets TabBar：扁平、自带活跃下划线，比 QTabWidget 更轻
        self._tab_bar = TabBar(self)
        self._tab_bar.addTab("merge", "合并")
        self._tab_bar.addTab("split", "拆分")
        self._tab_bar.tabBarClicked.connect(self._on_tab_changed)
        outer.addWidget(self._tab_bar)

        # ── 两个 Tab 内容（用 QStackedWidget 切） ──
        from PySide6.QtWidgets import QStackedWidget  # 局部 import 减少顶部噪音

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_merge_tab())
        self._stack.addWidget(self._build_split_tab())
        outer.addWidget(self._stack, 1)

        # ── 状态 + 进度（两 Tab 共用） ──
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self._status_label = BodyLabel("就绪", self)
        self._status_label.setStyleSheet("color: #666;")
        bottom.addWidget(self._status_label, 1)
        self._progress = ProgressBar(self)
        self._progress.setFixedWidth(220)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.hide()
        bottom.addWidget(self._progress)
        outer.addLayout(bottom)

    def _on_tab_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    # ── 合并 Tab ────────────────────────────────────────────────
    def _build_merge_tab(self) -> QWidget:
        page = QWidget(self)
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 12, 0, 0)
        v.setSpacing(8)

        v.addWidget(StrongBodyLabel("待合并 PDF 列表（自上而下顺序）", page))

        self._merge_list = QListWidget(page)
        self._merge_list.setAlternatingRowColors(True)
        v.addWidget(self._merge_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        b_add = PushButton("➕ 添加 PDF", page)
        b_add.clicked.connect(self._on_merge_add)
        btn_row.addWidget(b_add)
        b_up = PushButton("↑ 上移", page)
        b_up.clicked.connect(lambda: self._on_merge_move(-1))
        btn_row.addWidget(b_up)
        b_down = PushButton("↓ 下移", page)
        b_down.clicked.connect(lambda: self._on_merge_move(1))
        btn_row.addWidget(b_down)
        b_del = PushButton("× 删除选中", page)
        b_del.clicked.connect(self._on_merge_remove)
        btn_row.addWidget(b_del)
        b_clear = PushButton("清空", page)
        b_clear.clicked.connect(self._on_merge_clear)
        btn_row.addWidget(b_clear)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        # 输出文件
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        out_row.addWidget(BodyLabel("输出 PDF：", page))
        self._merge_out_edit = LineEdit(page)
        self._merge_out_edit.setPlaceholderText("点右侧 [选择文件] 指定输出 PDF 名称")
        self._merge_out_edit.setReadOnly(True)
        out_row.addWidget(self._merge_out_edit, 1)
        b_out = PushButton("选择文件", page)
        b_out.clicked.connect(self._on_merge_pick_out)
        out_row.addWidget(b_out)
        v.addLayout(out_row)

        # 主操作按钮
        self._merge_btn = PrimaryPushButton("▶ 开始合并", page)
        self._merge_btn.clicked.connect(self._on_merge_run)
        v.addWidget(self._merge_btn)

        return page

    def _on_merge_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择 PDF 文件", "", "PDF (*.pdf)"
        )
        for p_str in paths:
            p = Path(p_str)
            if p not in self._merge_inputs:
                self._merge_inputs.append(p)
                self._merge_list.addItem(QListWidgetItem(f"📑 {p.name}"))

    def _on_merge_move(self, step: int) -> None:
        row = self._merge_list.currentRow()
        new_row = row + step
        if row < 0 or not (0 <= new_row < len(self._merge_inputs)):
            return
        self._merge_inputs[row], self._merge_inputs[new_row] = (
            self._merge_inputs[new_row], self._merge_inputs[row],
        )
        # 同步 ListWidget
        item = self._merge_list.takeItem(row)
        if item is None:
            return
        self._merge_list.insertItem(new_row, item)
        self._merge_list.setCurrentRow(new_row)

    def _on_merge_remove(self) -> None:
        row = self._merge_list.currentRow()
        if row < 0:
            return
        del self._merge_inputs[row]
        self._merge_list.takeItem(row)

    def _on_merge_clear(self) -> None:
        self._merge_inputs.clear()
        self._merge_list.clear()

    def _on_merge_pick_out(self) -> None:
        out, _ = QFileDialog.getSaveFileName(
            self, "保存合并 PDF", "merged.pdf", "PDF (*.pdf)"
        )
        if not out:
            return
        self._merge_out_path = Path(out)
        self._merge_out_edit.setText(str(self._merge_out_path))

    def _on_merge_run(self) -> None:
        if len(self._merge_inputs) < 2:
            show_warning_infobar(
                self,
                title="参数未填完",
                reason="合并至少需要 2 个 PDF",
                hint="点「➕ 添加 PDF」选 2 个或更多文件。",
            )
            return
        if self._merge_out_path is None:
            show_warning_infobar(
                self,
                title="参数未填完",
                reason="未选择输出 PDF 文件",
                hint="点「选择文件」指定输出路径与文件名。",
            )
            return

        worker = _MergeWorker(list(self._merge_inputs), self._merge_out_path)
        self._launch_worker(worker, "合并")

    # ── 拆分 Tab ────────────────────────────────────────────────
    def _build_split_tab(self) -> QWidget:
        page = QWidget(self)
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 12, 0, 0)
        v.setSpacing(8)

        # 输入文件
        in_row = QHBoxLayout()
        in_row.setSpacing(6)
        in_row.addWidget(BodyLabel("输入 PDF：", page))
        self._split_in_edit = LineEdit(page)
        self._split_in_edit.setPlaceholderText("点右侧 [选择] 挑一个 PDF")
        self._split_in_edit.setReadOnly(True)
        in_row.addWidget(self._split_in_edit, 1)
        b_in = PushButton("选择", page)
        b_in.clicked.connect(self._on_split_pick_in)
        in_row.addWidget(b_in)
        v.addLayout(in_row)

        # 模式：单选
        v.addWidget(StrongBodyLabel("拆分模式", page))
        self._mode_per_page = RadioButton("按页拆（每页 1 个 PDF）", page)
        self._mode_per_page.setChecked(True)
        self._mode_per_page.toggled.connect(self._on_split_mode_changed)
        v.addWidget(self._mode_per_page)

        range_row = QHBoxLayout()
        range_row.setSpacing(6)
        self._mode_range = RadioButton("按页号范围拆", page)
        self._mode_range.toggled.connect(self._on_split_mode_changed)
        range_row.addWidget(self._mode_range)
        self._range_edit = LineEdit(page)
        self._range_edit.setPlaceholderText("示例：1-3,5,7-9")
        self._range_edit.setEnabled(False)
        range_row.addWidget(self._range_edit, 1)
        v.addLayout(range_row)

        # 输出目录
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        out_row.addWidget(BodyLabel("输出目录：", page))
        self._split_out_edit = LineEdit(page)
        self._split_out_edit.setPlaceholderText("拆出的 PDF 都会落到这个目录")
        self._split_out_edit.setReadOnly(True)
        out_row.addWidget(self._split_out_edit, 1)
        b_out = PushButton("选择目录", page)
        b_out.clicked.connect(self._on_split_pick_out)
        out_row.addWidget(b_out)
        v.addLayout(out_row)

        v.addStretch(1)

        self._split_btn = PrimaryPushButton("▶ 开始拆分", page)
        self._split_btn.clicked.connect(self._on_split_run)
        v.addWidget(self._split_btn)

        return page

    def _on_split_mode_changed(self, _checked: bool) -> None:
        # 范围模式才启用文本框
        self._range_edit.setEnabled(self._mode_range.isChecked())

    def _on_split_pick_in(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 PDF 文件", "", "PDF (*.pdf)"
        )
        if not path:
            return
        self._split_input = Path(path)
        self._split_in_edit.setText(str(self._split_input))

    def _on_split_pick_out(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not path:
            return
        self._split_out_dir = Path(path)
        self._split_out_edit.setText(str(self._split_out_dir))

    def _on_split_run(self) -> None:
        if self._split_input is None:
            show_warning_infobar(
                self, title="参数未填完",
                reason="未选择输入 PDF",
                hint="点输入 PDF 右侧的 [选择] 按钮挑一个文件。",
            )
            return
        if self._split_out_dir is None:
            show_warning_infobar(
                self, title="参数未填完",
                reason="未选择输出目录",
                hint="点输出目录右侧的 [选择目录] 按钮指定位置。",
            )
            return
        if self._mode_range.isChecked():
            expr = self._range_edit.text().strip()
            if not expr:
                show_warning_infobar(
                    self, title="参数未填完",
                    reason="按范围拆需要填页号表达式",
                    hint='例如 "1-3,5,7-9"。',
                )
                return
            worker: _BaseWorker = _SplitRangeWorker(
                self._split_input, self._split_out_dir, expr
            )
        else:
            worker = _SplitPerPageWorker(self._split_input, self._split_out_dir)

        self._launch_worker(worker, "拆分")

    # ── worker 调度 ─────────────────────────────────────────────
    def _launch_worker(self, worker: _BaseWorker, label: str) -> None:
        worker.signals.started.connect(lambda: self._on_worker_started(label))
        worker.signals.finished.connect(self._on_worker_finished)
        worker.signals.failed.connect(self._on_worker_failed)
        self._active_worker = worker
        self._pool.start(worker)
        log.info("PDF worker [%s] 已投递", label)

    def _on_worker_started(self, label: str) -> None:
        self._merge_btn.setEnabled(False)
        self._split_btn.setEnabled(False)
        # PDF 任务一次性：用 0 - 0 范围切到不确定模式（marquee 风格）
        self._progress.setRange(0, 0)
        self._progress.show()
        self._status_label.setText(f"⏳ 正在{label}…")

    def _on_worker_finished(self, summary: str) -> None:
        self._reset_action_ui()
        self._status_label.setText(f"✅ 完成：{summary}")
        show_success_infobar(self, title="任务完成", content=summary)
        self._active_worker = None

    def _on_worker_failed(self, exc: Exception) -> None:
        self._reset_action_ui()
        log.error("PDF worker 失败：%s", exc, exc_info=exc)
        self._status_label.setText("❌ 失败（详见 InfoBar）")
        show_error_infobar(self, exc, where="PDF 工具")
        self._active_worker = None

    def _reset_action_ui(self) -> None:
        self._merge_btn.setEnabled(True)
        self._split_btn.setEnabled(True)
        self._progress.hide()
        self._progress.setRange(0, 100)


# ──────────────────────────────────────────────────────────────────
# Workers（QRunnable + QObject 信号载体；与 plot_curves_view 同款）
# ──────────────────────────────────────────────────────────────────
class _WorkerSignals(QObject):
    started = Signal()
    finished = Signal(str)  # 总结字符串
    failed = Signal(object)  # Exception


class _BaseWorker(QRunnable):
    """worker 公用骨架：emit started → 跑 _run() → emit finished/failed。"""

    def __init__(self) -> None:
        super().__init__()
        self.signals = _WorkerSignals()

    def run(self) -> None:  # noqa: D401
        self._safe_emit("started")
        try:
            summary = self._do()
            self._safe_emit("finished", summary)
        except Exception as e:
            self._safe_emit("failed", e)

    def _do(self) -> str:
        raise NotImplementedError

    def _safe_emit(self, name: str, *args: object) -> None:
        sig = getattr(self.signals, name)
        try:
            sig.emit(*args)
        except RuntimeError:
            # signals 已销毁（主窗口关闭等）
            pass


class _MergeWorker(_BaseWorker):
    def __init__(self, inputs: list[Path], out_path: Path) -> None:
        super().__init__()
        self._inputs = inputs
        self._out = out_path

    def _do(self) -> str:
        out = merge_pdfs(self._inputs, self._out)
        return f"已合并 {len(self._inputs)} 个 PDF → {out.name}"


class _SplitPerPageWorker(_BaseWorker):
    def __init__(self, in_path: Path, out_dir: Path) -> None:
        super().__init__()
        self._in = in_path
        self._out_dir = out_dir

    def _do(self) -> str:
        written = split_pdf_per_page(self._in, self._out_dir)
        return f"已拆出 {len(written)} 个单页 PDF"


class _SplitRangeWorker(_BaseWorker):
    def __init__(self, in_path: Path, out_dir: Path, expr: str) -> None:
        super().__init__()
        self._in = in_path
        self._out_dir = out_dir
        self._expr = expr

    def _do(self) -> str:
        written = split_pdf_by_ranges(self._in, self._out_dir, self._expr)
        return f"已按范围 {self._expr} 拆出 {len(written)} 个 PDF"


# 注册到 error_infobar 的标题映射（PdfOpError → 友好标题）
def _register_error_titles() -> None:
    from civ_core.ui.components import error_infobar

    error_infobar._TITLE_BY_TYPE.setdefault("PdfOpError", "PDF 操作失败")


_register_error_titles()
