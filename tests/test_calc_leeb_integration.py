"""INSP-001 里氏硬度端到端集成测试（用真实规范表 + Excel 中的实测数据）。

数据来源：docs/civil_kb/formulas/计算表格.xlsx → 钢材硬度 sheet 序号 1（地上一层 2×H 钢柱）
  厚度 12mm，测量角度 +90°（向上垂直），3 个测区每区 9 个 HL 读数。

测试目标：
  1. 三表（厚度/角度/强度）seed 后 calc_leeb_hardness_steel 跑通端到端
  2. HL_m 截尾平均完全精确（不涉及插值，是验证最强约束）
  3. 厚度修正 12mm → HL_t=0（表内精确匹配）
  4. 角度修正在 HL_m 上插值（+90° 档：450→-24, 500→-22）
  5. fb_min 在 HL_corrected 上插值，fb_max=fb_min+150
"""

from __future__ import annotations

import sqlite3

import pytest

from civ_core.core.calc_functions import calc_leeb_hardness_steel
from civ_core.infra_io.standards_db import StandardsDB, seed_all_leeb_tables


@pytest.fixture
def db_real() -> StandardsDB:
    """真实规范表 seed 进 :memory: DB。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    d = StandardsDB(conn)
    d.create_tables()
    seed_all_leeb_tables(d)
    return d


# Excel 序号 1（地上一层 2×H 钢柱）原始数据：3 测区 × 9 点
SEQ1_ZONE1 = (483, 481, 480, 481, 474, 479, 479, 483, 474)
SEQ1_ZONE2 = (488, 479, 488, 479, 481, 486, 487, 485, 493)
SEQ1_ZONE3 = (476, 489, 470, 481, 487, 476, 478, 486, 473)
SEQ1_THICKNESS = 12.0
SEQ1_ANGLE = 90.0  # 向上垂直（+90° 档）


def test_seq1_hl_m_exact() -> None:
    """HL_m 截尾平均（剔 2 高 2 低取 5 个）—— 手算精确值。

    测区 1: sorted=[474,474,479,479,480,481,481,483,483]，剔后 [479,479,480,481,481]，mean=2400/5=480
    测区 2: sorted=[479,479,481,485,486,487,488,488,493]，剔后 [481,485,486,487,488]，mean=2427/5=485.4→485
    测区 3: sorted=[470,473,476,476,478,481,486,487,489]，剔后 [476,476,478,481,486]，mean=2397/5=479.4→479
    """
    from civ_core.core.calc_functions import _trim_mean_leeb

    assert _trim_mean_leeb(SEQ1_ZONE1) == 480
    assert _trim_mean_leeb(SEQ1_ZONE2) == 485
    assert _trim_mean_leeb(SEQ1_ZONE3) == 479


def test_seq1_full_pipeline(db_real: StandardsDB) -> None:
    """端到端：3 测区 → 构件级聚合，验证关键中间量与最终推定值。"""
    r = calc_leeb_hardness_steel(
        test_areas_raw=[SEQ1_ZONE1, SEQ1_ZONE2, SEQ1_ZONE3],
        thickness=SEQ1_THICKNESS,
        angle_degrees=SEQ1_ANGLE,
        db=db_real,
    )
    assert len(r.test_areas) == 3

    # ── 测区 1：HL_m=480 ──────────────────────────────────────
    a1 = r.test_areas[0]
    assert a1.hl_m == 480
    assert a1.hl_t == 0.0  # 12mm 表内精确匹配
    # +90° 档 HL_m=480 → 在 450(-24) 和 500(-22) 之间插值 t=0.6 → -22.8
    assert a1.hl_a == pytest.approx(-22.8, abs=0.001)
    assert a1.hl_corrected == pytest.approx(457.2, abs=0.001)
    # 强度表 456→502, 458→506；457.2 → t=0.6 → 504.4
    assert a1.fb_min == pytest.approx(504.4, abs=0.01)
    assert a1.fb_max == pytest.approx(654.4, abs=0.01)

    # ── 测区 2：HL_m=485 ──────────────────────────────────────
    a2 = r.test_areas[1]
    assert a2.hl_m == 485
    # +90° 档 HL_m=485 → 450(-24)/500(-22) 插值 t=0.7 → -22.6
    assert a2.hl_a == pytest.approx(-22.6, abs=0.001)
    assert a2.hl_corrected == pytest.approx(462.4, abs=0.001)
    # 强度表 462→514, 464→518；462.4 → t=0.2 → 514.8
    assert a2.fb_min == pytest.approx(514.8, abs=0.01)

    # ── 测区 3：HL_m=479 ──────────────────────────────────────
    a3 = r.test_areas[2]
    assert a3.hl_m == 479
    # +90° 档 HL_m=479 → 450(-24)/500(-22) 插值 t=0.58 → -22.84
    assert a3.hl_a == pytest.approx(-22.84, abs=0.001)
    assert a3.hl_corrected == pytest.approx(456.16, abs=0.001)

    # ── 构件级聚合 ─────────────────────────────────────────────
    expected_fb_min_avg = (a1.fb_min + a2.fb_min + a3.fb_min) / 3
    expected_fb_max_avg = (a1.fb_max + a2.fb_max + a3.fb_max) / 3
    assert r.comp_fb_min_avg == pytest.approx(expected_fb_min_avg, abs=0.01)
    assert r.comp_fb_max_avg == pytest.approx(expected_fb_max_avg, abs=0.01)
    assert r.comp_fb_est == pytest.approx(
        (expected_fb_min_avg + expected_fb_max_avg) / 2, abs=0.01
    )
    # 单构件 → 批级 = comp_fb_min_avg
    assert r.batch_fb_char_avg == pytest.approx(r.comp_fb_min_avg, abs=0.01)

    # 抗拉强度推定值应在合理范围（Q355 钢材抗拉强度 ≥ 470 MPa）
    assert 480 < r.comp_fb_est < 700, "推定抗拉强度应在合理范围"


def test_thickness_gt_12_returns_zero_correction(db_real: StandardsDB) -> None:
    """板厚 > 12mm（如 20mm）→ HL_t = 0（哨兵 999.0 让插值返回 0）。"""
    r = calc_leeb_hardness_steel(
        test_areas_raw=[SEQ1_ZONE1],
        thickness=20.0,
        angle_degrees=0.0,
        db=db_real,
    )
    assert r.test_areas[0].hl_t == 0.0


def test_thinner_plate_positive_correction(db_real: StandardsDB) -> None:
    """6mm 薄板 → HL_t = +30 表内精确匹配；但需保证 HL_corr 落在强度表范围内。

    用 HL_m=400 + thickness=6 + angle=-90°（向下垂直，基线档 HL_a=0）→ HL_corr=430，
    在强度表 [255, 480] 内。
    """
    raw = (400,) * 9
    r = calc_leeb_hardness_steel(
        test_areas_raw=[raw],
        thickness=6.0,
        angle_degrees=-90.0,
        db=db_real,
    )
    assert r.test_areas[0].hl_t == 30.0
    assert r.test_areas[0].hl_corrected == 430.0


def test_upward_vertical_no_angle_correction(db_real: StandardsDB) -> None:
    """-90°（向下垂直，规范基线档）→ HL_a = 0 对所有 HL_m（规范表 -90° 列全部为 0）。

    这是规范的物理基准：枪口朝下垂直冲击时即为基线方向，
    实测里氏值无需修正。其它角度（如水平 0°）实际都是负值修正。
    """
    r = calc_leeb_hardness_steel(
        test_areas_raw=[SEQ1_ZONE1],
        thickness=12.0,
        angle_degrees=-90.0,
        db=db_real,
    )
    assert r.test_areas[0].hl_a == 0.0


def test_horizontal_has_nonzero_correction(db_real: StandardsDB) -> None:
    """0°（水平）实际是负值修正（HL_m=480 → 在 450(-10)/500(-10) 间 → -10）。

    规范的物理含义：水平方向冲击时重力影响中等，需要 -10~-14 的修正。
    """
    r = calc_leeb_hardness_steel(
        test_areas_raw=[SEQ1_ZONE1],
        thickness=12.0,
        angle_degrees=0.0,
        db=db_real,
    )
    # 0° 列 HL_m=450→-10, 500→-10；HL_m=480 插值 = -10
    assert r.test_areas[0].hl_a == -10.0


def test_typo_fix_650_plus_90_is_negative_18(db_real: StandardsDB) -> None:
    """源 Excel 中 (HL_m=650, +90°) 漏负号为 18，已修正为 -18，端到端验证。

    HL_m=650 → +90° 修正 = -18 → HL_corr=632，但强度表只到 480；
    为了端到端验证修正值生效，直接断言中间量 hl_a。
    """
    from civ_core.core.calc_functions import _lookup_2d_fixed_key1_interp_key2
    from civ_core.infra_io.standards_db import TABLE_LEEB_ANGLE

    # 直接查表验证修正值
    hl_a = _lookup_2d_fixed_key1_interp_key2(
        db_real,
        TABLE_LEEB_ANGLE,
        key1=90.0,
        key2=650.0,
        value_idx="value1",
        key1_label="测量角度",
    )
    assert hl_a == -18.0, "源 Excel 漏负号已修正：(650, +90°) → -18"
