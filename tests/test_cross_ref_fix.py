"""core/cross_ref_fix.py 的单元测试（不依赖真 Word，全用 mock）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from civ_core.models.schema import (
    AppException,
    CrossRefFixStats,
    ProgressUpdate,
)

from civ_core.core.cross_ref_fix import (
    DEFAULT_SWITCH,
    WD_FIELD_REF,
    CrossRefFixParams,
    fix_cross_references,
)


# ──────────────────────────────────────────────────────────────────
# 测试桩：伪造 Word.Fields 集合
# ──────────────────────────────────────────────────────────────────
class FakeCode:
    """模拟 field.Code，可读可写 .Text。"""

    def __init__(self, text: str):
        self.Text = text


class FakeField:
    def __init__(self, ftype: int, code_text: str):
        self.Type = ftype
        self.Code = FakeCode(code_text)


class FakeFields:
    """模拟 Word.Document.Fields 集合 (1-indexed)。"""

    def __init__(self, fields: list[FakeField]):
        self._fields = fields

    @property
    def Count(self) -> int:
        return len(self._fields)

    def Item(self, i: int) -> FakeField:
        return self._fields[i - 1]


def _make_doc(fields: list[FakeField]) -> SimpleNamespace:
    return SimpleNamespace(Fields=FakeFields(fields))


# ──────────────────────────────────────────────────────────────────
# 测试用例
# ──────────────────────────────────────────────────────────────────
def test_no_fields() -> None:
    doc = _make_doc([])
    stats = fix_cross_references(doc)
    assert stats == CrossRefFixStats(refs_processed=0, refs_updated=0)


def test_skips_non_ref_fields() -> None:
    """只处理 Type == 3 的；其他域类型完全跳过。"""
    doc = _make_doc(
        [
            FakeField(ftype=1, code_text="DATE"),  # 非 REF
            FakeField(ftype=WD_FIELD_REF, code_text="REF _Ref1 \\h"),  # REF, 缺开关
            FakeField(ftype=88, code_text="HYPERLINK ..."),  # 非 REF
        ]
    )
    stats = fix_cross_references(doc)
    assert stats.refs_processed == 1
    assert stats.refs_updated == 1
    assert "MERGEFORMAT" in doc.Fields.Item(2).Code.Text


def test_already_has_switch_is_noop() -> None:
    """已含 \\* MERGEFORMAT 的不再追加。"""
    doc = _make_doc(
        [
            FakeField(ftype=WD_FIELD_REF, code_text=f"REF _Ref1 \\h {DEFAULT_SWITCH}"),
        ]
    )
    original = doc.Fields.Item(1).Code.Text
    stats = fix_cross_references(doc)
    assert stats.refs_processed == 1
    assert stats.refs_updated == 0
    assert doc.Fields.Item(1).Code.Text == original


def test_case_insensitive_switch_check() -> None:
    """开关检查应大小写不敏感。"""
    doc = _make_doc(
        [
            FakeField(ftype=WD_FIELD_REF, code_text=r"REF _Ref1 \h \* mergeformat"),  # 小写
        ]
    )
    stats = fix_cross_references(doc)
    assert stats.refs_updated == 0  # 不重复追加


def test_dry_run_does_not_mutate() -> None:
    """dry_run=True 只统计，不改 .Text。"""
    f = FakeField(ftype=WD_FIELD_REF, code_text="REF _Ref1 \\h")
    doc = _make_doc([f])
    stats = fix_cross_references(doc, params=CrossRefFixParams(dry_run=True))
    assert stats.refs_processed == 1
    assert stats.refs_updated == 1  # 统计算"待更新"
    assert f.Code.Text == "REF _Ref1 \\h"  # 但实际未改


def test_progress_callback_called() -> None:
    """progress 回调每个域调一次，total/current 数值正确。"""
    fields = [FakeField(WD_FIELD_REF, "REF _R \\h") for _ in range(5)]
    doc = _make_doc(fields)

    received: list[ProgressUpdate] = []
    fix_cross_references(doc, progress=received.append)

    assert len(received) == 5
    assert received[0].current == 1 and received[0].total == 5
    assert received[-1].current == 5
    assert all(isinstance(p, ProgressUpdate) for p in received)


def test_single_field_failure_does_not_abort() -> None:
    """中间某个 field 抛异常不应熔断整个扫描。"""

    class ExplodingField:
        Type = WD_FIELD_REF

        @property
        def Code(self):
            raise RuntimeError("boom")

    doc = _make_doc(
        [
            FakeField(WD_FIELD_REF, "REF a \\h"),
            ExplodingField(),  # type: ignore
            FakeField(WD_FIELD_REF, "REF b \\h"),
        ]
    )
    stats = fix_cross_references(doc)
    # 第 1、3 个成功，第 2 个跳过
    assert stats.refs_processed == 2
    assert stats.refs_updated == 2


def test_fields_attr_missing_raises_app_exception() -> None:
    """target_doc 缺少 Fields → 业务异常 AppException（带 hint）。"""
    doc = SimpleNamespace()  # 没有 .Fields
    with pytest.raises(AppException) as exc_info:
        fix_cross_references(doc)
    assert "Fields" in str(exc_info.value)
    assert exc_info.value.user_hint != ""
