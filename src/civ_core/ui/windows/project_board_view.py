"""ProjectBoardView：项目管理看板主页。

布局：顶栏 + 主视图（列表/看板可切换）+ 右侧滑出抽屉。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPropertyAnimation, QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
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
        # 紧凑垂直间距：12→6，确保整个对话框高度不会遮挡父窗标题栏 / 关闭按钮
        self.formLayout.setVerticalSpacing(6)
        self.formLayout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.formLayout.addRow("项目编号 *:", self.idLineEdit)
        self.formLayout.addRow("项目名称 *:", self.nameLineEdit)
        self.formLayout.addRow("委托方:", self.clientLineEdit)
        self.formLayout.addRow("检测类型:", self.typeLineEdit)
        self.formLayout.addRow("项目金额:", self.amountLineEdit)
        self.formLayout.addRow("保存位置:", folder_row)

        self.viewLayout.addLayout(self.formLayout)
        self.widget.setMinimumWidth(420)
        # 限制最大高度：父窗 80%，避免对话框比父窗还高、把窗口标题栏顶出屏幕
        if parent is not None:
            parent_h = parent.height() if parent.height() > 0 else 720
            self.widget.setMaximumHeight(int(parent_h * 0.8))

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

        # ESC 快捷键关闭（MessageBoxBase 默认不绑 ESC，用户被对话框卡住时的最后退路）
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence("Escape"), self, activated=self.reject)

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
        # 四边都留间距：右边给"+新建项目"按钮透气；上下避免标题贴到 Tab 栏
        layout.setContentsMargins(16, 12, 16, 12)
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
        # 启动时恢复上次筛选档（默认全部）
        _saved_filter = QSettings("ZGQ", "CivCore").value("projects/filter_type", FILTER_ALL)
        if _saved_filter not in self._filter_buttons:
            _saved_filter = FILTER_ALL
        for ftype, btn in self._filter_buttons.items():
            btn.setChecked(ftype == _saved_filter)

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
        self._btn_new.setToolTip("新建检测项目 (Ctrl+N)")
        self._btn_new.clicked.connect(self._on_new_project)
        top.addWidget(self._btn_new)

        # 全局快捷键：Ctrl+N 新建项目（工程软件惯例）
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_project)

        layout.addLayout(top)

        # ── 主体：QSplitter（左视图 / 右抽屉），用户可拖动手柄调整抽屉宽度 ────
        self._body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._body_splitter.setHandleWidth(4)
        self._body_splitter.setChildrenCollapsible(False)

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
        # 启用点击表头排序；从 QSettings 恢复上次排序状态，默认按创建日期倒序
        self._table_view.setSortingEnabled(True)
        self._restore_sort_state()
        self._table_view.setStyleSheet(qss_table())

        hdr = self._table_view.horizontalHeader()
        # 全部 Interactive：拖动任一分隔线只影响该分隔线两侧的列，符合
        # Excel / 资源管理器等工程软件惯例。
        # 注：不再用 Stretch（之前用 Stretch 会让"中间列"吸收所有变化，
        # 导致用户拖动 Type|Amount 时反而看到 NameCol 在收缩，反直觉）。
        hdr.setSectionResizeMode(ProjectTableModel.StatusCol, QHeaderView.ResizeMode.Fixed)
        for col in (
            ProjectTableModel.NumberCol,
            ProjectTableModel.NameCol,
            ProjectTableModel.TypeCol,
            ProjectTableModel.AmountCol,
            ProjectTableModel.DateCol,
            ProjectTableModel.ProgressCol,
        ):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        # 应用初始列宽（用户预设优先；没存过则用默认）
        self._apply_default_column_widths()
        self._restore_column_widths()
        # 列宽变化时持久化（仅 user 主动拖动触发，初始化期间也会触发但写入一致值无害）
        hdr.sectionResized.connect(self._on_section_resized)
        # 表格 viewport 大小变化 → 让 NameCol 自动吸收剩余空间（不用 Stretch 避免拖动反向）
        self._table_view.installEventFilter(self)

        self._table_view.clicked.connect(self._on_table_row_clicked)
        # 右键菜单（工程软件惯例：表格行右键 → 快捷操作）
        self._table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_view.customContextMenuRequested.connect(self._on_table_context_menu)

        # 表格内嵌一个 stack：表格 / 空状态 二选一
        self._table_stack = QStackedWidget()
        self._table_stack.addWidget(self._table_view)
        self._table_stack.addWidget(self._build_empty_state())
        self._view_stack.addWidget(self._table_stack)

        # proxy 行数变化 → 自动切换 table / empty
        self._proxy.modelReset.connect(self._refresh_empty_state)
        self._proxy.rowsInserted.connect(self._refresh_empty_state)
        self._proxy.rowsRemoved.connect(self._refresh_empty_state)
        self._refresh_empty_state()
        # 应用启动时恢复的筛选档（持久化值不等于默认时立即生效）
        if _saved_filter != FILTER_ALL:
            self._proxy.set_filter_type(_saved_filter)

        # 看板视图
        self._board_widget = ProjectBoardWidget()
        self._board_widget.set_service(self._service)
        self._board_widget.card_clicked = self._on_board_card_clicked
        self._view_stack.addWidget(self._board_widget)

        self._body_splitter.addWidget(self._view_stack)

        # 右侧 Drawer（放进 splitter，用户可拖左侧手柄调整宽度）
        self._drawer = ProjectDrawer()
        self._drawer.opened = self._on_drawer_opened
        self._drawer.closed = self._on_drawer_closed
        self._drawer.project_deleted = self._on_project_deleted
        self._body_splitter.addWidget(self._drawer)
        # 关闭态：splitter sizes = [view, 0]；打开态：[view, saved_drawer_w or 400]
        self._body_splitter.setSizes([1, 0])
        self._body_splitter.setStretchFactor(0, 1)
        self._body_splitter.setStretchFactor(1, 0)
        self._body_splitter.splitterMoved.connect(self._on_drawer_resized)

        layout.addWidget(self._body_splitter, 1)

        # ── 底部状态栏：项目数 + DB 路径 ─────────────────────────────
        self._status_label = QLabel()
        self._status_label.setStyleSheet(
            "color: #757575; font-size: 12px; padding: 2px 6px; "
            "border-top: 1px solid #E0E0E0;"
        )
        layout.addWidget(self._status_label)
        self._proxy.modelReset.connect(self._refresh_status_bar)
        self._proxy.rowsInserted.connect(self._refresh_status_bar)
        self._proxy.rowsRemoved.connect(self._refresh_status_bar)
        self._refresh_status_bar()

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
        """4 档筛选切换：联动按钮态 + 通知 Proxy 立即重过滤 + 持久化到 QSettings。"""
        for ftype, btn in self._filter_buttons.items():
            btn.setChecked(ftype == filter_type)
        self._proxy.set_filter_type(filter_type)
        settings = QSettings("ZGQ", "CivCore")
        settings.setValue("projects/filter_type", filter_type)

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

    def _project_at_proxy_index(self, proxy_index) -> Project | None:
        """proxy 索引 → Project 对象。"""
        if not proxy_index.isValid():
            return None
        source_idx = self._proxy.mapToSource(proxy_index)
        return self._model.data(
            self._model.index(source_idx.row(), 0),
            Qt.ItemDataRole.UserRole,
        )

    def _on_table_context_menu(self, pos) -> None:
        """表格右键菜单：打开详情 / 暂存切换 / 归档切换 / 打开文件夹 / 删除。"""
        index = self._table_view.indexAt(pos)
        proj = self._project_at_proxy_index(index)
        if proj is None:
            return

        menu = QMenu(self._table_view)
        act_open = QAction("打开详情", menu)
        act_hold = QAction("取消暂存" if proj.is_on_hold else "暂存", menu)
        act_arch = QAction("取消归档" if proj.is_archived else "归档", menu)
        act_folder = QAction("打开文件夹", menu)
        act_delete = QAction("删除项目…", menu)

        act_open.triggered.connect(lambda: self._open_drawer_for(proj))
        act_hold.triggered.connect(lambda: self._ctx_toggle_on_hold(proj))
        act_arch.triggered.connect(lambda: self._ctx_toggle_archived(proj))
        act_folder.triggered.connect(lambda: self._ctx_open_folder(proj))
        act_delete.triggered.connect(lambda: self._ctx_delete(proj))

        menu.addAction(act_open)
        menu.addSeparator()
        menu.addAction(act_hold)
        menu.addAction(act_arch)
        menu.addSeparator()
        menu.addAction(act_folder)
        menu.addAction(act_delete)
        # 文件夹未绑定时禁用打开
        if proj.folder_path is None:
            act_folder.setEnabled(False)

        menu.exec(self._table_view.viewport().mapToGlobal(pos))

    def _open_drawer_for(self, proj: Project) -> None:
        self._drawer.set_project(proj, self._service)
        self._drawer.open()

    def _ctx_toggle_on_hold(self, proj: Project) -> None:
        try:
            self._service.set_on_hold(proj.project_id, not proj.is_on_hold)
            self._model.refresh()
        except ValueError as e:
            QMessageBox.warning(self, "操作失败", str(e))

    def _ctx_toggle_archived(self, proj: Project) -> None:
        try:
            self._service.set_archived(proj.project_id, not proj.is_archived)
            self._model.refresh()
        except ValueError as e:
            QMessageBox.warning(self, "操作失败", str(e))

    def _ctx_open_folder(self, proj: Project) -> None:
        if proj.folder_path is None:
            return
        from civ_core.infra_io.project_folder import open_project_folder
        try:
            open_project_folder(proj.folder_path)
        except FileNotFoundError:
            QMessageBox.warning(self, "打开失败", f"文件夹不存在：\n{proj.folder_path}")

    def _ctx_delete(self, proj: Project) -> None:
        from civ_core.ui.components.project_drawer import DeleteConfirmDialog
        dlg = DeleteConfirmDialog(proj.project_number, self.window())
        if not dlg.exec():
            return
        self._service.delete_project(proj.project_id)
        self._model.refresh()
        if self._view_stack.currentIndex() == 1:
            self._board_widget.refresh()

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
        except ValueError as e:
            QMessageBox.warning(self, "创建失败", str(e))
            return

        # 默认按对话框选定的 folder_path 物理建文件夹 + 4 个标准子文件夹。
        # 失败不阻断 DB 记录已创建；用户可手动在抽屉里改路径再点"打开文件夹"补建。
        if proj.folder_path is not None:
            try:
                from civ_core.infra_io.project_folder import SUBFOLDER_NAMES
                proj.folder_path.mkdir(parents=True, exist_ok=True)
                for sub in SUBFOLDER_NAMES:
                    (proj.folder_path / sub).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(
                    self, "文件夹创建警告",
                    f"项目已保存到数据库，但本地文件夹创建失败：\n{e}\n\n"
                    f"可以在右侧抽屉里手动修改路径再点「打开文件夹」补建。",
                )

        self._model.refresh()
        if self._view_stack.currentIndex() == 1:
            self._board_widget.refresh()
    def _on_project_deleted(self, _project_id: int) -> None:
        self._model.refresh()
        if self._view_stack.currentIndex() == 1:
            self._board_widget.refresh()

    def _on_drawer_closed(self) -> None:
        # 收起 drawer：splitter 第二格设为 0
        sizes = self._body_splitter.sizes()
        total = sum(sizes) if sum(sizes) > 0 else 1
        self._body_splitter.setSizes([total, 0])
        self._model.refresh()
        if self._view_stack.currentIndex() == 1:
            self._board_widget.refresh()

    _DRAWER_DEFAULT_WIDTH = 400
    _DRAWER_MIN_WIDTH = 280

    def _on_drawer_opened(self) -> None:
        """展开 drawer：从 QSettings 取上次宽度（默认 400），splitter setSizes。"""
        settings = QSettings("ZGQ", "CivCore")
        raw = settings.value("projects/drawer_width")
        try:
            drawer_w = int(raw) if raw is not None else self._DRAWER_DEFAULT_WIDTH
        except (TypeError, ValueError):
            drawer_w = self._DRAWER_DEFAULT_WIDTH
        drawer_w = max(self._DRAWER_MIN_WIDTH, drawer_w)
        total = sum(self._body_splitter.sizes())
        if total <= 0:
            total = self._body_splitter.width() or 1000
        view_w = max(200, total - drawer_w)
        self._body_splitter.setSizes([view_w, drawer_w])

    def _on_drawer_resized(self, _pos: int, _index: int) -> None:
        """用户拖动 splitter 手柄 → 保存 drawer 宽度到 QSettings。"""
        sizes = self._body_splitter.sizes()
        if len(sizes) < 2 or sizes[1] < self._DRAWER_MIN_WIDTH:
            return
        settings = QSettings("ZGQ", "CivCore")
        settings.setValue("projects/drawer_width", int(sizes[1]))

    def refresh(self) -> None:
        self._model.refresh()
        if self._view_stack.currentIndex() == 1:
            self._board_widget.refresh()

    # ════════════════════════════════════════════════════════════
    # 空状态
    # ════════════════════════════════════════════════════════════
    def _build_empty_state(self) -> QWidget:
        """构造空状态占位页（无项目 / 筛选无结果时显示）。"""
        from civ_core.infra_io.style_loader import load_style_preset
        sty = load_style_preset()
        page = QWidget()
        v = QVBoxLayout(page)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setSpacing(12)

        icon = QLabel("📂")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 56px;")
        v.addWidget(icon)

        self._empty_title = QLabel("还没有项目")
        self._empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_title.setStyleSheet(
            f"font-size: {sty.typography.size_subtitle}px; font-weight: 600; "
            f"color: {sty.colors.text_primary};"
        )
        v.addWidget(self._empty_title)

        self._empty_hint = QLabel("点击右上角「+ 新建项目」开始（Ctrl+N）")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setStyleSheet(
            f"font-size: {sty.typography.size_body}px; color: {sty.colors.text_secondary};"
        )
        v.addWidget(self._empty_hint)

        return page

    def _refresh_status_bar(self, *_args) -> None:
        """更新底部状态栏：总数 / 进行中 / 暂存 / 已归档 + DB 路径 tooltip。"""
        all_projects = self._service.list_projects()
        total = len(all_projects)
        active = sum(1 for p in all_projects if not p.is_on_hold and not p.is_archived)
        on_hold = sum(1 for p in all_projects if p.is_on_hold and not p.is_archived)
        archived = sum(1 for p in all_projects if p.is_archived)
        showing = self._proxy.rowCount()
        self._status_label.setText(
            f"显示 {showing} / 共 {total} 个项目  ·  正在进行 {active}  ·  "
            f"暂存 {on_hold}  ·  已归档 {archived}"
        )
        from pathlib import Path
        db_path = Path("~/.civ-core/projects.db").expanduser()
        self._status_label.setToolTip(f"数据库：{db_path}")

    def _refresh_empty_state(self, *_args) -> None:
        """proxy 行数 0 → 切到空状态；> 0 → 切回表格。"""
        is_empty = self._proxy.rowCount() == 0
        self._table_stack.setCurrentIndex(1 if is_empty else 0)
        if is_empty:
            # 区分两种空：DB 真的没数据 vs 仅当前筛选无匹配
            db_total = self._model.rowCount()
            if db_total == 0:
                self._empty_title.setText("还没有项目")
                self._empty_hint.setText("点击右上角「+ 新建项目」开始（Ctrl+N）")
            else:
                self._empty_title.setText("没有匹配当前筛选的项目")
                self._empty_hint.setText("切换上方筛选档查看更多")

    # ════════════════════════════════════════════════════════════
    # 列宽持久化（QSettings("ZGQ", "CivCore") / projects/column_width/<col>）
    # ════════════════════════════════════════════════════════════
    _COLUMN_WIDTH_DEFAULTS = {
        ProjectTableModel.StatusCol: 40,
        ProjectTableModel.NumberCol: 110,
        ProjectTableModel.NameCol: 280,
        ProjectTableModel.TypeCol: 100,
        ProjectTableModel.AmountCol: 100,
        ProjectTableModel.DateCol: 110,
        ProjectTableModel.ProgressCol: 80,
    }
    _NAME_COL_MIN_WIDTH = 160  # NameCol 自动填充时的最小宽度

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

    def _restore_sort_state(self) -> None:
        """从 QSettings 恢复排序列 / 顺序，默认 DateCol 倒序。"""
        settings = QSettings("ZGQ", "CivCore")
        try:
            col = int(settings.value("projects/sort_column", ProjectTableModel.DateCol))
        except (TypeError, ValueError):
            col = ProjectTableModel.DateCol
        order_raw = settings.value("projects/sort_order", "desc")
        order = Qt.SortOrder.AscendingOrder if order_raw == "asc" else Qt.SortOrder.DescendingOrder
        # 越界保护
        if not (0 <= col < self._model.columnCount()):
            col = ProjectTableModel.DateCol
        self._table_view.sortByColumn(col, order)
        # 监听后续变更并持久化
        self._table_view.horizontalHeader().sortIndicatorChanged.connect(self._on_sort_changed)

    def _on_sort_changed(self, col: int, order: Qt.SortOrder) -> None:
        settings = QSettings("ZGQ", "CivCore")
        settings.setValue("projects/sort_column", int(col))
        settings.setValue(
            "projects/sort_order",
            "asc" if order == Qt.SortOrder.AscendingOrder else "desc",
        )

    def _on_section_resized(self, col: int, _old: int, new_size: int) -> None:
        """用户拖动列宽 → 写 QSettings。仅持久化我们关心的列。"""
        if col not in self._COLUMN_WIDTH_DEFAULTS:
            return
        if new_size < 20:
            return  # 太窄当作误触不写
        settings = QSettings("ZGQ", "CivCore")
        settings.setValue(f"projects/column_width/{col}", int(new_size))

    def eventFilter(self, watched, event) -> bool:
        """监听表格 viewport resize：自动让 NameCol 吸收剩余宽度。

        策略：仅在「表格本身变宽 & NameCol 当前宽度小于理想填充宽度」时
        扩展 NameCol。不在用户主动拖窄 NameCol 时反弹（尊重用户操作）。
        """
        from PySide6.QtCore import QEvent
        if watched is self._table_view and event.type() == QEvent.Type.Resize:
            self._autofit_name_column()
        return super().eventFilter(watched, event)

    def _autofit_name_column(self) -> None:
        """NameCol 自动填充剩余可视宽度（仅在剩余 > NameCol 当前宽度时扩展）。"""
        viewport_w = self._table_view.viewport().width()
        other_w = sum(
            self._table_view.columnWidth(c)
            for c in self._COLUMN_WIDTH_DEFAULTS
            if c != ProjectTableModel.NameCol
        )
        ideal_name_w = max(self._NAME_COL_MIN_WIDTH, viewport_w - other_w)
        current = self._table_view.columnWidth(ProjectTableModel.NameCol)
        # 仅当理想宽度比当前大时扩展（避免反复抢用户拖动）；
        # 收窄场景由 sectionResized 持久化机制兜底。
        if ideal_name_w > current:
            # 暂时阻断信号，避免触发 _on_section_resized 把自动填充值当用户操作存
            hdr = self._table_view.horizontalHeader()
            hdr.blockSignals(True)
            self._table_view.setColumnWidth(ProjectTableModel.NameCol, ideal_name_w)
            hdr.blockSignals(False)
