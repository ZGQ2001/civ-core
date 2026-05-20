"""ProjectTree：左侧 Side Bar（VSCode Explorer 风）。

布局：
  ┌──────────────────────────────────────┐
  │ 资源管理器       [📂][＋][⟳][⋮]     │  ← header（标题 + 图标按钮组）
  ├──────────────────────────────────────┤
  │ ∨ PROJECT-ROOT                      │
  │   > 委托方提供资料                   │
  │   > 数据                             │
  │   > 报告                             │
  │   > 模板                             │
  └──────────────────────────────────────┘

行为：
  - 没工作区时显示 empty state（按钮提示）
  - 默认隐藏 .civ-core 和点开头文件
  - 双击文件 → 系统默认程序打开
  - header 按钮：打开 / 新建 / 刷新 / 全部折叠
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileSystemModel,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon

# 项目树最小宽度（VSCode Side Bar 一般 200-260）
MIN_WIDTH = 170


class _SidebarHeader(QWidget):
    """Side Bar 顶部标题栏（VSCode 风）：title + 右侧 4 个图标按钮。

    Signals:
        open_clicked: 打开文件夹
        new_clicked: 新建标准结构
        refresh_clicked: 刷新树
        collapse_clicked: 全部折叠
    """

    open_clicked = Signal()
    new_clicked = Signal()
    refresh_clicked = Signal()
    collapse_clicked = Signal()

    HEADER_HEIGHT = 32
    BTN_SIZE = 22
    ICON_SIZE = 14

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarHeader")
        self.setFixedHeight(self.HEADER_HEIGHT)

        h = QHBoxLayout(self)
        h.setContentsMargins(12, 0, 6, 0)
        h.setSpacing(2)

        label = QLabel(title.upper(), self)
        label.setObjectName("sidebarHeaderTitle")
        h.addWidget(label)
        h.addStretch(1)

        # 4 个图标按钮（VSCode Explorer header 风格，无 emoji，纯 FluentIcon 线条）
        for icon, tooltip, sig in (
            (FluentIcon.FOLDER, "打开文件夹", self.open_clicked),
            (FluentIcon.ADD, "新建标准项目结构", self.new_clicked),
            (FluentIcon.SYNC, "刷新", self.refresh_clicked),
            (FluentIcon.UP, "全部折叠", self.collapse_clicked),
        ):
            btn = QToolButton(self)
            btn.setObjectName("sidebarHeaderBtn")
            btn.setIcon(icon.icon())
            btn.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
            btn.setToolTip(tooltip)
            btn.setFixedSize(self.BTN_SIZE, self.BTN_SIZE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(sig.emit)
            h.addWidget(btn)


class ProjectTree(QFrame):
    """Side Bar（header + 文件树 / empty state）。

    Signals:
        file_double_clicked(Path): 双击文件（非目录）。
        workspace_changed(Path): set_root 切换工作区。
        open_folder_requested(): 用户请求打开文件夹（empty 按钮或 header 按钮）。
        create_workspace_requested(): 用户请求新建标准结构（同上）。
    """

    file_double_clicked = Signal(Path)
    workspace_changed = Signal(Path)
    open_folder_requested = Signal()
    create_workspace_requested = Signal()

    HIDDEN_NAMES = (".civ-core",)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("projectTree")
        self.setMinimumWidth(MIN_WIDTH)
        self.setFrameShape(QFrame.Shape.NoFrame)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # header
        self._header = _SidebarHeader("资源管理器", self)
        self._header.open_clicked.connect(self.open_folder_requested.emit)
        self._header.new_clicked.connect(self.create_workspace_requested.emit)
        self._header.refresh_clicked.connect(self._on_refresh)
        self._header.collapse_clicked.connect(self._on_collapse_all)
        v.addWidget(self._header)

        # 内容区：tree / empty 二选一
        self._stack = QStackedWidget(self)
        v.addWidget(self._stack, 1)

        # 文件树
        self._model = QFileSystemModel(self)
        self._model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllEntries)
        self._model.setNameFilterDisables(True)

        self._tree = QTreeView(self._stack)
        self._tree.setObjectName("projectTreeView")
        self._tree.setModel(self._model)
        for col in range(1, 4):
            self._tree.setColumnHidden(col, True)
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setIndentation(14)
        self._tree.setRootIsDecorated(True)
        self._tree.doubleClicked.connect(self._on_double_clicked)
        self._model.directoryLoaded.connect(self._on_dir_loaded)
        self._stack.addWidget(self._tree)

        # empty state（VSCode 风欢迎页）
        self._empty = self._build_empty_state()
        self._stack.addWidget(self._empty)

        self._stack.setCurrentWidget(self._empty)
        self._root: Path | None = None

    def _build_empty_state(self) -> QWidget:
        w = QWidget(self._stack)
        w.setObjectName("projectTreeEmpty")
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setContentsMargins(16, 24, 16, 24)
        v.setSpacing(8)

        hint = QLabel("尚未打开工作区。", w)
        hint.setObjectName("projectTreeEmptyHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)

        btn_open = QPushButton("打开文件夹", w)
        btn_open.setObjectName("projectTreeOpenBtn")
        btn_open.setProperty("variant", "primary")
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.clicked.connect(self.open_folder_requested.emit)

        btn_new = QPushButton("新建标准结构", w)
        btn_new.setObjectName("projectTreeNewBtn")
        btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new.clicked.connect(self.create_workspace_requested.emit)

        v.addStretch(1)
        v.addWidget(hint)
        v.addSpacing(8)
        v.addWidget(btn_open)
        v.addWidget(btn_new)
        v.addStretch(2)
        return w

    # ── 公开 API ──────────────────────────────────────────
    def set_root(self, root: Path) -> None:
        root = Path(root)
        if not root.is_dir():
            raise ValueError(f"工作区根必须是已存在的目录：{root}")
        self._root = root
        idx = self._model.setRootPath(str(root))
        self._tree.setRootIndex(idx)
        self._stack.setCurrentWidget(self._tree)
        self.workspace_changed.emit(root)

    def clear_root(self) -> None:
        self._root = None
        self._stack.setCurrentWidget(self._empty)

    def root(self) -> Path | None:
        return self._root

    def is_empty_state(self) -> bool:
        return self._stack.currentWidget() is self._empty

    # ── 私有 ──────────────────────────────────────────
    def _on_double_clicked(self, index: QModelIndex) -> None:
        path = Path(self._model.filePath(index))
        if path.is_file():
            self.file_double_clicked.emit(path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_dir_loaded(self, dir_path: str) -> None:
        parent_index = self._model.index(dir_path)
        if not parent_index.isValid():
            return
        for row in range(self._model.rowCount(parent_index)):
            child_idx = self._model.index(row, 0, parent_index)
            name = self._model.fileName(child_idx)
            if name in self.HIDDEN_NAMES:
                self._tree.setRowHidden(row, parent_index, True)

    def _on_refresh(self) -> None:
        """刷新文件树（重新 set_root 触发重新扫描）。"""
        if self._root is not None:
            self.set_root(self._root)

    def _on_collapse_all(self) -> None:
        """折叠所有展开的节点。"""
        self._tree.collapseAll()
