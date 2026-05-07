"""绘曲线图工具 —— 三栏视图骨架（QSplitter）。

布局：
  ┌─────────────┬───────────────────┬──────────────────────┐
  │ 模板列表     │ 设置面板           │ 预览区                │
  │ (Step 10)   │ (Step 11)         │ (后续步骤)             │
  │             │                   │                      │
  │             │                   │                      │
  └─────────────┴───────────────────┴──────────────────────┘
        左               中                  右

为什么 QSplitter 而不是固定 QHBoxLayout：
  • 不同分辨率 / 不同长度的模板名 / 不同字段量的设置面板，宽度需求差异大
  • 用户可以自己拖动分隔条，记忆习惯（持久化拖到何处是后续步骤的事）
  • setCollapsible(False) 防止误把某栏拖没

第二阶段渐进填充：
  Step 9（当前）：搭起 QSplitter + 3 个 _PanePlaceholder 占位
  Step 10        左栏换 TemplateListPane（真模板列表，从 cfg.paths.curve_templates 读）
  Step 11        中栏换 PlotSettingsPanel（SettingCardGroup + PlotJob 双向绑定）
  Step 12        中栏底部加"生成"按钮 + 异步 worker
  Step 13        异常通过 InfoBar 三段式提示
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    PrimaryPushButton,
    ProgressBar,
    SimpleCardWidget,
    StrongBodyLabel,
)

from civil_auto.configs.loader import AppConfig
from civil_auto.core.plot_curves import (
    RunResult,
    run_plot_curves,
)
from civil_auto.domain.schema import PlotRunSettings
from civil_auto.ui.components.error_infobar import (
    show_error_infobar,
    show_success_infobar,
    show_warning_infobar,
)
from civil_auto.ui.components.plot_settings_panel import PlotSettingsPanel
from civil_auto.ui.components.template_list import TemplateListPane
from civil_auto.utils.logger import get_logger

log = get_logger(__name__)

# 三栏初始宽度（单位：像素，按 1320×840 默认窗口算）。
# 主窗口 sidebar ≈ 280 → 视图区可用宽 ≈ 1040，三栏 220/380/440 比较舒展。
# QSplitter.setSizes 会按比例缩放，所以这些数字只是相对权重。
_INITIAL_SIZES = (220, 380, 440)


class _PanePlaceholder(SimpleCardWidget):
    """单个面板的统一占位皮：标题 + 副标题，居中。

    用 SimpleCardWidget 而不是裸 QWidget，是为了在 QSplitter 中
    每栏都有清晰的圆角卡片视觉边界，方便看出"三栏在哪里"。
    Step 10/11 真组件接入时，会换掉子内容（保留 SimpleCardWidget 外壳）。
    """

    def __init__(
        self,
        object_name: str,
        title: str,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = StrongBodyLabel(title, self)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 副标题始终建出来，便于运行期 set_subtitle() 改写（即使首次为空）
        self._subtitle_label = BodyLabel(subtitle, self)
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setStyleSheet("color: #888;")
        self._subtitle_label.setVisible(bool(subtitle))
        layout.addWidget(self._subtitle_label)

    def set_subtitle(self, text: str) -> None:
        """运行期更新副标题（临时提供给 step 10 的信号验证用）。"""
        self._subtitle_label.setText(text)
        self._subtitle_label.setVisible(bool(text))


class PlotCurvesView(QWidget):
    """绘曲线图工具的根视图（注册到 MainWindow.plot_curves_page 槽位）。

    cfg 透传给后续接入的真子面板（如 SettingsPane 需要 paths.data_output 默认值），
    本步骤仅占位，cfg 暂时只用来打日志。
    """

    def __init__(self, cfg: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # objectName 必须与 MainWindow 原 placeholder 一致，否则 qfluentwidgets 导航 routing 错位
        self.setObjectName("plotCurvesPage")
        self._cfg = cfg
        # 当前 worker（运行期间持有强引用，避免被 GC 在跑到一半时回收）
        self._active_worker: _PlotCurvesWorker | None = None
        # 复用 QApplication 全局线程池：进程生命周期内复用线程，比 QThread per-task 省
        self._pool = QThreadPool.globalInstance()

        self._build_layout()
        log.debug(
            "PlotCurvesView ready (initial sizes=%s, sum=%d, pool max=%d)",
            _INITIAL_SIZES,
            sum(_INITIAL_SIZES),
            self._pool.maxThreadCount(),
        )

    def _build_layout(self) -> None:
        # 外层 layout：只放一个 QSplitter，留窄边距
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        # 左栏：模板列表（step 10）
        # 注意：TemplateListPane.__init__ 不会自己 refresh —— 必须 build 完所有面板、
        # connect 完所有信号之后再 refresh()，否则首次 setCurrentRow(0) 触发的
        # template_selected slot 可能访问到尚未创建的 settings_pane / preview_pane。
        self.template_pane = TemplateListPane(self)

        # 中栏：设置面板（step 11）
        self.settings_pane = PlotSettingsPanel(self._cfg, self)

        # 右栏：预览区（仍是占位，后续步骤接入）
        self.preview_pane = _PanePlaceholder(
            "previewPane",
            "预览区",
            "后续步骤接入：缩略图列表 + 单击放大；生成进度也在这里展示",
        )

        # 现在所有面板都就位了，连信号，再触发首次加载
        self.template_pane.template_selected.connect(self._on_template_selected)

        # 横向 QSplitter
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("plotCurvesSplitter")
        splitter.setChildrenCollapsible(False)  # 防止用户误把某栏拖没
        splitter.setHandleWidth(6)
        splitter.addWidget(self.template_pane)
        splitter.addWidget(self.settings_pane)
        splitter.addWidget(self.preview_pane)
        splitter.setSizes(list(_INITIAL_SIZES))

        # 三栏的拉伸优先级：模板列表固定窄，设置面板和预览区可拉伸
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)

        outer.addWidget(splitter, 1)
        self._splitter = splitter  # 测试 / 后续步骤可访问

        # ── 底部操作栏：状态文字 / 进度条 / 生成按钮 ──
        bottom = self._build_action_bar()
        outer.addLayout(bottom)

        # 所有结构都搭好了，触发首次加载（refresh 内部 setCurrentRow(0) 会触发
        # template_selected → _on_template_selected，此时 settings_pane 已存在）
        self.template_pane.refresh()

    def _build_action_bar(self) -> QHBoxLayout:
        """底部操作栏：状态 + 进度 + "生成"按钮。"""
        bar = QHBoxLayout()
        bar.setContentsMargins(4, 8, 4, 4)
        bar.setSpacing(12)

        self._status_label = BodyLabel("就绪", self)
        self._status_label.setStyleSheet("color: #666;")
        bar.addWidget(self._status_label, 1)  # stretch=1 占满中间

        self._progress = ProgressBar(self)
        self._progress.setFixedWidth(220)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.hide()  # 空闲态隐藏
        bar.addWidget(self._progress)

        self._generate_btn = PrimaryPushButton("生成", self)
        self._generate_btn.setMinimumWidth(120)
        self._generate_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._generate_btn)

        return bar

    # ── slots ────────────────────────────────────────────────────
    def _on_template_selected(self, name: str) -> None:
        """用户在左栏切模板 → 把模板名推到中栏设置面板。"""
        log.info("已选模板：%s", name)
        self.settings_pane.set_template_name(name)

    def _on_generate_clicked(self) -> None:
        """点击"生成" → 校验设置 → 投递 worker 到 QThreadPool。"""
        s = self.settings_pane.settings

        # 必填字段缺失：黄色 InfoBar 提示用户去左/中栏补完
        missing = self._missing_required_fields(s)
        if missing:
            log.warning("生成被拒：缺少必填字段 %s", missing)
            self._status_label.setText("⚠️ 设置未填完")
            show_warning_infobar(
                self,
                title="参数未填完",
                reason=f"还差这些必填项：{ ' / '.join(missing) }",
                hint=(
                    "「输入 Excel」「输出目录」在中栏的设置面板里点按钮选；"
                    "「模板」在左栏列表里选。"
                ),
            )
            return

        # 投递 worker
        worker = _PlotCurvesWorker(s)
        worker.signals.started.connect(self._on_worker_started)
        worker.signals.progress.connect(self._on_worker_progress)
        worker.signals.finished.connect(self._on_worker_finished)
        worker.signals.failed.connect(self._on_worker_failed)
        self._active_worker = worker  # 保活
        self._pool.start(worker)
        log.info("worker 已投递到线程池")

    @staticmethod
    def _missing_required_fields(s: PlotRunSettings) -> list[str]:
        """返回缺失必填字段的人类可读名列表。"""
        missing: list[str] = []
        if s.input_path is None:
            missing.append("输入 Excel")
        if s.template_name is None:
            missing.append("模板")
        if s.output_dir is None:
            missing.append("输出目录")
        return missing

    # ── worker signals → UI ────────────────────────────────────
    def _on_worker_started(self) -> None:
        # UI 上锁：禁用"生成"防重入；进度归零并显示
        self._generate_btn.setEnabled(False)
        self._generate_btn.setText("生成中…")
        self._progress.setValue(0)
        self._progress.show()
        self._status_label.setText("⏳ 正在处理…")

    def _on_worker_progress(self, done: int, total: int) -> None:
        if total <= 0:
            return
        pct = int(done * 100 / total)
        self._progress.setValue(pct)
        self._status_label.setText(f"⏳ 进度 {done}/{total}")

    def _on_worker_finished(self, result: RunResult) -> None:
        # UI 解锁，复位状态
        self._reset_action_ui()
        n_ok = len(result.written)
        n_fail = len(result.failed)
        log.info("worker 完成：成功 %d / 失败 %d", n_ok, n_fail)

        if n_fail == 0:
            # 完全成功：状态行 + 右上角绿色 InfoBar 双重反馈
            self._status_label.setText(f"✅ 完成：成功 {n_ok} 张")
            show_success_infobar(
                self,
                title="批量绘图完成",
                content=f"成功 {n_ok} 张图，已写入 {result.written[0].parent if result.written else '输出目录'}",
            )
        else:
            # 部分失败：黄色 InfoBar，把首条失败的诊断展开给用户看
            self._status_label.setText(
                f"⚠️ 完成：成功 {n_ok} 张 / 失败 {n_fail} 张"
            )
            first_job, first_exc = result.failed[0]
            extra_n = n_fail - 1
            extra_tail = f"，另有 {extra_n} 张失败，详见 logs/app.log" if extra_n else ""
            show_warning_infobar(
                self,
                title="批量绘图部分失败",
                reason=f"成功 {n_ok} 张 / 失败 {n_fail} 张{extra_tail}",
                hint=(
                    f"首个失败：{first_job.output_path.name}\n"
                    f"  {type(first_exc).__name__}: {first_exc}\n"
                    f"  {getattr(first_exc, 'hint', '') or '（无建议）'}"
                ),
                duration=8000,
            )

        self._active_worker = None

    def _on_worker_failed(self, exc: Exception) -> None:
        """worker 整体失败（模板缺失 / Excel 读不到 / Sheet 空 / 缺列等）。

        三段式 InfoBar 取代原 traceback：
          标题 = "生成绘图：<异常类型映射>"
          原因 = str(exc)
          建议 = exc.hint（如果异常带）
        详细堆栈写到 logs/app.log，UI 上不弹原始 traceback。
        """
        self._reset_action_ui()
        log.error("worker 失败：%s", exc, exc_info=exc)
        self._status_label.setText("❌ 失败（详见 InfoBar）")
        show_error_infobar(self, exc, where="生成绘图")
        self._active_worker = None

    def _reset_action_ui(self) -> None:
        self._generate_btn.setEnabled(True)
        self._generate_btn.setText("生成")
        self._progress.hide()
        self._progress.setValue(0)


# ──────────────────────────────────────────────────────────────────
# Worker（QRunnable + QObject 信号载体的标准组合）
# ──────────────────────────────────────────────────────────────────
# 为什么不用 QThread per-task：
#   • QThreadPool 复用线程，连续投多个任务时省掉创建/销毁开销
#   • QRunnable 是一次性任务的天然抽象，run() 返回即结束，不用手写 quit/wait
#
# 信号为何独立成 _PlotCurvesWorkerSignals：
#   • QRunnable 不是 QObject，不能直接挂 Signal
#   • 把信号塞到一个独立 QObject 里，让 worker 持有，emit 时走 Qt 跨线程队列
class _PlotCurvesWorkerSignals(QObject):
    """worker 的信号载体。Signals 在主线程构造，emit 来自 worker 线程，
    Qt 自动用 QueuedConnection 把回调投到主线程，UI 安全。"""

    started = Signal()
    progress = Signal(int, int)  # (done, total)
    finished = Signal(object)  # RunResult —— 不带强类型避免 Qt 的元类型注册问题
    failed = Signal(object)  # Exception 同上


class _PlotCurvesWorker(QRunnable):
    """跑 run_plot_curves 的一次性任务。

    持有 PlotRunSettings 浅拷贝；run() 内部把 progress_cb 桥接到 Qt 信号，
    Qt 跨线程会把每次 emit 投到主线程的事件队列里。
    """

    def __init__(self, settings: PlotRunSettings) -> None:
        super().__init__()
        self._settings = settings
        self.signals = _PlotCurvesWorkerSignals()

    def run(self) -> None:  # noqa: D401 —— Qt 约定的入口名
        self._safe_emit("started")
        try:
            # 这里 input_path / template_name / output_dir 已被 _missing_required_fields
            # 拦过；为类型严密再 assert 一次，命中说明上游校验有 bug
            assert self._settings.input_path is not None
            assert self._settings.template_name is not None
            assert self._settings.output_dir is not None

            result = run_plot_curves(
                excel_path=self._settings.input_path,
                sheet_name=self._settings.sheet_name,
                template_name=self._settings.template_name,
                output_dir=self._settings.output_dir,
                header_row=self._settings.header_row,
                progress_cb=lambda d, t: self._safe_emit("progress", d, t),
            )
            self._safe_emit("finished", result)
        except Exception as e:
            # 异常也走信号，由 UI 统一处理；不要在 worker 线程里弹 InfoBar
            self._safe_emit("failed", e)

    def _safe_emit(self, name: str, *args: object) -> None:
        """对 self.signals.<name>.emit(*args) 的容错包装。

        极端时序下（比如主窗口在 worker 跑到一半时被关闭），signals 的 C++
        对象会被 Qt 销毁，emit 抛 RuntimeError。worker 线程拿不到 UI，记录
        都丢；但不能让 RuntimeError 把 worker 的 except 链也击穿（那样 Qt
        会打印一堆 'Error calling Python override of QRunnable::run()' 噪音）。
        """
        signal = getattr(self.signals, name)
        try:
            signal.emit(*args)
        except RuntimeError:
            # signals 对象已销毁 —— 主线程那边没人收得到了，悄悄丢
            pass
