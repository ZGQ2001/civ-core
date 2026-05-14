"""缩略图视窗：批量出图完成后，展示所有结果 PNG 的缩略图列表。

数据来源
========
`run_plot_curves(...).written` 返回 `list[Path]`，每个 path 对应一行的 PNG。
plot_curves_view 在 worker_finished 时把这个列表喂给本面板（set_thumbnails）。

交互
====
  • 点击缩略图 → emit row_clicked(idx) → view 路由到 LivePreviewPane.highlight_row(idx)
  • 当前选中行通过 set_current_index(idx) 显示边框高亮（与 LivePreviewPane 双向联动）

视觉
====
  IconMode 横向列出，每个 item 96×96 缩略图 + 下方编号"#1"/"#2"...
  深色/浅色主题由全局 QSS 自动套用。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel

from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 缩略图边长（像素）。96 是综合体验最佳：能看清曲线形状 + 横向不挤
_THUMB_SIZE = 96
# 每个 item 的总尺寸（缩略图 + 编号文字 + padding）
_ITEM_SIZE = QSize(_THUMB_SIZE + 16, _THUMB_SIZE + 32)


class ThumbnailPane(QWidget):
    """缩略图列表面板。

    使用 QListWidget(IconMode) 而非 QListView + Model 的原因：
      • 数据量级小（典型批次 < 50 张），不需要 model/view 分离
      • IconMode 内置 "图标在上 + 文字在下" 的 item 布局，省去自绘
      • QListWidget API 简单（addItem / item / clear），写起来比 model 干净
    """

    row_clicked = Signal(int)  # 用户点击第 idx 张缩略图

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("thumbnailPane")
        # 显式允许窄宽：底栏在窄窗口下不应被本面板顶大
        self.setMinimumWidth(0)

        self._build_layout()
        self._paths: list[Path] = []

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        # 顶部说明 —— 没图时也能给用户一句话指引
        self._hint = BodyLabel("点击「▶ 生成全部曲线 PNG」后这里会列出所有图", self)
        self._hint.setStyleSheet("color: #8B92A0;")
        layout.addWidget(self._hint)

        # 缩略图列表
        self._list = QListWidget(self)
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setIconSize(QSize(_THUMB_SIZE, _THUMB_SIZE))
        self._list.setGridSize(_ITEM_SIZE)
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setMovement(QListWidget.Movement.Static)
        self._list.setSpacing(4)
        self._list.setWordWrap(False)
        # uniform item sizes 让滚动平滑
        self._list.setUniformItemSizes(True)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list, 1)

    def set_thumbnails(self, paths: list[Path]) -> None:
        """重设缩略图列表 —— 通常在批量出图 worker 完成后调用。

        加载策略：同步 + QPixmap.scaled。在 50 张 PNG 量级下，UI 卡顿可
        接受（< 200ms）。如果未来批次过百，可改成异步分批加载。
        """
        self._paths = list(paths)
        self._list.clear()
        if not self._paths:
            self._hint.setText("点击「▶ 生成全部曲线 PNG」后这里会列出所有图")
            self._hint.setVisible(True)
            return
        self._hint.setText(f"共 {len(self._paths)} 张 · 点击切换主预览")
        self._hint.setVisible(True)

        for idx, p in enumerate(self._paths):
            item = QListWidgetItem(f"#{idx + 1}", self._list)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            pix = QPixmap(str(p))
            if not pix.isNull():
                # 等比缩放到固定尺寸（KeepAspectRatio 防变形）
                scaled = pix.scaled(
                    _THUMB_SIZE,
                    _THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                item.setIcon(QIcon(scaled))
            item.setToolTip(str(p))
            self._list.addItem(item)

    def set_current_index(self, idx: int) -> None:
        """主预览切到第 idx 行 → 缩略图列表也高亮对应项（双向联动）。

        idx 越界 / 负数 → 清空选中。
        """
        if idx < 0 or idx >= self._list.count():
            self._list.clearSelection()
            return
        # 用 setCurrentRow 触发标准选中态（含 selection-background-color QSS）
        self._list.blockSignals(True)
        try:
            self._list.setCurrentRow(idx)
            # 滚到可见
            item = self._list.item(idx)
            if item is not None:
                self._list.scrollToItem(item)
        finally:
            self._list.blockSignals(False)

    def clear(self) -> None:
        """清空缩略图（用户切预设 / 切数据源时调用）。"""
        self._paths.clear()
        self._list.clear()
        self._hint.setText("点击「▶ 生成全部曲线 PNG」后这里会列出所有图")

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(idx, int):
            return
        log.debug("ThumbnailPane: 用户点击第 %d 张缩略图", idx)
        self.row_clicked.emit(idx)


__all__ = ["ThumbnailPane"]
