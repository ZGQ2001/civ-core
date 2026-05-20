"""ShellWindow：QMainWindow 主壳（VSCode 风）。

布局（横向，顶栏跨全宽）：
  ┌──────────────────── BreadcrumbBar（顶栏，跨全宽）──────────────────────┐
  │ [📁打开][➕新建]  项目名 › 当前工具                       [工具按钮位] │
  ├──────────────────────────────────────────────────────────────────────┤
  │ Activity │ ProjectTree │ ToolContainer (QStackedWidget) │  AgentPanel │
  │  Bar 48  │  常驻        │  当前工具页（B2 才拆上下二段）  │   占位空壳  │
  └──────────────────────────────────────────────────────────────────────┘

启动行为（VSCode 风）：
  - 启动时 **不弹模态对话框**；直接进 shell
  - 有 last_workspace → 自动加载文件树
  - 无 workspace → 项目树栏显示 empty state（"未打开工作区" + 两个按钮）
  - 顶栏左侧常驻 [打开文件夹] [新建标准结构]，随时切换工作区

为什么弃 FluentWindow：
  - FluentWindow 的 page 是整块区域，无法做跨 page 共享外壳
  - QMainWindow + 自己的 ActivityBar 自由度高，也更接近 VSCode 风
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
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
from civ_core.ui.components.agent_panel import AgentPanel
from civ_core.ui.components.breadcrumb_bar import BreadcrumbBar
from civ_core.ui.components.project_tree import ProjectTree
from civ_core.ui.windows.leeb_hardness_view import LeebHardnessView
from civ_core.ui.windows.pdf_tools_view import PdfToolsView
from civ_core.ui.windows.plot_curves_view import PlotCurvesView
from civ_core.ui.windows.settings_view import SettingsView, load_user_theme
from civ_core.ui.windows.word2pdf_view import Word2PdfView
from civ_core.utils.logger import get_logger

log = get_logger(__name__)

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
        self._workspace: Path | None = None  # _load_workspace 会更新
        self.setObjectName("shellWindow")

        # 规范库 standards.db init（供 leeb_hardness 等工具页用）
        self._standards_db, self._standards_conn = init_standards_db()

        self._build_ui(cfg)
        self._apply_window_metrics(cfg)

        # 用户偏好的主题
        effective_theme = load_user_theme(default=cfg.ui.theme)
        if effective_theme != cfg.ui.theme:
            set_theme_runtime(effective_theme)

        # 默认进 plot_curves
        self._activity_bar.set_current("plot_curves")

        # 工作区初始化：有则加载，否则 empty state
        if workspace is not None and Path(workspace).is_dir():
            self._load_workspace(Path(workspace))
        else:
            self._update_breadcrumb()  # 空状态也刷一次面包屑
            log.info("ShellWindow ready (无工作区，等待用户打开)")

    # ── UI 装配 ──────────────────────────────────────────
    def _build_ui(self, cfg: AppConfig) -> None:
        central = QWidget(self)
        central.setObjectName("shellCentral")
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 顶栏面包屑（跨全宽）+ leading 区"打开文件夹/新建"按钮
        self._breadcrumb = BreadcrumbBar(central)
        outer.addWidget(self._breadcrumb)

        btn_open = QPushButton("📁 打开", self._breadcrumb)
        btn_open.setObjectName("shellOpenBtn")
        btn_open.setToolTip("打开已有工作区文件夹")
        btn_open.clicked.connect(self._on_open_folder_clicked)
        self._breadcrumb.add_leading_action(btn_open)

        btn_new = QPushButton("➕ 新建", self._breadcrumb)
        btn_new.setObjectName("shellNewBtn")
        btn_new.setToolTip("新建标准项目结构")
        btn_new.clicked.connect(self._on_new_workspace_clicked)
        self._breadcrumb.add_leading_action(btn_new)

        # 中部行：[ActivityBar | Splitter [ProjectTree | ToolContainer | AgentPanel]]
        mid_container = QWidget(central)
        mid_h = QHBoxLayout(mid_container)
        mid_h.setContentsMargins(0, 0, 0, 0)
        mid_h.setSpacing(0)

        # ActivityBar：parent 给 mid_container，避免 layout reparent 混乱
        self._activity_bar = ActivityBar(_TOOLS, mid_container)
        mid_h.addWidget(self._activity_bar)

        # Splitter：parent 也给 mid_container；handle 加粗一点便于拖动
        self._splitter = QSplitter(Qt.Orientation.Horizontal, mid_container)
        self._splitter.setObjectName("shellMainSplitter")
        self._splitter.setHandleWidth(4)
        # B1 阶段先关掉子组件 collapsible：避免拖到 0 视觉上"反向"
        self._splitter.setChildrenCollapsible(False)
        # opaqueResize=True：拖动时实时刷新（VSCode 行为），否则只有松手才更新
        self._splitter.setOpaqueResize(True)

        # 内部三栏：parent 设为 splitter（addWidget 也会 reparent，但显式更安全）
        self._project_tree = ProjectTree(self._splitter)
        self._splitter.addWidget(self._project_tree)

        self._tool_container = QStackedWidget(self._splitter)
        self._tool_container.setObjectName("toolContainer")
        self._build_tool_pages(cfg)
        self._splitter.addWidget(self._tool_container)

        self._agent_panel = AgentPanel(self._splitter)
        self._splitter.addWidget(self._agent_panel)

        # stretch：必须在 setSizes 之前，否则 setSizes 会决定初始比例，stretch 仅在 resize 时生效
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        self._splitter.setSizes([240, 800, 260])

        mid_h.addWidget(self._splitter, 1)
        outer.addWidget(mid_container, 1)

        # 信号接线
        self._activity_bar.current_tool_changed.connect(self._on_tool_changed)
        self._project_tree.open_folder_requested.connect(self._on_open_folder_clicked)
        self._project_tree.create_workspace_requested.connect(self._on_new_workspace_clicked)

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
        self._update_breadcrumb(tool_name=name)

    def _update_breadcrumb(self, tool_name: str | None = None) -> None:
        if tool_name is None:
            tool_name = self._activity_bar.current()
        tool_label = next((t[2] for t in _TOOLS if t[0] == tool_name), tool_name)
        ws_label = self._workspace.name if self._workspace is not None else "未打开工作区"
        self._breadcrumb.set_breadcrumb(ws_label, tool_label)

    # ── 工作区切换 ────────────────────────────────────────
    def _load_workspace(self, root: Path) -> None:
        """切换/加载工作区：刷新文件树 + 持久化 + 面包屑 + 窗口标题 + Agent。"""
        self._workspace = root
        self._project_tree.set_root(root)
        self._agent_panel.set_workspace(root)
        save_last_workspace(root)
        self.setWindowTitle(f"{self._cfg.app.name} — {root.name}")
        self._update_breadcrumb()
        log.info("已加载工作区：%s", root)

    def _on_open_folder_clicked(self) -> None:
        """[打开文件夹] 按钮 / 项目树 empty state 的同名按钮触发。"""
        start_dir = str(self._workspace.parent if self._workspace else Path.home())
        d = QFileDialog.getExistingDirectory(self, "打开工作区文件夹", start_dir)
        if not d:
            return
        self._load_workspace(Path(d))

    def _on_new_workspace_clicked(self) -> None:
        """[新建标准结构]：选父目录 → 输项目名 → 创建骨架 → 加载。

        Bug 修复：QInputDialog.getText 不能把 Qt.WindowType.Dialog 当 echoMode 传 —— 那是
        EchoMode 位置，传错会导致对话框完全打不开（之前 B1 的 bug）。
        """
        start_dir = str(self._workspace.parent if self._workspace else Path.home())
        parent_dir = QFileDialog.getExistingDirectory(
            self,
            "选择父目录（项目将在此目录下创建）",
            start_dir,
        )
        if not parent_dir:
            return
        # 注意：getText 这里只传 parent/title/label，不传 echoMode（会被错当参数）
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

    # ── 关闭：保存几何 + splitter ──────────────────────────
    def closeEvent(self, event) -> None:  # type: ignore[override]
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.setValue(_KEY_GEOMETRY, self.saveGeometry())
        settings.setValue(_KEY_SPLITTER, self._splitter.saveState())
        super().closeEvent(event)


# ── 启动 helper：bootstrap.run 用这个拿初始 workspace（None = empty state） ──
def initial_workspace() -> Path | None:
    """VSCode 风：返回 last_workspace 路径，不存在 / 无效则返回 None。

    不再弹模态对话框 —— None 时 ShellWindow 会进入 empty state，
    用户在主窗口里点"打开文件夹/新建"按钮切换工作区。
    """
    return load_last_workspace()
