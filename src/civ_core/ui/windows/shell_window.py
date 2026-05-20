"""ShellWindow：QMainWindow 主壳（VSCode Dark+ 风）。

布局：
  ┌──────── BreadcrumbBar 28px：项目名 / 当前工具 ─────────┬─[工具按钮]┐
  ├──┬──────────────────────────┬───────────────────────────────────────┤
  │图│ 资源管理器  [打开新刷折] │                                       │
  │标├──────────────────────────┤  ToolContainer (QStackedWidget)       │
  │轨│  文件树 / empty 欢迎页   │  当前工具页                            │
  │道│                          │  (B2 才拆上下二段)                     │
  │48│                          │                                       │
  └──┴──────────────────────────┴───────────────────────────────────────┘

VSCode 设计要点：
  - 顶栏只有面包屑文字（小号、灰色），不放大按钮
  - 「打开/新建/刷新/折叠」放在 Side Bar header（贴近资源管理器，跟 VSCode 一致）
  - Activity Bar 选中态：左侧 2px 蓝色 indicator（QSS 控制）
  - 默认无 Agent 侧栏（占位空壳 B1 阶段隐藏，等真 UI-4 接入再加回）
  - 工具页 lazy 构造：用户切到才造，减少拖动 splitter 时多页同时 relayout 卡顿

启动行为：
  - 不弹模态对话框；有 last_workspace → 自动加载，否则 empty state
  - 用户在 Side Bar header 或 empty state 切换工作区
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon

from civ_core.apps.bootstrap import set_theme_runtime
from civ_core.configs.loader import AppConfig
from civ_core.infra_io.standards_db import init_standards_db
from civ_core.infra_io.workspace_scaffold import create_standard_structure
from civ_core.infra_io.workspace_settings import (
    load_last_workspace,
    save_last_workspace,
)
from civ_core.ui.components.activity_bar import ActivityBar
from civ_core.ui.components.breadcrumb_bar import BreadcrumbBar
from civ_core.ui.components.project_tree import ProjectTree
from civ_core.ui.windows.settings_view import load_user_theme
from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 工具清单：(name, icon, tooltip)
_TOOLS: list[tuple[str, FluentIcon, str]] = [
    ("plot_curves", FluentIcon.MARKET, "绘曲线图"),
    ("leeb_hardness", FluentIcon.ROBOT, "里氏硬度"),
    ("pdf_tools", FluentIcon.DOCUMENT, "PDF 工具"),
    ("word2pdf", FluentIcon.SEND, "Word→PDF"),
    ("settings", FluentIcon.SETTING, "设置"),
]

_SETTINGS_ORG = "ZGQ"
_SETTINGS_APP = "CivCore"
_KEY_GEOMETRY = "shell/geometry"
_KEY_SPLITTER = "shell/splitter"


class ShellWindow(QMainWindow):
    def __init__(self, cfg: AppConfig, workspace: Path | None = None) -> None:
        super().__init__()
        self._cfg = cfg
        self._workspace: Path | None = None
        self.setObjectName("shellWindow")

        # 规范库 standards.db init（供 leeb_hardness 等用，工具构造时按需访问）
        self._standards_db, self._standards_conn = init_standards_db()

        self._build_ui(cfg)
        self._apply_window_metrics(cfg)

        effective_theme = load_user_theme(default=cfg.ui.theme)
        if effective_theme != cfg.ui.theme:
            set_theme_runtime(effective_theme)

        # 默认进 plot_curves（触发 lazy 构造默认页）
        self._activity_bar.set_current("plot_curves")

        if workspace is not None and Path(workspace).is_dir():
            self._load_workspace(Path(workspace))
        else:
            self._update_breadcrumb()
            log.info("ShellWindow ready (无工作区)")

    # ── UI 装配 ──────────────────────────────────────────
    def _build_ui(self, cfg: AppConfig) -> None:
        central = QWidget(self)
        central.setObjectName("shellCentral")
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 顶栏面包屑（小号灰色文字，无按钮）
        self._breadcrumb = BreadcrumbBar(central)
        outer.addWidget(self._breadcrumb)

        # 中部行：[ActivityBar | Splitter [ProjectTree | ToolContainer]]
        mid = QWidget(central)
        mid_h = QHBoxLayout(mid)
        mid_h.setContentsMargins(0, 0, 0, 0)
        mid_h.setSpacing(0)

        self._activity_bar = ActivityBar(_TOOLS, mid)
        mid_h.addWidget(self._activity_bar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, mid)
        self._splitter.setObjectName("shellMainSplitter")
        self._splitter.setHandleWidth(1)
        self._splitter.setChildrenCollapsible(False)
        # opaqueResize=False：拖动时只显示分隔条幻影，松手才更新内容；
        # 这是修复 B1 拖动卡顿的关键 —— 工具页内部还有自己的 QSplitter +
        # matplotlib canvas 等重控件，实时 resize 在 Qt 下会很卡。
        # VSCode 看似实时是 Web 渲染层效率，Qt 做不到同等性能，退让到松手刷新。
        self._splitter.setOpaqueResize(False)

        self._project_tree = ProjectTree(self._splitter)
        self._splitter.addWidget(self._project_tree)

        self._tool_container = QStackedWidget(self._splitter)
        self._tool_container.setObjectName("toolContainer")
        self._setup_lazy_tools(cfg)
        self._splitter.addWidget(self._tool_container)

        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([240, 1000])

        mid_h.addWidget(self._splitter, 1)
        outer.addWidget(mid, 1)

        # 信号接线
        self._activity_bar.current_tool_changed.connect(self._on_tool_changed)
        self._project_tree.open_folder_requested.connect(self._on_open_folder_clicked)
        self._project_tree.create_workspace_requested.connect(self._on_new_workspace_clicked)

    # ── Lazy 工具页：placeholder + factory，用户切到才造 ────
    def _setup_lazy_tools(self, cfg: AppConfig) -> None:
        # 工厂表：所有工具页的延迟构造函数
        # 延迟 import 避免启动早期加载 matplotlib / openpyxl 等重模块
        self._page_factories: dict[str, Callable[[], QWidget]] = {
            "plot_curves": lambda: self._make_plot_curves(cfg),
            "leeb_hardness": lambda: self._make_leeb(cfg),
            "pdf_tools": lambda: self._make_pdf(cfg),
            "word2pdf": lambda: self._make_word2pdf(cfg),
            "settings": lambda: self._make_settings(cfg),
        }
        # 已构造的工具页缓存
        self._pages: dict[str, QWidget] = {}
        # placeholder index：每个 name 对应 QStackedWidget 里的固定 index
        self._page_indices: dict[str, int] = {}
        for name in self._page_factories.keys():
            ph = QWidget()
            ph.setObjectName(f"toolPlaceholder_{name}")
            self._page_indices[name] = self._tool_container.addWidget(ph)

    def _make_plot_curves(self, cfg: AppConfig) -> QWidget:
        from civ_core.ui.windows.plot_curves_view import PlotCurvesView

        return PlotCurvesView(cfg)

    def _make_leeb(self, cfg: AppConfig) -> QWidget:
        from civ_core.ui.windows.leeb_hardness_view import LeebHardnessView

        return LeebHardnessView(self._standards_db)

    def _make_pdf(self, cfg: AppConfig) -> QWidget:
        from civ_core.ui.windows.pdf_tools_view import PdfToolsView

        return PdfToolsView(cfg)

    def _make_word2pdf(self, cfg: AppConfig) -> QWidget:
        from civ_core.ui.windows.word2pdf_view import Word2PdfView

        return Word2PdfView(cfg)

    def _make_settings(self, cfg: AppConfig) -> QWidget:
        from civ_core.ui.windows.settings_view import SettingsView

        effective_theme = load_user_theme(default=cfg.ui.theme)
        return SettingsView(initial_theme=effective_theme)

    def _ensure_page(self, name: str) -> QWidget | None:
        """工具页 lazy 构造：第一次需要时才造，造完替换原 placeholder。"""
        if name in self._pages:
            return self._pages[name]
        factory = self._page_factories.get(name)
        if factory is None:
            return None
        log.info("延迟构造工具页：%s", name)
        page = factory()
        self._pages[name] = page
        idx = self._page_indices[name]
        old = self._tool_container.widget(idx)
        self._tool_container.removeWidget(old)
        if old is not None:
            old.deleteLater()
        self._tool_container.insertWidget(idx, page)
        return page

    # ── 几何 / 持久化 ──────────────────────────────────────
    def _apply_window_metrics(self, cfg: AppConfig) -> None:
        w, h = cfg.ui.startup_size
        self.resize(w, h)
        self.setMinimumSize(820, 520)
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
        page = self._ensure_page(name)
        if page is None:
            log.warning("未知工具：%s", name)
            return
        self._tool_container.setCurrentIndex(self._page_indices[name])
        self._update_breadcrumb(tool_name=name)

    def _update_breadcrumb(self, tool_name: str | None = None) -> None:
        if tool_name is None:
            tool_name = self._activity_bar.current()
        tool_label = next((t[2] for t in _TOOLS if t[0] == tool_name), tool_name)
        ws_label = self._workspace.name if self._workspace is not None else "未打开工作区"
        self._breadcrumb.set_breadcrumb(ws_label, tool_label)

    # ── 工作区切换 ────────────────────────────────────────
    def _load_workspace(self, root: Path) -> None:
        self._workspace = root
        self._project_tree.set_root(root)
        save_last_workspace(root)
        self.setWindowTitle(f"{self._cfg.app.name} — {root.name}")
        self._update_breadcrumb()
        log.info("已加载工作区：%s", root)

    def _on_open_folder_clicked(self) -> None:
        start_dir = str(self._workspace.parent if self._workspace else Path.home())
        d = QFileDialog.getExistingDirectory(self, "打开工作区文件夹", start_dir)
        if not d:
            return
        self._load_workspace(Path(d))

    def _on_new_workspace_clicked(self) -> None:
        """选父目录 → 输项目名 → 创建标准骨架 → 加载。

        B1 老 bug：QInputDialog.getText 第 4 参是 echoMode，之前错传
        Qt.WindowType.Dialog 让输入框打不开，"没反应"的根因。已修正。
        """
        start_dir = str(self._workspace.parent if self._workspace else Path.home())
        parent_dir = QFileDialog.getExistingDirectory(
            self, "选择父目录（项目将在此目录下创建）", start_dir
        )
        if not parent_dir:
            return
        name, ok = QInputDialog.getText(self, "新建标准项目", "项目文件夹名：")
        if not ok or not name.strip():
            return
        root = Path(parent_dir) / name.strip()
        try:
            create_standard_structure(root)
        except OSError as e:
            QMessageBox.critical(self, "创建失败", f"无法创建项目文件夹：\n{e}")
            return
        self._load_workspace(root)

    # ── 关闭 ──────────────────────────────────────────
    def closeEvent(self, event) -> None:  # type: ignore[override]
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.setValue(_KEY_GEOMETRY, self.saveGeometry())
        settings.setValue(_KEY_SPLITTER, self._splitter.saveState())
        super().closeEvent(event)


def initial_workspace() -> Path | None:
    """VSCode 风启动：返回 last_workspace；不存在 / 无效返回 None。"""
    return load_last_workspace()
