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

    # 注入全局 QSS（空间感 + 层级感 + 轻工业感）—— 不替换 qfluentwidgets 内置样式，
    # 只补充我们 objectName 命名的容器外观（卡片化分组、细线条边框、冷灰背景等）。
    _apply_global_qss(app)

    log.info(
        "QApplication ready | name=%s version=%s theme=%s accent=%s",
        cfg.app.name,
        cfg.app.version,
        cfg.ui.theme,
        cfg.ui.accent_color,
    )
    return app, cfg  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────
# 视觉风格：空间感 + 层级感 + 轻工业感
# ──────────────────────────────────────────────────────────────────
# 设计原则（向用户解释「为什么这么改」）：
#   1. 空间感 —— splitter handle 加粗 + 分组之间留细分隔线 + 卡片有抬起阴影
#   2. 层级感 —— 主面板浅冷灰 (#F4F6F9)，卡片白底；分组标题强 weight + 字间距
#   3. 轻工业感 —— 数字输入框等宽字体（Consolas/Menlo/Cascadia）+ 细线边框
#                  (#DCE0E5) + 微圆角 (4px) + 表头浅浅描边
#
# 选择器都加 objectName，避免误覆盖 qfluentwidgets 内部控件的样式。
_APP_QSS = """
/* ── 主面板背景：略冷的金属浅灰（#F4F6F9 比纯白多一丝工业感） ── */
QWidget#presetAccordionContent,
QWidget#plotCurvesRightColumn,
QWidget#bottomTabPanel,
QWidget#livePreviewPane {
    background-color: #F4F6F9;
}

/* ── 分组卡片：白底圆角 + 细线 + 间距，制造"层"的视觉 ── */
QWidget[objectName^="collapsibleSection_"] {
    background-color: #FFFFFF;
    border: 1px solid #DCE0E5;
    border-radius: 6px;
    margin: 4px 2px;
}

/* 分组标题按钮：去掉 Python 字符串里写的 border-bottom（与卡片边框冲突），
   改为更克制的左侧色条（科技蓝），右侧大字间距 */
QWidget[objectName^="collapsibleSection_"] > QToolButton {
    background: transparent;
    border: none;
    border-left: 3px solid #0078D4;
    padding: 7px 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: #1F2933;
    text-align: left;
}
QWidget[objectName^="collapsibleSection_"] > QToolButton:hover {
    background: rgba(0,120,212,0.06);
}

/* ── splitter handle：4px 不够明显，改为带中线视觉的细带 ── */
QSplitter#plotCurvesSplitter::handle:horizontal,
QSplitter#plotCurvesRightSplitter::handle:vertical {
    background-color: #DCE0E5;
}
QSplitter#plotCurvesSplitter::handle:horizontal:hover,
QSplitter#plotCurvesRightSplitter::handle:vertical:hover {
    background-color: #0078D4;
}

/* ── 实时预览图容器：内嵌细描边 + 浅底，给图一个"画框" ── */
QLabel#livePreviewImage {
    background-color: #FAFBFC;
    border: 1px solid #DCE0E5;
    border-radius: 4px;
}

/* ── 数字字段：等宽字体（轻工业感最关键的一笔） ── */
QSpinBox, QDoubleSpinBox {
    font-family: "Consolas", "Cascadia Mono", "Menlo", "DejaVu Sans Mono", monospace;
}

/* ── 数据源表格：等宽数字 + 浅灰表头 ── */
QTableView {
    font-family: "Consolas", "Cascadia Mono", "Menlo", "DejaVu Sans Mono", monospace;
    gridline-color: #E5E8EC;
}
QHeaderView::section {
    background-color: #EEF1F5;
    border: none;
    border-right: 1px solid #DCE0E5;
    border-bottom: 1px solid #DCE0E5;
    padding: 4px 6px;
    font-weight: 600;
    color: #364152;
}
"""


def _apply_global_qss(app: QApplication) -> None:
    """把 _APP_QSS 注入 QApplication.styleSheet 之上（追加而非覆盖）。

    追加策略：qfluentwidgets 的内置样式表已经在 setTheme/setThemeColor 之后
    挂到 app 上。我们用 `existing + _APP_QSS` 而不是 setStyleSheet(_APP_QSS)，
    避免把 qfluentwidgets 自己的钩刷掉（按钮 hover、滑块滑道等）。
    """
    existing = app.styleSheet() or ""
    app.setStyleSheet(existing + "\n" + _APP_QSS)


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
