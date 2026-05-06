"""绘曲线图工具的"模板列表"面板（左栏）。

职责：
  • 从 cfg.paths.curve_templates 指定的 JSON 读取所有模板
    （默认 ./templates/plot_curves/curve_templates.json）
  • 用户点击某条 → 发 template_selected 信号，右栏的设置面板据此切换
  • 顶部小刷新按钮：用户在外部编辑器改完 JSON 不必重启程序

错误处理：
  • 模板库不存在 / JSON 语法错 / 字段缺：捕 PlotCurvesError，UI 上显示
    一行红字提示，不让 ListWidget 崩
  • 模板库为空：列表禁用，提示"请先创建模板"

为什么不直接 import config.loader：
  • core.plot_curves.load_templates 已经把"路径解析 + 异常包装"做好了；
    UI 层重复一遍是浪费，也容易行为漂移
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    ListWidget,
    StrongBodyLabel,
    TransparentToolButton,
)

from civil_auto.core.plot_curves import (
    PlotCurvesError,
    get_template_names,
    load_templates,
)
from civil_auto.utils.logger import get_logger

log = get_logger(__name__)

# Qt.UserRole 上挂的整张模板 dict —— 右栏 SettingsPane 之后能直接吃，免得再读一遍 JSON
_ROLE_TEMPLATE_DICT = Qt.ItemDataRole.UserRole


class TemplateListPane(QWidget):
    """模板列表面板。

    Signals:
      template_selected(str) —— 用户切到某条模板时发出，参数是模板名（dict 通过
                                item.data(Qt.UserRole) 也能直接取到）
    """

    template_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("templateListPane")

        self._build_layout()
        # 注意：__init__ 不主动调 refresh()。
        # 调用方必须先 connect(template_selected, ...)，再调 refresh() —— 否则
        # refresh() 内部 setCurrentRow(0) 触发的首次信号会因为还没接收方而丢失。

    # ── 构造 ──────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        # ── 顶部：标题 + 刷新按钮 ──
        header = QHBoxLayout()
        header.setSpacing(6)

        title = StrongBodyLabel("模板列表", self)
        header.addWidget(title)
        header.addStretch(1)

        self._refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self._refresh_btn.setToolTip("重新读取 curve_templates.json")
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)

        outer.addLayout(header)

        # ── 副标题：状态行（显示模板总数 / 错误信息）──
        self._status_label = CaptionLabel("", self)
        self._status_label.setWordWrap(True)
        outer.addWidget(self._status_label)

        # ── 中部：列表 ──
        self._list = ListWidget(self)
        # 单选 + 不让用户拖排序
        self._list.setSelectionMode(self._list.SelectionMode.SingleSelection)
        self._list.currentItemChanged.connect(self._on_current_changed)
        outer.addWidget(self._list, 1)

        # ── 底部：空状态提示（默认隐藏，empty/error 时显示）──
        self._empty_label = BodyLabel("", self)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: #c33;")
        self._empty_label.hide()
        outer.addWidget(self._empty_label)

    # ── 公共 API ──────────────────────────────────────────────────
    def refresh(self) -> None:
        """重新加载模板库并刷新列表。被刷新按钮 / 外部代码调用。"""
        self._list.clear()
        self._empty_label.hide()
        self._list.show()

        try:
            templates = load_templates()  # 走 cfg.paths.curve_templates
        except PlotCurvesError as e:
            log.warning("模板库加载失败：%s", e)
            self._show_error(f"⚠️ 加载失败：{e}")
            return

        names = get_template_names(templates)
        if not names:
            self._show_error(
                "模板库为空。\n请先在 [曲线模板编辑器] 创建模板，或手工编辑 "
                "templates/plot_curves/curve_templates.json。"
            )
            return

        for name in names:
            tpl_dict: dict[str, Any] = templates[name]
            item = QListWidgetItem(name, self._list)
            item.setData(_ROLE_TEMPLATE_DICT, tpl_dict)
            # tooltip 上额外显示几个识别字段，鼠标悬停能预判内容
            curves_n = len(tpl_dict.get("curves", []))
            id_col = tpl_dict.get("id_column", "?")
            item.setToolTip(f"标识列：{id_col}\n曲线条数：{curves_n}")

        self._status_label.setText(f"共 {len(names)} 个模板")
        log.info("模板列表已刷新：%d 条", len(names))

        # 默认选第一个，让右栏立刻有"已选"状态
        self._list.setCurrentRow(0)

    def selected_template_name(self) -> str | None:
        """返回当前选中的模板名；没选返回 None。"""
        item = self._list.currentItem()
        return item.text() if item is not None else None

    def selected_template_dict(self) -> dict[str, Any] | None:
        """返回当前选中模板的完整 dict；没选返回 None。"""
        item = self._list.currentItem()
        if item is None:
            return None
        data = item.data(_ROLE_TEMPLATE_DICT)
        return data if isinstance(data, dict) else None

    # ── 内部 ──────────────────────────────────────────────────────
    def _show_error(self, message: str) -> None:
        """把列表收掉，露出红字提示。"""
        self._list.hide()
        self._empty_label.setText(message)
        self._empty_label.show()
        self._status_label.setText("")

    def _on_current_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        name = current.text()
        log.debug("template selected: %s", name)
        self.template_selected.emit(name)
