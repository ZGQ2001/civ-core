"""预设管理器：合并系统预设 + 用户预设，对外暴露统一的"运行时预设列表"。

设计要点
========
  • 系统预设（只读，随程序发布）
      - 路径：`cfg.paths.curve_presets`（即 `presets/<tool>/curve_presets.json`）
      - 由开发者通过 git 维护，**程序运行时禁止写入**
  • 用户预设（可写，用户自定义）
      - 路径：`cfg.paths.user_presets_dir / <tool>/curve_presets.json`
      - dev.enabled=true  → 仓库内 `tests/fixtures/presets/<tool>/...`（git 管理）
      - dev.enabled=false → `~/.civ-core/presets/<tool>/...`（最终用户场景）
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
      - 写入只针对**用户预设**。`save_user_preset` / `delete_user_preset`
        / `copy_system_to_user` 三个 API 全部走 `atomic_writer` 防破损。
      - 系统预设路径在本模块里没有任何写入入口；硬性禁止运行时改 presets/。

为什么不直接放 `core/plot_curves.py`
====================================
  • core/ 不得直接读写文件（v2.3 总纲）
  • 多工具复用：今后 word2pdf / auto_filler 等工具的预设也走同一套合并逻辑
  • 测试隔离：preset_manager 的合并语义是纯函数（除了 IO 入口），可单独测
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from civ_core.configs.loader import load_config
from civ_core.infra_io.file_manager import atomic_writer
from civ_core.utils.logger import get_logger

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


# ──────────────────────────────────────────────────────────────────
# 写入 API（仅写用户预设；T-4 编辑器用）
# ──────────────────────────────────────────────────────────────────
# 设计取舍：
#   • 写入粒度是"整张用户 JSON 文件原子替换"，不做条目级别 patch。
#     用户预设文件本身就不大（顶多十几个预设），整张读改写比维护
#     增量补丁简单得多，也避免 atomic_writer 半场介入的边界。
#   • 系统预设永远不写。`get_system_presets_path` 只用来读，三个
#     写入函数没有任何路径参数，全部强制落到 `get_user_presets_path` 上。
#   • 写入前对用户文件用宽松读：如果用户文件是坏的（同 _read_json_lenient
#     的兜底），我们当成空字典开始写——不会让"用户文件原本是坏的"导致
#     新的写入再失败。坏文件被覆盖反而是修复。
#
# JSON 输出风格：indent=4 + ensure_ascii=False，与系统预设保持一致，
# 让用户用任何编辑器都能直接看懂改一改（例如复制一份手工调字段）。

_JSON_DUMP_KW = {"indent": 4, "ensure_ascii": False}


def _write_user_raw(path: Path, raw: dict[str, Any]) -> None:
    """把整张用户预设 dict 原子写到 path。

    atomic_writer 已经替我们做了：
      • 父目录自动 mkdir
      • 临时文件同盘写入 + os.replace 原子替换
      • 异常时清理临时文件
      • 文件被占用时抛 FileBusyError（带 hint）
    """
    with atomic_writer(path) as tmp:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(raw, f, **_JSON_DUMP_KW)
            f.write("\n")  # 末尾留个换行，对 git diff 友好
    log.info("用户预设已写入：%s", path)


def save_user_preset(
    name: str,
    data: dict[str, Any],
    *,
    tool: str = "plot_curves",
) -> None:
    """保存（新增或覆盖）一条用户预设到用户目录。

    语义：
      • 用户文件不存在 → 自动创建一份只含本条的文件
      • 用户文件存在 → 把本条 name 写进/覆盖原文件，其它条目保留原样
      • name 即使与系统预设同名也允许：保存后用户预设会在合并时覆盖系统预设

    注意：这个函数不会校验 data 的内部结构。校验由调用方（UI 层）在保存前做，
    这里只负责"把字典原子落盘"。要校验放在这里，会让所有写入路径都得过一遍
    schema，反而把简单的复制/重命名也卡住了。
    """
    if not name or name.startswith("_"):
        # "_" 开头的 key 在合并时会被过滤掉，写进去也没意义；直接拒
        raise PresetError(
            f"非法预设名：{name!r}",
            hint="预设名不能为空，也不能以下划线开头（保留给注释 key）",
        )

    path = get_user_presets_path(tool)
    raw = _read_json_lenient(path)  # 现有用户预设，坏文件兜底为空
    raw[name] = copy.deepcopy(data)  # 深拷贝，防外面改 dict 影响落盘内容
    _write_user_raw(path, raw)
    log.info("save_user_preset: name=%r tool=%r", name, tool)


def delete_user_preset(name: str, *, tool: str = "plot_curves") -> None:
    """从用户预设里删除一条。

    语义：
      • 该条不在用户文件里 → 抛 PresetError（多半是系统预设；系统预设不可删）
      • 删后用户文件如果变成空 dict，仍写回（不删文件本身），保持
        "用户文件存在 = 用户启用过自定义"的可观测语义

    UI 应该在调这个函数前先判断 PresetEntry.source：
      - SYSTEM → 按钮置灰，不让点
      - USER  → 弹确认后再调
    这里只是兜底防御，不依赖 UI 把关。
    """
    path = get_user_presets_path(tool)
    raw = _read_json_lenient(path)
    if name not in raw:
        raise PresetError(
            f"用户预设里找不到 {name!r}",
            hint=(
                "可能的原因：(1) 这是系统预设，系统预设不可删；"
                "(2) 名字拼错；(3) 用户文件已被外部改动。"
            ),
        )
    del raw[name]
    _write_user_raw(path, raw)
    log.info("delete_user_preset: name=%r tool=%r", name, tool)


def copy_system_to_user(
    source_name: str,
    new_name: str,
    *,
    tool: str = "plot_curves",
) -> None:
    """把任一现存预设（系统或用户）复制为用户预设的新条目。

    语义：
      • 在合并后的列表里查 source_name —— 系统/用户都可作为复制源
        （用户也常想"基于我现有的预设再分一份"）
      • new_name 已经在用户预设里 → 抛 PresetError，防误覆盖
        （要覆盖请直接调 save_user_preset；这里语义是"新增"）
      • new_name 与系统预设同名也允许（结果是用户预设覆盖系统预设，
        和手工编辑系统预设达到的效果一致）

    用法（T-4 列表区"复制为我的预设"按钮）：
        try:
            copy_system_to_user("锚杆荷载-位移曲线", "我的锚杆 (副本)")
        except PresetError as e:
            show_error_infobar(self, e, where="复制预设")
    """
    if not new_name or new_name.startswith("_"):
        raise PresetError(
            f"非法新预设名：{new_name!r}",
            hint="预设名不能为空，也不能以下划线开头",
        )

    # 找复制源：直接走合并后的列表，系统/用户都能命中
    merged = {e.name: e for e in load_merged_presets(tool)}
    if source_name not in merged:
        raise PresetError(
            f"找不到要复制的预设：{source_name!r}",
            hint=f"已知预设：{list(merged.keys())}",
        )

    # 防误覆盖：new_name 不能已存在于用户预设（系统同名是允许的，覆盖系统是常见诉求）
    user_raw = _read_json_lenient(get_user_presets_path(tool))
    if new_name in user_raw:
        raise PresetError(
            f"用户预设里已经有 {new_name!r}，请改个名字",
            hint="如果确实要覆盖，请直接编辑后保存，而不是复制。",
        )

    # 直接复用 save_user_preset 的写入路径，避免重复实现读改写
    save_user_preset(new_name, merged[source_name].data, tool=tool)
    log.info(
        "copy_system_to_user: source=%r → new=%r tool=%r",
        source_name,
        new_name,
        tool,
    )


def rename_user_preset(
    old_name: str,
    new_name: str,
    *,
    tool: str = "plot_curves",
) -> None:
    """重命名一条用户预设，原位（保留在 dict 里原有的顺序位置）。

    语义：
      • 只能重命名「用户」预设；系统预设不可改名（要改名请先 copy_system_to_user
        到一个新名，再删原"系统覆盖项"）
      • old_name 不在用户文件里 → PresetError（"找不到要重命名的"）
      • new_name 与 old_name 相同 → 视为 no-op，直接返回
      • new_name 已经在用户文件里（且不是 old_name 本身）→ PresetError（防误覆盖）
      • new_name 与系统预设同名 → 允许（与 copy_system_to_user 一致：用户主动覆盖系统预设）

    为什么要原位重建 dict 而不是 pop+赋值：
      • pop 后再赋值会把新 key 排到末尾，UI 的 ComboBox 顺序会跳，对用户视觉体验差
      • 这里手动遍历重建一份新 dict，保留原始插入位置
    """
    if not new_name or new_name.startswith("_"):
        raise PresetError(
            f"非法新预设名：{new_name!r}",
            hint="预设名不能为空，也不能以下划线开头（保留给注释 key）",
        )

    if new_name == old_name:
        # 同名重命名：不改任何东西，直接返回，避免没必要的写盘
        log.info("rename_user_preset: 新旧同名 %r，no-op", new_name)
        return

    path = get_user_presets_path(tool)
    raw = _read_json_lenient(path)
    if old_name not in raw:
        raise PresetError(
            f"用户预设里找不到要重命名的 {old_name!r}",
            hint=(
                "可能的原因：(1) 这是系统预设，系统预设不可改名（请改用复制）；"
                "(2) 名字拼错；(3) 用户文件已被外部改动。"
            ),
        )
    if new_name in raw:
        # 注意：上面已经处理过 new_name == old_name 的情况，这里能命中说明
        # new_name 是另一条已存在的用户预设
        raise PresetError(
            f"用户预设里已经有 {new_name!r}，请换个名字",
            hint="重命名不会合并两条预设；如果想替换那条，请先删除它再重命名。",
        )

    # 原位重建：保留 old_name 的位置，只把 key 换成 new_name
    new_raw: dict[str, Any] = {}
    for k, v in raw.items():
        if k == old_name:
            new_raw[new_name] = v
        else:
            new_raw[k] = v
    _write_user_raw(path, new_raw)
    log.info(
        "rename_user_preset: %r → %r tool=%r",
        old_name,
        new_name,
        tool,
    )
