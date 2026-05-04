"""配置加载层：读 config.yaml → Pydantic 校验 → 暴露 typed AppConfig 单例。

设计要点：
  1. 单一入口 `load_config()` 走 lru_cache，进程内只解析一次。
  2. 所有路径字段在 validator 阶段就解析为「绝对 Path」并 mkdir，业务代码拿到的
     永远是可直接 open() 的真实路径。
  3. 任何配置错误都抛 `ConfigError`（继承自 RuntimeError），UI 层用 InfoBar 友好提示。
  4. 旧的 04_Config/*.json 加载逻辑放在 `legacy.py` —— 这里只管 config.yaml 主轴。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ──────────────────────────────────────────────────────────────────
# 1. 异常
# ──────────────────────────────────────────────────────────────────
class ConfigError(RuntimeError):
    """配置加载/校验失败。UI 层应捕获并用 InfoBar 提示用户。"""


# ──────────────────────────────────────────────────────────────────
# 2. Schema (Pydantic)
# ──────────────────────────────────────────────────────────────────
class AppMeta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = "工程自动化主控制台"
    version: str = "1.0.0"


class PathsConfig(BaseModel):
    """所有路径字段。validate 阶段保持原样字符串/相对路径；
    在 load_config() 末尾由 _resolve_paths 统一解析为绝对路径并 mkdir。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    templates: Path
    data_raw: Path
    data_output: Path
    logs: Path
    legacy_config_dir: Path | None = None

    @field_validator(
        "templates", "data_raw", "data_output", "logs", "legacy_config_dir", mode="before"
    )
    @classmethod
    def _to_path(cls, v: Any) -> Any:
        return None if v is None else Path(str(v))


class UIConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    theme: Literal["auto", "light", "dark"] = "auto"
    language: str = "zh_CN"
    accent_color: str = "#0078D4"
    startup_size: list[int] = Field(default_factory=lambda: [1320, 840], min_length=2, max_length=2)
    sidebar_width: int = Field(default=280, ge=200, le=480)


class LoggingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    console_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    file_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    max_file_mb: int = Field(default=10, ge=1, le=500)
    backup_count: int = Field(default=5, ge=0, le=50)


class BatchQueueConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_concurrent: int = Field(default=1, ge=1, le=8)
    retry_on_fail: bool = False
    pause_on_error: bool = True


class WordConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kill_residual_on_start: bool = True
    unblock_files: bool = True
    backup_before_format: bool = True


class Thresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_undo_steps: int = Field(default=50, ge=0, le=1000)
    log_panel_lines: int = Field(default=5000, ge=100, le=100_000)


class AppConfig(BaseModel):
    """根配置对象。业务代码统一通过 `load_config()` 拿到这个类型。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    app: AppMeta = Field(default_factory=AppMeta)
    paths: PathsConfig
    ui: UIConfig = Field(default_factory=UIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    batch_queue: BatchQueueConfig = Field(default_factory=BatchQueueConfig)
    word: WordConfig = Field(default_factory=WordConfig)
    thresholds: Thresholds = Field(default_factory=Thresholds)


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


@lru_cache(maxsize=1)
def load_config(config_path: Path | None = None) -> AppConfig:
    """读 config.yaml → 校验 → 解析路径 → 返回 frozen AppConfig。

    config_path 不传时自动定位项目根下的 config.yaml。
    """
    project_root = find_project_root()
    cfg_path = Path(config_path) if config_path else project_root / "config.yaml"

    if not cfg_path.is_file():
        raise ConfigError(
            f"找不到配置文件：{cfg_path}\n请把 config.yaml 放到项目根，或从仓库示例复制一份。"
        )

    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            raw: dict = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML 语法错误（{cfg_path}）：{e}") from e

    try:
        cfg = AppConfig.model_validate(raw)
    except Exception as e:
        raise ConfigError(f"配置校验失败：\n{e}") from e

    return _resolve_paths(cfg, project_root)


def reload_config() -> AppConfig:
    """强制重新加载（清缓存）。用户改完 config.yaml 想热更新时调。"""
    load_config.cache_clear()
    return load_config()


# ──────────────────────────────────────────────────────────────────
# 内部：路径解析
# ──────────────────────────────────────────────────────────────────
def _resolve_paths(cfg: AppConfig, project_root: Path) -> AppConfig:
    """把 cfg.paths 里所有相对路径转为绝对路径，并确保目录存在。

    返回新的 AppConfig（frozen=True 不允许就地改）。
    """

    def _abs(p: Path | None) -> Path | None:
        if p is None:
            return None
        return p if p.is_absolute() else (project_root / p).resolve()

    new_paths = cfg.paths.model_copy(
        update={
            "templates": _abs(cfg.paths.templates),
            "data_raw": _abs(cfg.paths.data_raw),
            "data_output": _abs(cfg.paths.data_output),
            "logs": _abs(cfg.paths.logs),
            "legacy_config_dir": _abs(cfg.paths.legacy_config_dir),
        }
    )

    # 确保必要目录存在
    for f in ("templates", "data_raw", "data_output", "logs"):
        path: Path = getattr(new_paths, f)
        path.mkdir(parents=True, exist_ok=True)

    return cfg.model_copy(update={"paths": new_paths})


# ──────────────────────────────────────────────────────────────────
# 4. 旧 JSON 配置兼容层
# ──────────────────────────────────────────────────────────────────
def load_legacy_json(filename: str) -> dict:
    """读 04_Config/<filename>.json（report_style_config.json 等）。"""
    cfg = load_config()
    if cfg.paths.legacy_config_dir is None:
        raise ConfigError("config.yaml 未配置 paths.legacy_config_dir")
    full = cfg.paths.legacy_config_dir / filename
    if not full.is_file():
        raise ConfigError(f"旧配置文件不存在：{full}")
    with full.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_legacy_json(filename: str, data: dict) -> None:
    cfg = load_config()
    if cfg.paths.legacy_config_dir is None:
        raise ConfigError("config.yaml 未配置 paths.legacy_config_dir")
    full = cfg.paths.legacy_config_dir / filename
    full.parent.mkdir(parents=True, exist_ok=True)
    with full.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
