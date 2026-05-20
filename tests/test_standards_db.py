"""standards_db SQLite 层测试。

为什么用通用表设计 standards_tables：
  规范查表千差万别（1D：厚度修正；2D：回弹×碳化测强曲线；多列：钻芯 k1/k2_005/k2_010），
  与其每种表建一张物理表，不如用 (table_name, key1, key2?) → (value1, value2?, value3?)
  通用结构，配合常量 TableName 枚举区分用途。插值由 calc_functions 负责。

测试覆盖：
  - 建表幂等
  - put_row / put_rows 写入 + UNIQUE(table_name, key1, key2) 冲突 ON CONFLICT REPLACE
  - get_row 精确取
  - list_rows 按 table_name 全量、按 key1 升序
  - delete_table 清空某张逻辑表
  - INSP-002 k1/k2 系数表初始化（seed_core_drilling_k_table）后能读全 60 行
"""

from __future__ import annotations

import sqlite3

import pytest

from civ_core.infra_io.standards_db import (
    TABLE_CORE_DRILLING_K,
    StandardsDB,
    StandardsRow,
    seed_core_drilling_k_table,
)


@pytest.fixture
def db() -> StandardsDB:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db = StandardsDB(conn)
    db.create_tables()
    return db


# ── 建表幂等 ─────────────────────────────────────────────────────
def test_create_tables_idempotent(db: StandardsDB) -> None:
    """重复建表不应报错。"""
    db.create_tables()
    db.create_tables()


# ── put_row + get_row round-trip ─────────────────────────────────
def test_put_and_get_row_1d(db: StandardsDB) -> None:
    """1D 表（key2=None）。"""
    db.put_row(StandardsRow(table_name="t_thick", key1=10.0, value1=1.5))
    row = db.get_row("t_thick", key1=10.0)
    assert row is not None
    assert row.value1 == 1.5
    assert row.key2 is None


def test_put_and_get_row_2d(db: StandardsDB) -> None:
    """2D 表（key2 非空）。"""
    db.put_row(StandardsRow(table_name="t_2d", key1=20.0, key2=2.0, value1=15.5))
    row = db.get_row("t_2d", key1=20.0, key2=2.0)
    assert row is not None
    assert row.value1 == 15.5


def test_put_row_multi_value(db: StandardsDB) -> None:
    """k1/k2_005/k2_010 三列同时存。"""
    db.put_row(
        StandardsRow(
            table_name="t_multi",
            key1=15.0,
            value1=1.11397,
            value2=2.56600,
            value3=2.32898,
        )
    )
    row = db.get_row("t_multi", key1=15.0)
    assert row is not None
    assert row.value1 == pytest.approx(1.11397)
    assert row.value2 == pytest.approx(2.56600)
    assert row.value3 == pytest.approx(2.32898)


def test_get_row_missing_returns_none(db: StandardsDB) -> None:
    assert db.get_row("not_exist", key1=1.0) is None


# ── ON CONFLICT REPLACE：重复 key 应覆盖 ──────────────────────────
def test_put_row_replace_on_conflict(db: StandardsDB) -> None:
    db.put_row(StandardsRow(table_name="t", key1=1.0, value1=10.0))
    db.put_row(StandardsRow(table_name="t", key1=1.0, value1=20.0))
    row = db.get_row("t", key1=1.0)
    assert row is not None
    assert row.value1 == 20.0


# ── list_rows 按 key1 升序 ───────────────────────────────────────
def test_list_rows_sorted_by_key1(db: StandardsDB) -> None:
    db.put_rows(
        [
            StandardsRow(table_name="t", key1=3.0, value1=30.0),
            StandardsRow(table_name="t", key1=1.0, value1=10.0),
            StandardsRow(table_name="t", key1=2.0, value1=20.0),
        ]
    )
    rows = db.list_rows("t")
    assert [r.key1 for r in rows] == [1.0, 2.0, 3.0]


def test_list_rows_filtered_by_table(db: StandardsDB) -> None:
    """不同 table_name 互不污染。"""
    db.put_row(StandardsRow(table_name="a", key1=1.0, value1=1.0))
    db.put_row(StandardsRow(table_name="b", key1=2.0, value1=2.0))
    assert len(db.list_rows("a")) == 1
    assert len(db.list_rows("b")) == 1


# ── delete_table ────────────────────────────────────────────────
def test_delete_table_clears_only_target(db: StandardsDB) -> None:
    db.put_row(StandardsRow(table_name="a", key1=1.0, value1=1.0))
    db.put_row(StandardsRow(table_name="b", key1=2.0, value1=2.0))
    db.delete_table("a")
    assert db.list_rows("a") == []
    assert len(db.list_rows("b")) == 1


# ── INSP-002 k1/k2 表初始化 ──────────────────────────────────────
def test_seed_core_drilling_k_table(db: StandardsDB) -> None:
    """seed 函数应录入 60 行（n=10..50 共 41 行 + n=60..200 共 15 行 + n=250..500 共 4 行）= 60 行。"""
    seed_core_drilling_k_table(db)
    rows = db.list_rows(TABLE_CORE_DRILLING_K)
    assert len(rows) == 60

    # 抽检 n=15 这一行的三个系数（INSP-002 文档表 A.0.2）
    row15 = db.get_row(TABLE_CORE_DRILLING_K, key1=15.0)
    assert row15 is not None
    assert row15.value1 == pytest.approx(1.11397, abs=1e-5)
    assert row15.value2 == pytest.approx(2.56600, abs=1e-5)
    assert row15.value3 == pytest.approx(2.32898, abs=1e-5)

    # 抽检边界：n=10 / n=500
    row10 = db.get_row(TABLE_CORE_DRILLING_K, key1=10.0)
    assert row10 is not None
    assert row10.value1 == pytest.approx(1.01730, abs=1e-5)

    row500 = db.get_row(TABLE_CORE_DRILLING_K, key1=500.0)
    assert row500 is not None
    assert row500.value1 == pytest.approx(1.53671, abs=1e-5)


def test_seed_idempotent(db: StandardsDB) -> None:
    """重复 seed 不应翻倍（ON CONFLICT REPLACE 兜底）。"""
    seed_core_drilling_k_table(db)
    seed_core_drilling_k_table(db)
    rows = db.list_rows(TABLE_CORE_DRILLING_K)
    assert len(rows) == 60
