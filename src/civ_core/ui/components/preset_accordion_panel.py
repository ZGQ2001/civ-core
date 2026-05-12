"""预设风琴参数面板（L-1 占位 / L-3b 实装）。

L-1 Step 1：仅作为左栏占位，确认两栏 QSplitter 布局正确。
界面只有一行说明文字，提示开发者本面板在 L-3b（风琴面板外壳）阶段才会接入。

L-3b 计划实装的分组（自上而下，与 PROGRESS.md 一致）：
  1. 预设选择（永远置顶不可折叠）
  2. 数据源
  3. 曲线定义（装 L-3a 的 CurvesEditor）
  4. 坐标轴
  5. 样式
  6. 输出
数值字段统一走「滑块 + Spin/LineEdit」联动组合；删除按钮二次确认走
qfluentwidgets.MessageBox；系统预设可改写，保存时 copy_system_to_user。

为什么先做占位：
  • L-1 只动布局骨架，旧的 preset_list / preset_form_panel 暂留待 L-3b 拆解吸收
  • 占位 widget 留 objectName，方便测试 / DevTools 定位
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SubtitleLabel


class PresetAccordionPanel(QWidget):
    """预设参数风琴面板。当前为占位实现（仅显示等待提示）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # objectName 用于 qfluentwidgets 路由 / 测试定位
        self.setObjectName("presetAccordionPanel")
        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        title = SubtitleLabel("参数面板", self)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = BodyLabel(
            "（L-3b 阶段接入风琴折叠分组：预设选择 / 数据源 / 曲线定义 / 坐标轴 / 样式 / 输出）",
            self,
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #888;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
