"""统一的 QSS 拼装入口，所有项目管理 UI 共用。

设计：
  • 不导出全局 sty 单例 —— 每次 qss_* 调用都现取 load_style_preset()，
    用户改完 yaml 调 reload_style_preset() 后下次构建生效
  • 只覆盖出现 2 次以上的样式片段；一次性样式直接在调用点拼接
  • 不与 plot_curves 等其他工具共用（避免一个模块改动牵连不相干工具）
"""

from __future__ import annotations

from civ_core.infra_io.style_loader import load_style_preset


def qss_title_label() -> str:
    s = load_style_preset()
    return (
        f"font-size: {s.typography.size_title}px; font-weight: bold; "
        f"color: {s.colors.text_primary};"
    )


def qss_segmented_button() -> str:
    """筛选按钮（全部 / 正在进行 / 暂存 / 已归档 等 SegmentedWidget 风格）。"""
    s = load_style_preset()
    return (
        f"QPushButton {{ border: 1px solid {s.colors.border}; "
        f"border-radius: {s.dimensions.radius}px; "
        f"padding: 0 {s.dimensions.spacing_lg}px; "
        f"font-size: {s.typography.size_body}px; background: {s.colors.bg}; }}"
        f"QPushButton:checked {{ background: {s.colors.primary}; color: white; "
        f"border-color: {s.colors.primary}; }}"
    )


def qss_view_toggle_button() -> str:
    """视图切换按钮（列表 / 看板），与 segmented 风格略不同（深灰高亮）。"""
    s = load_style_preset()
    return (
        f"QPushButton {{ border: 1px solid {s.colors.border}; "
        f"border-radius: {s.dimensions.radius}px; "
        f"padding: 0 {s.dimensions.spacing_md + 2}px; "
        f"font-size: {s.typography.size_body}px; background: {s.colors.bg}; }}"
        "QPushButton:checked { background: #424242; color: white; }"
    )


def qss_primary_button() -> str:
    """主操作按钮（如「+ 新建项目」）。"""
    s = load_style_preset()
    return (
        f"QPushButton {{ background: {s.colors.primary}; color: white; border: none; "
        f"border-radius: {s.dimensions.radius}px; "
        f"padding: 0 {s.dimensions.spacing_xl}px; "
        f"font-size: {s.typography.size_caption}px; }}"
        f"QPushButton:hover {{ background: {s.colors.primary_hover}; }}"
    )


def qss_table() -> str:
    """QTableView + QHeaderView 样式（项目看板表格）。"""
    s = load_style_preset()
    return (
        f"QTableView {{ border: none; background: {s.colors.bg}; "
        f"alternate-background-color: {s.colors.bg_alt}; }}"
        f"QTableView::item {{ padding: {s.dimensions.spacing_sm}px "
        f"{s.dimensions.spacing_md - 2}px; }}"
        f"QHeaderView::section {{ background: {s.colors.bg_header}; border: none; "
        f"border-bottom: 1px solid {s.colors.border}; "
        f"padding: {s.dimensions.spacing_md - 2}px {s.dimensions.spacing_md - 2}px; "
        f"font-size: {s.typography.size_caption}px; font-weight: bold; "
        f"color: {s.colors.text_secondary}; }}"
    )


def qss_card() -> str:
    """看板卡片样式。"""
    s = load_style_preset()
    return (
        f"QFrame {{ background: {s.colors.bg}; "
        f"border: 1px solid {s.colors.border}; "
        f"border-radius: {s.dimensions.radius}px; "
        f"padding: {s.dimensions.spacing_md}px; }}"
        f"QFrame:hover {{ border-color: {s.colors.primary}; "
        f"background: {s.colors.bg_hover}; }}"
    )
