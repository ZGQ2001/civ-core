"""绘曲线图工具的"预设列表"面板（左栏）。

职责：
  • 通过 `infra_io.preset_manager.load_merged_presets("plot_curves")` 拿到合并后的列表
    （系统预设 + 用户预设；同名用户覆盖；异名用户追加）
  • 每条列表项前缀图标显示来源：🔒 系统预设（只读） / ✏️ 我的预设（可编辑）
  • 用户点击某条 → 发 `preset_selected(str)` 信号，参数是预设名
  • 顶部小刷新按钮：用户在外部编辑器改完 JSON 不必重启程序
  • 底部按钮组（T-4）：[+新建] [复制为我的预设] [删除]
      - 复制 / 删除直接调 preset_manager 的写入 API，再 refresh
      - 新建只发信号 `new_preset_requested()`，让 view 切到「预设设置」Tab 等用户填

错误处理：
  • 系统预设缺失 / JSON 语法错：捕 PresetError，UI 上显示一行红字提示
  • 用户预设侧的问题：preset_manager 内部已兜底（log warning + 当空处理），
    UI 这里不会感知到，最多看到"我的预设没显示出来"
  • 合并后列表为空：列表禁用，提示去创建预设
  • 写入失败（FileBusyError / 同名冲突等）：捕 PresetError → InfoBar 红字提示，
    不影响列表本身的状态
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    LineEdit,
    ListWidget,
    MessageBox,
    MessageBoxBase,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    TransparentToolButton,
)

from civ_core.infra_io.preset_manager import (
    PresetEntry,
    PresetError,
    PresetSource,
    copy_system_to_user,
    delete_user_preset,
    load_merged_presets,
)
from civ_core.ui.components.error_infobar import (
    show_error_infobar,
    show_success_infobar,
)
from civ_core.utils.logger import get_logger

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


class _NameInputDialog(MessageBoxBase):
    """输入名字的小对话框。复制为我的预设时弹这个。

    用 MessageBoxBase 而不是 QInputDialog，是为了视觉风格与 qfluentwidgets
    的其他对话框一致（Mica 背景 + 圆角按钮）。
    """

    def __init__(
        self,
        title: str,
        default_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.titleLabel = SubtitleLabel(title, self)
        self.viewLayout.addWidget(self.titleLabel)

        self.nameEdit = LineEdit(self)
        self.nameEdit.setPlaceholderText("输入预设名（必填）")
        self.nameEdit.setText(default_name)
        # 自动选中默认文本，方便用户直接打字覆盖
        self.nameEdit.selectAll()
        self.viewLayout.addWidget(self.nameEdit)

        # qfluentwidgets 默认按钮叫 OK / Cancel，本地化一下
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")

        # 把焦点显式给到输入框，回车直接提交
        self.nameEdit.setFocus()

        # 让宽度适合输入预设名（默认 MessageBoxBase 偏窄）
        self.widget.setMinimumWidth(360)

    def name(self) -> str:
        return self.nameEdit.text().strip()


class PresetListPane(QWidget):
    """预设列表面板。

    Signals:
      preset_selected(str) —— 用户切到某条预设时发出，参数是**预设名**（不带图标前缀）。
                              若需要 source / data，调 selected_preset_entry() 取整张 PresetEntry。
      new_preset_requested() —— 用户点了「+新建」按钮。view 接到后切到「预设设置」Tab、
                                清空表单、解锁只读。本组件不做任何写入，留给 view 在
                                用户保存时统一处理。
    """

    preset_selected = Signal(str)
    new_preset_requested = Signal()

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

        # ── 底部：操作按钮组 [+新建] [复制] [删除] ──
        # 三按钮一行；窄栏宽度有限，按钮文字尽量短
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setContentsMargins(0, 6, 0, 0)

        self._new_btn = PrimaryPushButton("+新建", self)
        self._new_btn.setToolTip("新建一条空白预设（在「预设设置」里填好后保存到我的预设）")
        self._new_btn.clicked.connect(self._on_new_clicked)
        btn_row.addWidget(self._new_btn)

        self._copy_btn = PushButton("复制", self)
        self._copy_btn.setToolTip(
            "把当前选中的预设复制为「我的预设」（系统预设不能直接改，要改先复制）"
        )
        self._copy_btn.clicked.connect(self._on_copy_clicked)
        btn_row.addWidget(self._copy_btn)

        self._delete_btn = PushButton("删除", self)
        self._delete_btn.setToolTip("从我的预设里删除当前选中条目（系统预设不可删）")
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        btn_row.addWidget(self._delete_btn)

        outer.addLayout(btn_row)
        # 初始按钮态：未选中 → 复制/删除都禁用
        self._update_action_buttons(entry=None)

    # ── 公共 API ──────────────────────────────────────────────────
    def refresh(self, *, select_name: str | None = None) -> None:
        """重新加载并刷新列表。

        Args:
          select_name:
            刷新后要选中哪条预设。
            None  → 默认选第一个（用于初次加载）
            ""    → 不选任何条目（按钮组全禁，配合"+新建"工作流）
            其它  → 选中该名字对应的条目；找不到则回退默认行为
        """
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
        target_row: int | None = None  # select_name 命中的行号
        for row, entry in enumerate(entries):
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

            if select_name and entry.name == select_name:
                target_row = row

        self._status_label.setText(
            f"共 {len(entries)} 个预设（🔒 系统 {sys_count} ・ ✏️ 我的 {user_count}）"
        )
        log.info(
            "预设列表已刷新：合计 %d（系统 %d / 用户 %d）",
            len(entries),
            sys_count,
            user_count,
        )

        # 选中策略：
        #   select_name == ""        → 不选任何项（"+新建"工作流会单独处理表单）
        #   select_name is None      → 默认第一个
        #   select_name 命中具体行   → 选该行
        #   select_name 给了但没命中 → 回退到第一个（可能用户在其它进程改了文件）
        if select_name == "":
            self._list.setCurrentRow(-1)  # 清空选中
            self._update_action_buttons(entry=None)
        elif target_row is not None:
            self._list.setCurrentRow(target_row)
        else:
            if select_name:
                log.warning("refresh: 没找到要选中的预设 %r，回退到第一个", select_name)
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
            # 当前没有选中（refresh(select_name="") 或刷成空 list 走到）
            self._update_action_buttons(entry=None)
            return
        # 注意：item.text() 是带图标前缀的显示文本，不是真预设名；
        # 必须从 PresetEntry 拿 name，避免把 "🔒 锚杆荷载-位移曲线" 当成名字传出去。
        entry = current.data(_ROLE_PRESET_ENTRY)
        if not isinstance(entry, PresetEntry):
            log.warning("列表项缺 PresetEntry data，跳过 selected 信号")
            self._update_action_buttons(entry=None)
            return
        log.debug("preset selected: %s (source=%s)", entry.name, entry.source.value)
        self._update_action_buttons(entry=entry)
        self.preset_selected.emit(entry.name)

    # ── 按钮态联动 ──────────────────────────────────────────────
    def _update_action_buttons(self, entry: PresetEntry | None) -> None:
        """按当前选中项更新 [+新建] / [复制] / [删除] 三按钮的可用性。

        规则（与 PROGRESS.md T-4 交互一致）：
          | 当前选中 | +新建 | 复制 | 删除 |
          |----------|-------|------|------|
          | 无       | ✓    | ✗    | ✗    |
          | 系统     | ✓    | ✓    | ✗    |
          | 用户     | ✓    | ✓    | ✓    |
        """
        # +新建 任何时候都可点
        self._new_btn.setEnabled(True)

        # 复制：必须有选中项才能复制；系统 / 用户都允许（用户预设也能"再分一份")
        has_selection = entry is not None
        self._copy_btn.setEnabled(has_selection)

        # 删除：仅对用户预设启用
        is_user = entry is not None and entry.source is PresetSource.USER
        self._delete_btn.setEnabled(is_user)

    # ── 按钮 handler ──────────────────────────────────────────────
    def _on_new_clicked(self) -> None:
        """+新建：发信号给 view，由 view 切到「预设设置」Tab + 清空表单。

        本组件**不写盘**——空白预设的 name 还得用户在表单里填，等用户点"保存修改"
        时才落到 user JSON。所以这里只做信号通知，不调 preset_manager。

        刷新前先取消列表选中（refresh(select_name="")），避免视觉上有"高亮一条
        系统预设但右边表单是空的"这种自相矛盾的状态。
        """
        log.info("用户点了 [+新建]")
        self.refresh(select_name="")  # 取消选中
        self.new_preset_requested.emit()

    def _on_copy_clicked(self) -> None:
        """复制：弹对话框输入新名 → 调 copy_system_to_user → refresh + 选中新项。"""
        entry = self.selected_preset_entry()
        if entry is None:
            log.warning("点了复制但没有选中项，忽略")
            return

        default_name = f"{entry.name} (副本)"
        dlg = _NameInputDialog("复制为我的预设", default_name=default_name, parent=self)
        if not dlg.exec():
            return  # 用户取消

        new_name = dlg.name()
        if not new_name:
            show_error_infobar(
                self,
                PresetError("预设名不能为空", hint="请输入新预设的名字"),
                where="复制预设",
            )
            return

        try:
            copy_system_to_user(entry.name, new_name)
        except PresetError as e:
            log.warning("复制失败：%s", e)
            show_error_infobar(self, e, where="复制预设")
            return

        log.info("已复制 %r → %r", entry.name, new_name)
        show_success_infobar(
            self,
            title="已复制为我的预设",
            content=f"{entry.name} → {new_name}（可在「预设设置」中编辑）",
        )
        # 刷新并选中新条目，让中栏 form 立刻显示新副本
        self.refresh(select_name=new_name)

    def _on_delete_clicked(self) -> None:
        """删除：弹确认 → 调 delete_user_preset → refresh（选首项）。

        删除前必再做一次 source 校验：极端时序下按钮态可能滞后于选中变化，
        防御性地拦一下"用户点删除时实际选的是系统预设"。
        """
        entry = self.selected_preset_entry()
        if entry is None:
            log.warning("点了删除但没有选中项，忽略")
            return
        if entry.source is not PresetSource.USER:
            log.warning("拒绝删除系统预设：%r", entry.name)
            show_error_infobar(
                self,
                PresetError(
                    f"系统预设不可删除：{entry.name}",
                    hint="如需修改，请先「复制为我的预设」再编辑/删除副本。",
                ),
                where="删除预设",
            )
            return

        # 确认对话框
        confirm = MessageBox(
            "确认删除？",
            f"将永久删除「我的预设」中的 {entry.name!r}。\n该操作不可恢复。",
            self,
        )
        confirm.yesButton.setText("删除")
        confirm.cancelButton.setText("取消")
        if not confirm.exec():
            return

        try:
            delete_user_preset(entry.name)
        except PresetError as e:
            log.warning("删除失败：%s", e)
            show_error_infobar(self, e, where="删除预设")
            return

        log.info("已删除用户预设：%r", entry.name)
        show_success_infobar(
            self,
            title="已删除",
            content=f"{entry.name} 已从我的预设中移除",
        )
        self.refresh()  # 默认选第一个
