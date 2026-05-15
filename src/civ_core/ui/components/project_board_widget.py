"""ProjectBoardWidget：3 列看板（待处理 | 进行中 | 已完成）。

按 Project.board_column() 分列，每列 QScrollArea + 垂直堆叠紧凑卡片。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import Project


class _BoardColumn(QWidget):
    """看板中的一列。"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #424242; padding: 4px 0;"
        )
        layout.addWidget(self.title_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        container = QWidget()
        self.items_layout = QVBoxLayout(container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(6)
        self.items_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll)


class ProjectBoardWidget(QWidget):
    """3 列看板：待处理 / 进行中 / 已完成。

    用法：
        board = ProjectBoardWidget()
        board.set_service(service)
        board.refresh()
    """

    project_clicked = None  # 占位，实际信号在 ProjectBoardView 层连接

    def __init__(self, parent=None):
        super().__init__(parent)
        self._service: ProjectService | None = None
        self._pending_items: list[Project] = []
        self._in_progress_items: list[Project] = []
        self._completed_items: list[Project] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._pending_column = _BoardColumn("待处理")
        self._in_progress_column = _BoardColumn("进行中")
        self._completed_column = _BoardColumn("已完成")

        layout.addWidget(self._pending_column)
        layout.addWidget(self._in_progress_column)
        layout.addWidget(self._completed_column)

    def set_service(self, service: ProjectService) -> None:
        self._service = service

    def refresh(self) -> None:
        """重新从 service 加载数据并分列渲染。"""
        if self._service is None:
            return

        projects = self._service.list_projects()

        self._pending_items = [p for p in projects if p.board_column() == "待处理"]
        self._in_progress_items = [p for p in projects if p.board_column() == "进行中"]
        self._completed_items = [p for p in projects if p.board_column() == "已完成"]

        self._rebuild_column(self._pending_column, self._pending_items, "待处理")
        self._rebuild_column(self._in_progress_column, self._in_progress_items, "进行中")
        self._rebuild_column(self._completed_column, self._completed_items, "已完成")

    def _rebuild_column(
        self, column: _BoardColumn, projects: list[Project], title: str
    ) -> None:
        """清空列中旧卡片，重建新卡片。"""
        column.title_label.setText(f"{title} ({len(projects)})")

        # 清空旧卡片（保留 stretch）
        while column.items_layout.count() > 1:
            item = column.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 插入新卡片（stretch 前）
        for proj in projects:
            card = self._make_card(proj)
            column.items_layout.insertWidget(
                column.items_layout.count() - 1, card
            )

    def _make_card(self, proj: Project) -> QFrame:
        """构造一张紧凑卡片。"""
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 8px;
            }
            QFrame:hover {
                border-color: #1976D2;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # 编号 + 名称
        number = QLabel(proj.project_number)
        number.setStyleSheet("color: #757575; font-size: 8px; border: none;")
        layout.addWidget(number)

        name = QLabel(proj.name)
        name.setWordWrap(True)
        name.setStyleSheet("color: #212121; font-size: 10px; font-weight: bold; border: none;")
        layout.addWidget(name)

        # 类型 + 金额
        info = QLabel(f"{proj.inspection_type}  ·  ¥{proj.amount:,.0f}")
        info.setStyleSheet("color: #757575; font-size: 8px; border: none;")
        layout.addWidget(info)

        return card
