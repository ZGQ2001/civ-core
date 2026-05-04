"""统一异常分层（手册 §5.2 + §10.2 决策）。

四档分类：
    ConfigError    — 配置加载 / schema 校验失败
    InputError     — 用户输入数据不符（缺列、格式错）
    BusinessError  — 业务规则触发（Word 未启、文档未保存、模板缺失）
    InfraIOError   — 基础设施失败（文件占用、权限、COM 不可用、磁盘）

所有自定义异常顶层基类是 CivilAutoError，便于 main.py / UI 层统一捕获兜底。

呈现规范（手册 §3.0 P0-7 三段式）：
    str(exc) 输出形如：
        [<location>] <cause>
        修复建议：<hint>
    其中 location / hint 可选；只传 cause 时退化为单行。

用法范例::

    raise BusinessError(
        cause="文档尚未保存到本地磁盘",
        location="WordApp.attach",
        hint="请先按 Ctrl+S 把文档保存到硬盘后重试",
    )

迁移说明：
  本文件取代 models/schema.py 里散落的 AppException 体系。新代码必须 import
  这里的类；models/schema.py 里的旧类保留给「迁移过渡期」内的旧业务模块用。
"""

from __future__ import annotations


class CivilAutoError(Exception):
    """全部业务/基础设施异常的顶层基类。

    禁止业务代码直接 `raise CivilAutoError(...)` —— 必须落到下面 4 个子档之一。
    保留这一层只为 main.py 做 try/except 兜底统一处理。
    """

    # 默认建议；子类可覆盖；调用方传入的 hint 优先级最高
    default_hint: str = ""

    def __init__(
        self,
        cause: str,
        *,
        location: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.cause = cause
        self.location = location
        # 用户传入 > 子类默认 > 空字符串
        self.hint = hint if hint is not None else self.default_hint
        super().__init__(self._render())

    # ──────────────────────────────────────────────────────────
    # 三段式渲染
    # ──────────────────────────────────────────────────────────
    def _render(self) -> str:
        """生成 P0-7 规范的三段式字符串。

        位置可选，建议可选；最简形式只输出 cause 一行。
        """
        head = f"[{self.location}] {self.cause}" if self.location else self.cause
        if self.hint:
            return f"{head}\n修复建议：{self.hint}"
        return head

    # 子类可覆盖此 prop 用于 UI 决定 InfoBar 颜色
    @property
    def severity(self) -> str:
        """ "info" | "warning" | "error" | "critical" """
        return "error"


# ══════════════════════════════════════════════════════════════════
# 1. 配置层
# ══════════════════════════════════════════════════════════════════
class ConfigError(CivilAutoError):
    """config.toml 解析、schema 校验、必填项缺失等。

    通常发生在 `app/bootstrap.py` 启动阶段；用户层面提示「请检查 config.toml」。
    """

    default_hint = "请检查 config.toml 是否存在、字段是否完整、类型是否正确。"


class ConfigSchemaError(ConfigError):
    """字段类型错、超出允许范围、枚举值非法。"""

    default_hint = "请按 docs/dev_guide/ 中的 config.toml 模板核对该字段的类型与取值范围。"


class ConfigMissingError(ConfigError):
    """必填字段缺失或文件本身找不到。"""

    default_hint = "请确认 config.toml 在项目根目录，且包含所有必填段落。"


# ══════════════════════════════════════════════════════════════════
# 2. 输入层
# ══════════════════════════════════════════════════════════════════
class InputError(CivilAutoError):
    """用户提供的数据文件结构不符合期望。

    通常发生在 `infra_io/excel_reader.py` 等读取 + 清洗阶段。
    """

    default_hint = "请检查输入文件的结构是否符合工具要求。"


class ColumnNotFoundError(InputError):
    """Excel 中找不到指定列名。"""

    default_hint = "请确认列名拼写正确，或参照模板调整源文件表头。"


class EmptyDataError(InputError):
    """读到的有效行数为 0。"""

    default_hint = "请确认源文件不为空、过滤条件不会把全部行删除。"


class InvalidFieldError(InputError):
    """字段类型/格式不符（如必填数字列里出现文本）。"""

    default_hint = "请清洗源数据：把异常单元格修正为期望的类型。"


# ══════════════════════════════════════════════════════════════════
# 3. 业务层
# ══════════════════════════════════════════════════════════════════
class BusinessError(CivilAutoError):
    """业务规则不满足，与基础设施无关。"""

    default_hint = "请按提示调整操作步骤后重试。"


class WordHostNotRunning(BusinessError):
    """Word / WPS 应用程序未启动，COM 附着失败。"""

    default_hint = "请先打开 Word 或 WPS 并打开目标文档（保存到本地）后重试。"


class DocumentUnsaved(BusinessError):
    """ActiveDocument 尚未保存到本地，备份/SaveAs 等流程被阻断。"""

    default_hint = "请先按 Ctrl+S 把文档保存到本地磁盘后再运行该工具。"


class TemplateMissing(BusinessError):
    """templates/ 目录下找不到对应的 docx/xlsx 模板。"""

    default_hint = "请确认 templates/ 下存在该模板文件，或在 config.toml 中调整模板路径。"


class RuleViolation(BusinessError):
    """业务规则校验失败（字段间约束、阈值检查等）。"""

    default_hint = "请按报错提示中的字段名调整源数据后重试。"


# ══════════════════════════════════════════════════════════════════
# 4. 基础设施层
# ══════════════════════════════════════════════════════════════════
class InfraIOError(CivilAutoError):
    """文件 / 进程 / COM 等基础设施失败。"""

    default_hint = "请检查文件是否被其他程序占用，或确认 Office 已正确安装。"


class FileLockedError(InfraIOError):
    """目标文件被其他进程占用 (P0-4)。"""

    default_hint = "请关闭占用该文件的程序（通常是 Word / Excel）后重试。"


class FileWriteError(InfraIOError):
    """文件写入失败（权限、磁盘满、临时文件移动失败等）。"""

    default_hint = "请确认目标目录有写权限，且磁盘空间充足。"


class ComUnavailable(InfraIOError):
    """pywin32 / COM 调用失败（Office 未装、COM 崩溃、Quit 失败等）。"""

    default_hint = "请确认本机已安装 Microsoft Office；若问题持续，重启 Office 进程后重试。"


# ══════════════════════════════════════════════════════════════════
# 便捷工具：一次性把异常按格式写入 logger
# ══════════════════════════════════════════════════════════════════
def format_for_log(exc: CivilAutoError) -> str:
    """生成给 logger 用的单行字符串（不含换行，便于 grep）。"""
    parts = [type(exc).__name__]
    if exc.location:
        parts.append(f"location={exc.location}")
    parts.append(f"cause={exc.cause!r}")
    if exc.hint:
        parts.append(f"hint={exc.hint!r}")
    return " | ".join(parts)
