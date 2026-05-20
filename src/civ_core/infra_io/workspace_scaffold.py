"""标准项目文件夹骨架生成。

为什么独立成模块：
  - 业务约定（4 个顶层子文件夹）+ 应用约定（.civ-core/）的唯一定义点；
    其他层引用常量而不是各自硬编码
  - 全部用 mkdir(exist_ok=True) 实现幂等：已存在的文件夹不报错，缺失的补齐；
    多次调用安全（用户在 UI 上重复点"生成标准结构"也不会出错）
  - 不在此处做"删除多余文件 / 校验骨架是否完整"等高阶行为，那些属于上层逻辑

约定来源：参考用户提供的实际项目目录（2026_03_26_门头沟…一号地块）的顶层结构。
"""

from __future__ import annotations

from pathlib import Path

# 顶层业务子文件夹（命名照用户实际项目目录搬来，是检测内业的通用约定）
STANDARD_SUBFOLDERS: tuple[str, ...] = (
    "委托方提供资料",
    "数据",
    "报告",
    "模板",
)

# 应用专属隐藏目录（默认在文件树里隐藏，避免污染业务目录视图）
APP_DOTFOLDER = ".civ-core"

# 应用专属子目录（styles 为项目级样式预设；outputs 为应用生成的中间产物）
APP_SUBFOLDERS: tuple[str, ...] = (
    "styles",
    "outputs",
)


def create_standard_structure(root: Path) -> Path:
    """在 root 下建立标准项目骨架；root 自身缺失也会一并 mkdir。

    幂等：已存在的目录不报错，缺失的补齐；用户已经放进去的文件原样保留。

    Args:
        root: 项目根目录路径。

    Returns:
        root（便于链式调用）。

    Raises:
        OSError: 当 root 路径已被一个非目录文件占用时，由 Path.mkdir 抛出。
    """
    root = Path(root)
    # parents=True：父目录不存在自动建；exist_ok=True：已有目录不报错。
    # 但若 root 路径已是一个文件，Path.mkdir 仍会抛 FileExistsError（OSError 子类），
    # 这是我们期望的行为——上层应当感知到，而不是静默把文件路径当目录用。
    root.mkdir(parents=True, exist_ok=True)
    for name in STANDARD_SUBFOLDERS:
        (root / name).mkdir(exist_ok=True)
    app_root = root / APP_DOTFOLDER
    app_root.mkdir(exist_ok=True)
    for sub in APP_SUBFOLDERS:
        (app_root / sub).mkdir(exist_ok=True)
    return root
