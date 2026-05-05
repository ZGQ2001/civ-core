"""跨模块流转的数据契约。

约定：
  • 业务热路径（每次任务都会构造的对象）用 dataclass —— 零开销、IDE 全补全
  • 配置类（外部 YAML 反序列化的对象）放在 config/loader.py 里的 Pydantic 模型
  • UI 元数据（工具列表、参数面板字段）也放这里 —— 它们是 UI 与业务之间的契约
  • 模块间严禁裸传 dict —— 任何返回多字段的函数都要用 dataclass
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


# ══════════════════════════════════════════════════════════════════
#  Section 1 ── 业务域模型（python-docx / matplotlib 操作的输入/输出契约）
# ══════════════════════════════════════════════════════════════════
@dataclass(slots=True)
class PhotoPair:
    """已排序 Word 表格里一对「图 + 题注」在源表中的位置（0-indexed）。"""

    num: int
    img_row_idx: int
    txt_row_idx: int
    img_col_idx: int
    txt_col_idx: int


# ── AxisSpec / CurveSeries / PlotJob 已迁移到 civil_auto.domain.schema ──
# 这里仅再导出，让仍引用旧路径的遗留代码（如 utils/plot_helpers.py、
# 本文件下方的 PlotJobResult）继续工作。新代码请直接：
#   from civil_auto.domain.schema import PlotJob, CurveSeries, AxisSpec
from civil_auto.domain.schema import AxisSpec, CurveSeries, PlotJob  # noqa: E402, F401


# ══════════════════════════════════════════════════════════════════
#  Section 2 ── UI 动态参数面板的字段契约
#  （规范 #3：QFormLayout 动态读取这里的 schema 自动生成输入框）
# ══════════════════════════════════════════════════════════════════
class FieldType(str, Enum):
    TEXT = "text"  # QLineEdit
    NUMBER = "number"  # QSpinBox / QDoubleSpinBox
    BOOL = "bool"  # CheckBox / SwitchButton
    SELECT = "select"  # ComboBox
    RADIO = "radio"  # RadioButton group
    FILE = "file"  # 文件选择器（QFileDialog 触发）
    DIRECTORY = "directory"  # 目录选择器
    COLOR = "color"  # 颜色选择器


@dataclass(slots=True)
class FieldSchema:
    """单个表单字段的元数据。UI 层根据 type 路由到对应的 fluent 控件。"""

    key: str  # 数据字典里的键名
    label: str  # 左侧标签文本
    type: FieldType
    default: Any = None
    required: bool = False
    help: str = ""  # 鼠标悬停提示

    # type-specific extras
    options: list[str] | None = None  # SELECT / RADIO 的选项
    file_filters: list[tuple[str, str]] | None = None
    min_value: float | None = None  # NUMBER 限值
    max_value: float | None = None
    decimals: int = 0  # NUMBER 小数位数
    unit: str = ""  # NUMBER 后缀单位（"%" / "mm"）


# ══════════════════════════════════════════════════════════════════
#  Section 3 ── 工具注册（替代硬编码 WORKFLOW_GROUPS）
# ══════════════════════════════════════════════════════════════════
class ToolKind(str, Enum):
    SUBPROCESS = "subprocess"  # 独立 Python 子进程（Word COM 隔离）
    EMBED = "embed"  # 嵌入式面板（QStackedWidget 一页）
    INPROC = "inproc"  # 直接在主进程跑（轻量、无 COM 依赖）


@dataclass(slots=True)
class ToolMeta:
    """单个工具的注册元数据。"""

    key: str  # 唯一标识
    display_name: str  # 侧边栏显示名
    description: str  # 详情页描述
    icon: str | None = None  # FluentIcon name 或资源路径
    kind: ToolKind = ToolKind.SUBPROCESS
    target: str = ""  # 子进程脚本路径 / "module:Class"
    fields: list[FieldSchema] = field(default_factory=list)
    requires_word: bool = False  # True → 启动前检查是否有 Word/WPS 实例


@dataclass(slots=True)
class ToolGroup:
    """一组同类工具（侧边栏的分类节点）。"""

    title: str  # "📝 报告排版" 等
    icon: str | None = None
    tools: list[ToolMeta] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
#  Section 4 ── 批量队列任务（规范 #9）
# ══════════════════════════════════════════════════════════════════
class TaskStatus(str, Enum):
    PENDING = "pending"  # 排队中
    RUNNING = "running"
    PAUSED = "paused"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class TaskItem:
    """批量队列里的一个任务实例（不是工具元数据，是"具体一次执行"）。"""

    id: str  # uuid4().hex 通常
    tool_key: str  # 引用 ToolMeta.key
    label: str  # UI 显示用（"批量绘图 — sheet1"）
    params: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0  # 0.0 ~ 1.0
    started_at: float | None = None  # epoch seconds
    finished_at: float | None = None
    error_message: str = ""


# ══════════════════════════════════════════════════════════════════
#  Section 5 ── 业务异常（规范 #10：UI 通过 InfoBar 友好提示）
# ══════════════════════════════════════════════════════════════════
class AppException(Exception):
    """所有业务异常的根。携带「修复建议」字段，UI 端直接展示给用户。"""

    user_hint: str = ""

    def __init__(self, message: str, *, hint: str = ""):
        super().__init__(message)
        self.user_hint = hint or self.user_hint


class WordNotRunningError(AppException):
    user_hint = "请先打开 Word 或 WPS，并打开目标文档（保存到本地）后重试。"


class DocumentNotSavedError(AppException):
    user_hint = "目标文档尚未保存到磁盘，请先 Ctrl+S 保存一次后重试。"


class ConfigSchemaError(AppException):
    user_hint = "config.yaml 里某个字段写错了，请按报错提示修正后重启。"


class TemplateMissingError(AppException):
    user_hint = "在 templates/ 目录下找不到对应的 docx/xlsx 模板，请确认文件就位。"


class IOReadError(AppException):
    user_hint = "读取文件失败，请检查路径、权限，以及文件是否被其他程序占用。"


# ══════════════════════════════════════════════════════════════════
#  Section 6 ── 进度回调契约（规范 #11：底部进度条与 worker 解耦）
# ══════════════════════════════════════════════════════════════════
@dataclass(slots=True)
class ProgressUpdate:
    """worker 线程通过 Signal(ProgressUpdate) 把进度推到 UI。"""

    current: int
    total: int
    message: str = ""

    @property
    def ratio(self) -> float:
        return (self.current / self.total) if self.total > 0 else 0.0


# 类型别名 —— core 层函数签名里直接用，避免与 Qt 耦合
ProgressCallback = Callable[[ProgressUpdate], None]


# ══════════════════════════════════════════════════════════════════
#  Section 7 ── IO 层操作结果 dataclass
#  （约定：所有 io/* 函数严禁返回 tuple/dict，必须返回这里定义的某个类型）
# ══════════════════════════════════════════════════════════════════
@dataclass(slots=True)
class BackupResult:
    """文档备份结果（utils/file_utils.backup_current_document 的返回）。"""

    success: bool
    backup_path: Path | None = None
    source_name: str = ""
    reason: str = ""  # success=False 时的人话原因
    created_at: datetime | None = None  # tz-aware


@dataclass(slots=True)
class WordContext:
    """io/word_app.WordApp 暴露的运行时句柄。

    把零散的 app/active_doc/host 包成一个对象 —— 业务层只用这个就够。
    """

    app: Any  # win32com.client COM dispatch
    active_doc: Any  # Word.Document
    host_kind: str  # "Word" | "WPS" | "Unknown"
    doc_path: Path
    doc_name: str


@dataclass(slots=True)
class PhotoScanResult:
    """utils/word_helpers.scan_photo_pairs 的返回。"""

    matched: dict[int, PhotoPair]
    unmatched: list[PhotoPair]
    total_rows: int

    @property
    def matched_count(self) -> int:
        return len(self.matched)

    @property
    def unmatched_count(self) -> int:
        return len(self.unmatched)


@dataclass(slots=True)
class CaptionRenumberMapping:
    """utils/word_helpers.build_caption_renumber_mapping 的返回。"""

    mapping: dict[int, int]  # 旧→新编号映射
    duplicates: list[int]  # 重复出现被忽略的旧编号

    @property
    def total(self) -> int:
        return len(self.mapping)


@dataclass(slots=True)
class CaptionReplaceResult:
    """utils/word_helpers.replace_in_caption_rows 的返回。"""

    output_path: Path
    run_level_replacements: int  # 逐 run 替换成功的次数
    paragraph_fallbacks: int  # 跨 run 整段重写的次数
    unmatched_old_ids: list[int]  # 找不到映射的旧编号


@dataclass(slots=True)
class ExcelReplaceResult:
    """io/excel_helpers.replace_in_excel_column 的返回。"""

    output_path: Path
    cells_replaced: int
    unmatched_old_ids: list[int]


@dataclass(slots=True)
class FormatStats:
    """body_format / table_format 等排版引擎的统计输出。"""

    success_count: int = 0
    skipped_count: int = 0
    manual_skip_count: int = 0
    failures: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BracketFixStats:
    """bracket_format 的输出。"""

    rules_applied: int = 0
    total_replacements: int = 0


@dataclass(slots=True)
class CrossRefFixStats:
    """fix_cross_ref 的输出。"""

    refs_processed: int = 0
    refs_updated: int = 0


@dataclass(slots=True)
class Word2PdfResult:
    """单次 Word→PDF 的结果。"""

    source: Path
    output: Path | None
    success: bool
    error: str = ""


@dataclass(slots=True)
class PlotJobResult:
    """plot_curves 单张图的结果。"""

    job: PlotJob
    success: bool
    output_path: Path | None = None
    error: str = ""


@dataclass(slots=True)
class BatchResult:
    """批量任务的总输出。core 层 run_batch() 返回它。"""

    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    items: list[Any] = field(default_factory=list)  # 单项结果（按 tool 决定具体类型）

    @property
    def total(self) -> int:
        return self.succeeded + self.failed + self.skipped
