"""绘曲线图工具 —— 三栏视图骨架（QSplitter）。

布局：
  ┌─────────────┬───────────────────┬──────────────────────┐
  │ 预设列表     │ Pivot 双 Tab：    │ 预览区                │
  │             │   绘图参数         │   大图查看            │
  │ 🔒/✏️ 列表 │   预设设置         │   缩略图列表          │
  │ [+新建]     │                   │                      │
  │ [复制][删除]│                   │                      │
  └─────────────┴───────────────────┴──────────────────────┘
        左               中                  右

为什么 QSplitter 而不是固定 QHBoxLayout：
  • 不同分辨率 / 不同长度的预设名 / 不同字段量的设置面板，宽度需求差异大
  • 用户可以自己拖动分隔条；P1 已加 QSettings 持久化记忆拖到的位置
  • setCollapsible(False) 防止误把某栏拖没

各栏组件来源：
  • 左栏：ui/components/preset_list.py PresetListPane
  • 中栏：ui/components/plot_center_pane.py PlotCenterPane（含 settings_panel + form_panel）
  • 右栏：ui/components/preview_pane.py PreviewPane
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    PrimaryPushButton,
    ProgressBar,
)

from civil_auto.configs.loader import AppConfig
from civil_auto.core.plot_curves import (
    RunResult,
    run_plot_curves,
)
from civil_auto.domain.schema import PlotRunSettings
from civil_auto.infra_io.preset_manager import (
    PresetError,
    PresetSource,
    save_user_preset,
)
from civil_auto.ui.components.error_infobar import (
    show_error_infobar,
    show_success_infobar,
    show_warning_infobar,
)
from civil_auto.ui.components.log_panel import LogPanel
from civil_auto.ui.components.plot_center_pane import PlotCenterPane
from civil_auto.ui.components.preset_list import PresetListPane
from civil_auto.ui.components.preview_pane import PreviewPane
from civil_auto.utils.logger import get_logger, get_qt_bridge

log = get_logger(__name__)

# 三栏初始宽度（单位：像素，按 1320×840 默认窗口算）。
# 主窗口 sidebar ≈ 280 → 视图区可用宽 ≈ 1040，三栏 220/380/440 比较舒展。
# QSplitter.setSizes 会按比例缩放，所以这些数字只是相对权重。
_INITIAL_SIZES = (220, 380, 440)

# QSettings 标识：决定持久化文件落到哪里。
# Windows  → HKEY_CURRENT_USER\Software\ZGQ\CivilAuto
# Linux    → ~/.config/ZGQ/CivilAuto.conf
# macOS    → ~/Library/Preferences/com.ZGQ.CivilAuto.plist
# 也可以用 IniFormat 强制走文本 ini，但默认 native 方式更"系统"，权限/同步问题少。
_SETTINGS_ORG = "ZGQ"
_SETTINGS_APP = "CivilAuto"
_SETTINGS_KEY_SPLITTER = "plot_curves/splitter_sizes"


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

        # 左栏：预设列表（step 10）
        # 注意：PresetListPane.__init__ 不会自己 refresh —— 必须 build 完所有面板、
        # connect 完所有信号之后再 refresh()，否则首次 setCurrentRow(0) 触发的
        # preset_selected slot 可能访问到尚未创建的 center_pane / preview_pane。
        self.preset_pane = PresetListPane(self)

        # 中栏：Pivot 双 Tab（绘图参数 / 预设设置）—— T-4 重构
        # PlotCenterPane 内部装着 PlotSettingsPanel + PresetFormPanel
        # 通过 .settings_panel / .form_panel 暴露给本视图做联动
        self.center_pane = PlotCenterPane(self._cfg, self)
        # settings_pane 别名：保持与原代码兼容（worker / 校验等仍叫这个名字）
        self.settings_pane = self.center_pane.settings_panel

        # 右栏：预览区（缩略图列表 + 大图查看）
        self.preview_pane = PreviewPane(self)

        # 现在所有面板都就位了，连信号，再触发首次加载
        self.preset_pane.preset_selected.connect(self._on_preset_selected)
        self.preset_pane.new_preset_requested.connect(self._on_new_preset_requested)

        # 「预设设置」表单的四个动作信号（系统/用户/新建三态）
        form = self.center_pane.form_panel
        form.copy_to_user_requested.connect(self._on_form_copy_clicked)
        form.save_requested.connect(self._on_form_save_clicked)
        form.reset_requested.connect(self._on_form_reset_clicked)
        form.cancel_new_requested.connect(self._on_form_cancel_new_clicked)

        # 横向 QSplitter
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("plotCurvesSplitter")
        splitter.setChildrenCollapsible(False)  # 防止用户误把某栏拖没
        splitter.setHandleWidth(6)
        splitter.addWidget(self.preset_pane)
        splitter.addWidget(self.center_pane)
        splitter.addWidget(self.preview_pane)
        # 持久化 sizes：上次拖动后保存的值优先；没保存过 / 损坏 → 用默认
        splitter.setSizes(self._restore_splitter_sizes())

        # 三栏的拉伸优先级：预设列表固定窄，设置面板和预览区可拉伸
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)

        # 用户拖动 → 立即写盘。QSettings 的 setValue 是文件级别 IO，
        # 一次拖动会触发若干次 splitterMoved（鼠标移动间隔），这点频率写盘代价低。
        # 不监听 view.closeEvent —— 进程异常退出时也能保住最后的拖动结果。
        splitter.splitterMoved.connect(self._on_splitter_moved)

        outer.addWidget(splitter, 1)
        self._splitter = splitter  # 测试 / 后续步骤可访问

        # ── 底部操作栏：状态文字 / 进度条 / 生成按钮 ──
        bottom = self._build_action_bar()
        outer.addLayout(bottom)

        # ── 最底部：可折叠日志面板（默认折叠，避免开屏一堆 INFO 干扰）──
        # 接 QtLogBridge —— bridge 在 setup_logging() 后才存在；
        # 测试场景未调用 setup_logging 时 bridge=None，跳过连接，面板仍可创建
        self.log_panel = LogPanel(self)
        bridge = get_qt_bridge()
        if bridge is not None:
            bridge.record_emitted.connect(self.log_panel.on_record)
            log.debug("LogPanel 已连接到 QtLogBridge")
        outer.addWidget(self.log_panel)

        # 所有结构都搭好了，触发首次加载（refresh 内部 setCurrentRow(0) 会触发
        # preset_selected → _on_preset_selected，此时 settings_pane 已存在）
        self.preset_pane.refresh()

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

        # 三栏布局依赖 3 个值；总和为 0 / 负数说明 sizes 全 0（minimised）
        if len(sizes) != 3 or sum(sizes) <= 0:
            log.warning(
                "QSettings 中 splitter sizes 异常 (len=%d, sum=%d)，回退到默认",
                len(sizes),
                sum(sizes),
            )
            return list(_INITIAL_SIZES)

        log.debug("已从 QSettings 恢复 splitter sizes: %s", sizes)
        return sizes

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        """splitterMoved 信号 → 立即把当前 sizes 写到 QSettings。"""
        sizes = self._splitter.sizes()
        # 防御：拖到边界时偶发 sizes 含 0（虽然 setChildrenCollapsible(False) 已挡过），
        # 不要把这种"只剩两栏"的状态存下去
        if any(s <= 0 for s in sizes):
            return
        self._make_settings().setValue(_SETTINGS_KEY_SPLITTER, sizes)

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
    def _on_preset_selected(self, name: str) -> None:
        """用户在左栏切预设 → 同步两件事：

        1) 「绘图参数」Tab 的 PlotSettingsPanel 显示当前预设名（worker 用）
        2) 「预设设置」Tab 的 PresetFormPanel 字段铺成 entry 的内容；
           系统预设 → 只读；用户预设 → 可编辑

        按 PROGRESS.md T-4 交互规则，单击预设后自动切到「预设设置」Tab，
        让用户能立即看到 / 改动当前预设字段，而不是停在绘图参数页里"看不见"。
        """
        log.info("已选预设：%s", name)
        self.settings_pane.set_preset_name(name)

        # 拉整张 PresetEntry，推到「预设设置」Tab；
        # 选不到（理论上不会，refresh 后 list 必有值）按 entry=None 处理（清空）
        entry = self.preset_pane.selected_preset_entry()
        form = self.center_pane.form_panel
        form.set_entry(entry)
        if entry is not None:
            form.set_read_only(entry.source is PresetSource.SYSTEM)

        # 切到「预设设置」Tab —— 让用户立即看到选中的预设字段
        self.center_pane.show_form_tab()

    def _on_new_preset_requested(self) -> None:
        """用户在左栏点了「+新建」。

        清空表单 + 切到「预设设置」Tab；写盘要等用户点「保存为我的预设」。
        """
        log.info("新建预设：清空表单 + 切到「预设设置」Tab")
        # 绘图参数 Tab 的"当前预设"显示也清掉，避免用户看到旧名字
        self.settings_pane.set_preset_name("")
        form = self.center_pane.form_panel
        form.set_entry(None)  # 清空所有字段
        form.set_read_only(False)  # 新建的预设永远是用户预设，可编辑
        self.center_pane.show_form_tab()

    # ── 表单按钮 → 写入流程 ─────────────────────────────────────
    def _on_form_copy_clicked(self) -> None:
        """系统预设态点 [复制为我的预设] —— 直接复用左栏的复制流程，

        用户当前选中的就是这条系统预设，preset_pane._on_copy_clicked 会
        弹同样的输名对话框 + 走 copy_system_to_user。这里不重复实现。
        """
        log.info("从表单底部触发复制流程")
        self.preset_pane._on_copy_clicked()

    def _on_form_reset_clicked(self) -> None:
        """[重置] —— 把表单字段恢复到加载时的原值。

        没让 form 自己处理是为了让"重置"语义集中在 view 层，
        以后如果要加二次确认（"未保存的修改将丢失"）就只改这里。
        """
        log.info("用户点了 [重置]")
        self.center_pane.form_panel.reset_to_baseline()

    def _on_form_cancel_new_clicked(self) -> None:
        """新建态点 [取消] —— refresh 选回首项，让 form 自动反映成"系统预设态"。"""
        log.info("用户取消新建")
        self.preset_pane.refresh()  # 默认选第一项 → 触发 _on_preset_selected

    def _on_form_save_clicked(self) -> None:
        """[保存修改] / [保存为我的预设] —— 校验 → 写盘 → refresh + InfoBar。"""
        form = self.center_pane.form_panel
        name = form.current_name()
        data = form.current_data()

        # 1) 字段校验
        issues = self._validate_preset_form(name, data, form.current_curves_text())
        if issues:
            log.warning("保存被拒：%d 项校验未通过", len(issues))
            show_warning_infobar(
                self,
                title="保存被拒：字段校验未通过",
                reason=f"共 {len(issues)} 项问题需要先解决：",
                hint="\n".join(f"• {x}" for x in issues),
                duration=8000,
            )
            return

        # 2) 落盘（preset_manager 的 save 是 upsert：同名覆盖）
        try:
            save_user_preset(name, data, tool="plot_curves")
        except PresetError as e:
            log.error("保存写盘失败：%s", e)
            show_error_infobar(self, e, where="保存预设")
            return

        log.info("已保存用户预设：%s", name)
        show_success_infobar(
            self,
            title="已保存到我的预设",
            content=f"{name}（共 {len(data.get('curves', []))} 条曲线）",
        )

        # 3) 刷新左栏并选中刚保存的条目，让 form 进入"用户预设态"（含重置按钮）
        self.preset_pane.refresh(select_name=name)

    @staticmethod
    def _validate_preset_form(
        name: str,
        data: dict,
        curves_text: str,
    ) -> list[str]:
        """轻量字段校验。返回所有问题点的人类可读列表，空 = 通过。

        本轮只做"最低门槛"校验：每个字段非空 + range 单调 + curves 是合法 list。
        不做深度校验（curves[i].points / Excel 列名一致性等），避免误伤用户的
        "在线编辑中"状态。深度校验由实际跑出图时再暴露。
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
                        issues.append(
                            f"{axis_label}范围 min ({r[0]}) 必须小于 max ({r[1]})"
                        )
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
                    issues.append(
                        f"曲线 JSON 解析失败：{item['_parse_error']}"
                    )
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
                    "「预设」在左栏列表里选。"
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
        # 预览区清空，让用户看到"开始新一轮"的视觉反馈
        self.preview_pane.clear()

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

        # 预览区接收成功生成的图（result.written）
        # 即使部分失败也展示成功的那些，让用户能立刻看到结果
        self.preview_pane.set_results(result.written)

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
