"""Word → PDF 批量转换视图（P3 新工具接入）。

布局：
  ┌─────────────────────────────────────────────────────────┐
  │ 标题 + 副标题                                              │
  │ 待转 Word 文件列表 [➕ 添加 / × 删 / 清空]                    │
  │ 输出目录 [选择目录]                                         │
  │ [▶ 开始批量转换]                                            │
  ├─────────────────────────────────────────────────────────┤
  │ 状态行 + 进度条（done/total）                                │
  └─────────────────────────────────────────────────────────┘

合规：
  • 不直接调 COM —— 走 infra_io/word_to_pdf.py 的 convert_batch
  • 异常通过 error_infobar 三段式
  • 长任务（启动 Word ~3s + 单文件 ~1s）QThreadPool 投递不卡 UI
  • progress_cb 把 (done, total, current) 透回主线程更新 ProgressBar / 状态
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
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
    StrongBodyLabel,
)

from civ_core.configs.loader import AppConfig
from civ_core.infra_io.word_to_pdf import (
    ConvertResult,
    Word2PdfError,
    convert_batch,
)
from civ_core.ui.components.error_infobar import (
    show_error_infobar,
    show_success_infobar,
    show_warning_infobar,
)
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


class Word2PdfView(QWidget):
    """Word/WPS → PDF 批量转换工具页（导航 routing key = word2PdfPage）。"""

    def __init__(self, cfg: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("word2PdfPage")
        self._cfg = cfg
        self._pool = QThreadPool.globalInstance()
        self._active_worker: _Word2PdfWorker | None = None

        self._inputs: list[Path] = []
        self._out_dir: Path | None = None

        self._build_layout()

    # ── UI ──────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(10)

        title = StrongBodyLabel("Word → PDF 批量转换", self)
        # 统一走 style_helper（与项目看板等其他页面 H1 一致）
        from civ_core.ui.style_helper import qss_title_label
        title.setStyleSheet(qss_title_label())
        outer.addWidget(title)

        subtitle = BodyLabel(
            "通过 Microsoft Word 或 WPS Office 把 .doc / .docx 批量另存为 PDF。"
            "本机必须装一种 Office。",
            self,
        )
        subtitle.setStyleSheet("color: #888;")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        outer.addWidget(StrongBodyLabel("待转 Word 文件列表", self))
        self._list = QListWidget(self)
        self._list.setAlternatingRowColors(True)
        outer.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        b_add = PushButton("➕ 添加 Word", self)
        b_add.clicked.connect(self._on_add)
        btn_row.addWidget(b_add)
        b_del = PushButton("× 删除选中", self)
        b_del.clicked.connect(self._on_remove)
        btn_row.addWidget(b_del)
        b_clear = PushButton("清空", self)
        b_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(b_clear)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        # 输出目录
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        out_row.addWidget(BodyLabel("输出目录：", self))
        self._out_edit = LineEdit(self)
        self._out_edit.setPlaceholderText("PDF 都会落到这个目录（与原 Word 同名）")
        self._out_edit.setReadOnly(True)
        out_row.addWidget(self._out_edit, 1)
        b_out = PushButton("选择目录", self)
        b_out.clicked.connect(self._on_pick_out)
        out_row.addWidget(b_out)
        outer.addLayout(out_row)

        # 主操作按钮
        self._run_btn = PrimaryPushButton("▶ 开始批量转换", self)
        self._run_btn.clicked.connect(self._on_run)
        outer.addWidget(self._run_btn)

        # 状态 + 进度
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

    # ── 列表操作 ────────────────────────────────────────────────
    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 Word 文件", "", "Word (*.doc *.docx)")
        for raw in paths:
            p = Path(raw)
            if p not in self._inputs:
                self._inputs.append(p)
                self._list.addItem(QListWidgetItem(f"📄 {p.name}"))

    def _on_remove(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        del self._inputs[row]
        self._list.takeItem(row)

    def _on_clear(self) -> None:
        self._inputs.clear()
        self._list.clear()

    def _on_pick_out(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not path:
            return
        self._out_dir = Path(path)
        self._out_edit.setText(str(self._out_dir))

    # ── 运行 ────────────────────────────────────────────────────
    def _on_run(self) -> None:
        if not self._inputs:
            show_warning_infobar(
                self,
                title="参数未填完",
                reason="还没添加任何 Word 文件",
                hint="点 [➕ 添加 Word] 挑选 .doc / .docx 文件。",
            )
            return
        if self._out_dir is None:
            show_warning_infobar(
                self,
                title="参数未填完",
                reason="未选择输出目录",
                hint="点 [选择目录] 指定 PDF 落盘位置。",
            )
            return

        worker = _Word2PdfWorker(list(self._inputs), self._out_dir)
        worker.signals.started.connect(self._on_started)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self._active_worker = worker
        self._pool.start(worker)
        log.info("Word→PDF worker 已投递（%d 个文件）", len(self._inputs))

    def _on_started(self) -> None:
        self._run_btn.setEnabled(False)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.show()
        self._status_label.setText("⏳ 正在启动 Word/WPS…")

    def _on_progress(self, done: int, total: int, cur_name: str) -> None:
        if total <= 0:
            return
        pct = int(done * 100 / total)
        self._progress.setValue(pct)
        self._status_label.setText(f"⏳ 进度 {done}/{total} · {cur_name}")

    def _on_finished(self, result: object) -> None:
        # signal 用 object，运行时确保是 ConvertResult
        assert isinstance(result, ConvertResult)
        self._reset_action_ui()
        n_ok = len(result.written)
        n_fail = len(result.failed)
        self._active_worker = None

        if n_fail == 0:
            self._status_label.setText(f"✅ 完成：成功 {n_ok} 个")
            show_success_infobar(
                self,
                title="批量转换完成",
                content=f"成功转换 {n_ok} 个 Word → PDF。",
            )
        else:
            self._status_label.setText(f"⚠️ 完成：成功 {n_ok} 个 / 失败 {n_fail} 个")
            first_path, first_exc = result.failed[0]
            extra = f"，另有 {n_fail - 1} 个失败，详见 logs/app.log" if n_fail > 1 else ""
            show_warning_infobar(
                self,
                title="批量转换部分失败",
                reason=f"成功 {n_ok} / 失败 {n_fail}{extra}",
                hint=(
                    f"首个失败：{first_path.name}\n"
                    f"  {type(first_exc).__name__}: {first_exc}\n"
                    f"  {getattr(first_exc, 'hint', '') or '（无具体建议）'}"
                ),
                duration=8000,
            )

    def _on_failed(self, exc: Exception) -> None:
        self._reset_action_ui()
        log.error("Word→PDF worker 整批失败：%s", exc, exc_info=exc)
        self._status_label.setText("❌ 失败（详见 InfoBar）")
        show_error_infobar(self, exc, where="Word 转 PDF")
        self._active_worker = None

    def _reset_action_ui(self) -> None:
        self._run_btn.setEnabled(True)
        self._progress.hide()


# ──────────────────────────────────────────────────────────────────
# Worker
# ──────────────────────────────────────────────────────────────────
class _Word2PdfWorkerSignals(QObject):
    started = Signal()
    progress = Signal(int, int, str)  # done, total, current file name
    finished = Signal(object)  # ConvertResult
    failed = Signal(object)  # Exception（整批失败：引擎挂载失败 / 空输入等）


class _Word2PdfWorker(QRunnable):
    def __init__(self, inputs: list[Path], out_dir: Path) -> None:
        super().__init__()
        self._inputs = inputs
        self._out_dir = out_dir
        self.signals = _Word2PdfWorkerSignals()

    def run(self) -> None:  # noqa: D401
        self._safe_emit("started")
        try:
            result = convert_batch(
                self._inputs,
                self._out_dir,
                progress_cb=lambda done, total, cur: self._safe_emit(
                    "progress", done, total, cur.name
                ),
            )
            self._safe_emit("finished", result)
        except Word2PdfError as e:
            self._safe_emit("failed", e)
        except Exception as e:
            # 兜底（pythoncom / pywin32 内部异常）
            self._safe_emit("failed", e)

    def _safe_emit(self, name: str, *args: object) -> None:
        sig = getattr(self.signals, name)
        try:
            sig.emit(*args)
        except RuntimeError:
            pass


# 注册 error_infobar 标题映射
def _register_error_titles() -> None:
    from civ_core.ui.components import error_infobar

    error_infobar._TITLE_BY_TYPE.setdefault("Word2PdfError", "Word 转 PDF 失败")


_register_error_titles()
