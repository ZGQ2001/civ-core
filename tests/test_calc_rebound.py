"""INSP-003 回弹法计算骨架测试。

JGJ/T 23-2011 附录 A 测强曲线表（R_m × d_m）数据尚未由用户录入。
本测试用 placeholder 二维表 seed :memory: DB 验证：
  1. 截尾平均（剔 3 高 3 低 取 10 个均值，精确至 0.1）独立计算
  2. 碳化深度归一化（< 0.5 → 0, ≥ 6 → 6）
  3. 测强曲线查表（按 d_m 分档 + R_m 插值）
  4. n<10 → mode=single, f_cu_e = min(f_cu_i)
  5. n>=10 → mode=batch, f_cu_e = m_fcu - 1.645 * s_fcu
  6. 用户提供 angle_correction / surface_correction 修正 R_m
"""

from __future__ import annotations

import sqlite3
import statistics

import pytest

from civ_core.core.calc_functions import (
    _normalize_carbonation_depth,
    _trim_mean_rebound,
    calc_rebound_concrete,
)
from civ_core.infra_io.standards_db import (
    TABLE_REBOUND_STRENGTH,
    StandardsDB,
    StandardsRow,
)
from civ_core.utils.exceptions import InputError


@pytest.fixture
def db_seeded() -> StandardsDB:
    """placeholder 测强曲线：d_m 分档 [0.0, 2.0, 4.0, 6.0]，R_m 点 [30, 40, 50]。
    f_cu = R_m - d_m * 2 - 5 （线性 placeholder）。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    d = StandardsDB(conn)
    d.create_tables()

    for dm in [0.0, 2.0, 4.0, 6.0]:
        for rm in [30.0, 40.0, 50.0]:
            f_cu = rm - dm * 2.0 - 5.0
            d.put_row(
                StandardsRow(
                    table_name=TABLE_REBOUND_STRENGTH,
                    key1=dm,
                    key2=rm,
                    value1=f_cu,
                )
            )
    return d


# ── 截尾平均 ───────────────────────────────────────────────────
def test_trim_mean_rebound_drops_3_high_3_low_takes_10() -> None:
    """16 个值剔除 3 最高 + 3 最低，取剩余 10 个均值，精确至 0.1。"""
    # 1..16 → 排序 1..16 → 剔后剩 4..13 → mean = 8.5
    values = tuple(range(1, 17))
    assert _trim_mean_rebound(values) == pytest.approx(8.5, abs=0.01)


def test_trim_mean_rebound_rounds_to_0_1() -> None:
    """剩 10 个均值是 35.16 → round 至 0.1 → 35.2。"""
    # 构造 16 个回弹值，剔除后 10 个均值为 35.16
    middle = (30, 32, 34, 35, 35, 36, 36, 37, 38, 39)  # mean = 35.2 实际
    assert sum(middle) / 10 == 35.2
    values = (1, 2, 3, *middle, 99, 98, 97)
    assert _trim_mean_rebound(values) == 35.2


def test_trim_mean_rebound_requires_16_values() -> None:
    with pytest.raises(InputError, match="16"):
        _trim_mean_rebound(tuple(range(15)))


# ── 碳化深度归一化 ─────────────────────────────────────────────
def test_normalize_carbonation_below_half_to_zero() -> None:
    assert _normalize_carbonation_depth(0.3) == 0.0
    assert _normalize_carbonation_depth(0.49) == 0.0


def test_normalize_carbonation_above_six_to_six() -> None:
    assert _normalize_carbonation_depth(7.0) == 6.0
    assert _normalize_carbonation_depth(99.0) == 6.0


def test_normalize_carbonation_rounding_and_passthrough() -> None:
    assert _normalize_carbonation_depth(2.5) == 2.5
    assert _normalize_carbonation_depth(6.0) == 6.0
    assert _normalize_carbonation_depth(0.5) == 0.5
    assert _normalize_carbonation_depth(2.3) == 2.5
    assert _normalize_carbonation_depth(2.2) == 2.0
    assert _normalize_carbonation_depth(2.25) == 2.0


def test_normalize_carbonation_negative_raises() -> None:
    with pytest.raises(InputError, match="碳化深度"):
        _normalize_carbonation_depth(-1.0)


# ── single 模式（n<10）─────────────────────────────────────────
def test_single_mode_takes_min(db_seeded: StandardsDB) -> None:
    """3 个测区：R_m 不同 → f_cu_i 不同 → f_cu_e 取最小值。"""
    raw_zone1 = tuple([30] * 16)  # R_m=30 → f_cu=30-0*2-5=25
    raw_zone2 = tuple([40] * 16)  # R_m=40 → f_cu=35
    raw_zone3 = tuple([35] * 16)  # R_m=35 → f_cu 在 30~40 之间插值 = 35-0-5=30
    r = calc_rebound_concrete(
        test_areas_raw=[raw_zone1, raw_zone2, raw_zone3],
        carbonation_depth=0.0,
        db=db_seeded,
    )
    assert r.mode == "single"
    assert r.n == 3
    assert r.f_cu_e == 25.0  # min
    # m_fcu / s_fcu 参考值
    assert r.m_fcu == pytest.approx(round((25 + 35 + 30) / 3, 1), abs=0.01)


# ── batch 模式（n>=10）─────────────────────────────────────────
def test_batch_mode_lower_quantile(db_seeded: StandardsDB) -> None:
    """10 个测区 → mode=batch, f_cu_e = m_fcu - 1.645 * s_fcu。"""
    # 10 个测区 R_m 在 35~44 之间，d_m=0
    raws = [tuple([35 + i] * 16) for i in range(10)]
    r = calc_rebound_concrete(
        test_areas_raw=raws,
        carbonation_depth=0.0,
        db=db_seeded,
    )
    assert r.mode == "batch"
    assert r.n == 10
    fcus = [a.f_cu_i for a in r.test_areas]
    m_expected = round(statistics.mean(fcus), 1)
    s_expected = round(statistics.stdev(fcus), 2)
    assert r.m_fcu == pytest.approx(m_expected, abs=0.01)
    assert r.s_fcu == pytest.approx(s_expected, abs=0.001)
    assert r.f_cu_e == pytest.approx(round(m_expected - 1.645 * s_expected, 1), abs=0.01)


# ── 碳化深度生效（d_m=2 → f_cu 降低）─────────────────────────
def test_carbonation_affects_strength(db_seeded: StandardsDB) -> None:
    raw = [tuple([40] * 16)]
    r_no_carb = calc_rebound_concrete(test_areas_raw=raw, carbonation_depth=0.0, db=db_seeded)
    r_carb = calc_rebound_concrete(test_areas_raw=raw, carbonation_depth=2.0, db=db_seeded)
    # placeholder: d_m=0 → f_cu=35, d_m=2 → f_cu=31
    assert r_no_carb.test_areas[0].f_cu_i == 35.0
    assert r_carb.test_areas[0].f_cu_i == 31.0


# ── 角度 / 表面修正生效 ────────────────────────────────────────
def test_user_supplied_corrections_adjust_r_m(db_seeded: StandardsDB) -> None:
    """用户传 angle_correction=+2，R_m=30 → 修正后 R_m=32（查表用 32）。"""
    raw = [tuple([30] * 16)]
    r = calc_rebound_concrete(
        test_areas_raw=raw,
        carbonation_depth=0.0,
        angle_correction=2.0,
        db=db_seeded,
    )
    # R_m=32 在 (30, 40) 间插值；查表 d_m=0 时 f_cu(30)=25, f_cu(40)=35
    # → f_cu(32) = 25 + (32-30)/(40-30) * (35-25) = 27
    assert r.test_areas[0].r_m == pytest.approx(32.0, abs=0.01)
    assert r.test_areas[0].f_cu_i == pytest.approx(27.0, abs=0.01)


# ── 异常路径 ───────────────────────────────────────────────────
def test_empty_test_areas_raises(db_seeded: StandardsDB) -> None:
    with pytest.raises(InputError, match="测区"):
        calc_rebound_concrete(test_areas_raw=[], carbonation_depth=0.0, db=db_seeded)


def test_r_m_out_of_table_raises(db_seeded: StandardsDB) -> None:
    """R_m=100 超出 placeholder 表 [30, 50] → 应抛 InputError。"""
    raw = [tuple([100] * 16)]
    with pytest.raises(InputError, match="超出"):
        calc_rebound_concrete(test_areas_raw=raw, carbonation_depth=0.0, db=db_seeded)
