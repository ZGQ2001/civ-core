"""全局 UI 样式预设契约。

设计：
  • 三个嵌套 frozen dataclass：Typography / Colors / Dimensions
  • 默认值就是「系统预设」的兜底，找不到 yaml 也能正常跑
  • 用户预设（~/.civ-core/presets/ui/style_preset.yaml）覆盖子键，
    缺失字段保留默认值
  • 不引 pydantic / yaml 库依赖，纯 Python dataclass

为什么不在 configs/loader.py 里加：
  • configs 走 toml；UI 样式走 yaml，分文件清晰
  • 主题相关字段未来会扩展（暗色主题、字号缩放等），单独一层好演进
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Typography:
    """字体族 + 字号。

    font_family_ui      — 比例字体（中文名称、按钮文字）
    font_family_mono    — 等宽字体（编号 / 金额 / 日期 / 进度 等数据列）
    """

    font_family_ui: str = "'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif"
    font_family_mono: str = "'JetBrains Mono', 'Consolas', monospace"
    size_title: int = 18
    size_subtitle: int = 14
    size_body: int = 12
    size_caption: int = 11
    size_small: int = 10


@dataclass(frozen=True, slots=True)
class Colors:
    """语义化颜色。

    分类：
      primary / danger — 强调色
      text_*           — 文字色（主/次/弱）
      border           — 描边
      bg_*             — 背景色（默认/交替/表头/抽屉/悬停）
      status_*         — 项目状态色（待办/进行/完成/暂存/归档）
    """

    primary: str = "#1976D2"
    primary_hover: str = "#1565C0"
    danger: str = "#E53935"
    danger_hover: str = "#C62828"
    text_primary: str = "#212121"
    text_secondary: str = "#757575"
    text_tertiary: str = "#9E9E9E"
    border: str = "#E0E0E0"
    bg: str = "#FFFFFF"
    bg_alt: str = "#F8F9FA"
    bg_header: str = "#F0F0F0"
    bg_drawer: str = "#FAFAFA"
    bg_hover: str = "#F5F8FF"
    status_pending: str = "#9E9E9E"
    status_active: str = "#1976D2"
    status_done: str = "#43A047"
    status_on_hold: str = "#FB8C00"
    status_archived: str = "#616161"


@dataclass(frozen=True, slots=True)
class Dimensions:
    """通用尺寸（圆角 / 间距 / 控件高度）。"""

    radius: int = 4
    spacing_sm: int = 4
    spacing_md: int = 8
    spacing_lg: int = 12
    spacing_xl: int = 16
    button_height: int = 30
    header_height: int = 32


@dataclass(frozen=True, slots=True)
class StylePreset:
    """根样式预设。所有 UI 组件应通过 load_style_preset() 拿到。"""

    typography: Typography = field(default_factory=Typography)
    colors: Colors = field(default_factory=Colors)
    dimensions: Dimensions = field(default_factory=Dimensions)
