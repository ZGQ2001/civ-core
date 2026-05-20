"""ShellWindow：QMainWindow 主壳（替代旧 FluentWindow MainWindow）。

布局（横向，顶栏跨全宽）：
  ┌──────────────────── BreadcrumbBar（顶栏，跨全宽）──────────────────────┐
  │ Activity │ ProjectTree │ ToolContainer (QStackedWidget) │  AgentPanel │
  │  Bar 48  │  常驻文件树 │  当前工具页（B2 才拆上下二段）  │   占位空壳  │
  └────────────────────────────────────────────────────────────────────────┘

启动门槛（Obsidian 风，由 resolve_workspace_or_prompt 实现）：
  1. QSettings 读 last_workspace 路径，若仍是有效目录 → 直接返回
  2. 否则弹 WorkspacePickerDialog；用户「打开 / 新建 / 取消」三选一
  3. 取消 → 返回 None，bootstrap.run() 据此提前 return 0（不进 app.exec()）

为什么弃 FluentWindow：
  - FluentWindow 的 page 是整块区域，没法把"项目树/Agent"做成跨 page 共享外壳；
    硬塞会导致每个 page 重复实例化 + 状态同步问题
  - QMainWindow + 自己的 ActivityBar 自由度高，也更接近 VSCode 风
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon

from civ_core.apps.bootstrap import set_theme_runtime
from civ_core.configs.loader import AppConfig
from civ_core.infra_io.standards_db import init_standards_db
from civ_core.infra_io.workspace_settings import (
    load_last_workspace,
    save_last_workspace,
)
from civ_core.ui.components.activity_bar import ActivityBar
from civ_core.ui.components.agent_panel import AgentPanel
from civ_core.ui.components.breadcrumb_bar import BreadcrumbBar
from civ_core.ui.components.project_tree import ProjectTree
from civ_core.ui.dialogs.workspace_picker import WorkspacePickerDialog
from civ_core.ui.windows.leeb_hardness_view import LeebHardnessView
from civ_core.ui.windows.pdf_tools_view import PdfToolsView
from civ_core.ui.windows.plot_curves_view import PlotCurvesView
from civ_core.ui.windows.settings_view import SettingsView, load_user_theme
from civ_core.ui.windows.word2pdf_view import Word2PdfView
from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 工具清单：(name, icon, tooltip) —— shell 自己用 name 作 stacked 的 key
_TOOLS: list[tuple[str, FluentIcon, str]] = [
    ("plot_curves", FluentIcon.MARKET, "绘曲线图"),
    ("leeb_hardness", FluentIcon.ROBOT, "里氏硬度"),
    ("pdf_tools", FluentIcon.DOCUMENT, "PDF 工具"),
    ("word2pdf", FluentIcon.SEND, "Word→PDF"),
    ("settings", FluentIcon.SETTING, "设置"),
]

# QSettings key：与窗口几何同 store
_SETTINGS_ORG = "ZGQ"
_SETTINGS_APP = "CivCore"
_KEY_GEOMETRY = "shell/geometry"
_KEY_SPLITTER = "shell/splitter"


class ShellWindow(QMainWindow):
    def __init__(self, cfg: AppConfig, workspace: Path) -> None:
        super().__init__()
        self._cfg = cfg
        self._workspace = Path(workspace)
        self.setObjectName("shellWindow")
        self.setWindowTitle(f"{cfg.app.name} — {self._workspace.name}")

        # 规范库 standards.db init（供 leeb_hardness 等工具页用）
        self._standards_db, self._standards_conn = init_standards_db()

        self._build_ui(cfg)
        self._apply_window_metrics(cfg)

        # 用户偏好的主题（settings_view 持久化的，可能比 config.toml 的还新）
        effective_theme = load_user_theme(default=cfg.ui.theme)
        if effective_theme != cfg.ui.theme:
            set_theme_runtime(effective_theme)

        # 默认进 plot_curves
        self._activity_bar.set_current("plot_curves")
        save_last_workspace(self._workspace)
        log.info("ShellWindow ready (workspace=%s)", self._workspace)

    # ── UI 装配 ──────────────────────────────────────────
    def _build_ui(self, cfg: AppConfig) -> None:
        central = QWidget(self)
        central.setObjectName("shellCentral")
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 顶栏面包屑（跨全宽）
        self._breadcrumb = BreadcrumbBar(self)
        outer.addWidget(self._breadcrumb)

        # 中部行：[ActivityBar | ProjectTree | ToolContainer | AgentPanel]
        # ActivityBar 固定 48 不进 splitter；后三栏进 splitter，用户可拖+折叠
        mid_container = QWidget(self)
        mid_h = QHBoxLayout(mid_container)
        mid_h.setContentsMargins(0, 0, 0, 0)
        mid_h.setSpacing(0)

        self._activity_bar = ActivityBar(_TOOLS, self)
        mid_h.addWidget(self._activity_bar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setObjectName("shellMainSplitter")
        self._splitter.setHandleWidth(2)
        self._splitter.setChildrenCollapsible(True)  # VSCode 风：拖到边可折叠

        # 左：常驻文件树
        self._project_tree = ProjectTree(self)
        self._project_tree.set_root(self._workspace)
        self._splitter.addWidget(self._project_tree)

        # 中：工具容器（QStackedWidget）
        self._tool_container = QStackedWidget(self)
        self._tool_container.setObjectName("toolContainer")
        self._build_tool_pages(cfg)
        self._splitter.addWidget(self._tool_container)

        # 右：Agent 占位
        self._agent_panel = AgentPanel(self)
        self._agent_panel.set_workspace(self._workspace)
        self._splitter.addWidget(self._agent_panel)

        # stretch：项目树/Agent 保持固定，中间拉伸
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        self._splitter.setSizes([220, 800, 260])

        mid_h.addWidget(self._splitter, 1)
        outer.addWidget(mid_container, 1)

        # 信号接线
        self._activity_bar.current_tool_changed.connect(self._on_tool_changed)

    def _build_tool_pages(self, cfg: AppConfig) -> None:
        """实例化各工具页；B1 阶段原样嵌入（保留各页内部布局）。"""
        self._plot_curves_page = PlotCurvesView(cfg)
        self._leeb_hardness_page = LeebHardnessView(self._standards_db)
        self._pdf_tools_page = PdfToolsView(cfg)
        self._word2pdf_page = Word2PdfView(cfg)
        effective_theme = load_user_theme(default=cfg.ui.theme)
        self._settings_page = SettingsView(initial_theme=effective_theme)

        self._pages: dict[str, QWidget] = {
            "plot_curves": self._plot_curves_page,
            "leeb_hardness": self._leeb_hardness_page,
            "pdf_tools": self._pdf_tools_page,
            "word2pdf": self._word2pdf_page,
            "settings": self._settings_page,
        }
        for w in self._pages.values():
            self._tool_container.addWidget(w)

    # ── 几何 / 持久化 ──────────────────────────────────────
    def _apply_window_metrics(self, cfg: AppConfig) -> None:
        w, h = cfg.ui.startup_size
        self.resize(w, h)
        # 比旧 MainWindow 大点：因为多了项目树和 Agent 栏
        self.setMinimumSize(900, 560)
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        geom = settings.value(_KEY_GEOMETRY)
        if geom:
            self.restoreGeometry(geom)
        else:
            self._center_on_primary_screen()
        splitter_state = settings.value(_KEY_SPLITTER)
        if splitter_state:
            self._splitter.restoreState(splitter_state)

    def _center_on_primary_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        x = avail.x() + (avail.width() - self.width()) // 2
        y = avail.y() + (avail.height() - self.height()) // 2
        self.move(max(avail.x(), x), max(avail.y(), y))

    # ── 工具切换 ──────────────────────────────────────────
    def _on_tool_changed(self, name: str) -> None:
        page = self._pages.get(name)
        if page is None:
            log.warning("未知工具：%s", name)
            return
        self._tool_container.setCurrentWidget(page)
        tool_label = next((t[2] for t in _TOOLS if t[0] == name), name)
        self._breadcrumb.set_breadcrumb(self._workspace.name, tool_label)

    # ── 关闭：保存几何 + splitter ──────────────────────────
    def closeEvent(self, event) -> None:  # type: ignore[override]
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.setValue(_KEY_GEOMETRY, self.saveGeometry())
        settings.setValue(_KEY_SPLITTER, self._splitter.saveState())
        super().closeEvent(event)


# ── 启动门槛（独立函数，方便 bootstrap.run 调用 + 测试） ─────────
def resolve_workspace_or_prompt(parent: QWidget | None = None) -> Path | None:
    """Obsidian 启动门槛：返回合法工作区路径，用户取消则 None。

    1. 读 QSettings 上次路径；仍是有效目录 → 直接返回
    2. 否则弹 WorkspacePickerDialog；用户选 / 新建 → 返回路径
    3. 用户取消 / 关闭对话框 → 返回 None（调用方应据此退出 App）
    """
    cached = load_last_workspace()
    if cached is not None:
        return cached
    dlg = WorkspacePickerDialog(parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    return dlg.selected_path()
