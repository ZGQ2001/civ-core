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
  5. MainWindow(cfg)            ← 此时再 import ui/，确保 QApplication 已存在
  6. app.exec()                 ← 阻塞主循环
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

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

    log.info(
        "QApplication ready | name=%s version=%s theme=%s",
        cfg.app.name,
        cfg.app.version,
        cfg.ui.theme,
    )
    return app, cfg  # type: ignore[return-value]


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
