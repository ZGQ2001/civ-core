"""绘曲线图工具 —— 三栏视图骨架（QSplitter）。

布局：
  ┌─────────────┬───────────────────┬──────────────────────┐
  │ 模板列表     │ 设置面板           │ 预览区                │
  │ (Step 10)   │ (Step 11)         │ (后续步骤)             │
  │             │                   │                      │
  │             │                   │                      │
  └─────────────┴───────────────────┴──────────────────────┘
        左               中                  右

为什么 QSplitter 而不是固定 QHBoxLayout：
  • 不同分辨率 / 不同长度的模板名 / 不同字段量的设置面板，宽度需求差异大
  • 用户可以自己拖动分隔条，记忆习惯（持久化拖到何处是后续步骤的事）
  • setCollapsible(False) 防止误把某栏拖没

第二阶段渐进填充：
  Step 9（当前）：搭起 QSplitter + 3 个 _PanePlaceholder 占位
  Step 10        左栏换 TemplateListPane（真模板列表，从 04_Config 读）
  Step 11        中栏换 PlotSettingsPanel（SettingCardGroup + PlotJob 双向绑定）
  Step 12        中栏底部加"生成"按钮 + 异步 worker
  Step 13        异常通过 InfoBar 三段式提示
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SimpleCardWidget, StrongBodyLabel

from civil_auto.config.loader import AppConfig
from civil_auto.utils.logger import get_logger

log = get_logger(__name__)

# 三栏初始宽度（单位：像素，按 1320×840 默认窗口算）。
# 主窗口 sidebar ≈ 280 → 视图区可用宽 ≈ 1040，三栏 220/380/440 比较舒展。
# QSplitter.setSizes 会按比例缩放，所以这些数字只是相对权重。
_INITIAL_SIZES = (220, 380, 440)


class _PanePlaceholder(SimpleCardWidget):
    """单个面板的统一占位皮：标题 + 副标题，居中。

    用 SimpleCardWidget 而不是裸 QWidget，是为了在 QSplitter 中
    每栏都有清晰的圆角卡片视觉边界，方便看出"三栏在哪里"。
    Step 10/11 真组件接入时，会换掉子内容（保留 SimpleCardWidget 外壳）。
    """

    def __init__(
        self,
        object_name: str,
        title: str,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = StrongBodyLabel(title, self)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        if subtitle:
            sub_label = BodyLabel(subtitle, self)
            sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub_label.setWordWrap(True)
            sub_label.setStyleSheet("color: #888;")
            layout.addWidget(sub_label)


class PlotCurvesView(QWidget):
    """绘曲线图工具的根视图（注册到 MainWindow.plot_curves_page 槽位）。

    cfg 透传给后续接入的真子面板（如 SettingsPane 需要 paths.data_output 默认值），
    本步骤仅占位，cfg 暂时只用来打日志。
    """

    def __init__(self, cfg: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # objectName 必须与 MainWindow 原 placeholder 一致，否则 qfluentwidgets 导航 routing 错位
        self.setObjectName("plotCurvesPage")
        self._cfg = cfg

        self._build_layout()
        log.debug(
            "PlotCurvesView ready (initial sizes=%s, sum=%d)",
            _INITIAL_SIZES,
            sum(_INITIAL_SIZES),
        )

    def _build_layout(self) -> None:
        # 外层 layout：只放一个 QSplitter，留窄边距
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        # 三个占位面板（暴露成 self.* 供 Step 10/11 直接替换 children）
        self.template_pane = _PanePlaceholder(
            "templateListPane",
            "模板列表",
            "Step 10 接入：从 04_Config/curve_templates.json 读取，点击切换右侧设置",
        )
        self.settings_pane = _PanePlaceholder(
            "plotSettingsPane",
            "设置面板",
            "Step 11 接入：SettingCardGroup + ScrollArea，参数与 PlotJob 双向绑定",
        )
        self.preview_pane = _PanePlaceholder(
            "previewPane",
            "预览区",
            "后续步骤接入：缩略图列表 + 单击放大；生成进度也在这里展示",
        )

        # 横向 QSplitter
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("plotCurvesSplitter")
        splitter.setChildrenCollapsible(False)  # 防止用户误把某栏拖没
        splitter.setHandleWidth(6)
        splitter.addWidget(self.template_pane)
        splitter.addWidget(self.settings_pane)
        splitter.addWidget(self.preview_pane)
        splitter.setSizes(list(_INITIAL_SIZES))

        # 三栏的拉伸优先级：模板列表固定窄，设置面板和预览区可拉伸
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)

        outer.addWidget(splitter)
        self._splitter = splitter  # 测试 / 后续步骤可访问
