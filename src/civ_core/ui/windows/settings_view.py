"""设置页：用户可调节的全局选项。

当前覆盖：
  • 外观主题（深色 / 浅色 / 跟随系统）—— 立即生效 + QSettings 持久化

持久化策略
==========
不写回 config.toml（loader.py 没提供 save_config），改用 QSettings 存用户
选择。两条路径：
  • config.toml `ui.theme` —— 项目级"默认"主题（git 维护）
  • QSettings `ui/theme` —— 用户级"覆盖"主题（每台机器独立）
启动时 cfg.ui.theme 是项目默认；如果 QSettings 有覆盖值，则在主窗口构造
完成后立即用 set_theme_runtime 套用一次。

后续扩展位置
============
本视图保留扩展空间：可加"启动尺寸/语言/日志级别"等条目，统一走 QSettings
持久化 + 运行时立即生效模式（避免重启）。
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    RadioButton,
    StrongBodyLabel,
    SubtitleLabel,
)

from civ_core.apps.bootstrap import set_theme_runtime
from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# QSettings key：用户级主题覆盖
_SETTINGS_ORG = "ZGQ"
_SETTINGS_APP = "CivCore"
_SETTINGS_KEY_THEME = "ui/theme"
_SETTINGS_KEY_PROJECT_DIR = "projects/default_root_dir"

# 三档主题 token 与用户可见标签的映射
_THEME_OPTIONS: tuple[tuple[str, str, str], ...] = (
    # (token, 标签, 副标题/说明)
    ("light", "浅色", "白底浅灰，适合白天 / 强光环境"),
    ("dark", "深色", "深底冷灰，适合夜间 / 长时间编辑"),
    ("auto", "跟随系统", "按 Windows 设置切换；改系统主题后重启应用生效"),
)


def load_user_theme(default: str = "auto") -> str:
    """读 QSettings 里的用户主题覆盖；没有 → default。

    供主窗口构造完成后调用一次，将运行时主题对齐到用户偏好。
    """
    v = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SETTINGS_KEY_THEME)
    if not v:
        return default
    s = str(v).lower()
    if s in {"light", "dark", "auto"}:
        return s
    return default


def save_user_theme(theme: str) -> None:
    """把用户选择写入 QSettings（每台机器独立）。"""
    QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(_SETTINGS_KEY_THEME, theme)


def load_project_root_dir(default: str = "") -> str:
    v = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SETTINGS_KEY_PROJECT_DIR)
    if not v:
        return default
    return str(v)


def save_project_root_dir(path: str) -> None:
    QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(_SETTINGS_KEY_PROJECT_DIR, path)


class SettingsView(QWidget):
    """设置页根视图。

    布局：标题 + 主题选项卡片（3 个 RadioButton + 副标题说明）+ 占位扩展位
    """

    def __init__(self, initial_theme: str = "auto", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # objectName 与 main_window 旧 placeholder 一致，导航 routing 不变
        self.setObjectName("settingsPage")
        self._radios: dict[str, RadioButton] = {}
        self._build_layout(initial_theme)

    def _build_layout(self, initial_theme: str) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.setSpacing(20)

        # 页面标题
        title = SubtitleLabel("设置", self)
        outer.addWidget(title)

        # ── 外观主题 ─────────────────────────────────────────────
        section_label = StrongBodyLabel("外观主题", self)
        outer.addWidget(section_label)

        hint = BodyLabel("切换立即生效，自动保存到本机配置。", self)
        hint.setStyleSheet("color: #8B92A0;")
        outer.addWidget(hint)

        group = QButtonGroup(self)
        for token, label, sub in _THEME_OPTIONS:
            row = QHBoxLayout()
            row.setContentsMargins(8, 0, 0, 0)
            row.setSpacing(10)

            radio = RadioButton(label, self)
            radio.setChecked(token == initial_theme)
            # lambda 闭包陷阱：用默认参数固定当前 token
            radio.toggled.connect(lambda checked, t=token: self._on_theme_radio(checked, t))
            self._radios[token] = radio
            group.addButton(radio)
            row.addWidget(radio)

            sub_label = BodyLabel(f"— {sub}", self)
            sub_label.setStyleSheet("color: #8B92A0;")
            sub_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(sub_label, 1)

            outer.addLayout(row)

        # ── 项目管理 ─────────────────────────────────────────────
        proj_label = StrongBodyLabel("项目管理", self)
        outer.addWidget(proj_label)

        hint2 = BodyLabel("新建项目时的默认保存文件夹。", self)
        hint2.setStyleSheet("color: #8B92A0;")
        outer.addWidget(hint2)

        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(8, 0, 0, 0)
        folder_row.setSpacing(10)

        self._folder_edit = QLineEdit(self)
        saved_dir = load_project_root_dir()
        self._folder_edit.setText(saved_dir)
        self._folder_edit.setPlaceholderText("未设置（默认创建时不自动生成文件夹）")
        self._folder_edit.setReadOnly(True)
        self._folder_edit.setStyleSheet(
            "QLineEdit { font-size: 12px; padding: 6px; border: 1px solid #E0E0E0; "
            "border-radius: 4px; background: #F5F5F5; }"
        )
        folder_row.addWidget(self._folder_edit)

        btn_browse = QPushButton("浏览...", self)
        btn_browse.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 6px 16px; border: 1px solid #E0E0E0; "
            "border-radius: 4px; } QPushButton:hover { border-color: #1976D2; }"
        )
        btn_browse.clicked.connect(self._on_browse_project_dir)
        folder_row.addWidget(btn_browse)

        outer.addLayout(folder_row)

        # 末尾 stretch：内容靠顶
        outer.addStretch(1)

    def _on_browse_project_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择默认项目保存位置", self._folder_edit.text())
        if d:
            self._folder_edit.setText(d)
            save_project_root_dir(d)
            log.info("默认项目文件夹已更新: %s", d)

    def _on_theme_radio(self, checked: bool, token: str) -> None:
        """用户切换主题：QSettings 持久化 + 运行时立即应用。"""
        if not checked:
            return
        log.info("用户切换主题：%s", token)
        save_user_theme(token)
        set_theme_runtime(token)


__all__ = ["SettingsView", "load_user_theme", "save_user_theme", "load_project_root_dir", "save_project_root_dir"]
