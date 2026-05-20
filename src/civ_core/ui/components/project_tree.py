"""ProjectTree：左侧常驻文件树（QTreeView + QFileSystemModel）。

为什么独立：
  - 跨工具页共享，shell 持有单例
  - 默认隐藏点开头文件 / .civ-core，业务视图不被应用专属目录污染
  - 双击文件 → 发信号 file_double_clicked + 系统默认程序打开
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileSystemModel,
    QFrame,
    QTreeView,
    QVBoxLayout,
)


class ProjectTree(QFrame):
    """文件树（QTreeView + QFileSystemModel）封装。

    Signals:
        file_double_clicked(Path): 双击了一个文件（非目录）时发出。
        workspace_changed(Path): 调用 set_root 切换工作区时发出。
    """

    file_double_clicked = Signal(Path)
    workspace_changed = Signal(Path)

    # 默认从树中过滤掉的目录名（应用专属隐藏目录）
    HIDDEN_NAMES = (".civ-core",)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("projectTree")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._model = QFileSystemModel(self)
        # NoDotAndDotDot：不显示 . 和 ..； AllEntries：含目录 + 文件；
        # 不开 Filter.Hidden → 默认隐藏点开头的文件/目录（这正好把 .civ-core 也带走）
        self._model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllEntries)
        # nameFilters 配合显式黑名单，双保险隐藏 .civ-core
        # （QFileSystemModel 没法用单个 setFilter 黑名单，只能交给上层视图判断）
        self._model.setNameFilterDisables(True)  # 不匹配的项灰显而非彻底隐藏；下面用 setRowHidden 隐藏

        self._tree = QTreeView(self)
        self._tree.setObjectName("projectTreeView")
        self._tree.setModel(self._model)
        # 只显示名字列，隐藏「大小/类型/修改日期」三列
        for col in range(1, 4):
            self._tree.setColumnHidden(col, True)
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(False)
        self._tree.setUniformRowHeights(True)
        self._tree.doubleClicked.connect(self._on_double_clicked)
        # 监听根目录扫描完成，触发对 .civ-core 的隐藏
        self._model.directoryLoaded.connect(self._on_dir_loaded)

        layout.addWidget(self._tree)

        self._root: Path | None = None

    # ── 公开 API ──────────────────────────────────────────
    def set_root(self, root: Path) -> None:
        """切换文件树的根目录；root 必须是已存在的目录。"""
        root = Path(root)
        if not root.is_dir():
            raise ValueError(f"工作区根必须是已存在的目录：{root}")
        self._root = root
        idx = self._model.setRootPath(str(root))
        self._tree.setRootIndex(idx)
        self.workspace_changed.emit(root)

    def root(self) -> Path | None:
        return self._root

    # ── 私有 ──────────────────────────────────────────
    def _on_double_clicked(self, index: QModelIndex) -> None:
        path = Path(self._model.filePath(index))
        if path.is_file():
            self.file_double_clicked.emit(path)
            # 系统默认程序打开（Word/Excel/PDF/图片 → 直接交给 OS）
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_dir_loaded(self, dir_path: str) -> None:
        """目录被 QFileSystemModel 扫描完成 → 把黑名单条目隐藏掉。

        QFileSystemModel 的扫描是异步的，必须等 directoryLoaded 才能找到行号。
        """
        parent_index = self._model.index(dir_path)
        if not parent_index.isValid():
            return
        for row in range(self._model.rowCount(parent_index)):
            child_idx = self._model.index(row, 0, parent_index)
            name = self._model.fileName(child_idx)
            if name in self.HIDDEN_NAMES:
                self._tree.setRowHidden(row, parent_index, True)
