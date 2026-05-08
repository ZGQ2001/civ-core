"""配置加载层：读 config.toml → dataclass 校验 → 暴露 typed AppConfig 单例。

设计要点：
  1. 单一入口 `load_config()` 走 lru_cache，进程内只解析一次。
  2. 所有路径字段在加载末尾由 `_resolve_paths` 统一解析为「绝对 Path」并 mkdir，
     业务代码拿到的永远是可直接 open() 的真实路径。
  3. 任何配置错误都抛 `ConfigError`（继承自 RuntimeError），UI 层用 InfoBar 友好提示。
  4. 旧的 04_Config/*.json 兼容层放在文件末尾，DEPRECATED，只为未迁移工具兜底。
  5. 校验放在每个 dataclass 的 __post_init__，与 v2.3 总纲一致：禁止 pydantic。
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, fields, replace
from functools import lru_cache
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────────────────────────
# 1. 异常
# ──────────────────────────────────────────────────────────────────
class ConfigError(RuntimeError):
    """配置加载/校验失败。UI 层应捕获并用 InfoBar 提示用户。"""


_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_THEMES = ("auto", "light", "dark")


def _require(condition: bool, msg: str) -> None:
    if not condition:
        raise ConfigError(msg)


# ──────────────────────────────────────────────────────────────────
# 2. Schema (frozen dataclass)
# ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AppMeta:
    name: str = "工程自动化主控制台"
    version: str = "1.0.0"


@dataclass(frozen=True)
class PathsConfig:
    """所有路径字段。构造时保留原样（可能是相对路径）；
    在 load_config() 末尾由 _resolve_paths 统一解析为绝对路径并 mkdir。

    字段语义：
      • 目录类（templates / data_raw / data_output / logs / user_presets_dir）→ mkdir(parents=True)
      • 文件类（curve_presets）→ 只确保 parent 目录存在，不创建文件本身
      • legacy_config_dir：DEPRECATED，仅为未迁移的旧工具兜底，不主动创建
      • user_presets_dir：派生字段（由 [dev] 段决定），不在 config.toml 直填，_resolve_paths 计算
    """

    templates: Path
    curve_presets: Path
    data_raw: Path
    data_output: Path
    logs: Path
    user_presets_dir: Path  # 派生字段：dev.enabled=true 时走仓库内 fixtures，否则走用户家目录
    legacy_config_dir: Path | None = None


@dataclass(frozen=True)
class UIConfig:
    theme: str = "auto"
    language: str = "zh_CN"
    accent_color: str = "#0078D4"
    # 用 tuple 而不是 list：dataclass(frozen=True) 默认值不能用可变对象
    startup_size: tuple[int, int] = (1320, 840)
    sidebar_width: int = 280

    def __post_init__(self) -> None:
        _require(
            self.theme in _THEMES,
            f"ui.theme 必须是 {_THEMES} 之一，得到 {self.theme!r}",
        )
        _require(len(self.startup_size) == 2, "ui.startup_size 必须长度为 2")
        _require(
            200 <= self.sidebar_width <= 480,
            f"ui.sidebar_width 必须在 [200, 480]，得到 {self.sidebar_width}",
        )


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    console_level: str = "INFO"
    file_level: str = "DEBUG"
    max_file_mb: int = 10
    backup_count: int = 5

    def __post_init__(self) -> None:
        for fname in ("level", "console_level", "file_level"):
            value = getattr(self, fname)
            _require(
                value in _LOG_LEVELS,
                f"logging.{fname} 必须是 {_LOG_LEVELS} 之一，得到 {value!r}",
            )
        _require(1 <= self.max_file_mb <= 500, "logging.max_file_mb 必须在 [1, 500]")
        _require(0 <= self.backup_count <= 50, "logging.backup_count 必须在 [0, 50]")


@dataclass(frozen=True)
class BatchQueueConfig:
    max_concurrent: int = 1
    retry_on_fail: bool = False
    pause_on_error: bool = True

    def __post_init__(self) -> None:
        _require(
            1 <= self.max_concurrent <= 8,
            f"batch_queue.max_concurrent 必须在 [1, 8]，得到 {self.max_concurrent}",
        )


@dataclass(frozen=True)
class WordConfig:
    kill_residual_on_start: bool = True
    unblock_files: bool = True
    backup_before_format: bool = True


@dataclass(frozen=True)
class DevConfig:
    """开发模式配置。

    enabled=true：用户预设走仓库内 user_presets_dir（默认 tests/fixtures/presets/），
                  方便测试用例和调试时把预设数据纳入 git。
    enabled=false：用户预设走 ~/.civ-core/presets/，是最终用户场景。

    user_presets_dir 仅在 enabled=true 时使用；enabled=false 时此字段不参与路径计算。
    """

    enabled: bool = False
    # 仓库内的相对路径；enabled=false 时被忽略
    user_presets_dir: str = "tests/fixtures/presets"


@dataclass(frozen=True)
class Thresholds:
    max_undo_steps: int = 50
    log_panel_lines: int = 5000

    def __post_init__(self) -> None:
        _require(
            0 <= self.max_undo_steps <= 1000,
            f"thresholds.max_undo_steps 必须在 [0, 1000]，得到 {self.max_undo_steps}",
        )
        _require(
            100 <= self.log_panel_lines <= 100_000,
            f"thresholds.log_panel_lines 必须在 [100, 100000]，得到 {self.log_panel_lines}",
        )


@dataclass(frozen=True)
class AppConfig:
    """根配置对象。业务代码统一通过 `load_config()` 拿到这个类型。"""

    paths: PathsConfig
    app: AppMeta = field(default_factory=AppMeta)
    ui: UIConfig = field(default_factory=UIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    batch_queue: BatchQueueConfig = field(default_factory=BatchQueueConfig)
    word: WordConfig = field(default_factory=WordConfig)
    thresholds: Thresholds = field(default_factory=Thresholds)
    dev: DevConfig = field(default_factory=DevConfig)


# ──────────────────────────────────────────────────────────────────
# 3. 加载入口
# ──────────────────────────────────────────────────────────────────
def find_project_root(start: Path | None = None) -> Path:
    """从起点向上找 pyproject.toml，返回项目根。失败返回 start。"""
    here = Path(start or __file__).resolve()
    for cand in [here, *here.parents]:
        if (cand / "pyproject.toml").is_file():
            return cand
    return here


def _filter_kwargs(cls: type, raw: dict[str, Any]) -> dict[str, Any]:
    """只保留 dataclass 已声明的字段，多余 key 报错（对应原 pydantic 的 extra='forbid'）。"""
    valid = {f.name for f in fields(cls)}
    extra = set(raw) - valid
    if extra:
        raise ConfigError(f"{cls.__name__} 出现未知字段：{sorted(extra)}")
    return {k: v for k, v in raw.items() if k in valid}


def _build_paths(raw: dict[str, Any]) -> PathsConfig:
    """paths 段：5 个必填路径 + 可选 legacy_config_dir。

    user_presets_dir 是派生字段，不从 toml 读；这里先填占位 Path，
    由 _resolve_paths 拿到 dev 配置后替换为实际路径。
    """
    kwargs = _filter_kwargs(PathsConfig, raw)
    for key in ("templates", "curve_presets", "data_raw", "data_output", "logs"):
        if key not in kwargs:
            raise ConfigError(f"paths.{key} 必填")
        kwargs[key] = Path(str(kwargs[key]))
    legacy = kwargs.get("legacy_config_dir")
    if legacy is not None:
        kwargs["legacy_config_dir"] = Path(str(legacy))
    # user_presets_dir 占位：_resolve_paths 会替换。这里给一个明显非法的占位避免误用
    kwargs["user_presets_dir"] = Path("__user_presets_placeholder__")
    return PathsConfig(**kwargs)


def _build_ui(raw: dict[str, Any]) -> UIConfig:
    """ui 段：把 toml 的 list 转成 dataclass 要求的 tuple[int, int]。"""
    kwargs = _filter_kwargs(UIConfig, raw)
    if "startup_size" in kwargs:
        size = list(kwargs["startup_size"])
        if len(size) != 2:
            raise ConfigError("ui.startup_size 必须长度为 2")
        kwargs["startup_size"] = (int(size[0]), int(size[1]))
    return UIConfig(**kwargs)


@lru_cache(maxsize=1)
def load_config(config_path: Path | None = None) -> AppConfig:
    """读 config.toml → 校验 → 解析路径 → 返回 frozen AppConfig。

    config_path 不传时自动定位项目根下的 config.toml。
    """
    project_root = find_project_root()
    cfg_path = Path(config_path) if config_path else project_root / "config.toml"

    if not cfg_path.is_file():
        raise ConfigError(
            f"找不到配置文件：{cfg_path}\n请把 config.toml 放到项目根。"
        )

    try:
        # tomllib 要求二进制模式，由库内部按 UTF-8 解析
        with cfg_path.open("rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"TOML 语法错误（{cfg_path}）：{e}") from e

    if "paths" not in raw:
        raise ConfigError("config.toml 缺少 [paths] 节")

    try:
        cfg = AppConfig(
            paths=_build_paths(raw["paths"]),
            app=AppMeta(**_filter_kwargs(AppMeta, raw.get("app", {}))),
            ui=_build_ui(raw.get("ui", {})),
            logging=LoggingConfig(**_filter_kwargs(LoggingConfig, raw.get("logging", {}))),
            batch_queue=BatchQueueConfig(
                **_filter_kwargs(BatchQueueConfig, raw.get("batch_queue", {}))
            ),
            word=WordConfig(**_filter_kwargs(WordConfig, raw.get("word", {}))),
            thresholds=Thresholds(**_filter_kwargs(Thresholds, raw.get("thresholds", {}))),
            dev=DevConfig(**_filter_kwargs(DevConfig, raw.get("dev", {}))),
        )
    except ConfigError:
        raise
    except Exception as e:
        raise ConfigError(f"配置校验失败：{e}") from e

    return _resolve_paths(cfg, project_root)


def reload_config() -> AppConfig:
    """强制重新加载（清缓存）。用户改完 config.toml 想热更新时调。"""
    load_config.cache_clear()
    return load_config()


# ──────────────────────────────────────────────────────────────────
# 内部：路径解析
# ──────────────────────────────────────────────────────────────────
def _resolve_paths(cfg: AppConfig, project_root: Path) -> AppConfig:
    """把 cfg.paths 里所有相对路径转为绝对路径，并确保目录存在。

    返回新的 AppConfig（frozen=True 不允许就地改，用 dataclasses.replace）。
    """

    def _abs(p: Path | None) -> Path | None:
        if p is None:
            return None
        return p if p.is_absolute() else (project_root / p).resolve()

    abs_curve_presets = _abs(cfg.paths.curve_presets)
    assert abs_curve_presets is not None  # 必填字段，_abs 不会返 None

    # 计算 user_presets_dir：派生字段，按 dev.enabled 决定路径
    #   • enabled=true  → project_root / cfg.dev.user_presets_dir（仓库内 fixtures）
    #   • enabled=false → ~/.civ-core/presets/（用户家目录）
    if cfg.dev.enabled:
        user_presets_dir = (project_root / cfg.dev.user_presets_dir).resolve()
    else:
        user_presets_dir = (Path.home() / ".civ-core" / "presets").resolve()

    new_paths = replace(
        cfg.paths,
        templates=_abs(cfg.paths.templates),
        curve_presets=abs_curve_presets,
        data_raw=_abs(cfg.paths.data_raw),
        data_output=_abs(cfg.paths.data_output),
        logs=_abs(cfg.paths.logs),
        user_presets_dir=user_presets_dir,
        legacy_config_dir=_abs(cfg.paths.legacy_config_dir),
    )

    # 目录类：确保存在（含 user_presets_dir 自动 mkdir，硬性要求"用户目录不存在 → 静默创建"）
    for fname in ("templates", "data_raw", "data_output", "logs", "user_presets_dir"):
        path: Path = getattr(new_paths, fname)
        path.mkdir(parents=True, exist_ok=True)
    # 文件类：只 mkdir parent；文件本身由各工具按需创建/读取
    new_paths.curve_presets.parent.mkdir(parents=True, exist_ok=True)
    # legacy_config_dir：DEPRECATED，不主动创建（旧工具自带兜底）

    return replace(cfg, paths=new_paths)


# ──────────────────────────────────────────────────────────────────
# 4. 旧 JSON 配置兼容层（DEPRECATED · 仅给未迁移工具兜底）
# ──────────────────────────────────────────────────────────────────
# 历史背景：旧版把所有工具的 JSON 配置堆在 ./04_Config/ 下。
# 新架构按工具子目录走 ./presets/<tool>/<file>.json，绘曲线图已迁移。
# 这两个函数留着只为 body_format / table_format 还在读 report_style_config.json，
# 那两个文件迁移到 src/ 后整段删除。
def load_legacy_json(filename: str) -> dict:
    """[DEPRECATED] 读 04_Config/<filename>.json（report_style_config.json 等）。

    新代码请直接用 cfg.paths.<新字段>，不要依赖本函数。
    """
    cfg = load_config()
    if cfg.paths.legacy_config_dir is None:
        raise ConfigError("config.toml 未配置 paths.legacy_config_dir")
    full = cfg.paths.legacy_config_dir / filename
    if not full.is_file():
        raise ConfigError(f"旧配置文件不存在：{full}")
    with full.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_legacy_json(filename: str, data: dict) -> None:
    """[DEPRECATED] 同 load_legacy_json，写入侧。"""
    cfg = load_config()
    if cfg.paths.legacy_config_dir is None:
        raise ConfigError("config.toml 未配置 paths.legacy_config_dir")
    full = cfg.paths.legacy_config_dir / filename
    full.parent.mkdir(parents=True, exist_ok=True)
    with full.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
