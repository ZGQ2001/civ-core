"""预设管理器：合并系统预设 + 用户预设，对外暴露统一的"运行时预设列表"。

设计要点
========
  • 系统预设（只读，随程序发布）
      - 路径：`cfg.paths.curve_presets`（即 `presets/<tool>/curve_presets.json`）
      - 由开发者通过 git 维护，**程序运行时禁止写入**
  • 用户预设（可写，用户自定义）
      - 路径：`cfg.paths.user_presets_dir / <tool>/curve_presets.json`
      - dev.enabled=true  → 仓库内 `tests/fixtures/presets/<tool>/...`（git 管理）
      - dev.enabled=false → `~/.civil_auto_workspace/presets/<tool>/...`（最终用户场景）
  • 合并语义（顶层"预设名"key 级别，**不递归到预设内部字段**）
      - 系统预设全部保留，按文件原序
      - 用户预设里**同名**键 → 覆盖系统预设对应项（保留在系统位置上，source 标为 USER）
      - 用户预设里**异名**键 → 追加到列表末尾（按文件原序）
      - 不做"用户只覆盖部分字段"的递归合并：用户复制整张系统预设后改完保存，
        避免"用户改了 y_axis 但系统又升级了 curves 字段"这种半残合成态
  • 兜底
      - 用户预设文件不存在 → 当作空字典处理，**不抛异常**
      - 用户预设 JSON 语法错 → log warning + 当作空字典，**不让用户预设把整个工具搞挂**
      - 系统预设文件不存在 / 语法错 → 抛 `PresetError`（致命，必须修）
  • 写保护
      - 本模块**只读**。写入用户预设由 T-4 的预设编辑器实现，
        统一走 `infra_io.file_manager.atomic_writer` 防破损

为什么不直接放 `core/plot_curves.py`
====================================
  • core/ 不得直接读写文件（v2.3 总纲）
  • 多工具复用：今后 word2pdf / auto_filler 等工具的预设也走同一套合并逻辑
  • 测试隔离：preset_manager 的合并语义是纯函数（除了 IO 入口），可单独测
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from civil_auto.configs.loader import load_config
from civil_auto.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# 异常
# ──────────────────────────────────────────────────────────────────
class PresetError(RuntimeError):
    """预设管理器异常。

    抛的场景：系统预设文件缺失 / JSON 语法错。
    用户预设侧的任何问题都走兜底，不抛异常（理由：用户改坏了自己的预设，
    不能让整个程序起不来；只在日志里 warning，UI 上回退到只显示系统预设）。
    """

    hint: str

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


# ──────────────────────────────────────────────────────────────────
# 数据类型
# ──────────────────────────────────────────────────────────────────
class PresetSource(Enum):
    """预设来源。UI 用它显示 🔒（系统）/ ✏️（用户）图标和决定能否编辑。"""

    SYSTEM = "system"  # 来自 presets/，只读
    USER = "user"  # 来自用户目录，可写


@dataclass(frozen=True, slots=True)
class PresetEntry:
    """单条合并后的预设。

    字段：
      name    预设名（JSON 顶层 key）
      data    预设内容（即 JSON 该 key 对应的 value，整张 dict）
      source  来源：SYSTEM 还是 USER
              UI 据此决定显示 🔒/✏️、是否启用"保存修改"按钮
    """

    name: str
    data: dict[str, Any]
    source: PresetSource


# ──────────────────────────────────────────────────────────────────
# 工具→文件映射（镜像系统预设的目录结构 presets/<tool>/<file>.json）
# ──────────────────────────────────────────────────────────────────
# 各工具在 user_presets_dir 下的相对路径。
# 当前只有 plot_curves；接入 word2pdf / auto_filler 等工具时在此追加。
_USER_PRESET_FILES: dict[str, str] = {
    "plot_curves": "plot_curves/curve_presets.json",
}


# ──────────────────────────────────────────────────────────────────
# 公共 API
# ──────────────────────────────────────────────────────────────────
def get_system_presets_path(tool: str = "plot_curves") -> Path:
    """系统预设文件的绝对路径。当前所有工具共用 cfg.paths.curve_presets 的口子，
    待接入新工具时这里改成按 tool 分发。"""
    cfg = load_config()
    if tool == "plot_curves":
        return cfg.paths.curve_presets
    raise PresetError(
        f"未知工具：{tool!r}",
        hint=f"已知工具：{list(_USER_PRESET_FILES.keys())}",
    )


def get_user_presets_path(tool: str = "plot_curves") -> Path:
    """用户预设文件的绝对路径（不保证文件存在；目录由 loader 已自动 mkdir）。

    返回值结构：`<user_presets_dir>/<tool>/curve_presets.json`，与系统预设镜像。
    用户预设文件本身不在这里创建——T-4 预设编辑器写入时再原子落盘。
    """
    cfg = load_config()
    if tool not in _USER_PRESET_FILES:
        raise PresetError(
            f"未知工具：{tool!r}",
            hint=f"已知工具：{list(_USER_PRESET_FILES.keys())}",
        )
    return cfg.paths.user_presets_dir / _USER_PRESET_FILES[tool]


def load_merged_presets(tool: str = "plot_curves") -> list[PresetEntry]:
    """加载并合并系统预设 + 用户预设，返回有序 PresetEntry 列表。

    顺序规则：
      1. 系统预设按 JSON 文件原序遍历
      2. 同名被用户覆盖时：保留位置，source 改成 USER，data 用用户的
      3. 用户独有的预设（异名）：按 JSON 文件原序追加到末尾

    "_" 开头的注释 key（如 "_comment"、"_field_doc"）一律过滤。
    """
    system_raw = _read_json_strict(get_system_presets_path(tool))
    user_raw = _read_json_lenient(get_user_presets_path(tool))

    return _merge(system_raw, user_raw)


def load_merged_presets_as_dict(tool: str = "plot_curves") -> dict[str, dict[str, Any]]:
    """合并后扁平化成 `{name: data}` dict，丢弃 source 信息。

    给只关心"取某个名字对应的预设"的调用方用（比如 core.plot_curves.run_plot_curves
    只需要按名字查 data，不在乎来自系统还是用户）。
    """
    return {e.name: e.data for e in load_merged_presets(tool)}


# ──────────────────────────────────────────────────────────────────
# 内部：合并核心（纯函数，单测直接用）
# ──────────────────────────────────────────────────────────────────
def _merge(
    system_raw: dict[str, Any],
    user_raw: dict[str, Any],
) -> list[PresetEntry]:
    """纯计算的合并函数。把 system_raw / user_raw 这两个原始 JSON dict
    合并成有序 PresetEntry 列表。"_" 开头的 key 过滤。

    分离出来是为了让单元测试不依赖文件系统：直接喂两个 dict 即可断言合并结果。
    """
    user_names = {k for k in user_raw if not k.startswith("_")}
    consumed_user_names: set[str] = set()
    merged: list[PresetEntry] = []

    # 第一遍：按系统顺序遍历
    for name, data in system_raw.items():
        if name.startswith("_"):
            continue
        if name in user_names:
            # 同名覆盖：保留系统位置，data 改成用户的，source = USER
            merged.append(
                PresetEntry(
                    name=name,
                    data=user_raw[name],
                    source=PresetSource.USER,
                )
            )
            consumed_user_names.add(name)
        else:
            merged.append(
                PresetEntry(
                    name=name,
                    data=data,
                    source=PresetSource.SYSTEM,
                )
            )

    # 第二遍：用户独有的预设按用户文件原序追加
    for name, data in user_raw.items():
        if name.startswith("_"):
            continue
        if name in consumed_user_names:
            continue
        merged.append(
            PresetEntry(
                name=name,
                data=data,
                source=PresetSource.USER,
            )
        )

    return merged


# ──────────────────────────────────────────────────────────────────
# 内部：JSON 读取
# ──────────────────────────────────────────────────────────────────
def _read_json_strict(path: Path) -> dict[str, Any]:
    """读系统预设：缺失/坏文件直接抛 PresetError。"""
    if not path.is_file():
        raise PresetError(
            f"系统预设文件不存在：{path}",
            hint=(
                "请检查 config.toml 的 paths.curve_presets 是否正确，"
                "或将系统预设 JSON 放到该路径下。"
            ),
        )
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise PresetError(
            f"系统预设 JSON 解析失败（{path.name}）：{e}",
            hint=f"路径：{path}，请检查 JSON 语法。",
        ) from e

    if not isinstance(data, dict):
        raise PresetError(
            f"系统预设 JSON 顶层必须是对象（dict），得到 {type(data).__name__}",
            hint=f"路径：{path}",
        )
    return data


def _read_json_lenient(path: Path) -> dict[str, Any]:
    """读用户预设：缺失返回空 dict，坏文件 log warning 后返回空 dict（不抛）。

    设计动机：用户改坏自己的预设不应该让整个工具起不来。
    UI 上效果是"看不到我的预设了"——比 InfoBar 红字 + 启动失败友好得多。
    """
    if not path.is_file():
        log.debug("用户预设文件不存在，按空处理：%s", path)
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        log.warning(
            "用户预设 JSON 解析失败，按空处理（请到 [曲线预设编辑器] 修复）：%s — %s",
            path,
            e,
        )
        return {}
    except OSError as e:
        # 罕见：磁盘被拔 / 权限改了。同样兜底，不让用户的工具崩
        log.warning("读取用户预设时 IO 错误，按空处理：%s — %s", path, e)
        return {}

    if not isinstance(data, dict):
        log.warning(
            "用户预设 JSON 顶层不是对象（dict），按空处理：%s（实际类型 %s）",
            path,
            type(data).__name__,
        )
        return {}
    return data
