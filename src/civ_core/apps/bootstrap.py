"""PySide6 应用启动装配（单一 run() 入口）。

为什么独立成模块（不直接堆 main.py 里）：
  • main.py 是 CLI/GUI 的 dispatcher，它只该做「认参数 → 决定走哪条路」
  • 把"创建 QApplication / 装日志 / 拉主窗口"集中在 bootstrap，让 pytest-qt
    /未来的多窗口场景能共享同一套装配，避免重复
  • main.py 里的 GUI 分支保持懒导入：CLI 跑工具时根本不会触发 PySide6 的几百兆 import

装配顺序（出错的话尽早退出，错误信息让用户能定位）：
  1. load_config()              ← 配置错的话直接 ConfigError，根本不进 GUI
  2. setup_from_config()        ← 控制台/文件/Qt 三 sink 起来；audit logger 也搭好
  3. QApplication()             ← HiDPI 策略要在 QApplication 之前设
  4. setTheme()                 ← qfluentwidgets 的全局主题
  5. _apply_global_qss()        ← 注入"空间/层级/轻工业感"应用级 QSS
  6. MainWindow(cfg)            ← 此时再 import ui/，确保 QApplication 已存在
  7. app.exec()                 ← 阻塞主循环
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme, setThemeColor

from civ_core.configs.loader import AppConfig, load_config
from civ_core.utils.logger import get_logger, get_qt_bridge, setup_from_config

log = get_logger(__name__)

# config.toml 的 ui.theme 字符串 → qfluentwidgets 枚举
_THEME_MAP: dict[str, Theme] = {
    "auto": Theme.AUTO,
    "light": Theme.LIGHT,
    "dark": Theme.DARK,
}


def create_app(argv: list[str] | None = None) -> tuple[QApplication, AppConfig]:
    """创建 QApplication + 装日志 + 应用主题，返回 (app, cfg)。

    幂等：进程内 QApplication 是单例，重复调用会复用现有实例（pytest-qt 友好）。
    所有可能抛错的步骤（load_config / setup_from_config）都在 QApplication 之前完成，
    GUI 还没起的时候出错，命令行窗口能看到完整 traceback。
    """
    cfg = load_config()
    setup_from_config(cfg.logging, cfg.paths.logs)

    # HiDPI 策略必须在 QApplication 构造之前设，否则 Qt 直接忽略
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    existing = QApplication.instance()
    if existing is not None:
        # pytest-qt 或重入场景：复用既有 instance；类型上仍按 QApplication 处理
        app = existing  # type: ignore[assignment]
    else:
        app = QApplication(argv if argv is not None else sys.argv)

    app.setApplicationName(cfg.app.name)
    app.setApplicationVersion(cfg.app.version)
    app.setOrganizationName("CivCore")

    # 全局默认字体（从 style_preset 取 body 字号 + UI 字体族）。
    # 之后所有未显式 setFont/setStyleSheet 的控件都会跟随此值，
    # 实现"全局字号统一"——业务代码只需要写 size_subtitle / size_caption 等增量。
    _apply_global_font(app)

    setTheme(_THEME_MAP.get(cfg.ui.theme, Theme.AUTO))
    # 主题色：把 config.toml 里的 ui.accent_color (科技蓝 #0078D4) 应用到全局
    # qfluentwidgets 用这个色染主按钮、滑块、选中态、checkbox 钩等强调位
    # save=False：不写盘到 qfluentwidgets 自己的配置（避免污染用户家目录的 qfluentwidgets/config.json）
    try:
        setThemeColor(QColor(cfg.ui.accent_color), save=False, lazy=True)
    except Exception as e:
        # 非法颜色字符串：保留默认，不致命
        log.warning("ui.accent_color=%r 无效，保留默认主题色：%s", cfg.ui.accent_color, e)

    # 注入全局 QSS：按 cfg.ui.theme（'auto'/'light'/'dark'）选用深/浅 QSS。
    # 不替换 qfluentwidgets 内置样式，只追加我们 objectName 命名的容器外观。
    _apply_global_qss(app, cfg.ui.theme)

    log.info(
        "QApplication ready | name=%s version=%s theme=%s accent=%s",
        cfg.app.name,
        cfg.app.version,
        cfg.ui.theme,
        cfg.ui.accent_color,
    )
    return app, cfg  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────
# 视觉风格：深色三层 + 圆角 4px + 细分隔线 + 蓝色仅激活态
# ──────────────────────────────────────────────────────────────────
# 设计原则（用户 2026-05-14 锁定）：
#   1. 深色底：眼睛友好、工业感强、对比度高
#   2. 三层背景明确划分（视觉层级 = 深度感）：
#        L0 #161A1F  根背景（窗口最底层）
#        L1 #1E232A  面板/分组卡片（中层）
#        L2 #262C35  输入控件 / 表头 / 高亮态（顶层，最浅）
#   3. 圆角 4px（比之前 6px 收小，更克制 / 更工程感）
#   4. 细分隔线 1px，颜色 #2E343D（与 L1/L2 接近但可分辨）
#   5. 蓝色 #0078D4 **仅在激活态出现**：focus / checked / selected / hover /
#      pressed / 当前 tab；非激活态用灰阶。这样视觉焦点清晰，不喧宾夺主。
#
# 文本色：
#   主文字 #D9DEE5（浅灰）/ 次文字 #8B92A0（中灰）/ 占位 #5B6573（深灰）
#
# Token 来源：VSCode Dark+ theme（github.com/microsoft/vscode）。
# 层次：activityBar #181818（最深）→ sideBar/editor #1F1F1F → input #313131。
# 选中蓝 #094771 / focus 边 #007FD4 / 文本 #CCCCCC / 次文本 #969696。
# 字号：UI 13px（≈10pt @96dpi），紧凑无圆角，VSCode 视觉密度。
_APP_QSS_DARK = """
/* ============================================================
   全局基底
   ============================================================ */
QWidget {
    background-color: #1F1F1F;
    color: #CCCCCC;
}
QMainWindow#shellWindow,
QWidget#shellCentral {
    background-color: #1F1F1F;
}

/* ============================================================
   顶栏面包屑（VSCode 风极简）
   ============================================================ */
QFrame#breadcrumbBar {
    background-color: #181818;
    border-bottom: 1px solid #2B2B2B;
}
QLabel#breadcrumbText {
    color: #969696;
    font-size: 12px;
    background: transparent;
}

/* ============================================================
   Activity Bar 48px 最深色侧栏
   ============================================================ */
QFrame#activityBar {
    background-color: #181818;
    border-right: 1px solid #2B2B2B;
}
QFrame#activityBar QToolButton {
    background-color: transparent;
    color: #858585;
    border: none;
    border-left: 2px solid transparent;  /* 占位防选中态高度跳 */
    margin: 0;
    padding: 0;
}
QFrame#activityBar QToolButton:hover {
    color: #FFFFFF;
}
QFrame#activityBar QToolButton:checked {
    color: #FFFFFF;
    border-left: 2px solid #007FD4;       /* VSCode 风激活指示条 */
}

/* ============================================================
   Side Bar（资源管理器：header + 文件树）
   ============================================================ */
QFrame#projectTree {
    background-color: #1F1F1F;
    border-right: 1px solid #2B2B2B;
}
QWidget#sidebarHeader {
    background-color: #1F1F1F;
    border-bottom: 1px solid #2B2B2B;
}
QLabel#sidebarHeaderTitle {
    color: #BBBBBB;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
    background: transparent;
}
QToolButton#sidebarHeaderBtn {
    background-color: transparent;
    color: #858585;
    border: none;
    border-radius: 3px;
}
QToolButton#sidebarHeaderBtn:hover {
    background-color: #2A2D2E;
    color: #FFFFFF;
}
QToolButton#sidebarHeaderBtn:pressed {
    background-color: #094771;
}

/* 文件树本体 */
QTreeView#projectTreeView {
    background-color: #1F1F1F;
    color: #CCCCCC;
    border: none;
    outline: 0;
    font-size: 13px;
    show-decoration-selected: 1;
}
QTreeView#projectTreeView::item {
    padding: 1px 0;
    border: none;
}
QTreeView#projectTreeView::item:hover {
    background-color: #2A2D2E;
}
QTreeView#projectTreeView::item:selected {
    background-color: #094771;
    color: #FFFFFF;
}
QTreeView#projectTreeView::item:selected:!active {
    background-color: #37373D;
}

/* Empty state（VSCode 风欢迎页） */
QWidget#projectTreeEmpty {
    background-color: #1F1F1F;
}
QLabel#projectTreeEmptyHint {
    color: #969696;
    font-size: 12px;
    background: transparent;
}

/* ============================================================
   QPushButton 通用（VSCode 蓝色 primary + 次按钮）
   ============================================================ */
QPushButton {
    background-color: #0E639C;
    color: #FFFFFF;
    border: none;
    border-radius: 2px;
    padding: 4px 14px;
    font-size: 12px;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #1177BB;
}
QPushButton:pressed {
    background-color: #0B5587;
}
QPushButton:disabled {
    background-color: #3A3A3A;
    color: #6E7681;
}
/* 次按钮（用 property=variant="secondary" 标记） */
QPushButton[variant="secondary"] {
    background-color: #2D2D2D;
    color: #CCCCCC;
    border: 1px solid #3C3C3C;
}
QPushButton[variant="secondary"]:hover {
    background-color: #3A3A3A;
}

/* ============================================================
   主 Splitter handle：极细 1px，hover 才显蓝
   ============================================================ */
QSplitter#shellMainSplitter::handle {
    background-color: #2B2B2B;
}
QSplitter#shellMainSplitter::handle:hover {
    background-color: #007FD4;
}

/* ============================================================
   保留工具页内部既有 splitter 样式（不破坏 plot_curves 内部布局）
   ============================================================ */
QSplitter#plotCurvesSplitter::handle:horizontal,
QSplitter#plotCurvesRightSplitter::handle:vertical {
    background-color: #2B2B2B;
}
QSplitter#plotCurvesSplitter::handle:horizontal:hover,
QSplitter#plotCurvesRightSplitter::handle:vertical:hover {
    background-color: #007FD4;
}

/* ============================================================
   工具页根 widget（plotCurvesPage / pdfToolsPage / 等）：与编辑器同色
   ============================================================ */
QWidget#plotCurvesPage,
QWidget#pdfToolsPage,
QWidget#word2pdfPage,
QWidget#homePage,
QWidget#settingsPage,
QStackedWidget#toolContainer {
    background-color: #1F1F1F;
}

/* 工具页内部面板层 */
QWidget#presetAccordionContent,
QWidget#plotCurvesRightColumn,
QWidget#bottomTabPanel,
QWidget#livePreviewPane {
    background-color: #1F1F1F;
}

/* 折叠分组卡片 */
QWidget[objectName^="collapsibleSection_"] {
    background-color: #252526;
    border: 1px solid #2B2B2B;
    border-radius: 3px;
    margin: 2px 2px;
}
QWidget[objectName^="collapsibleSection_"] > QWidget#collapsibleHeader {
    background: transparent;
    border: none;
    padding: 5px 8px;
    border-bottom: 1px solid transparent;
}
QWidget[objectName^="collapsibleSection_"] > QWidget#collapsibleHeader:hover {
    background: #2A2D2E;
    border-bottom: 1px solid #2B2B2B;
}
QLabel#collapsibleTitle {
    font-weight: 600;
    letter-spacing: 0.3px;
    color: #CCCCCC;
    background: transparent;
}
QLabel#collapsibleArrow {
    color: #858585;
    font-weight: 700;
    background: transparent;
}
QWidget#collapsibleHeader:hover QLabel#collapsibleArrow {
    color: #007FD4;
}

/* 预览图容器 */
QLabel#livePreviewImage {
    background-color: #181818;
    border: 1px solid #2B2B2B;
    border-radius: 3px;
}

QLabel {
    color: #CCCCCC;
    background: transparent;
}

/* ============================================================
   输入控件
   ============================================================ */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #313131;
    color: #CCCCCC;
    border: 1px solid #3C3C3C;
    border-radius: 2px;
    padding: 2px 6px;
    selection-background-color: #094771;
    selection-color: #FFFFFF;
    min-height: 20px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #007FD4;
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: #6E7681;
    background-color: #252526;
    border: 1px solid #2B2B2B;
}
QSpinBox, QDoubleSpinBox {
    font-family: "Cascadia Mono", "Consolas", "JetBrains Mono", monospace;
}

/* ============================================================
   表格
   ============================================================ */
QTableView {
    background-color: #1F1F1F;
    alternate-background-color: #252526;
    color: #CCCCCC;
    gridline-color: #2B2B2B;
    border: 1px solid #2B2B2B;
    border-radius: 2px;
    font-family: "Cascadia Mono", "Consolas", "JetBrains Mono", monospace;
    selection-background-color: #094771;
    selection-color: #FFFFFF;
}
QHeaderView::section {
    background-color: #252526;
    color: #CCCCCC;
    border: none;
    border-right: 1px solid #2B2B2B;
    border-bottom: 1px solid #2B2B2B;
    padding: 4px 8px;
    font-weight: 500;
    font-size: 12px;
}

/* ============================================================
   滚动条 - VSCode 极细透明
   ============================================================ */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: #424242;
    border-radius: 0;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #4F4F4F; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #424242;
    border-radius: 0;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #4F4F4F; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ============================================================
   QTabWidget（B2 底部 Tab 会用到，先打底）
   ============================================================ */
QTabWidget::pane {
    border-top: 1px solid #2B2B2B;
    background: #1F1F1F;
    top: -1px;
}
QTabBar::tab {
    background: #2D2D2D;
    color: #969696;
    padding: 4px 12px;
    border: none;
    margin: 0;
    font-size: 12px;
}
QTabBar::tab:selected {
    background: #1F1F1F;
    color: #FFFFFF;
    border-bottom: 1px solid #007FD4;
}
QTabBar::tab:hover:!selected {
    color: #CCCCCC;
}
"""


# ──────────────────────────────────────────────────────────────────
# 浅色版（同结构，三层色与深色对偶）：
#   L0 #F4F6F9 (根) / L1 #FFFFFF (面板) / L2 #EEF1F5 (输入控件/表头)
#   分隔线 #DCE0E5；文字主 #1F2933 / 次 #5B6573
#   蓝色 #0078D4 同样仅用于激活态（focus/hover/checked/selected）
# 与深色保持对称设计，唯一差别是颜色 token。
# ──────────────────────────────────────────────────────────────────
_APP_QSS_LIGHT = """
QWidget#plotCurvesPage,
QWidget#pdfToolsPage,
QWidget#word2pdfPage,
QWidget#homePage,
QWidget#settingsPage {
    background-color: #F4F6F9;
}

QWidget#presetAccordionContent,
QWidget#plotCurvesRightColumn,
QWidget#bottomTabPanel,
QWidget#livePreviewPane {
    background-color: #FFFFFF;
}

QWidget[objectName^="collapsibleSection_"] {
    background-color: #FAFBFC;
    border: 1px solid #DCE0E5;
    border-radius: 4px;
    margin: 3px 2px;
}

QWidget[objectName^="collapsibleSection_"] > QWidget#collapsibleHeader {
    background: transparent;
    border: none;
    padding: 7px 10px;
    border-bottom: 1px solid transparent;
}
QWidget[objectName^="collapsibleSection_"] > QWidget#collapsibleHeader:hover {
    background: #EEF1F5;
    border-bottom: 1px solid #DCE0E5;
}
QLabel#collapsibleTitle {
    font-weight: 600;
    letter-spacing: 0.5px;
    color: #1F2933;
    background: transparent;
}
QLabel#collapsibleArrow {
    color: #8B92A0;
    font-weight: 700;
    background: transparent;
}
QWidget#collapsibleHeader:hover QLabel#collapsibleArrow {
    color: #0078D4;
}

QSplitter#plotCurvesSplitter::handle:horizontal,
QSplitter#plotCurvesRightSplitter::handle:vertical {
    background-color: #DCE0E5;
}
QSplitter#plotCurvesSplitter::handle:horizontal:hover,
QSplitter#plotCurvesRightSplitter::handle:vertical:hover {
    background-color: #0078D4;
}

QLabel#livePreviewImage {
    background-color: #FAFBFC;
    border: 1px solid #DCE0E5;
    border-radius: 4px;
}

QLabel {
    color: #1F2933;
    background: transparent;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #FFFFFF;
    color: #1F2933;
    border: 1px solid #DCE0E5;
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: #0078D4;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #0078D4;
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: #8B92A0;
    background-color: #F4F6F9;
    border: 1px solid #E5E8EC;
}

QSpinBox, QDoubleSpinBox {
    font-family: "Consolas", "Cascadia Mono", "Menlo", "DejaVu Sans Mono", monospace;
}

QTableView {
    background-color: #FFFFFF;
    alternate-background-color: #F8F9FB;
    color: #1F2933;
    gridline-color: #E5E8EC;
    border: 1px solid #DCE0E5;
    border-radius: 4px;
    font-family: "Consolas", "Cascadia Mono", "Menlo", "DejaVu Sans Mono", monospace;
    selection-background-color: #0078D4;
    selection-color: #FFFFFF;
}
QHeaderView::section {
    background-color: #EEF1F5;
    color: #364152;
    border: none;
    border-right: 1px solid #DCE0E5;
    border-bottom: 1px solid #DCE0E5;
    padding: 4px 8px;
    font-weight: 600;
}

QScrollBar:vertical {
    background: #F4F6F9;
    width: 8px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: #DCE0E5;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #0078D4;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: #F4F6F9;
    height: 8px;
    margin: 0;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #DCE0E5;
    border-radius: 3px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #0078D4;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: transparent;
}
"""


def _apply_global_font(app: QApplication) -> None:
    """把 style_preset.yaml 里的 body 字号 + UI 字体族设为 QApplication 默认。

    为什么不直接写 QSS 选择器 `* { font: ... }`：QSS 通配符性能差且会被 qfluentwidgets
    内部样式覆盖；QApplication.setFont 是 Qt 推荐的"全局默认"入口，
    优先级低于任何具体 setFont/setStyleSheet，能被局部样式干净覆盖。
    """
    try:
        # 延迟 import：style_loader 链路涉及 config + yaml，启动早期 import 安全但不强求
        from civ_core.infra_io.style_loader import load_style_preset

        sty = load_style_preset()
        families = [s.strip().strip("'\"") for s in sty.typography.font_family_ui.split(",")]
        f = QFont()
        f.setFamilies(families)
        f.setPointSize(sty.typography.size_body)
        app.setFont(f)
        log.info(
            "全局字体应用：family=%s size=%dpt",
            ", ".join(families[:2]),
            sty.typography.size_body,
        )
    except Exception as e:
        log.warning("应用全局字体失败（保留 Qt 默认）：%s", e)


def _resolve_effective_theme(theme_name: str) -> str:
    """把 cfg.ui.theme（'auto'/'light'/'dark'）解析为实际生效的 'light' 或 'dark'。

    auto 模式下，借 qfluentwidgets.isDarkTheme()（它已读了系统主题 + setTheme
    的当前值）来判断。这样我们的 QSS 和 qfluentwidgets 内置样式总是同步。
    """
    name = (theme_name or "auto").lower()
    if name == "light":
        return "light"
    if name == "dark":
        return "dark"
    # auto：跟随 qfluentwidgets 当前状态
    try:
        from qfluentwidgets import isDarkTheme

        return "dark" if isDarkTheme() else "light"
    except Exception:
        return "dark"  # 极端兜底（默认深色，与之前一致）


# 保存原始 qfluentwidgets QSS（不含我们注入的），用于切主题时重新拼接
_ORIGINAL_FW_QSS: str | None = None


def _apply_global_qss(app: QApplication, theme_name: str = "auto") -> None:
    """把当前主题对应的 QSS 注入 QApplication.styleSheet。

    设计要点：
      • 第一次调用时记下"qfluentwidgets 已注入的原始 QSS"作为 baseline
      • 后续每次切主题，先重置回 baseline，再追加目标主题的 QSS ——
        避免上次主题的 QSS 残留覆盖
      • 这样 _apply_global_qss(app, "light") → _apply_global_qss(app, "dark")
        能干净切换，不会越叠越多
    """
    global _ORIGINAL_FW_QSS
    if _ORIGINAL_FW_QSS is None:
        _ORIGINAL_FW_QSS = app.styleSheet() or ""

    effective = _resolve_effective_theme(theme_name)
    qss = _APP_QSS_DARK if effective == "dark" else _APP_QSS_LIGHT
    app.setStyleSheet(_ORIGINAL_FW_QSS + "\n" + qss)


def set_theme_runtime(theme_name: str) -> None:
    """运行时切换主题（深/浅/自动），立即应用到当前 QApplication。

    设置页的 RadioButton 选中后调用本函数。流程：
      1. setTheme(qfluentwidgets) → 切内置控件配色
      2. _apply_global_qss → 重置 + 追加新主题的 QSS
    持久化由调用方负责（QSettings 或 config.toml 写回）。
    """
    app = QApplication.instance()
    if app is None:
        log.warning("set_theme_runtime: 没有活跃 QApplication，跳过")
        return
    setTheme(_THEME_MAP.get(theme_name, Theme.AUTO))
    _apply_global_qss(app, theme_name)
    log.info("主题已切换为 %s", theme_name)


def run(argv: list[str] | None = None) -> int:
    """启动 GUI 主循环，返回事件循环退出码（与 sys.exit 兼容）。

    Obsidian 启动门槛：进 shell 之前必须先解析出一个合法 workspace 路径；
    用户取消则 return 0 而不进 app.exec()（不显示空壳窗口）。
    """
    app, cfg = create_app(argv)

    # shell 在 create_app 之后再 import：确保 QApplication 已存在 +
    # 避免 ui/ 模块在配置错误时被加载（错误信息更干净）
    from civ_core.ui.windows.shell_window import ShellWindow, initial_workspace

    # VSCode 风：不弹模态对话框；有上次 workspace 就加载，没有就进 empty state
    window = ShellWindow(cfg, initial_workspace())
    window.show()

    # QtLogBridge 已经在 setup_from_config 里建好了；
    # 各工具页在构造时通过 get_qt_bridge() 自取并接到 LogPanel.on_record。
    bridge = get_qt_bridge()
    if bridge is not None:
        log.info("QtLogBridge 就绪（已接到日志面板）")

    return app.exec()
