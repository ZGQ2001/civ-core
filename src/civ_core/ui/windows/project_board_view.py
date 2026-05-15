"""ProjectBoardView：项目管理看板主页。

布局：顶栏 + 主视图（列表/看板可切换）+ 右侧滑出抽屉。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPropertyAnimation, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import LineEdit, MessageBoxBase, SubtitleLabel

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import BUILTIN_STAGE_NAMES, Project, ProjectStage
from civ_core.ui.components.project_board_widget import ProjectBoardWidget
from civ_core.ui.components.project_delegate import ProjectDelegate
from civ_core.ui.components.project_drawer import ProjectDrawer
from civ_core.ui.models.project_list_model import COL_WIDTHS, LEFT_PADDING, ProjectListModel


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
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #212121;"
        )
        top.addWidget(title)

        top.addSpacing(16)

        # 筛选: 简单用三个按钮模拟 SegmentedWidget
        self._btn_all = QPushButton("全部")
        self._btn_active = QPushButton("正在进行")
        self._btn_backlog = QPushButton("团队积压")
        for btn in (self._btn_all, self._btn_active, self._btn_backlog):
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setStyleSheet(
                "QPushButton { border: 1px solid #E0E0E0; border-radius: 4px; "
                "padding: 0 12px; font-size: 12px; background: #FFF; }"
                "QPushButton:checked { background: #1976D2; color: white; border-color: #1976D2; }"
            )
            top.addWidget(btn)
        self._btn_all.setChecked(True)

        self._btn_all.clicked.connect(lambda: self._on_filter_changed("全部"))
        self._btn_active.clicked.connect(lambda: self._on_filter_changed("正在进行"))
        self._btn_backlog.clicked.connect(lambda: self._on_filter_changed("团队积压"))

        top.addStretch()

        # 视图切换
        self._btn_list = QPushButton("列表")
        self._btn_board = QPushButton("看板")
        for btn in (self._btn_list, self._btn_board):
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setStyleSheet(
                "QPushButton { border: 1px solid #E0E0E0; border-radius: 4px; "
                "padding: 0 10px; font-size: 12px; background: #FFF; }"
                "QPushButton:checked { background: #424242; color: white; }"
            )
        self._btn_list.setChecked(True)
        self._btn_list.clicked.connect(self._show_list_view)
        self._btn_board.clicked.connect(self._switch_to_board)

        top.addWidget(self._btn_list)
        top.addWidget(self._btn_board)

        # 新建
        self._btn_new = QPushButton("＋ 新建项目")
        self._btn_new.setFixedHeight(30)
        self._btn_new.setStyleSheet(
            "QPushButton { background: #1976D2; color: white; border: none; "
            "border-radius: 4px; padding: 0 16px; font-size: 11px; }"
            "QPushButton:hover { background: #1565C0; }"
        )
        self._btn_new.clicked.connect(self._on_new_project)
        top.addWidget(self._btn_new)

        layout.addLayout(top)

        # ── 主体（横向：视图 + Drawer） ─────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # 主视图栈
        self._view_stack = QStackedWidget()

        # 列表视图
        self._model = ProjectListModel(self._service)

        # 表头
        header_row = QHBoxLayout()
        header_row.setContentsMargins(LEFT_PADDING, 0, 0, 0)
        header_row.setSpacing(0)
        header_style = "font-size: 11px; font-weight: bold; color: #757575; padding: 4px 0;"
        col_map = [
            ("", COL_WIDTHS["status"] + COL_WIDTHS["dot_pad"]),
            ("编号", COL_WIDTHS["number"]),
            ("项目名称", COL_WIDTHS["name"]),
            ("类型", COL_WIDTHS["type"]),
            ("金额", COL_WIDTHS["amount"]),
            ("日期", COL_WIDTHS["date"]),
            ("进度", COL_WIDTHS["progress"]),
        ]
        for text, w in col_map:
            lbl = QLabel(text)
            lbl.setFixedWidth(w)
            lbl.setStyleSheet(header_style)
            lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            header_row.addWidget(lbl)
        header_widget = QWidget()
        header_widget.setLayout(header_row)
        header_widget.setFixedHeight(28)
        header_widget.setStyleSheet("background: #F8F9FA; border-bottom: 1px solid #E8E8E8;")

        self._list_container = QVBoxLayout()
        self._list_container.setContentsMargins(0, 0, 0, 0)
        self._list_container.setSpacing(0)
        self._list_container.addWidget(header_widget)

        self._list_view = QListView()
        self._list_view.setModel(self._model)
        delegate = ProjectDelegate()
        self._list_view.setItemDelegate(delegate)
        self._list_view.setSpacing(0)
        self._list_view.setMinimumHeight(200)
        self._list_view.setStyleSheet(
            "QListView { border: none; background: #FFFFFF; }"
        )
        self._list_view.clicked.connect(self._on_item_clicked)
        self._list_container.addWidget(self._list_view)
        list_page = QWidget()
        list_page.setLayout(self._list_container)
        self._view_stack.addWidget(list_page)

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
        # 更新按钮状态
        self._btn_all.setChecked(filter_type == "全部")
        self._btn_active.setChecked(filter_type == "正在进行")
        self._btn_backlog.setChecked(filter_type == "团队积压")

        projects = self._service.filter_projects(filter_type)
        self._model._projects = projects
        self._model.layoutChanged.emit()

    # ════════════════════════════════════════════════════════════
    # 交互
    # ════════════════════════════════════════════════════════════
    def _on_board_card_clicked(self, proj: Project) -> None:
        self._drawer.set_project(proj, self._service)
        self._drawer.open()

    def _on_item_clicked(self, index) -> None:
        proj = self._model.data(index, ProjectListModel.ProjectObjectRole)
        if proj:
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
