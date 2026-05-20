"""WorkspacePickerDialog：启动门槛 / 切换工作区时的选择对话框（Obsidian 风）。

为什么独立成对话框：
  - shell 启动逻辑只关心"拿到一个合法的 workspace Path 或退出"，把
    选目录 / 新建 / 取消的交互细节集中在对话框里
  - 测试时 shell 可以 monkeypatch 这个对话框直接返回路径，绕过文件对话框

返回值：
  对话框 accept 时 selected_path() 不为 None；reject 时为 None。
  上层根据 None / 非 None 决定退出 App 还是继续。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from civ_core.infra_io.workspace_scaffold import create_standard_structure


class WorkspacePickerDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("打开工作区")
        self.setModal(True)
        self.setMinimumWidth(380)
        self._selected: Path | None = None

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        title = QLabel("选择一个项目工作区开始", self)
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        v.addWidget(title)

        hint = QLabel(
            "筑核需要先打开一个项目文件夹。\n"
            "标准结构 = 委托方提供资料 / 数据 / 报告 / 模板。",
            self,
        )
        hint.setStyleSheet("color: #8B92A0;")
        hint.setWordWrap(True)
        v.addWidget(hint)

        v.addSpacing(8)

        btn_open = QPushButton("打开已有文件夹…", self)
        btn_open.setObjectName("wsPickerOpenBtn")
        btn_open.clicked.connect(self._on_open_existing)
        v.addWidget(btn_open)

        btn_new = QPushButton("新建标准项目结构…", self)
        btn_new.setObjectName("wsPickerNewBtn")
        btn_new.clicked.connect(self._on_create_new)
        v.addWidget(btn_new)

        v.addStretch(1)

        h = QHBoxLayout()
        h.addStretch(1)
        btn_cancel = QPushButton("取消", self)
        btn_cancel.setObjectName("wsPickerCancelBtn")
        btn_cancel.clicked.connect(self.reject)
        h.addWidget(btn_cancel)
        v.addLayout(h)

    # ── 公开 API ──────────────────────────────────────────
    def selected_path(self) -> Path | None:
        """对话框被 accept 后返回选定的工作区路径；reject 则返回 None。"""
        return self._selected

    def set_selected_path(self, p: Path | None) -> None:
        """测试钩子：跳过文件对话框直接设值（pytest 用）。"""
        self._selected = p

    # ── 内部事件 ──────────────────────────────────────────
    def _on_open_existing(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self,
            "选择工作区文件夹",
            str(Path.home()),
        )
        if not d:
            return
        self._selected = Path(d)
        self.accept()

    def _on_create_new(self) -> None:
        parent_dir = QFileDialog.getExistingDirectory(
            self,
            "选择父目录（项目将在此目录下创建）",
            str(Path.home()),
        )
        if not parent_dir:
            return
        name, ok = QInputDialog.getText(
            self,
            "新建标准项目",
            "项目文件夹名：",
            Qt.WindowType.Dialog,
        )
        if not ok or not name.strip():
            return
        root = Path(parent_dir) / name.strip()
        try:
            create_standard_structure(root)
        except OSError as e:
            QMessageBox.critical(
                self,
                "创建失败",
                f"无法创建项目文件夹：\n{e}",
            )
            return
        self._selected = root
        self.accept()
