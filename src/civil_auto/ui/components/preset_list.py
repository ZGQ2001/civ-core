"""绘曲线图工具的"预设列表"面板（左栏）。

职责：
  • 通过 `infra_io.preset_manager.load_merged_presets("plot_curves")` 拿到合并后的列表
    （系统预设 + 用户预设；同名用户覆盖；异名用户追加）
  • 每条列表项前缀图标显示来源：🔒 系统预设（只读） / ✏️ 我的预设（可编辑）
  • 用户点击某条 → 发 `preset_selected(str)` 信号，参数是预设名
  • 顶部小刷新按钮：用户在外部编辑器改完 JSON 不必重启程序

错误处理：
  • 系统预设缺失 / JSON 语法错：捕 PresetError，UI 上显示一行红字提示
  • 用户预设侧的问题：preset_manager 内部已兜底（log warning + 当空处理），
    UI 这里不会感知到，最多看到"我的预设没显示出来"
  • 合并后列表为空：列表禁用，提示去创建预设

T-3 之后的预期：
  • T-4 会重做这个面板（Pivot 双 Tab + 系统/用户分区显示），
    本步骤只做最小可用的"图标前缀 + 来源 tooltip"，避免双重返工
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    ListWidget,
    StrongBodyLabel,
    TransparentToolButton,
)

from civil_auto.infra_io.preset_manager import (
    PresetEntry,
    PresetError,
    PresetSource,
    load_merged_presets,
)
from civil_auto.utils.logger import get_logger

log = get_logger(__name__)

# Qt.UserRole 上挂的整个 PresetEntry —— 后续步骤可以直接拿 entry.data / entry.source 用，
# 免得再回 preset_manager 查一次。注意 item.text() 是带图标前缀的显示文本，不是真名；
# 所有"取预设名"的地方都从 entry.name 读，不要从 item.text() 截。
_ROLE_PRESET_ENTRY = Qt.ItemDataRole.UserRole

# 列表项前缀图标（与 PROGRESS.md T-4 mockup 保持一致：🔒 系统、✏️ 用户）
_SOURCE_ICON: dict[PresetSource, str] = {
    PresetSource.SYSTEM: "🔒",
    PresetSource.USER: "✏️",
}
_SOURCE_LABEL: dict[PresetSource, str] = {
    PresetSource.SYSTEM: "系统预设（只读）",
    PresetSource.USER: "我的预设",
}


class PresetListPane(QWidget):
    """预设列表面板。

    Signals:
      preset_selected(str) —— 用户切到某条预设时发出，参数是**预设名**（不带图标前缀）。
                              若需要 source / data，调 selected_preset_entry() 取整张 PresetEntry。
    """

    preset_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("presetListPane")

        self._build_layout()
        # 注意：__init__ 不主动调 refresh()。
        # 调用方必须先 connect(preset_selected, ...)，再调 refresh() —— 否则
        # refresh() 内部 setCurrentRow(0) 触发的首次信号会因为还没接收方而丢失。

    # ── 构造 ──────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        # ── 顶部：标题 + 刷新按钮 ──
        header = QHBoxLayout()
        header.setSpacing(6)

        title = StrongBodyLabel("预设列表", self)
        header.addWidget(title)
        header.addStretch(1)

        self._refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self._refresh_btn.setToolTip("重新读取系统预设 + 用户预设并合并")
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)

        outer.addLayout(header)

        # ── 副标题：状态行（显示预设总数 / 错误信息）──
        self._status_label = CaptionLabel("", self)
        self._status_label.setWordWrap(True)
        outer.addWidget(self._status_label)

        # ── 中部：列表 ──
        self._list = ListWidget(self)
        # 单选 + 不让用户拖排序
        self._list.setSelectionMode(self._list.SelectionMode.SingleSelection)
        self._list.currentItemChanged.connect(self._on_current_changed)
        outer.addWidget(self._list, 1)

        # ── 底部：空状态提示（默认隐藏，empty/error 时显示）──
        self._empty_label = BodyLabel("", self)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: #c33;")
        self._empty_label.hide()
        outer.addWidget(self._empty_label)

    # ── 公共 API ──────────────────────────────────────────────────
    def refresh(self) -> None:
        """重新加载并刷新列表。被刷新按钮 / 外部代码调用。"""
        self._list.clear()
        self._empty_label.hide()
        self._list.show()

        try:
            entries = load_merged_presets("plot_curves")
        except PresetError as e:
            # 这里只会因系统预设文件缺失/坏才走到（用户侧 preset_manager 已兜底）
            log.warning("预设库加载失败：%s", e)
            tail = f"\n建议：{e.hint}" if e.hint else ""
            self._show_error(f"⚠️ 加载失败：{e}{tail}")
            return

        if not entries:
            self._show_error(
                "预设库为空。\n请先在 [曲线预设编辑器] 创建预设，或手工编辑 "
                "presets/plot_curves/curve_presets.json。"
            )
            return

        sys_count = 0
        user_count = 0
        for entry in entries:
            icon = _SOURCE_ICON[entry.source]
            item = QListWidgetItem(f"{icon} {entry.name}", self._list)
            item.setData(_ROLE_PRESET_ENTRY, entry)

            # tooltip：来源 + 识别字段，悬停能预判内容
            curves_n = len(entry.data.get("curves", []))
            id_col = entry.data.get("id_column", "?")
            item.setToolTip(
                f"来源：{_SOURCE_LABEL[entry.source]}\n"
                f"标识列：{id_col}\n"
                f"曲线条数：{curves_n}"
            )

            if entry.source is PresetSource.SYSTEM:
                sys_count += 1
            else:
                user_count += 1

        self._status_label.setText(
            f"共 {len(entries)} 个预设（🔒 系统 {sys_count} ・ ✏️ 我的 {user_count}）"
        )
        log.info(
            "预设列表已刷新：合计 %d（系统 %d / 用户 %d）",
            len(entries),
            sys_count,
            user_count,
        )

        # 默认选第一个，让右栏立刻有"已选"状态
        self._list.setCurrentRow(0)

    def selected_preset_name(self) -> str | None:
        """返回当前选中的预设名；没选返回 None。"""
        entry = self.selected_preset_entry()
        return entry.name if entry is not None else None

    def selected_preset_entry(self) -> PresetEntry | None:
        """返回当前选中的整张 PresetEntry（含 name/data/source）；没选返回 None。

        UI 后续要展示来源图标、判断"是否可编辑"时直接拿 entry.source 就够。
        """
        item = self._list.currentItem()
        if item is None:
            return None
        data = item.data(_ROLE_PRESET_ENTRY)
        return data if isinstance(data, PresetEntry) else None

    def selected_preset_dict(self) -> dict[str, Any] | None:
        """返回当前选中预设的内容 dict（不含 source 信息）；没选返回 None。

        保留这个 API 是为了兼容现有调用方；新代码建议直接用 selected_preset_entry()。
        """
        entry = self.selected_preset_entry()
        return entry.data if entry is not None else None

    # ── 内部 ──────────────────────────────────────────────────────
    def _show_error(self, message: str) -> None:
        """把列表收掉，露出红字提示。"""
        self._list.hide()
        self._empty_label.setText(message)
        self._empty_label.show()
        self._status_label.setText("")

    def _on_current_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        # 注意：item.text() 是带图标前缀的显示文本，不是真预设名；
        # 必须从 PresetEntry 拿 name，避免把 "🔒 锚杆荷载-位移曲线" 当成名字传出去。
        entry = current.data(_ROLE_PRESET_ENTRY)
        if not isinstance(entry, PresetEntry):
            log.warning("列表项缺 PresetEntry data，跳过 selected 信号")
            return
        log.debug("preset selected: %s (source=%s)", entry.name, entry.source.value)
        self.preset_selected.emit(entry.name)
