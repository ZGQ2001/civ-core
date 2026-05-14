"""绘曲线图工具 —— 两栏视图骨架（L-1 重构）。

布局：
  ┌──────────────────────┬──────────────────────────────────────┐
  │ 参数面板（左）        │ 实时预览（右）                         │
  │ PresetAccordionPanel │ LivePreviewPane                       │
  │ （L-3b 实装风琴分组）│ （L-2 实装实时渲染管线）              │
  └──────────────────────┴──────────────────────────────────────┘
                                 ↓
                        ┌─ 状态 ── 进度 ── [生成] ─┐
                        │  日志面板（可折叠）       │
                        └────────────────────────┘

L-1 Step 1 范围
================
  • 三栏 QSplitter → 两栏 QSplitter（左参数 / 右预览）
  • 旧的 PresetListPane / PlotCenterPane / PreviewPane 在本视图不再使用；
    其中 plot_center_pane 已删，preset_list / preset_form_panel / preview_pane
    暂留待 L-3b 拆解吸收
  • QSettings 键名沿用 `plot_curves/splitter_sizes`，但维度从 3→2；
    老用户的三栏遗留值在 _restore_splitter_sizes 中被识别为损坏 → 回退默认
  • Worker / 生成按钮 / 日志面板 保留，面板无关逻辑在 L-2/L-3 重新挂回数据流

未挂回的业务（占位 stub）
========================
  • 预设选择 / 表单字段 / 预览结果展示：等 LivePreviewPane(L-2) +
    PresetAccordionPanel(L-3b) 实装后，view 层重新连信号
  • "生成"按钮当前因缺少 preset 数据源会进入 _missing_required_fields 的
    友善 InfoBar 提示分支，不会跑出图；这是 L-1 期间的预期行为

为什么 QSplitter 而不是固定 QHBoxLayout：
  • 不同分辨率 / 参数字段量差异大，左右栏宽度需要自由拖
  • setChildrenCollapsible(False) 防止误把某栏拖没
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    PrimaryPushButton,
    ProgressBar,
    TransparentToolButton,
)

from civ_core.configs.loader import AppConfig
from civ_core.core.data_cache import EXCEL_DATA_CACHE
from civ_core.core.plot_curves import (
    RunResult,
    run_plot_curves,
)
from civ_core.domain.schema import PlotRunSettings
from civ_core.infra_io.excel_reader import ExcelReadError
from civ_core.ui.components.bottom_tab_panel import BottomTabPanel
from civ_core.ui.components.error_infobar import (
    show_error_infobar,
    show_success_infobar,
    show_warning_infobar,
)
from civ_core.ui.components.live_preview_pane import LivePreviewPane
from civ_core.ui.components.preset_accordion_panel import PresetAccordionPanel
from civ_core.ui.components.preset_undo import PresetUndoController
from civ_core.utils.logger import get_logger, get_qt_bridge

log = get_logger(__name__)

# 两栏初始宽度（单位：像素）。
# 默认假设 1320×840 窗口，侧栏 ≈ 280 → 视图区可用宽 ≈ 1040；
# 600/400 给参数面板更宽（待 L-3b 装 6 个分组 + 滑块+输入框联动控件需要空间），
# 预览图 400px 也能看清缩略大致；用户可自由拖动，结果落 QSettings。
# QSplitter.setSizes 会按比例缩放，所以这些数字只是相对权重。
_INITIAL_SIZES = (600, 400)

# QSettings 标识：决定持久化文件落到哪里。
# Windows  → HKEY_CURRENT_USER\Software\ZGQ\CivCore
# Linux    → ~/.config/ZGQ/CivCore.conf
# macOS    → ~/Library/Preferences/com.ZGQ.CivCore.plist
_SETTINGS_ORG = "ZGQ"
_SETTINGS_APP = "CivCore"
# 键名保持不变（沿用三栏时代的 key），但维度从 3→2；
# 老用户存的 list[3] 会在读取时被识别为长度异常 → 回退默认（一次性丢弃）
_SETTINGS_KEY_SPLITTER = "plot_curves/splitter_sizes"
# L-4：底栏 Tab 面板折叠态持久化（沿用 LogPanel 设计的语义但用新键）
_SETTINGS_KEY_BOTTOM_COLLAPSED = "plot_curves/bottom_panel_collapsed"
# UX 重构：右栏垂直 splitter（上预览 / 下底栏）的高度比例
_SETTINGS_KEY_RIGHT_SPLITTER = "plot_curves/right_splitter_sizes"
# 默认右栏上下比例：预览 ≈ 580 / 底栏 ≈ 200（底栏折叠时高度收到约 32）
_INITIAL_RIGHT_SIZES = (580, 200)
# P1.5-Step2：叠加对比模式开关持久化
_SETTINGS_KEY_OVERLAY_MODE = "plot_curves/overlay_mode"


class PlotCurvesView(QWidget):
    """绘曲线图工具的根视图（注册到 MainWindow.plot_curves_page 槽位）。

    L-1 Step 1：两栏占位骨架，业务数据流在 L-2/L-3 阶段接回。
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
        """工程软件式布局：左栏参数面板 | 右栏(垂直 splitter [预览+工具栏 / 底栏 Tab])。"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(0)

        # ── 子组件 ──
        self.preset_accordion_panel = PresetAccordionPanel(self)
        self.live_preview_pane = LivePreviewPane(self)
        self.bottom_panel = BottomTabPanel(self)
        # 兼容别名：仍暴露 log_panel（healthcheck / 老代码可能用到）
        self.log_panel = self.bottom_panel.log_panel

        # ── 信号路由 ──
        # 参数面板 → 实时预览
        self.preset_accordion_panel.preset_changed.connect(self.live_preview_pane.set_preset)
        self.preset_accordion_panel.data_source_changed.connect(
            self.live_preview_pane.set_data_source
        )
        self.preset_accordion_panel.request_redraw_signal.connect(
            self.live_preview_pane.request_redraw
        )
        # P1.5-② 撤销/重做：监听 preset_changed → 入栈；Ctrl+Z/Y 快捷键
        # 必须在其他 preset_changed 连接之前 / 之后无所谓，控制器只读不改 data
        self._undo_ctrl = PresetUndoController(self.preset_accordion_panel, parent=self)
        self.preset_accordion_panel.preset_changed.connect(self._undo_ctrl.on_preset_changed)
        # QShortcut 在 view 范围内生效；用 StandardKey 兼容平台（macOS Cmd 自动映射）
        self._undo_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Undo), self)
        self._undo_shortcut.activated.connect(self._undo_ctrl.undo)
        self._redo_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Redo), self)
        self._redo_shortcut.activated.connect(self._undo_ctrl.redo)

        # 左右切图快捷键（Windows 相册风格）：用 Alt+← / Alt+→ 而非裸 ← / →
        # —— 裸方向键会和 LineEdit / SpinBox / ComboBox 等文本输入冲突；Alt
        # 组合让用户能在任何焦点状态下都顺利切图
        self._prev_shortcut = QShortcut(QKeySequence("Alt+Left"), self)
        self._prev_shortcut.activated.connect(self.live_preview_pane.goto_prev_row)
        self._next_shortcut = QShortcut(QKeySequence("Alt+Right"), self)
        self._next_shortcut.activated.connect(self.live_preview_pane.goto_next_row)

        # 参数面板 → 数据源 Tab
        self.preset_accordion_panel.preset_changed.connect(self._refresh_data_source_pane)
        self.preset_accordion_panel.data_source_changed.connect(self._on_data_source_changed)
        # 数据源行点击 → 预览高亮
        self.bottom_panel.data_source_pane.row_highlighted.connect(
            self.live_preview_pane.highlight_row
        )
        # 缩略图点击 → 预览高亮（点击切图）
        self.bottom_panel.thumbnail_pane.row_clicked.connect(self.live_preview_pane.highlight_row)
        # 反向：每次预览切行后，缩略图列表也高亮对应项（双向联动）
        self.live_preview_pane.jobs_state_changed.connect(
            lambda _count, idx: self.bottom_panel.thumbnail_pane.set_current_index(idx)
        )
        # P1.5-Step3c：反向 —— 叠加模式下 hover 曲线 → 表格滚动到对应行
        # DataSourcePane.highlight_row 内有 _suppress_emit 防回环，安全
        self.live_preview_pane.point_hovered.connect(
            self.bottom_panel.data_source_pane.highlight_row
        )
        # QtLogBridge → 日志面板
        bridge = get_qt_bridge()
        if bridge is not None:
            bridge.record_emitted.connect(self.bottom_panel.log_panel.on_record)
            log.debug("LogPanel 已连接到 QtLogBridge")

        # ── 右栏：上=工具栏+预览 / 下=底栏 Tab（垂直 splitter）──
        right_widget = self._build_right_column()

        # ── 主水平 QSplitter ──
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("plotCurvesSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        splitter.addWidget(self.preset_accordion_panel)
        splitter.addWidget(right_widget)
        splitter.setSizes(self._restore_splitter_sizes())
        # 左栏：宽度不主动扩张；右栏吃掉所有水平 stretch
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.splitterMoved.connect(self._on_splitter_moved)
        outer.addWidget(splitter, 1)
        self._splitter = splitter

        # 底栏折叠态恢复（必须在右栏已 build 后）
        self.bottom_panel.collapse_changed.connect(self._on_bottom_collapse_changed)
        initial_collapsed = self._restore_bottom_collapsed()
        self.bottom_panel.set_collapsed(initial_collapsed)
        # set_collapsed 在状态相同时不 emit 信号；而构造时初始状态可能与默认
        # 不同（也可能相同），都需要强制同步一次 splitter sizes，避免初始
        # 显示成"底栏卡在中间"的尴尬状态
        self._apply_bottom_collapsed_to_splitter(initial_collapsed)

        # 关键 bugfix：PresetAccordionPanel.__init__ 在 refresh() 末尾会
        # emit 一次 preset_changed（带默认预设的完整数据），但那时 view 层
        # 的 signal connect 还没建立 —— 这次 emit 是"空喊"，没人收到。
        # 结果：LivePreviewPane._preset 一直是 None，用户不动预设、直接
        # 选 Excel 时实时预览会卡在"请先选预设"。
        # 这里在所有 connect 完成后主动同步一次当前预设给 LivePreviewPane。
        self.live_preview_pane.set_preset(self.preset_accordion_panel.current_preset_data())

    def _build_right_column(self) -> QWidget:
        """右栏：工具栏(生成按钮+状态+进度) → 预览图 → 底栏 Tab。
        预览与底栏之间用垂直 QSplitter 隔开，比例可调，持久化。
        """
        right = QWidget(self)
        right.setObjectName("plotCurvesRightColumn")
        # 显式允许窄宽：底栏 DataSourcePane 在 11 列长表头场景下不会
        # 通过 minimumSizeHint 链条把整个主窗口拉过屏幕宽度
        right.setMinimumWidth(0)
        v = QVBoxLayout(right)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 预览上方工具栏（替代原底部 action_bar，让"生成"紧邻预览图）
        toolbar = self._build_preview_toolbar()
        v.addLayout(toolbar)

        vsplit = QSplitter(Qt.Orientation.Vertical, right)
        vsplit.setObjectName("plotCurvesRightSplitter")
        vsplit.setChildrenCollapsible(False)
        vsplit.setHandleWidth(6)
        vsplit.addWidget(self.live_preview_pane)
        vsplit.addWidget(self.bottom_panel)
        vsplit.setSizes(self._restore_right_splitter_sizes())
        # 预览吃掉竖向 stretch（用户拉高窗口时主要给预览，不给底栏）
        vsplit.setStretchFactor(0, 1)
        vsplit.setStretchFactor(1, 0)
        vsplit.splitterMoved.connect(self._on_right_splitter_moved)
        self._right_splitter = vsplit

        v.addWidget(vsplit, 1)
        return right

    def _build_preview_toolbar(self) -> QHBoxLayout:
        """工程软件式工具栏：[生成按钮] + 状态 + 进度。

        生成按钮放在预览图正上方，语义直白（"按当前预设把这些数据导出 PNG"），
        告别原"右下角孤立小按钮"。
        """
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        bar.setSpacing(8)

        self._generate_btn = PrimaryPushButton("▶ 生成全部曲线 PNG", self)
        self._generate_btn.setToolTip(
            "按当前预设 + Excel 数据源，把所有行批量导出 PNG 到「输出目录」"
        )
        self._generate_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._generate_btn)

        # 左右切图（Windows 相册风格）：按 jobs_count 启停；点击循环切行
        # 同时支持键盘快捷键（Alt+← / Alt+→），见 _build_layout 末尾的 QShortcut
        self._prev_btn = TransparentToolButton(self)
        self._prev_btn.setText("◀")
        self._prev_btn.setToolTip("上一张 (Alt+←) —— 切到上一行的曲线图")
        self._prev_btn.clicked.connect(self.live_preview_pane.goto_prev_row)
        self._prev_btn.setEnabled(False)
        bar.addWidget(self._prev_btn)

        self._row_indicator = BodyLabel("—/—", self)
        self._row_indicator.setToolTip("当前预览第几行 / 共多少行")
        self._row_indicator.setStyleSheet("color: #8B92A0; font-family: Consolas;")
        bar.addWidget(self._row_indicator)

        self._next_btn = TransparentToolButton(self)
        self._next_btn.setText("▶")
        self._next_btn.setToolTip("下一张 (Alt+→) —— 切到下一行的曲线图")
        self._next_btn.clicked.connect(self.live_preview_pane.goto_next_row)
        self._next_btn.setEnabled(False)
        bar.addWidget(self._next_btn)

        # 接 jobs_state_changed 信号 → 更新指示器 + 启停切图按钮
        self.live_preview_pane.jobs_state_changed.connect(self._on_jobs_state_changed)

        # P1.5-Step2：叠加对比开关（默认关）
        # 开 → 预览把所有行的曲线画到一张图，每根试件一种颜色；
        # 数据源 Tab 点行 → 该根曲线加粗高亮 + 其余半透明
        self._overlay_chk = CheckBox("叠加对比", self)
        self._overlay_chk.setToolTip(
            "开启后预览改成叠加图：每根试件一条曲线；点表格行 → 该根高亮加粗"
        )
        # 先 connect 再 setChecked：让 setChecked 触发 toggled，
        # 自动把模式同步给 live_preview_pane（一次副作用：可能起一次重绘）
        self._overlay_chk.toggled.connect(self._on_overlay_toggled)
        self._overlay_chk.setChecked(self._restore_overlay_mode())
        bar.addWidget(self._overlay_chk)

        self._status_label = BodyLabel("就绪", self)
        self._status_label.setStyleSheet("color: #666;")
        bar.addWidget(self._status_label, 1)

        self._progress = ProgressBar(self)
        self._progress.setFixedWidth(200)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.hide()
        bar.addWidget(self._progress)

        return bar

    # ── splitter 持久化 ──────────────────────────────────────────
    def _make_settings(self) -> QSettings:
        """构造 QSettings 实例。

        抽出工厂方法主要是为了让单测能 monkey patch 重定向到 tmp 文件，
        避免污染开发机的真实 user-scope settings。
        """
        return QSettings(_SETTINGS_ORG, _SETTINGS_APP)

    def _restore_splitter_sizes(self) -> list[int]:
        """读 QSettings 里上次保存的 splitter sizes；没有 / 损坏 → 默认值。

        QSettings 的 native 后端会按平台决定值类型：
          - Windows 注册表里 list[int] 存为 QStringList，读出来就是 list[str]
          - Linux INI 文件同样
        所以这里要再 int() 一遍并做长度 / 总和合法性校验。

        L-1 改造点：长度从 == 3 改成 == 2；老用户存的三栏值会因为长度不符
        被识别为损坏 → 回退默认（一次性丢弃，下次拖动后即被两栏值覆盖）。
        """
        settings = self._make_settings()
        saved = settings.value(_SETTINGS_KEY_SPLITTER)
        if saved is None:
            return list(_INITIAL_SIZES)

        try:
            sizes = [int(x) for x in saved]
        except (TypeError, ValueError):
            log.warning("QSettings 中 splitter sizes 损坏（不是数字列表），回退到默认")
            return list(_INITIAL_SIZES)

        # 两栏布局严格要求 2 个值；总和为 0 / 负数说明 sizes 全 0（minimised）
        if len(sizes) != 2 or sum(sizes) <= 0:
            log.warning(
                "QSettings 中 splitter sizes 异常 (len=%d, sum=%d)，回退到默认",
                len(sizes),
                sum(sizes),
            )
            return list(_INITIAL_SIZES)

        log.debug("已从 QSettings 恢复 splitter sizes: %s", sizes)
        return sizes

    # ── L-4：底栏折叠态持久化 ─────────────────────────────────────
    def _restore_bottom_collapsed(self) -> bool:
        """读 QSettings 中的折叠态；默认 True（开屏不展开）。"""
        v = self._make_settings().value(_SETTINGS_KEY_BOTTOM_COLLAPSED)
        if v is None:
            return True
        # QSettings 各后端返回类型不同：bool / "true"/"false" / int
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return bool(v)
        return str(v).lower() in {"true", "1", "yes"}

    def _on_bottom_collapse_changed(self, collapsed: bool) -> None:
        self._make_settings().setValue(_SETTINGS_KEY_BOTTOM_COLLAPSED, collapsed)
        self._apply_bottom_collapsed_to_splitter(collapsed)

    def _apply_bottom_collapsed_to_splitter(self, collapsed: bool) -> None:
        """同步底栏折叠态到垂直 splitter sizes（VS Code 终端风格）。

        collapsed=True：底栏只剩工具栏高度（≈ 32–40px 一行），预览区吃满剩余空间
                        —— 不这么做的话 splitter 不会重新分配，底栏控件本身只占
                        工具栏高度但 splitter 仍分配了原 200px 给它，剩余空白
                        在视觉上像"底栏卡在中间"。
        collapsed=False：恢复用户上一次 expand 时的拖动比例（_last_expanded_right_sizes）。

        本方法对外暴露，因为：
          - signal 路径会调（_on_bottom_collapse_changed）
          - 构造时如果初始就是 collapsed，必须再调一次同步 splitter 初值
        """
        if not hasattr(self, "_right_splitter"):
            return  # splitter 还没建（构造极早期）
        if collapsed:
            cur = self._right_splitter.sizes()
            bottom_min = max(
                self.bottom_panel.minimumSizeHint().height(),
                self.bottom_panel.sizeHint().height(),
                32,
            )
            # 记下"上次 expanded 时的 sizes"，仅当当前确实是 expanded（底栏 >
            # 工具栏高度）才记录，避免反复 collapse 时把"已折叠 sizes" 误存
            if sum(cur) > 0 and cur[1] > bottom_min + 4:
                self._last_expanded_right_sizes = list(cur)
            total = max(sum(cur), 200)  # 防御性：极端情况 total=0
            self._right_splitter.setSizes([total - bottom_min, bottom_min])
        else:
            sizes = getattr(self, "_last_expanded_right_sizes", None) or list(_INITIAL_RIGHT_SIZES)
            self._right_splitter.setSizes(sizes)

    # ── P1.5-Step2：叠加对比模式持久化 ────────────────────────────
    def _restore_overlay_mode(self) -> bool:
        """读 QSettings 中的叠加模式；默认 False（开屏单行）。"""
        v = self._make_settings().value(_SETTINGS_KEY_OVERLAY_MODE)
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return bool(v)
        return str(v).lower() in {"true", "1", "yes"}

    def _on_overlay_toggled(self, checked: bool) -> None:
        """工具栏复选框 → 预览面板模式切换 + 持久化。"""
        self.live_preview_pane.set_overlay_mode(checked)
        self._make_settings().setValue(_SETTINGS_KEY_OVERLAY_MODE, checked)

    def _on_jobs_state_changed(self, jobs_count: int, current_idx: int) -> None:
        """LivePreviewPane 渲染完一次 → 更新工具栏指示器 + 启停切图按钮。"""
        if jobs_count <= 0:
            self._row_indicator.setText("—/—")
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            return
        self._row_indicator.setText(f"{current_idx + 1}/{jobs_count}")
        enabled = jobs_count > 1
        self._prev_btn.setEnabled(enabled)
        self._next_btn.setEnabled(enabled)

    # ── 数据源 Tab 数据流 ─────────────────────────────────────────
    def _refresh_data_source_pane(self, *_args: object) -> None:
        """preset_changed 或 data_source_changed 时刷新底栏数据表。

        *_args 让本方法既能挂 preset_changed(dict) 也能挂
        data_source_changed(Path, sheet) —— 多余参数忽略。
        """
        preset = self.preset_accordion_panel.current_preset_data()
        rs = self.preset_accordion_panel.current_run_settings()
        input_path = rs.input_path
        sheet_name = rs.sheet_name
        header_row = rs.header_row
        if input_path is None:
            self.bottom_panel.data_source_pane.clear()
            return
        try:
            rows = EXCEL_DATA_CACHE.get_rows(input_path, sheet_name, header_row)
        except ExcelReadError as e:
            log.warning("DataSourcePane 加载数据失败：%s", e)
            self.bottom_panel.data_source_pane.clear()
            return
        self.bottom_panel.data_source_pane.set_preset_and_data(preset, rows)

    def _on_data_source_changed(self, *_args: object) -> None:
        """data_source_changed 信号到达时，让数据源 Tab 也刷新一次。"""
        self._refresh_data_source_pane()

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        """主水平 splitter 拖动 → 写盘。"""
        sizes = self._splitter.sizes()
        if any(s <= 0 for s in sizes):
            return
        self._make_settings().setValue(_SETTINGS_KEY_SPLITTER, sizes)

    # ── 右栏垂直 splitter 持久化 ─────────────────────────────────
    def _restore_right_splitter_sizes(self) -> list[int]:
        """读 QSettings 中右栏上下两段的高度；容错回退默认。"""
        saved = self._make_settings().value(_SETTINGS_KEY_RIGHT_SPLITTER)
        if saved is None:
            return list(_INITIAL_RIGHT_SIZES)
        try:
            sizes = [int(x) for x in saved]
        except (TypeError, ValueError):
            return list(_INITIAL_RIGHT_SIZES)
        if len(sizes) != 2 or sum(sizes) <= 0:
            return list(_INITIAL_RIGHT_SIZES)
        return sizes

    def _on_right_splitter_moved(self, _pos: int, _index: int) -> None:
        sizes = self._right_splitter.sizes()
        if any(s <= 0 for s in sizes):
            return
        self._make_settings().setValue(_SETTINGS_KEY_RIGHT_SPLITTER, sizes)

    # ── 业务入口（L-1 期间为占位 stub，L-2/L-3 阶段挂回数据流） ────
    def _current_run_settings(self) -> PlotRunSettings:
        """收集当前运行参数。L-3b 起从 PresetAccordionPanel 取真实值。"""
        return self.preset_accordion_panel.current_run_settings()

    def _on_generate_clicked(self) -> None:
        """点击"生成" → 校验设置 → 投递 worker 到 QThreadPool。

        L-1 期间，_current_run_settings() 始终返回空设置 → 必填检查不过 →
        给用户友善 InfoBar 提示"参数面板待 L-3b 接入"，不会跑出图。
        """
        s = self._current_run_settings()

        # 必填字段缺失：黄色 InfoBar 提示用户去左栏补完
        missing = self._missing_required_fields(s)
        if missing:
            log.warning("生成被拒：缺少必填字段 %s", missing)
            self._status_label.setText("⚠️ 设置未填完")
            show_warning_infobar(
                self,
                title="参数未填完",
                reason=f"还差这些必填项：{' / '.join(missing)}",
                hint=(
                    "「输入 Excel」「输出目录」在左栏【数据源】分组里选；"
                    "「预设」在左栏【预设选择】分组里下拉。"
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
    def _validate_preset_form(
        name: str,
        data: dict,
        curves_text: str,
    ) -> list[str]:
        """轻量字段校验。返回所有问题点的人类可读列表，空 = 通过。

        L-1 期间为 dead code（view 内未调用），保留是因为：
          • 19 个测试用例覆盖的纯逻辑函数，重写代价高
          • L-3b 把 PresetAccordionPanel 接到 save flow 时还要靠它做拦截

        校验范围（"最低门槛"，不做深度业务校验）：
          每个字段非空 + range 单调 + curves 是合法 list；
          curves[i].points / Excel 列名一致性等留给真正跑出图时再暴露。
        """
        issues: list[str] = []

        # name
        if not name:
            issues.append("预设名称不能为空")
        elif name.startswith("_"):
            issues.append("预设名称不能以下划线开头（保留给注释）")

        # 字符串字段非空
        if not str(data.get("id_column", "")).strip():
            issues.append("标识列不能为空")

        fname = str(data.get("filename_template", ""))
        if not fname.strip():
            issues.append("文件名模板不能为空")
        elif "{id}" not in fname:
            issues.append("文件名模板必须包含 {id} 占位符")

        if not str(data.get("title_template", "")).strip():
            issues.append("图标题模板不能为空")

        # 轴 label 非空 + range 校验
        for axis_label, axis_key in [("X 轴", "x_axis"), ("Y 轴", "y_axis")]:
            axis = data.get(axis_key) or {}
            if not str(axis.get("label", "")).strip():
                issues.append(f"{axis_label}标签不能为空")
            r = axis.get("range")
            if r is not None:
                # _RangeRow 总是给出 [min, max, step]；防御性兜底
                if not isinstance(r, list) or len(r) < 3:
                    issues.append(f"{axis_label}范围数据格式异常")
                else:
                    if r[0] >= r[1]:
                        issues.append(f"{axis_label}范围 min ({r[0]}) 必须小于 max ({r[1]})")
                    if r[2] <= 0:
                        issues.append(f"{axis_label}范围 step ({r[2]}) 必须 > 0")

        # curves
        curves = data.get("curves")
        if not isinstance(curves, list):
            issues.append("曲线必须是 JSON 列表")
        else:
            # 检查 PresetFormPanel 塞的解析错误标记
            for item in curves:
                if isinstance(item, dict) and "_parse_error" in item:
                    issues.append(f"曲线 JSON 解析失败：{item['_parse_error']}")
                    break  # 一条错就足够提示，不重复
            else:
                if curves_text.strip() and not curves:
                    # 文本框非空但解析后为空（罕见）
                    issues.append("曲线字段无法解析为 JSON 列表")
                for i, c in enumerate(curves):
                    if not isinstance(c, dict):
                        issues.append(f"第 {i + 1} 条曲线必须是 JSON 对象")
                        continue
                    if not str(c.get("name", "")).strip():
                        issues.append(f"第 {i + 1} 条曲线缺少 name 字段")

        return issues

    @staticmethod
    def _missing_required_fields(s: PlotRunSettings) -> list[str]:
        """返回缺失必填字段的人类可读名列表。"""
        missing: list[str] = []
        if s.input_path is None:
            missing.append("输入 Excel")
        if s.preset_name is None:
            missing.append("预设")
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
        # L-2 接入后，这里要清空 LivePreviewPane 当前图

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

        # 把成功的 PNG 路径喂给底栏「缩略图」Tab，让用户直观看到所有结果
        # 并能点缩略图切换主预览
        self.bottom_panel.thumbnail_pane.set_thumbnails(result.written)
        # 自动展开底栏 + 切到缩略图 Tab —— 用户刚生成完想看结果，这一步省一次点击
        if result.written:
            self.bottom_panel.set_collapsed(False)
            self.bottom_panel.show_thumb_tab()

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
            self._status_label.setText(f"⚠️ 完成：成功 {n_ok} 张 / 失败 {n_fail} 张")
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
            # 这里 input_path / preset_name / output_dir 已被 _missing_required_fields
            # 拦过；为类型严密再 assert 一次，命中说明上游校验有 bug
            assert self._settings.input_path is not None
            assert self._settings.preset_name is not None
            assert self._settings.output_dir is not None

            result = run_plot_curves(
                excel_path=self._settings.input_path,
                sheet_name=self._settings.sheet_name,
                preset_name=self._settings.preset_name,
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
