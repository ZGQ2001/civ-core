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
from PySide6.QtGui import QColor
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
# 选择器都加 objectName，避免误覆盖 qfluentwidgets 内部控件的样式。
_APP_QSS_DARK = """
/* ──────────────────────────────────────────────────────────────
   L0 根背景：窗口主体 / 各页根 widget
   ────────────────────────────────────────────────────────────── */
QWidget#plotCurvesPage,
QWidget#pdfToolsPage,
QWidget#word2pdfPage,
QWidget#homePage,
QWidget#settingsPage {
    background-color: #161A1F;
}

/* ──────────────────────────────────────────────────────────────
   L1 面板层：参数面板内容区 / 右栏 / 底栏 / 预览容器
   ────────────────────────────────────────────────────────────── */
QWidget#presetAccordionContent,
QWidget#plotCurvesRightColumn,
QWidget#bottomTabPanel,
QWidget#livePreviewPane {
    background-color: #1E232A;
}

/* ──────────────────────────────────────────────────────────────
   分组卡片：L1 底上的卡片，比 L1 略深 (#1A1F26) 制造"凹陷"层级
   圆角收小到 4px；分隔用细线 #2E343D，不再用左侧蓝色条占位
   ────────────────────────────────────────────────────────────── */
QWidget[objectName^="collapsibleSection_"] {
    background-color: #1A1F26;
    border: 1px solid #2E343D;
    border-radius: 4px;
    margin: 3px 2px;
}

/* 分组标题栏：默认无蓝色，仅 hover/expand 态有微妙强调。
   _SectionHeader（QWidget）+ 内含固定宽度箭头 QLabel + 弹性 title QLabel。 */
QWidget[objectName^="collapsibleSection_"] > QWidget#collapsibleHeader {
    background: transparent;
    border: none;
    padding: 7px 10px;
    border-bottom: 1px solid transparent;  /* 占位防 hover 时高度跳 */
}
QWidget[objectName^="collapsibleSection_"] > QWidget#collapsibleHeader:hover {
    background: #232932;          /* 比 L1 卡片略浅 */
    border-bottom: 1px solid #2E343D;
}
/* 标题文字：浅灰主色 + 微字间距 */
QLabel#collapsibleTitle {
    font-weight: 600;
    letter-spacing: 0.5px;
    color: #D9DEE5;
    background: transparent;
}
/* 箭头：默认灰，仅当鼠标 hover 在 header 上时变蓝（激活态） */
QLabel#collapsibleArrow {
    color: #6B7280;
    font-weight: 700;
    background: transparent;
}
QWidget#collapsibleHeader:hover QLabel#collapsibleArrow {
    color: #0078D4;
}

/* ──────────────────────────────────────────────────────────────
   Splitter handle：默认与 L1 同色（看不出来），hover 才显出蓝色
   ────────────────────────────────────────────────────────────── */
QSplitter#plotCurvesSplitter::handle:horizontal,
QSplitter#plotCurvesRightSplitter::handle:vertical {
    background-color: #2E343D;
}
QSplitter#plotCurvesSplitter::handle:horizontal:hover,
QSplitter#plotCurvesRightSplitter::handle:vertical:hover {
    background-color: #0078D4;
}

/* ──────────────────────────────────────────────────────────────
   实时预览图容器：深色"画框" —— L0 底色 + 细描边
   ────────────────────────────────────────────────────────────── */
QLabel#livePreviewImage {
    background-color: #14181D;
    border: 1px solid #2E343D;
    border-radius: 4px;
}

/* ──────────────────────────────────────────────────────────────
   通用文本：BodyLabel 默认色（次级文字）
   ────────────────────────────────────────────────────────────── */
QLabel {
    color: #D9DEE5;
    background: transparent;
}

/* ──────────────────────────────────────────────────────────────
   输入控件：L2 浅色底 / 圆角 4 / 细描边 / focus 才显蓝边
   ────────────────────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #262C35;
    color: #E1E5EA;
    border: 1px solid #2E343D;
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: #0078D4;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #0078D4;   /* 激活态才变蓝 —— 关键约束 */
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: #5B6573;
    background-color: #1B2026;
    border: 1px solid #262C35;
}

/* 数字字段统一等宽字体（工程感关键一笔） */
QSpinBox, QDoubleSpinBox {
    font-family: "Consolas", "Cascadia Mono", "Menlo", "DejaVu Sans Mono", monospace;
}

/* ──────────────────────────────────────────────────────────────
   表格：L1 底 / 表头 L2 / 选中行用蓝（激活态）
   ────────────────────────────────────────────────────────────── */
QTableView {
    background-color: #1A1F26;
    alternate-background-color: #1E232A;
    color: #D9DEE5;
    gridline-color: #2E343D;
    border: 1px solid #2E343D;
    border-radius: 4px;
    font-family: "Consolas", "Cascadia Mono", "Menlo", "DejaVu Sans Mono", monospace;
    selection-background-color: #0078D4;
    selection-color: #FFFFFF;
}
QHeaderView::section {
    background-color: #262C35;
    color: #B8BFC9;
    border: none;
    border-right: 1px solid #2E343D;
    border-bottom: 1px solid #2E343D;
    padding: 4px 8px;
    font-weight: 600;
}

/* ──────────────────────────────────────────────────────────────
   滚动条：细窄设计 —— 因为 PresetAccordionPanel 启用了 always-on，
   做得越细越不抢戏；hover 时才有蓝色提示
   ────────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #1E232A;
    width: 8px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: #2E343D;
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
    background: #1E232A;
    height: 8px;
    margin: 0;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #2E343D;
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
    """启动 GUI 主循环，返回事件循环退出码（与 sys.exit 兼容）。"""
    app, cfg = create_app(argv)

    # 主窗口在 create_app 之后再 import：确保 QApplication 已存在 +
    # 避免 ui/ 模块在配置错误时被加载（错误信息更干净）
    from civ_core.ui.windows.main_window import MainWindow

    window = MainWindow(cfg)
    window.show()

    # QtLogBridge 已经在 setup_from_config 里建好了；
    # PlotCurvesView 在构造时通过 get_qt_bridge() 自取并接到 LogPanel.on_record。
    bridge = get_qt_bridge()
    if bridge is not None:
        log.info("QtLogBridge 就绪（已接到日志面板）")

    return app.exec()
