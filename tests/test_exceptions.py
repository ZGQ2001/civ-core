"""utils/exceptions.py 的单元测试 —— 验证四档分类、三段式渲染、继承关系。"""

from __future__ import annotations

import pytest

from civ_core.utils.exceptions import (
    BusinessError,
    CivCoreError,
    ColumnNotFoundError,
    ComUnavailable,
    ConfigError,
    ConfigMissingError,
    ConfigSchemaError,
    DocumentUnsaved,
    EmptyDataError,
    FileLockedError,
    FileWriteError,
    InfraIOError,
    InputError,
    InvalidFieldError,
    RuleViolation,
    TemplateMissing,
    WordHostNotRunning,
    format_for_log,
)


# ──────────────────────────────────────────────────────────────────
# 1. 四档继承关系
# ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "cls,base",
    [
        (ConfigSchemaError, ConfigError),
        (ConfigMissingError, ConfigError),
        (ColumnNotFoundError, InputError),
        (EmptyDataError, InputError),
        (InvalidFieldError, InputError),
        (WordHostNotRunning, BusinessError),
        (DocumentUnsaved, BusinessError),
        (TemplateMissing, BusinessError),
        (RuleViolation, BusinessError),
        (FileLockedError, InfraIOError),
        (FileWriteError, InfraIOError),
        (ComUnavailable, InfraIOError),
    ],
)
def test_subclass_in_correct_tier(cls: type, base: type) -> None:
    assert issubclass(cls, base)
    assert issubclass(cls, CivCoreError)


@pytest.mark.parametrize("base", [ConfigError, InputError, BusinessError, InfraIOError])
def test_tier_base_subclasses_root(base: type) -> None:
    assert issubclass(base, CivCoreError)


# ──────────────────────────────────────────────────────────────────
# 2. 三段式渲染（手册 §3.0 P0-7）
# ──────────────────────────────────────────────────────────────────
def test_render_with_location_and_hint() -> None:
    e = BusinessError(
        cause="文档未保存",
        location="WordApp.attach",
        hint="按 Ctrl+S 保存",
    )
    s = str(e)
    assert "[WordApp.attach]" in s
    assert "文档未保存" in s
    assert "修复建议：按 Ctrl+S 保存" in s


def test_render_without_location() -> None:
    """没传 location 时，第一行直接是 cause（不含 location 前缀）。"""
    e = ConfigError(cause="缺 [paths] 段")  # cause 里允许含方括号（例：toml 段名）
    first_line = str(e).split("\n")[0]
    assert not first_line.startswith("[")  # location 渲染会以 [ 起头
    assert first_line.startswith("缺 [paths] 段")


def test_render_falls_back_to_default_hint() -> None:
    """子类 default_hint 在不传 hint 时生效。"""
    e = WordHostNotRunning(cause="GetActiveObject 失败")
    assert e.hint == WordHostNotRunning.default_hint
    assert "Word" in str(e) and "WPS" in str(e)


def test_explicit_hint_overrides_default() -> None:
    e = WordHostNotRunning(cause="X", hint="自定义提示")
    assert e.hint == "自定义提示"
    assert "自定义提示" in str(e)


def test_render_no_hint_when_explicitly_empty() -> None:
    """传 hint='' 应抑制修复建议行。"""
    e = ConfigError(cause="x", hint="")
    assert "修复建议" not in str(e)


# ──────────────────────────────────────────────────────────────────
# 3. raise / catch 行为
# ──────────────────────────────────────────────────────────────────
def test_can_be_raised_and_caught_at_each_tier() -> None:
    with pytest.raises(BusinessError):
        raise WordHostNotRunning(cause="x")
    with pytest.raises(CivCoreError):
        raise FileLockedError(cause="x")
    with pytest.raises(InfraIOError):
        raise ComUnavailable(cause="x")


def test_top_level_catch_all() -> None:
    """main.py 兜底捕获 CivCoreError 应能拦下所有自定义异常。"""
    for cls in [ConfigSchemaError, ColumnNotFoundError, RuleViolation, FileLockedError]:
        try:
            raise cls(cause="x")
        except CivCoreError:
            pass  # OK
        except Exception:
            pytest.fail(f"{cls.__name__} 未被 CivCoreError 兜底捕获")


# ──────────────────────────────────────────────────────────────────
# 4. format_for_log
# ──────────────────────────────────────────────────────────────────
def test_format_for_log_single_line() -> None:
    e = ColumnNotFoundError(
        cause="找不到列 [桩号]",
        location="excel_reader.read_chunks",
        hint="请检查表头",
    )
    line = format_for_log(e)
    assert "\n" not in line
    assert "ColumnNotFoundError" in line
    assert "location=excel_reader.read_chunks" in line
    assert "桩号" in line
    assert "请检查表头" in line


def test_format_for_log_omits_missing_fields() -> None:
    e = InfraIOError(cause="x")
    line = format_for_log(e)
    assert "location=" not in line
    # default_hint 非空，所以应该有 hint=
    assert "hint=" in line


# ──────────────────────────────────────────────────────────────────
# 5. severity（给 V1 阶段 InfoBar 用）
# ──────────────────────────────────────────────────────────────────
def test_default_severity_is_error() -> None:
    e = ConfigError(cause="x")
    assert e.severity == "error"
