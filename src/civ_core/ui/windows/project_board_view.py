"""ProjectBoardView：项目管理看板主页。

布局：顶栏 + 主视图（列表/看板可切换）+ 右侧滑出抽屉。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListView,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import Project
from civ_core.ui.components.project_board_widget import ProjectBoardWidget
from civ_core.ui.components.project_delegate import ProjectDelegate
from civ_core.ui.components.project_drawer import ProjectDrawer
from civ_core.ui.models.project_list_model import ProjectListModel


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
        header_row.setContentsMargins(14, 0, 0, 0)
        header_row.setSpacing(0)
        header_style = "font-size: 11px; font-weight: bold; color: #757575; padding: 4px 0;"
        for text, width in [("状态", 30), ("编号", 64), ("项目名称", 208), ("类型", 98), ("金额", 88), ("进度", 96)]:
            lbl = QLabel(text)
            lbl.setFixedWidth(width)
            lbl.setStyleSheet(header_style)
            lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            header_row.addWidget(lbl)
        header_row.addStretch()
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
        """简化版新建对话框。"""
        msg = QMessageBox(self)
        msg.setWindowTitle("新建项目")
        msg.setText("输入项目编号：")
        # 简陋实现：用一个 QInputDialog 代替
        from PySide6.QtWidgets import QInputDialog
        number, ok = QInputDialog.getText(
            self, "新建项目", "项目编号（如 P2024001）："
        )
        if not ok or not number.strip():
            return
        name, ok = QInputDialog.getText(self, "新建项目", "项目名称：")
        if not ok or not name.strip():
            return
        client, ok = QInputDialog.getText(self, "新建项目", "委托方：")
        if not ok:
            return
        itype, ok = QInputDialog.getText(self, "新建项目", "检测类型：")
        if not ok:
            return
        amount_str, ok = QInputDialog.getText(self, "新建项目", "项目金额：")
        amount = float(amount_str) if ok and amount_str else 0.0

        from civ_core.domain.project_schema import BUILTIN_STAGE_NAMES, Project, ProjectStage
        stages = tuple(ProjectStage(name=n) for n in BUILTIN_STAGE_NAMES)
        proj = Project(
            project_number=number.strip(),
            name=name.strip(),
            client=client.strip() if client else "",
            inspection_type=itype.strip() if itype else "",
            amount=amount,
            stages=stages,
        )
        try:
            self._service.create_project(proj, create_folder=False)
            self._model.refresh()
            if self._view_stack.currentIndex() == 1:
                self._board_widget.refresh()
        except ValueError as e:
            QMessageBox.warning(self, "创建失败", str(e))

    def _on_drawer_closed(self) -> None:
        """抽屉关闭后刷新视图。"""
        self._model.refresh()
        if self._view_stack.currentIndex() == 1:
            self._board_widget.refresh()

    def refresh(self) -> None:
        self._model.refresh()
        if self._view_stack.currentIndex() == 1:
            self._board_widget.refresh()
