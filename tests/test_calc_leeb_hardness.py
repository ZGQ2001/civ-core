"""INSP-001 钢材里氏硬度计算骨架测试。

文档 INSP-001 中"厚度修正表 / 角度修正表 / 强度换算表"的真实数据
（GB/T 17394.4-2014 / GB/T 50344-2019 附录 N）尚未由用户录入。
本测试用 placeholder 表数据 seed 进 :memory: DB，验证：
  1. 截尾平均（剔 2 高 2 低 取 5 个均值 → 四舍五入取整）独立计算正确
  2. 单测区：HL_m + HL_t + HL_a = HL_corrected
  3. 强度查表 → fb_min；fb_max = fb_min + 150
  4. 多测区聚合：构件下/上限 = avg(各测区) / 推定 = (下+上)/2
  5. 单构件 batch_fb_char_avg == comp_fb_min_avg
"""

from __future__ import annotations

import sqlite3

import pytest

from civ_core.core.calc_functions import (
    _trim_mean_leeb,
    calc_leeb_hardness_steel,
)
from civ_core.infra_io.standards_db import (
    TABLE_LEEB_ANGLE,
    TABLE_LEEB_STRENGTH,
    TABLE_LEEB_THICKNESS,
    StandardsDB,
    StandardsRow,
)
from civ_core.utils.exceptions import InputError


# ── helpers ──────────────────────────────────────────────────────
@pytest.fixture
def db_seeded() -> StandardsDB:
    """初始化 placeholder 数据：让骨架链路能跑通，等真实表数据再替换。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    d = StandardsDB(conn)
    d.create_tables()

    # 厚度修正表（1D：厚度 mm → HL_t）：6mm=-5, 10mm=-2, 15mm=0, 25mm=+1, 50mm=+2
    for thick, hl_t in [(6.0, -5.0), (10.0, -2.0), (15.0, 0.0), (25.0, 1.0), (50.0, 2.0)]:
        d.put_row(StandardsRow(table_name=TABLE_LEEB_THICKNESS, key1=thick, value1=hl_t))

    # 角度修正表（2D：度数 × HL_m → HL_a）
    # 度数：-90 向上垂直 / -45 向上45° / 0 水平 / +45 向下45° / +90 向下垂直
    # placeholder：0° 水平时修正 0；垂直与 45° 给小偏移
    for deg, base_offset in [(-90.0, -3.0), (-45.0, -2.0), (0.0, 0.0), (45.0, 2.0), (90.0, 3.0)]:
        for hl_m in [350.0, 400.0, 500.0]:
            d.put_row(
                StandardsRow(
                    table_name=TABLE_LEEB_ANGLE,
                    key1=deg,
                    key2=hl_m,
                    value1=base_offset,
                )
            )

    # 强度换算表（1D：HL_corrected → fb_min MPa）。线性 placeholder：fb_min = HL_corr - 5
    for hl_corr, fb_min in [
        (350.0, 345.0),
        (400.0, 395.0),
        (450.0, 445.0),
        (500.0, 495.0),
    ]:
        d.put_row(
            StandardsRow(table_name=TABLE_LEEB_STRENGTH, key1=hl_corr, value1=fb_min)
        )

    return d


# ── 截尾平均（不依赖 db） ───────────────────────────────────────
def test_trim_mean_leeb_drops_2_high_2_low_takes_5_avg() -> None:
    """9 个值剔除 2 最高 + 2 最低，取剩余 5 个均值四舍五入取整。"""
    # 排序后：350, 380, 395, 400, 401, 402, 410, 415, 450
    # 剔后 5 个：395, 400, 401, 402, 410 → mean = 401.6 → ROUND = 402
    values = (450, 380, 410, 415, 402, 350, 401, 395, 400)
    assert _trim_mean_leeb(values) == 402


def test_trim_mean_leeb_uniform() -> None:
    """全等 → 直接返回该值。"""
    assert _trim_mean_leeb((400,) * 9) == 400


def test_trim_mean_leeb_requires_9_values() -> None:
    with pytest.raises(InputError, match="9"):
        _trim_mean_leeb((400,) * 8)


# ── 单测区端到端 ────────────────────────────────────────────────
def test_single_test_area_full_pipeline(db_seeded: StandardsDB) -> None:
    """1 个测区：HL_m=400, 厚度 25 → HL_t=1, 角度档 3 → HL_a=0,
    HL_corrected=401 → 强度查表（在 400~450 之间插值）→ fb_min≈396, fb_max=fb_min+150。
    """
    test_areas_raw = [(400,) * 9]
    r = calc_leeb_hardness_steel(
        test_areas_raw=test_areas_raw,
        thickness=25.0,
        angle_degrees=0.0,
        db=db_seeded,
    )
    area = r.test_areas[0]
    assert area.hl_m == 400
    assert area.hl_t == 1.0
    assert area.hl_a == 0.0
    assert area.hl_corrected == 401.0
    # 401 在 (400, 450) 之间 → fb_min = 395 + (401-400)/(450-400) * (445-395) = 395 + 1
    assert area.fb_min == pytest.approx(396.0, abs=0.5)
    assert area.fb_max == pytest.approx(area.fb_min + 150, abs=0.01)


# ── 多测区聚合 ─────────────────────────────────────────────────
def test_multi_areas_aggregation(db_seeded: StandardsDB) -> None:
    """3 个测区，原始平均都为 400，验证聚合字段一致性。"""
    test_areas_raw = [(400,) * 9, (400,) * 9, (400,) * 9]
    r = calc_leeb_hardness_steel(
        test_areas_raw=test_areas_raw,
        thickness=25.0,
        angle_degrees=0.0,
        db=db_seeded,
    )
    assert len(r.test_areas) == 3
    fb_min_avg = sum(a.fb_min for a in r.test_areas) / 3
    fb_max_avg = sum(a.fb_max for a in r.test_areas) / 3
    assert r.comp_fb_min_avg == pytest.approx(fb_min_avg, abs=0.01)
    assert r.comp_fb_max_avg == pytest.approx(fb_max_avg, abs=0.01)
    assert r.comp_fb_est == pytest.approx((fb_min_avg + fb_max_avg) / 2, abs=0.01)
    # 单构件场景下 batch_fb_char_avg == comp_fb_min_avg
    assert r.batch_fb_char_avg == pytest.approx(r.comp_fb_min_avg, abs=0.01)


# ── 角度档修正生效 ─────────────────────────────────────────────
def test_angle_category_affects_correction(db_seeded: StandardsDB) -> None:
    """档 1（向上垂直）HL_a=-3 vs 档 3（水平）HL_a=0。"""
    raw = [(400,) * 9]
    r1 = calc_leeb_hardness_steel(
        test_areas_raw=raw, thickness=25.0, angle_degrees=-90.0, db=db_seeded
    )
    r3 = calc_leeb_hardness_steel(
        test_areas_raw=raw, thickness=25.0, angle_degrees=0.0, db=db_seeded
    )
    assert r1.test_areas[0].hl_a == -3.0
    assert r3.test_areas[0].hl_a == 0.0
    assert r1.test_areas[0].hl_corrected < r3.test_areas[0].hl_corrected


# ── 厚度修正生效 ───────────────────────────────────────────────
def test_thickness_correction(db_seeded: StandardsDB) -> None:
    """6mm → HL_t=-5；50mm → HL_t=2。"""
    raw = [(400,) * 9]
    r6 = calc_leeb_hardness_steel(
        test_areas_raw=raw, thickness=6.0, angle_degrees=0.0, db=db_seeded
    )
    r50 = calc_leeb_hardness_steel(
        test_areas_raw=raw, thickness=50.0, angle_degrees=0.0, db=db_seeded
    )
    assert r6.test_areas[0].hl_t == -5.0
    assert r50.test_areas[0].hl_t == 2.0


# ── 异常路径 ───────────────────────────────────────────────────
def test_no_test_areas_raises(db_seeded: StandardsDB) -> None:
    with pytest.raises(InputError, match="测区"):
        calc_leeb_hardness_steel(
            test_areas_raw=[],
            thickness=25.0,
            angle_degrees=0.0,
            db=db_seeded,
        )


def test_invalid_angle_degrees_raises(db_seeded: StandardsDB) -> None:
    """30° 不在规范 5 档内（-90/-45/0/+45/+90）。"""
    with pytest.raises(InputError, match="角度"):
        calc_leeb_hardness_steel(
            test_areas_raw=[(400,) * 9],
            thickness=25.0,
            angle_degrees=30.0,
            db=db_seeded,
        )


def test_thickness_out_of_table_range_raises(db_seeded: StandardsDB) -> None:
    """厚度 100mm 超出 placeholder 表范围 (6~50)，应抛 InputError。"""
    with pytest.raises(InputError, match="范围"):
        calc_leeb_hardness_steel(
            test_areas_raw=[(400,) * 9],
            thickness=100.0,
            angle_degrees=0.0,
            db=db_seeded,
        )
