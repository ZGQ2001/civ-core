"""绘曲线图工具的"预览区"面板（右栏）。

布局
====
  ┌──────────────────────────────┐
  │                              │
  │   [大图 QLabel]              │
  │   等比缩放铺满上半部分         │
  │                              │
  ├──────────────────────────────┤
  │ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ...     │
  │ │ ▩ │ │ ▩ │ │ ▩ │ │ ▩ │     │
  │ └──┘ └──┘ └──┘ └──┘         │
  │ 缩略图列表（IconMode）         │
  └──────────────────────────────┘

设计取舍
========
  • 用 QSplitter 垂直分割 —— 用户能拖动大图区/缩略图区的比例
  • 缩略图同步加载（PNG 通常 < 500KB，几十张瞬间完成）；
    若后续遇到性能问题再换异步 worker
  • 大图等比缩放 + 缓存原 QPixmap，resize 时不重读文件
  • 不做历史保留：每次新出图 set_results 会清空旧列表

对外 API
========
  • set_results(paths: list[Path])
      worker.finished 回调来调，把生成的 PNG 列出来；自动选中第一张展示大图
  • clear()
      worker.started 回调来调，让用户看到"开始新一轮"的反馈

不在本组件做的事
================
  • 进度条 / 进度文字 —— view 底部 action bar 已有
  • 失败列表展示 —— 走 view 的 InfoBar
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QListView,
    QListWidgetItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    ListWidget,
    StrongBodyLabel,
)

from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 缩略图尺寸：96×96 是 Windows / macOS Finder 中等图标的标准；
# 太大占用列表空间，太小看不清曲线趋势。
_THUMB_SIZE = 96

# 列表项里 QListWidgetItem 的 UserRole 上挂图片的 Path（QPixmap 不挂避免重复存储）
_ROLE_PATH = Qt.ItemDataRole.UserRole

# 预览大图相对预览区高度的占比（剩下给缩略图列表）
# 不能写死像素，因为右栏宽度由用户拖动；用 splitter sizes 比例控制
_BIG_AREA_RATIO = (3, 1)  # 大图区 : 缩略图区 = 3 : 1


class PreviewPane(QWidget):
    """绘图结果的预览区。

    工作流：
      1. worker started → view 调 clear() → 列表清空 + 大图区显示空状态
      2. worker finished → view 调 set_results(written_paths)
         → 缩略图列表填充 + 默认选中第一张 → 大图自动加载第一张
      3. 用户单击其它缩略图 → 大图区切换显示
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("previewPane")

        # 当前选中图的原始 QPixmap，用于 resize 时无损重缩放
        self._current_pixmap: QPixmap | None = None

        self._build_layout()
        log.debug("PreviewPane ready")

    # ── 构造 ──────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        # 标题（与左栏 / 中栏视觉对齐）
        outer.addWidget(StrongBodyLabel("预览区", self))

        # 上大下小：用 QSplitter Vertical 让用户能拖比例
        self._splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(6)

        # ── 上半：大图区 ──
        # 用裸 QLabel 而不是 ImageLabel —— ImageLabel 行为偏向 fixed-size 图标；
        # 我们要的是"图随容器尺寸变化"，QLabel + 自己写 resizeEvent 最直接
        big_area = QWidget(self._splitter)
        big_layout = QVBoxLayout(big_area)
        big_layout.setContentsMargins(0, 0, 0, 0)

        self._big_label = BodyLabel("", big_area)
        self._big_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._big_label.setMinimumHeight(180)
        # 让 QLabel 接受任何 size 的 pixmap —— 不设 setScaledContents（默认 False）；
        # 我们手动在 _refresh_big_image 里 scale，保留原图比例
        self._big_label.setStyleSheet(
            "QLabel { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 6px; }"
        )
        big_layout.addWidget(self._big_label, 1)

        self._splitter.addWidget(big_area)

        # ── 下半：缩略图列表（IconMode）──
        self._thumb_list = ListWidget(self._splitter)
        self._thumb_list.setViewMode(QListView.ViewMode.IconMode)
        self._thumb_list.setIconSize(QSize(_THUMB_SIZE, _THUMB_SIZE))
        self._thumb_list.setResizeMode(QListView.ResizeMode.Adjust)
        self._thumb_list.setMovement(QListView.Movement.Static)  # 用户不能拖排序
        self._thumb_list.setSpacing(8)
        # 缩略图 + 文件名最少需要 ~110px 宽 + ~20px 文件名行高
        self._thumb_list.setGridSize(QSize(_THUMB_SIZE + 24, _THUMB_SIZE + 36))
        self._thumb_list.setUniformItemSizes(True)
        self._thumb_list.setMinimumHeight(_THUMB_SIZE + 60)
        self._thumb_list.setSelectionMode(self._thumb_list.SelectionMode.SingleSelection)
        self._thumb_list.currentItemChanged.connect(self._on_current_changed)
        self._splitter.addWidget(self._thumb_list)

        self._splitter.setSizes(list(_BIG_AREA_RATIO))
        self._splitter.setStretchFactor(0, _BIG_AREA_RATIO[0])
        self._splitter.setStretchFactor(1, _BIG_AREA_RATIO[1])

        outer.addWidget(self._splitter, 1)

        # 起始空态
        self._show_empty_state()

    # ── 公共 API ──────────────────────────────────────────────────
    def set_results(self, paths: list[Path]) -> None:
        """worker.finished 后调，把生成的 PNG 列出来。

        清旧 + 加新 + 选中第一张。空 list 等价于 clear()，把 UI 留在空态。
        """
        self._thumb_list.clear()
        self._current_pixmap = None

        if not paths:
            self._show_empty_state()
            return

        # 同步加载缩略图。100 张以内基本无感。
        # 失败的图（被外部误删 / 写入半截）会以"无效"占位 + 文件名展示，
        # 不让单个坏图把整张列表搅黄。
        for path in paths:
            item = QListWidgetItem(path.name, self._thumb_list)
            item.setData(_ROLE_PATH, path)
            item.setToolTip(str(path))

            pix = QPixmap(str(path))
            if not pix.isNull():
                # 缩略图按 _THUMB_SIZE 等比缩放，保持高质量平滑
                scaled = pix.scaled(
                    _THUMB_SIZE,
                    _THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                item.setIcon(scaled)  # type: ignore[arg-type]
            else:
                # 加载失败 → tooltip 标注，不贴 icon（默认空白）
                item.setToolTip(f"{path}\n（缩略图加载失败）")
                log.warning("缩略图加载失败：%s", path)

        # 默认选第一张 → 触发 _on_current_changed → 大图刷新
        self._thumb_list.setCurrentRow(0)

    def clear(self) -> None:
        """worker.started 调，清空所有内容回到空态。"""
        self._thumb_list.clear()
        self._current_pixmap = None
        self._show_empty_state()

    # ── 内部 ──────────────────────────────────────────────────────
    def _show_empty_state(self) -> None:
        """大图区显示一句灰字提示。缩略图列表已清空，不再单独处理。

        注意 QLabel 的 setText / setPixmap 互斥：先 clear() 抹掉 pixmap，
        再 setText 才能让文字真正显示出来。这条坑值得注释一下。
        """
        self._big_label.clear()  # 抹掉可能挂着的 pixmap
        self._big_label.setText("运行批量出图后，缩略图会出现在这里")

    def _on_current_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        """切换缩略图选中 → 大图区加载对应原图。"""
        if current is None:
            self._show_empty_state()
            return

        path = current.data(_ROLE_PATH)
        if not isinstance(path, Path):
            self._show_empty_state()
            return

        pix = QPixmap(str(path))
        if pix.isNull():
            self._big_label.setText(f"无法加载：{path.name}")
            self._current_pixmap = None
            return

        self._current_pixmap = pix
        self._refresh_big_image()

    def _refresh_big_image(self) -> None:
        """把 _current_pixmap 等比缩放到 _big_label 当前可用尺寸。

        resizeEvent 也调这个，保证用户拖大窗口时图自动放大。
        """
        if self._current_pixmap is None or self._current_pixmap.isNull():
            return

        # 给容器留 12px 内边距，避免图紧贴边框
        target_w = max(self._big_label.width() - 12, 50)
        target_h = max(self._big_label.height() - 12, 50)

        scaled = self._current_pixmap.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        # 清掉空态文字
        self._big_label.setText("")
        self._big_label.setPixmap(scaled)

    # ── Qt 事件 ───────────────────────────────────────────────────
    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt 命名约定)
        """父 widget 改大小 → 大图重新缩放。"""
        super().resizeEvent(event)
        self._refresh_big_image()
