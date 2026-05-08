"""绘曲线图工具的"设置面板"（中栏）。

按 v2.3 总纲第二阶段步骤 11：
  • SettingCardGroup 嵌入 ScrollArea
  • 卡片值与 PlotRunSettings dataclass 双向绑定
  • 仅做"装数据 + 表单"，"生成"按钮 / 异步执行 / InfoBar 异常 留给 step 12-13

四张卡：
  ① 输入 Excel       PushSettingCard ── 弹 QFileDialog 选 .xlsx
  ② 工作表           ComboCard       ── 输入 Excel 选好后从 sheet 列表填充
  ③ 输出目录         PushSettingCard ── 弹 QFileDialog 选目录
  ④ 表头行号         SpinCard        ── 默认 1，范围 [1, 99]

双向绑：
  • UI → dataclass：每张卡的内置信号（pathChanged / valueChanged 等）改 self._settings
  • dataclass → UI：set_settings(rs) 反向把 dataclass 推到卡上（block signals 防回环）
  • 任何方向变化都会 emit settings_changed()，调用方拿 .settings 读最新状态
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    PushSettingCard,
    ScrollArea,
    SettingCard,
    SettingCardGroup,
    SpinBox,
)

from civ_core.configs.loader import AppConfig
from civ_core.domain.schema import PlotRunSettings
from civ_core.infra_io.excel_reader import ExcelReadError, read_sheet_names
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# 自定义 SettingCard 变体（qfluentwidgets 内置没有 Combo / Spin 卡）
# ──────────────────────────────────────────────────────────────────
class _ComboCard(SettingCard):
    """在 SettingCard 右侧塞一个 ComboBox。值变更通过 value_changed 上抛。

    items 是动态的 —— 比如 sheet 名要等输入 Excel 选好后才知道，
    set_items() 会清空再填，并尽量保留当前选中项（如果新列表里有）。
    """

    value_changed = Signal(str)

    def __init__(
        self,
        icon: FluentIcon,
        title: str,
        content: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(icon, title, content, parent)
        self.combo = ComboBox(self)
        self.combo.setMinimumWidth(180)
        self.combo.setEnabled(False)  # 默认禁用，set_items 后启用
        self.combo.currentTextChanged.connect(self.value_changed)
        # 在末尾的 stretch(1) 之后追加：自动靠右
        self.hBoxLayout.addWidget(self.combo, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def set_items(self, items: list[str], current: str | None = None) -> None:
        """重新填充候选项；尽量保留 current（如果它在新列表里）。"""
        self.combo.blockSignals(True)
        try:
            self.combo.clear()
            self.combo.addItems(items)
            if current and current in items:
                self.combo.setCurrentText(current)
            self.combo.setEnabled(bool(items))
        finally:
            self.combo.blockSignals(False)
        # 切完候选项后主动 emit 一次当前值，让外部能感知"已重置"
        self.value_changed.emit(self.combo.currentText())

    def current(self) -> str:
        return self.combo.currentText()


class _SpinCard(SettingCard):
    """在 SettingCard 右侧塞一个 SpinBox。"""

    value_changed = Signal(int)

    def __init__(
        self,
        icon: FluentIcon,
        title: str,
        content: str = "",
        min_v: int = 1,
        max_v: int = 99,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(icon, title, content, parent)
        self.spin = SpinBox(self)
        self.spin.setRange(min_v, max_v)
        self.spin.setMinimumWidth(120)
        self.spin.valueChanged.connect(self.value_changed)
        self.hBoxLayout.addWidget(self.spin, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def set_value(self, v: int) -> None:
        self.spin.blockSignals(True)
        try:
            self.spin.setValue(v)
        finally:
            self.spin.blockSignals(False)

    def value(self) -> int:
        return self.spin.value()


# ──────────────────────────────────────────────────────────────────
# 主面板
# ──────────────────────────────────────────────────────────────────
class PlotSettingsPanel(ScrollArea):
    """绘曲线图设置面板。

    Signals:
      settings_changed() —— 任意一张卡发生变化都会 emit；订阅方拿 .settings 读取
                            （不在信号里携带值，避免序列化痛苦 + 鼓励"按需 pull"）

    Public API:
      .settings          property，返回当前 PlotRunSettings 浅拷贝（防外部误改）
      .set_settings(rs)  把外部 dataclass 推进面板，UI 反映之
      .set_preset_name(name)  专用入口：左栏 PresetListPane 切预设时调
    """

    settings_changed = Signal()

    def __init__(self, cfg: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("plotSettingsPane")
        self._cfg = cfg
        # 默认 output_dir 用 cfg.paths.data_output —— 用户没主动选时有个合理落脚点
        self._settings = PlotRunSettings(output_dir=cfg.paths.data_output)

        self._build_ui()
        self._wire_card_signals()
        self._reflect_settings_to_ui()  # 把默认值推到卡上
        log.debug("PlotSettingsPanel ready (default output_dir=%s)", cfg.paths.data_output)

    # ── 构造 ──────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # ScrollArea 自身的样式：透明 viewport，避免双层背景叠出灰色边
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        # 内容容器
        content = QWidget(self)
        content.setObjectName("plotSettingsContent")
        content.setStyleSheet("QWidget#plotSettingsContent { background: transparent; }")
        self.setWidget(content)

        outer = QVBoxLayout(content)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        # SettingCardGroup —— 一组相关设置项的容器
        group = SettingCardGroup("批量绘图参数", content)

        self.input_card = PushSettingCard(
            "选择文件…",
            FluentIcon.DOCUMENT,
            "输入 Excel",
            "尚未选择",
            content,
        )
        group.addSettingCard(self.input_card)

        self.sheet_card = _ComboCard(
            FluentIcon.LAYOUT,
            "工作表",
            "选好 Excel 后会自动列出可用 sheet",
            content,
        )
        group.addSettingCard(self.sheet_card)

        self.output_card = PushSettingCard(
            "选择目录…",
            FluentIcon.FOLDER,
            "输出目录",
            str(self._cfg.paths.data_output),  # 默认值显示
            content,
        )
        group.addSettingCard(self.output_card)

        self.header_card = _SpinCard(
            FluentIcon.MENU,
            "表头行号",
            "Excel 第几行是表头（1-based，默认 1）",
            min_v=1,
            max_v=99,
            parent=content,
        )
        group.addSettingCard(self.header_card)

        outer.addWidget(group)

        # 当前预设名展示（只读 —— 由左栏 PresetListPane 推过来）
        # 单独一张卡而不是塞进上面的 group：视觉上区分"用户调的参数" vs "外部推来的状态"
        self._preset_label = SettingCard(
            FluentIcon.PALETTE,
            "当前预设",
            "（从左栏选择）",
            content,
        )
        outer.addWidget(self._preset_label)

        outer.addStretch(1)  # 卡片不要被拉伸；底部留空

    def _wire_card_signals(self) -> None:
        self.input_card.clicked.connect(self._pick_input_file)
        self.output_card.clicked.connect(self._pick_output_dir)
        self.sheet_card.value_changed.connect(self._on_sheet_changed)
        self.header_card.value_changed.connect(self._on_header_changed)

    # ── 公共 API ──────────────────────────────────────────────────
    @property
    def settings(self) -> PlotRunSettings:
        """返回当前设置的浅拷贝（防外部 mutate 走漏 settings_changed 信号）。"""
        s = self._settings
        return PlotRunSettings(
            input_path=s.input_path,
            sheet_name=s.sheet_name,
            preset_name=s.preset_name,
            output_dir=s.output_dir,
            header_row=s.header_row,
        )

    def set_settings(self, rs: PlotRunSettings) -> None:
        """把外部 dataclass 推进面板，UI 反映之。整段过程 block 信号，防回环。"""
        self._settings = PlotRunSettings(
            input_path=rs.input_path,
            sheet_name=rs.sheet_name,
            preset_name=rs.preset_name,
            output_dir=rs.output_dir,
            header_row=rs.header_row,
        )
        self._reflect_settings_to_ui()
        self.settings_changed.emit()

    def set_preset_name(self, name: str | None) -> None:
        """左栏 PresetListPane 切预设时调这个入口。

        name=None 或空字符串 → 清空"当前预设"显示（"+新建"工作流走到这里：
        预设还没起名字 / 还没保存）。
        """
        self._settings.preset_name = name or None
        # 显示文本：空时回退到"（从左栏选择）"占位提示，与 _build_ui 的初始内容一致
        self._preset_label.setContent(name or "（从左栏选择）")
        self.settings_changed.emit()

    # ── 内部：UI <- dataclass ────────────────────────────────────
    def _reflect_settings_to_ui(self) -> None:
        """把 self._settings 全字段写回 UI（block 信号，避免触发反向回调）。"""
        s = self._settings

        self.input_card.setContent(str(s.input_path) if s.input_path else "尚未选择")
        self.output_card.setContent(
            str(s.output_dir) if s.output_dir else "尚未选择"
        )
        self.header_card.set_value(s.header_row)
        # preset_name 由 set_preset_name 单独管，这里不动
        if s.preset_name:
            self._preset_label.setContent(s.preset_name)

    # ── 内部：dataclass <- UI（信号槽）──────────────────────────
    def _pick_input_file(self) -> None:
        # 默认初始目录：上次选过的文件目录 / cfg.paths.data_raw / cwd
        if self._settings.input_path is not None:
            start = str(self._settings.input_path.parent)
        else:
            start = str(self._cfg.paths.data_raw)

        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "选择数据 Excel",
            start,
            "Excel 文件 (*.xlsx *.xlsm);;所有文件 (*)",
        )
        if not path_str:
            return

        path = Path(path_str)
        self._settings.input_path = path
        self.input_card.setContent(str(path))

        # 顺手把 sheets 拉出来填到工作表卡里
        try:
            sheets = read_sheet_names(path)
        except ExcelReadError as e:
            log.warning("读取 sheet 名失败：%s", e)
            sheets = []

        # set_items 会 emit value_changed，从而走 _on_sheet_changed 更新 sheet_name
        self.sheet_card.set_items(sheets, current=sheets[0] if sheets else None)
        log.info("已选输入 Excel：%s（sheets=%s）", path.name, sheets)
        self.settings_changed.emit()

    def _pick_output_dir(self) -> None:
        if self._settings.output_dir is not None:
            start = str(self._settings.output_dir)
        else:
            start = str(self._cfg.paths.data_output)

        dir_str = QFileDialog.getExistingDirectory(self, "选择输出目录", start)
        if not dir_str:
            return

        d = Path(dir_str)
        self._settings.output_dir = d
        self.output_card.setContent(str(d))
        log.info("已选输出目录：%s", d)
        self.settings_changed.emit()

    def _on_sheet_changed(self, name: str) -> None:
        # 空字符串 = "暂无 sheets"；不写回 dataclass
        self._settings.sheet_name = name or None
        self.settings_changed.emit()

    def _on_header_changed(self, v: int) -> None:
        self._settings.header_row = v
        self.settings_changed.emit()
