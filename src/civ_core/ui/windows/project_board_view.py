"""ProjectBoardView：项目管理看板主页。

布局：顶栏 + 主视图（列表/看板可切换）+ 右侧滑出抽屉。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPropertyAnimation, QSettings, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import LineEdit, MessageBoxBase, SubtitleLabel

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import BUILTIN_STAGE_NAMES, Project, ProjectStage
from civ_core.ui.components.project_board_widget import ProjectBoardWidget
from civ_core.ui.components.project_drawer import ProjectDrawer
from civ_core.ui.components.project_table_delegate import ProjectTableDelegate
from civ_core.ui.models.project_filter_sort_proxy import (
    FILTER_ACTIVE,
    FILTER_ALL,
    FILTER_ARCHIVED,
    FILTER_ON_HOLD,
    ProjectFilterSortProxy,
)
from civ_core.ui.models.project_table_model import ProjectTableModel
from civ_core.ui.style_helper import (
    qss_primary_button,
    qss_segmented_button,
    qss_table,
    qss_title_label,
    qss_view_toggle_button,
)


class NewProjectDialog(MessageBoxBase):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("新建检测项目", self)

        self.idLineEdit = LineEdit(self)
        self.idLineEdit.setPlaceholderText("如: P202605...")
        self.idLineEdit.setClearButtonEnabled(True)
        self.idLineEdit.textChanged.connect(lambda: self._clear_error(self.idLineEdit))

        self.nameLineEdit = LineEdit(self)
        self.nameLineEdit.setPlaceholderText("如: 某某道路桥梁检测")
        self.nameLineEdit.setClearButtonEnabled(True)
        self.nameLineEdit.textChanged.connect(lambda: self._clear_error(self.nameLineEdit))

        self.clientLineEdit = LineEdit(self)
        self.clientLineEdit.setPlaceholderText("委托单位")
        self.clientLineEdit.setClearButtonEnabled(True)

        self.typeLineEdit = LineEdit(self)
        self.typeLineEdit.setPlaceholderText("如: 施工质量评价")
        self.typeLineEdit.setClearButtonEnabled(True)

        self.amountLineEdit = LineEdit(self)
        self.amountLineEdit.setPlaceholderText("0")
        self.amountLineEdit.setClearButtonEnabled(True)

        self._folder_edit = QLineEdit(self)
        self._folder_edit.setPlaceholderText("自动生成（或点击浏览选择）")
        self._folder_edit.setReadOnly(True)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder_edit)
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(btn_browse)

        self.viewLayout.addWidget(self.titleLabel)

        self.formLayout = QFormLayout()
        self.formLayout.setVerticalSpacing(12)
        self.formLayout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.formLayout.addRow("项目编号 *:", self.idLineEdit)
        self.formLayout.addRow("项目名称 *:", self.nameLineEdit)
        self.formLayout.addRow("委托方:", self.clientLineEdit)
        self.formLayout.addRow("检测类型:", self.typeLineEdit)
        self.formLayout.addRow("项目金额:", self.amountLineEdit)
        self.formLayout.addRow("保存位置:", folder_row)

        self.viewLayout.addLayout(self.formLayout)
        self.widget.setMinimumWidth(400)

        # 自动路径推导：编号或名称变化 → 更新文件夹预览
        self.idLineEdit.textChanged.connect(self._update_auto_path)
        self.nameLineEdit.textChanged.connect(self._update_auto_path)
        self._manual_folder = False  # 用户手工选了路径则挂起自动推导

        # 拦截确定按钮
        try:
            self.yesButton.clicked.disconnect()
        except Exception:
            pass
        self.yesButton.clicked.connect(self._validate_and_accept)

    def _browse_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择项目文件夹")
        if d:
            self._folder_edit.setText(d)
            self._manual_folder = True

    def _update_auto_path(self) -> None:
        if self._manual_folder:
            return
        from datetime import date

        from PySide6.QtCore import QSettings
        settings = QSettings("ZGQ", "CivCore")
        base = settings.value("projects/default_root_dir") or str(Path.home() / "CivProjects")
        num = self.idLineEdit.text().strip()
        name = self.nameLineEdit.text().strip()
        if num or name:
            today = date.today().strftime("%Y%m%d")
            parts = [today]
            if num:
                parts.append(num)
            if name:
                parts.append(name)
            auto = str(Path(base) / "_".join(parts))
            self._folder_edit.setText(auto)

    def _validate_and_accept(self) -> None:
        valid = True
        if not self.nameLineEdit.text().strip():
            self._trigger_error(self.nameLineEdit)
            valid = False
        if not self.idLineEdit.text().strip():
            self._trigger_error(self.idLineEdit)
            valid = False
        if valid:
            self.accept()

    def _trigger_error(self, widget: QLineEdit) -> None:
        widget.setStyleSheet(
            "QLineEdit { border: 1px solid #E53935; background: #FFF5F5; "
            "border-radius: 3px; padding: 3px 6px; }"
        )
        widget.setFocus()
        anim = QPropertyAnimation(widget, b"pos", widget)
        anim.setDuration(400)
        base = widget.pos()
        anim.setKeyValueAt(0.0, base)
        anim.setKeyValueAt(0.1, base + QPoint(6, 0))
        anim.setKeyValueAt(0.2, base + QPoint(-6, 0))
        anim.setKeyValueAt(0.3, base + QPoint(5, 0))
        anim.setKeyValueAt(0.4, base + QPoint(-5, 0))
        anim.setKeyValueAt(0.5, base + QPoint(3, 0))
        anim.setKeyValueAt(0.6, base + QPoint(-3, 0))
        anim.setKeyValueAt(0.7, base + QPoint(1, 0))
        anim.setKeyValueAt(0.8, base + QPoint(-1, 0))
        anim.setKeyValueAt(1.0, base)
        setattr(widget, "_shake_anim", anim)
        anim.start()

    def _clear_error(self, widget: QLineEdit) -> None:
        widget.setStyleSheet("")

    def get_project(self) -> Project:
        stages = tuple(ProjectStage(name=n) for n in BUILTIN_STAGE_NAMES)
        folder_str = self._folder_edit.text().strip()
        amount = 0.0
        if self.amountLineEdit.text().strip():
            try:
                amount = float(self.amountLineEdit.text().strip())
            except ValueError:
                pass
        return Project(
            project_number=self.idLineEdit.text().strip(),
            name=self.nameLineEdit.text().strip(),
            client=self.clientLineEdit.text().strip(),
            inspection_type=self.typeLineEdit.text().strip(),
            amount=amount,
            folder_path=Path(folder_str) if folder_str else None,
            stages=stages,
        )

class ProjectBoardView(QWidget):
    """项目管理看板主页。

    用法：
        view = ProjectBoardView(service)
        layout.addWidget(view)
    """

    def __init__(self, service: ProjectService, parent=None):
        super().__init__(parent)
        self._service = service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 0, 0)
        layout.setSpacing(8)

        # ── 顶栏 ────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top.setSpacing(8)

        title = QLabel("项目看板")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title.setStyleSheet(qss_title_label())
        top.addWidget(title)

        top.addSpacing(16)

        # 筛选：4 档（全部 / 正在进行 / 暂存 / 已归档），通过 Proxy 生效
        self._btn_all = QPushButton(FILTER_ALL)
        self._btn_active = QPushButton(FILTER_ACTIVE)
        self._btn_on_hold = QPushButton(FILTER_ON_HOLD)
        self._btn_archived = QPushButton(FILTER_ARCHIVED)
        self._filter_buttons = {
            FILTER_ALL: self._btn_all,
            FILTER_ACTIVE: self._btn_active,
            FILTER_ON_HOLD: self._btn_on_hold,
            FILTER_ARCHIVED: self._btn_archived,
        }
        for btn in self._filter_buttons.values():
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setStyleSheet(qss_segmented_button())
            top.addWidget(btn)
        self._btn_all.setChecked(True)

        for ftype, btn in self._filter_buttons.items():
            btn.clicked.connect(lambda _checked=False, t=ftype: self._on_filter_changed(t))

        top.addStretch()

        # 视图切换
        self._btn_list = QPushButton("列表")
        self._btn_board = QPushButton("看板")
        for btn in (self._btn_list, self._btn_board):
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setStyleSheet(qss_view_toggle_button())
        self._btn_list.setChecked(True)
        self._btn_list.clicked.connect(self._show_list_view)
        self._btn_board.clicked.connect(self._switch_to_board)

        top.addWidget(self._btn_list)
        top.addWidget(self._btn_board)

        # 新建
        self._btn_new = QPushButton("＋ 新建项目")
        self._btn_new.setFixedHeight(30)
        self._btn_new.setStyleSheet(qss_primary_button())
        self._btn_new.clicked.connect(self._on_new_project)
        top.addWidget(self._btn_new)

        layout.addLayout(top)

        # ── 主体（横向：视图 + Drawer） ─────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # 主视图栈
        self._view_stack = QStackedWidget()

        # 表格视图 —— 套一层 ProjectFilterSortProxy 实现筛选 + 排序
        self._model = ProjectTableModel(self._service)
        self._proxy = ProjectFilterSortProxy(self)
        self._proxy.setSourceModel(self._model)

        self._table_view = QTableView()
        self._table_view.setModel(self._proxy)
        self._table_view.setItemDelegate(ProjectTableDelegate())
        self._table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table_view.setShowGrid(False)
        self._table_view.verticalHeader().setVisible(False)
        self._table_view.horizontalHeader().setStretchLastSection(False)
        self._table_view.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._table_view.setAlternatingRowColors(True)
        # 启用点击表头排序；默认按创建日期倒序
        self._table_view.setSortingEnabled(True)
        self._table_view.sortByColumn(ProjectTableModel.DateCol, Qt.SortOrder.DescendingOrder)
        self._table_view.setStyleSheet(qss_table())

        hdr = self._table_view.horizontalHeader()
        # 状态列固定（图标列，不让用户拖）；名称列 Stretch 占满剩余；其余 Interactive 可拖
        hdr.setSectionResizeMode(ProjectTableModel.StatusCol, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(ProjectTableModel.NumberCol, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(ProjectTableModel.NameCol, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(ProjectTableModel.TypeCol, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(ProjectTableModel.AmountCol, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(ProjectTableModel.DateCol, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(ProjectTableModel.ProgressCol, QHeaderView.ResizeMode.Interactive)
        # 应用初始列宽（用户预设优先；没存过则用默认）
        self._apply_default_column_widths()
        self._restore_column_widths()
        # 列宽变化时持久化（仅 user 主动拖动触发，初始化期间也会触发但写入一致值无害）
        hdr.sectionResized.connect(self._on_section_resized)

        self._table_view.clicked.connect(self._on_table_row_clicked)
        self._view_stack.addWidget(self._table_view)
        # 看板视图
        self._board_widget = ProjectBoardWidget()
        self._board_widget.set_service(self._service)
        self._board_widget.card_clicked = self._on_board_card_clicked
        self._view_stack.addWidget(self._board_widget)

        body.addWidget(self._view_stack, 1)

        # 右侧 Drawer
        self._drawer = ProjectDrawer()
        self._drawer.closed = self._on_drawer_closed
        self._drawer.project_deleted = self._on_project_deleted
        body.addWidget(self._drawer)

        layout.addLayout(body, 1)

    # ════════════════════════════════════════════════════════════
    # 视图切换
    # ════════════════════════════════════════════════════════════
    def _show_list_view(self) -> None:
        self._btn_list.setChecked(True)
        self._btn_board.setChecked(False)
        self._view_stack.setCurrentIndex(0)

    def _switch_to_board(self) -> None:
        self._btn_list.setChecked(False)
        self._btn_board.setChecked(True)
        self._board_widget.refresh()
        self._view_stack.setCurrentIndex(1)

    # ════════════════════════════════════════════════════════════
    # 筛选
    # ════════════════════════════════════════════════════════════
    def _on_filter_changed(self, filter_type: str) -> None:
        """4 档筛选切换：联动按钮态 + 通知 Proxy 立即重过滤。"""
        for ftype, btn in self._filter_buttons.items():
            btn.setChecked(ftype == filter_type)
        self._proxy.set_filter_type(filter_type)

    # ════════════════════════════════════════════════════════════
    # 交互
    # ════════════════════════════════════════════════════════════
    def _on_table_row_clicked(self, index) -> None:
        # index 来自 proxy，需要映射回 source 再取 Project 对象
        source_idx = self._proxy.mapToSource(index)
        proj = self._model.data(
            self._model.index(source_idx.row(), 0),
            Qt.ItemDataRole.UserRole,
        )
        if proj:
            self._drawer.set_project(proj, self._service)
            self._drawer.open()

    def _on_board_card_clicked(self, proj: Project) -> None:
        self._drawer.set_project(proj, self._service)
        self._drawer.open()

    def _on_new_project(self) -> None:
        dlg = NewProjectDialog(self.window())
        if not dlg.exec():
            return
        proj = dlg.get_project()
        if not proj.project_number or not proj.name:
            QMessageBox.warning(self, "创建失败", "项目编号和名称不能为空")
            return
        try:
            self._service.create_project(proj, create_folder=False)
            self._model.refresh()
            if self._view_stack.currentIndex() == 1:
                self._board_widget.refresh()
        except ValueError as e:
            QMessageBox.warning(self, "创建失败", str(e))
    def _on_project_deleted(self, _project_id: int) -> None:
        self._model.refresh()
        if self._view_stack.currentIndex() == 1:
            self._board_widget.refresh()

    def _on_drawer_closed(self) -> None:
        self._model.refresh()
        if self._view_stack.currentIndex() == 1:
            self._board_widget.refresh()

    def refresh(self) -> None:
        self._model.refresh()
        if self._view_stack.currentIndex() == 1:
            self._board_widget.refresh()

    # ════════════════════════════════════════════════════════════
    # 列宽持久化（QSettings("ZGQ", "CivCore") / projects/column_width/<col>）
    # ════════════════════════════════════════════════════════════
    _COLUMN_WIDTH_DEFAULTS = {
        ProjectTableModel.StatusCol: 40,
        ProjectTableModel.NumberCol: 110,
        ProjectTableModel.TypeCol: 100,
        ProjectTableModel.AmountCol: 100,
        ProjectTableModel.DateCol: 110,
        ProjectTableModel.ProgressCol: 80,
    }

    def _apply_default_column_widths(self) -> None:
        for col, w in self._COLUMN_WIDTH_DEFAULTS.items():
            self._table_view.setColumnWidth(col, w)

    def _restore_column_widths(self) -> None:
        """从 QSettings 恢复用户上次拖动的列宽。"""
        settings = QSettings("ZGQ", "CivCore")
        for col in self._COLUMN_WIDTH_DEFAULTS:
            raw = settings.value(f"projects/column_width/{col}")
            if raw is None:
                continue
            try:
                w = int(raw)
            except (TypeError, ValueError):
                continue
            if 20 <= w <= 800:  # 防御越界值
                self._table_view.setColumnWidth(col, w)

    def _on_section_resized(self, col: int, _old: int, new_size: int) -> None:
        """用户拖动列宽 → 写 QSettings。仅持久化我们关心的列。"""
        if col not in self._COLUMN_WIDTH_DEFAULTS:
            return
        if new_size < 20:
            return  # 太窄当作误触不写
        settings = QSettings("ZGQ", "CivCore")
        settings.setValue(f"projects/column_width/{col}", int(new_size))
