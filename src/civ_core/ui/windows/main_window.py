"""主窗口骨架（FluentWindow + 顶层导航）。

第二阶段渐进式填充：
  Step 8（当前）：搭起骨架 + 注册导航项；每个工具页用 _PlaceholderPage 占位
  Step 9         绘曲线图页换成 plot_curves_view.py（真三栏布局）
  Step 10–13    模板列表 / 设置面板 / 异步执行 / InfoBar 异常提示

为什么用 FluentWindow 而不是 MSFluentWindow：
  • FluentWindow 是默认/通用样式，左侧导航条 + 顶部标题栏，跨 Win10/11 表现稳定
  • MSFluentWindow 需要 Mica/Acrylic，对部分系统主题不友好
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, FluentWindow, NavigationItemPosition

from civ_core.apps.bootstrap import set_theme_runtime
from civ_core.configs.loader import AppConfig
from civ_core.core.project_service import ProjectService
from civ_core.infra_io.project_db import ProjectDB
from civ_core.ui.windows.pdf_tools_view import PdfToolsView
from civ_core.ui.windows.plot_curves_view import PlotCurvesView
from civ_core.ui.windows.project_board_view import ProjectBoardView
from civ_core.ui.windows.settings_view import SettingsView, load_user_theme
from civ_core.ui.windows.word2pdf_view import Word2PdfView
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


class _PlaceholderPage(QWidget):
    """占位页：居中标题 + 副标题，告诉开发者这里"谁来填、什么时候填"。

    qfluentwidgets 的导航栈用每个 page 的 objectName 做 routing key —— 必须显式设，
    否则 addSubInterface 会报 assertion 失败。
    """

    def __init__(self, object_name: str, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName(object_name)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)

        big = QLabel(title, self)
        big.setStyleSheet("font-size: 28px; font-weight: 600;")
        big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(big)

        if subtitle:
            small = QLabel(subtitle, self)
            small.setStyleSheet("font-size: 14px; color: #888;")
            small.setAlignment(Qt.AlignmentFlag.AlignCenter)
            small.setWordWrap(True)
            layout.addWidget(small)


class MainWindow(FluentWindow):
    """应用主窗口。

    持有 cfg 是为了让子页能读 paths.* / ui.* —— 子页通过构造参数拿到自己关心的字段，
    不直接 import config，避免循环依赖。
    """

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self._cfg = cfg

        self._build_pages(cfg)
        self._register_navigation()
        self._apply_window_metrics(cfg)
        # Win11 Mica 毛玻璃：自动 fallback 到 Acrylic（Win10）或纯色（更低）；
        # qfluentwidgets ≥ 1.7 提供 setMicaEffectEnabled。任何异常都不致命 ——
        # 没有毛玻璃也能用，只是少了视觉层次
        try:
            self.setMicaEffectEnabled(True)
        except Exception as e:
            log.warning("启用 Mica 毛玻璃失败（系统/版本不支持，已忽略）：%s", e)

        # 默认落在首页
        self.switchTo(self.home_page)
        log.info("MainWindow ready (size=%dx%d)", *cfg.ui.startup_size)

    # ── 构造 ──────────────────────────────────────────────────────
    def _build_pages(self, cfg: AppConfig) -> None:
        # 项目看板：默认主页（Linear 风格，列表/看板可切换）
        db_path = Path("~/.civ-core/projects.db").expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        db = ProjectDB(conn)
        db.create_tables()
        svc = ProjectService(db)
        self.home_page = ProjectBoardView(svc)
        self.home_page.setObjectName("homePage")
        # 绘曲线图页：三栏视图（步骤 9 已接入；子面板内容在 step 10/11/13 渐进填充）
        self.plot_curves_page = PlotCurvesView(cfg)
        # PDF 工具页（合并 + 拆分）
        self.pdf_tools_page = PdfToolsView(cfg)
        # Word → PDF 批量转换页
        self.word2pdf_page = Word2PdfView(cfg)
        # 设置页：用户级主题覆盖优先；如果 QSettings 有覆盖值就用它，否则用
        # config.toml 的默认（cfg.ui.theme）。Radio 的初始选中态按当前生效值。
        effective_theme = load_user_theme(default=cfg.ui.theme)
        self.settings_page = SettingsView(initial_theme=effective_theme)
        # 如果用户级覆盖与 config 默认不一致，启动时立即套用一次（避免首屏
        # 显示出与用户偏好不符的主题）
        if effective_theme != cfg.ui.theme:
            set_theme_runtime(effective_theme)

    def _register_navigation(self) -> None:
        # 顶部：工具页
        self.addSubInterface(self.home_page, FluentIcon.HOME, "项目看板")
        self.addSubInterface(self.plot_curves_page, FluentIcon.MARKET, "绘曲线图")
        self.addSubInterface(self.pdf_tools_page, FluentIcon.DOCUMENT, "PDF 工具")
        self.addSubInterface(self.word2pdf_page, FluentIcon.SEND, "Word→PDF")
        # 底部：辅助项
        self.addSubInterface(
            self.settings_page,
            FluentIcon.SETTING,
            "设置",
            position=NavigationItemPosition.BOTTOM,
        )

    def _apply_window_metrics(self, cfg: AppConfig) -> None:
        self.setWindowTitle(cfg.app.name)
        w, h = cfg.ui.startup_size
        self.resize(w, h)
        # 显式给一个保守的最小尺寸：让用户从右下角 / 右边缘往内拖时能真正缩小，
        # 而不被子组件累加的 sizeHint 顶住。720×480 已能完整看到导航 + 左栏 +
        # 一个最低限度的预览/底栏；再小排版会塌但 Qt 自身仍能正常处理。
        self.setMinimumSize(720, 480)
        # 优先从 QSettings 恢复上次的窗口几何；首次启动则居中主屏
        settings = QSettings("ZGQ", "CivCore")
        geom = settings.value("mainwindow/geometry")
        if geom:
            self.restoreGeometry(geom)
        else:
            self._center_on_primary_screen()

    def _center_on_primary_screen(self) -> None:
        """把窗口移到主屏可用区域中心（任务栏 / Dock 之外的区域）。"""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        x = avail.x() + (avail.width() - self.width()) // 2
        y = avail.y() + (avail.height() - self.height()) // 2
        self.move(max(avail.x(), x), max(avail.y(), y))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """保存窗口几何到 QSettings，供下次启动 restoreGeometry 恢复。"""
        settings = QSettings("ZGQ", "CivCore")
        settings.setValue("mainwindow/geometry", self.saveGeometry())
        super().closeEvent(event)
