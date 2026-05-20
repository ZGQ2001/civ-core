"""ProjectTree：左侧常驻文件树（VSCode 风，Explorer 视图）。

行为：
  - 没工作区时显示 empty state（"未打开文件夹" + 两个按钮）—— VSCode 风
  - 调 set_root(path) 切到树视图，clear_root() 切回 empty
  - 默认隐藏 .civ-core 和点开头文件
  - 双击文件 → 系统默认程序打开 + 发 file_double_clicked
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileSystemModel,
    QFrame,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

# 项目树栏的最小宽度：防止拖到 0 视觉错乱
MIN_WIDTH = 160


class ProjectTree(QFrame):
    """文件树（QTreeView + QFileSystemModel）+ 无工作区时的 empty state。

    Signals:
        file_double_clicked(Path): 双击了一个文件（非目录）。
        workspace_changed(Path): 调用 set_root 切换工作区。
        open_folder_requested(): 用户点击 empty state 的"打开文件夹"。
        create_workspace_requested(): 用户点击 empty state 的"新建标准结构"。
    """

    file_double_clicked = Signal(Path)
    workspace_changed = Signal(Path)
    open_folder_requested = Signal()
    create_workspace_requested = Signal()

    # 默认从树中隐藏的目录名（应用专属目录）
    HIDDEN_NAMES = (".civ-core",)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("projectTree")
        self.setMinimumWidth(MIN_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 用 QStackedWidget 在"空状态欢迎页"和"文件树视图"之间切换
        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack)

        # ── 文件树视图 ────────────────────────────────────────
        self._model = QFileSystemModel(self)
        self._model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllEntries)
        # nameFilterDisables=True：不匹配的项灰显而非彻底隐藏；不开 Hidden 默认隐藏点开头
        self._model.setNameFilterDisables(True)

        self._tree = QTreeView(self._stack)
        self._tree.setObjectName("projectTreeView")
        self._tree.setModel(self._model)
        for col in range(1, 4):
            self._tree.setColumnHidden(col, True)
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(False)
        self._tree.setUniformRowHeights(True)
        self._tree.doubleClicked.connect(self._on_double_clicked)
        self._model.directoryLoaded.connect(self._on_dir_loaded)

        self._stack.addWidget(self._tree)

        # ── empty state（VSCode 风欢迎页） ─────────────────────
        self._empty = self._build_empty_state()
        self._stack.addWidget(self._empty)

        # 初始：empty state（没 workspace）
        self._stack.setCurrentWidget(self._empty)

        self._root: Path | None = None

    def _build_empty_state(self) -> QWidget:
        """VSCode 风"未打开文件夹"欢迎页。"""
        w = QWidget(self._stack)
        w.setObjectName("projectTreeEmpty")
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setContentsMargins(16, 24, 16, 24)
        v.setSpacing(10)

        title = QLabel("未打开工作区", w)
        title.setStyleSheet("font-size: 12px; color: #B8BFC9;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        hint = QLabel("打开已有项目文件夹，或新建一个标准结构。", w)
        hint.setStyleSheet("font-size: 10px; color: #8B92A0;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)

        btn_open = QPushButton("打开文件夹", w)
        btn_open.setObjectName("projectTreeOpenBtn")
        btn_open.clicked.connect(self.open_folder_requested.emit)

        btn_new = QPushButton("新建标准结构", w)
        btn_new.setObjectName("projectTreeNewBtn")
        btn_new.clicked.connect(self.create_workspace_requested.emit)

        v.addStretch(1)
        v.addWidget(title)
        v.addWidget(hint)
        v.addSpacing(8)
        v.addWidget(btn_open)
        v.addWidget(btn_new)
        v.addStretch(1)
        return w

    # ── 公开 API ──────────────────────────────────────────
    def set_root(self, root: Path) -> None:
        """切换文件树的根目录；root 必须是已存在的目录。"""
        root = Path(root)
        if not root.is_dir():
            raise ValueError(f"工作区根必须是已存在的目录：{root}")
        self._root = root
        idx = self._model.setRootPath(str(root))
        self._tree.setRootIndex(idx)
        self._stack.setCurrentWidget(self._tree)
        self.workspace_changed.emit(root)

    def clear_root(self) -> None:
        """切回 empty state（没工作区状态）。"""
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
        """QFileSystemModel 扫描某目录完成 → 把黑名单条目（.civ-core）隐藏。"""
        parent_index = self._model.index(dir_path)
        if not parent_index.isValid():
            return
        for row in range(self._model.rowCount(parent_index)):
            child_idx = self._model.index(row, 0, parent_index)
            name = self._model.fileName(child_idx)
            if name in self.HIDDEN_NAMES:
                self._tree.setRowHidden(row, parent_index, True)
