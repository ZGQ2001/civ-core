"""INSP-002 钻芯法计算函数测试。

calc_core_drilling_concrete(values, *, db, take, small_diameter, design_fcu=None)
  → CoreDrillingResult

测试覆盖：
  - n=10 精确命中表（常规芯样 / 小直径芯样两种 k2）
  - n=15 与文档示例对齐（k1=1.11397, k2_005=2.56600）
  - n=18 表里有，验证基本流程
  - n=55 表里没有，要在 n=50 和 n=60 之间线性插值 k1/k2
  - n 越界（<10 / >500）抛 InputError
  - take='upper' 与 'lower' 推定值正确
  - design_fcu 传入时自动判定 passed
  - 精度：f_cu_cor_m / f_cu_e1 / f_cu_e2 精确至 0.1，s_cu 精确至 0.01
"""

from __future__ import annotations

import math
import sqlite3
import statistics

import pytest

from civ_core.core.calc_functions import calc_core_drilling_concrete
from civ_core.infra_io.standards_db import StandardsDB, seed_core_drilling_k_table
from civ_core.utils.exceptions import InputError


@pytest.fixture
def db() -> StandardsDB:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    d = StandardsDB(conn)
    d.create_tables()
    seed_core_drilling_k_table(d)
    return d


# ── 精确命中：n=10，常规 ─────────────────────────────────────────
def test_n10_regular_take_lower(db: StandardsDB) -> None:
    values = (28.5, 30.1, 31.7, 29.4, 28.9, 30.6, 31.2, 29.8, 30.0, 29.6)
    r = calc_core_drilling_concrete(values, db=db, take="lower")
    # 直接核对统计量
    assert r.n == 10
    assert r.f_cu_cor_m == pytest.approx(round(statistics.mean(values), 1), abs=0.01)
    s_expected = round(statistics.stdev(values), 2)
    assert r.s_cu == pytest.approx(s_expected, abs=0.001)
    # 系数命中 n=10（常规芯样 k2 用 k2_005 = 2.91096）
    assert r.k1 == pytest.approx(1.01730, abs=1e-5)
    assert r.k2 == pytest.approx(2.91096, abs=1e-5)
    # 推定值
    e1_expected = round(r.f_cu_cor_m - r.k1 * r.s_cu, 1)
    e2_expected = round(r.f_cu_cor_m - r.k2 * r.s_cu, 1)
    assert r.f_cu_e1 == pytest.approx(e1_expected, abs=0.01)
    assert r.f_cu_e2 == pytest.approx(e2_expected, abs=0.01)
    assert r.f_cu_est == r.f_cu_e2
    assert r.take == "lower"


def test_n10_small_diameter_uses_k2_010(db: StandardsDB) -> None:
    """小直径芯样：k2 取 k2_010 列 = 2.56837。"""
    values = tuple([30.0] * 10)  # 标准差 = 0 → 推定值 = 平均
    r = calc_core_drilling_concrete(values, db=db, take="lower", small_diameter=True)
    assert r.k2 == pytest.approx(2.56837, abs=1e-5)


def test_n15_matches_doc_example(db: StandardsDB) -> None:
    """INSP-002 文档示例 A：n=15, k1=1.11397, k2_005=2.56600。"""
    values = tuple(28.0 + 0.1 * i for i in range(15))
    r = calc_core_drilling_concrete(values, db=db, take="upper")
    assert r.k1 == pytest.approx(1.11397, abs=1e-5)
    assert r.k2 == pytest.approx(2.56600, abs=1e-5)
    # take=upper → est = e1
    assert r.f_cu_est == r.f_cu_e1


# ── 线性插值：n=55（落在 50 与 60 之间）────────────────────────
def test_n55_linear_interpolation(db: StandardsDB) -> None:
    """n=55 介于 50 与 60 之间，k 按 (n-50)/(60-50) 线性插值。"""
    values = tuple(30.0 + 0.01 * i for i in range(55))
    r = calc_core_drilling_concrete(values, db=db, take="lower")

    # 期望 k 值：(k_50 + k_60) / 2
    k1_50, k1_60 = 1.32939, 1.35412
    k2_50, k2_60 = 2.06499, 2.02216
    assert r.k1 == pytest.approx((k1_50 + k1_60) / 2, abs=1e-5)
    assert r.k2 == pytest.approx((k2_50 + k2_60) / 2, abs=1e-5)


# ── 边界 / 异常路径 ─────────────────────────────────────────────
def test_n_less_than_10_raises(db: StandardsDB) -> None:
    with pytest.raises(InputError, match="n"):
        calc_core_drilling_concrete((30.0,) * 9, db=db, take="lower")


def test_n_greater_than_500_raises(db: StandardsDB) -> None:
    with pytest.raises(InputError, match="500"):
        calc_core_drilling_concrete((30.0,) * 501, db=db, take="lower")


def test_invalid_take_raises(db: StandardsDB) -> None:
    with pytest.raises(InputError, match="take"):
        calc_core_drilling_concrete((30.0,) * 10, db=db, take="middle")  # type: ignore[arg-type]


# ── design_fcu → passed 判定 ────────────────────────────────────
def test_design_fcu_pass(db: StandardsDB) -> None:
    """推定值 >= 设计强度 → passed=True。"""
    values = tuple([35.0] * 10)  # s=0 → e1=e2=35
    r = calc_core_drilling_concrete(values, db=db, take="lower", design_fcu=30.0)
    assert r.passed is True
    assert r.f_cu_est == pytest.approx(35.0, abs=0.01)


def test_design_fcu_fail(db: StandardsDB) -> None:
    values = tuple([20.0] * 10)
    r = calc_core_drilling_concrete(values, db=db, take="lower", design_fcu=30.0)
    assert r.passed is False


def test_default_passed_true_when_no_design(db: StandardsDB) -> None:
    """未传 design_fcu 时，passed 缺省 True（外部自行判定）。"""
    r = calc_core_drilling_concrete((30.0,) * 10, db=db, take="lower")
    assert r.passed is True


# ── 数据完整性 ────────────────────────────────────────────────
def test_result_contains_raw_values(db: StandardsDB) -> None:
    values = tuple(28.0 + i for i in range(10))
    r = calc_core_drilling_concrete(values, db=db, take="lower")
    assert r.f_cu_cor_values == values


def test_zero_variance(db: StandardsDB) -> None:
    """全等值 → s=0 → e1=e2=mean。"""
    values = tuple([25.5] * 12)
    r = calc_core_drilling_concrete(values, db=db, take="upper")
    assert r.s_cu == 0.0
    assert r.f_cu_e1 == pytest.approx(25.5, abs=0.01)
    assert r.f_cu_e2 == pytest.approx(25.5, abs=0.01)
    assert math.isfinite(r.f_cu_est)
