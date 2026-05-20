"""calc_schema 数据契约测试。

3 类结果 dataclass 对应 3 份公式文档：
  LeebHardnessResult    ← INSP-001 钢材里氏硬度推算抗拉强度
  CoreDrillingResult    ← INSP-002 钻芯法混凝土抗压强度推定
  ReboundResult         ← INSP-003 回弹法混凝土抗压强度推定

每个 dataclass 都 frozen，__post_init__ 校验关键不变量
（n>=1、推定值非负、推定上下限关系等），让脏数据进 core 层就报错。
"""

from __future__ import annotations

import pytest

from civ_core.domain.calc_schema import (
    CoreDrillingResult,
    LeebHardnessResult,
    LeebHardnessTestArea,
    ReboundResult,
    ReboundTestArea,
)


# ── LeebHardnessTestArea (测区级) ────────────────────────────────
def test_leeb_test_area_basic() -> None:
    area = LeebHardnessTestArea(
        raw_hl_values=(401, 412, 395, 408, 402, 411, 399, 415, 405),
        hl_m=406,
        hl_t=2.0,
        hl_a=-3.0,
        hl_corrected=405.0,
        fb_min=400.0,
        fb_max=550.0,
    )
    assert area.hl_m == 406
    assert area.fb_max == area.fb_min + 150  # INSP-001 §1.4 规则


def test_leeb_test_area_requires_9_raw_values() -> None:
    """规范固定每测区 9 个测点，少一个就该报错。"""
    with pytest.raises(ValueError, match="9 个"):
        LeebHardnessTestArea(
            raw_hl_values=(400, 410, 420, 430, 440, 450, 460, 470),  # 只 8 个
            hl_m=440,
            hl_t=0.0,
            hl_a=0.0,
            hl_corrected=440.0,
            fb_min=500.0,
            fb_max=650.0,
        )


def test_leeb_test_area_fb_max_must_exceed_fb_min() -> None:
    with pytest.raises(ValueError, match="fb_max"):
        LeebHardnessTestArea(
            raw_hl_values=tuple([400] * 9),
            hl_m=400,
            hl_t=0.0,
            hl_a=0.0,
            hl_corrected=400.0,
            fb_min=500.0,
            fb_max=400.0,
        )


# ── LeebHardnessResult (构件 + 批级) ─────────────────────────────
def test_leeb_result_aggregation() -> None:
    a1 = _mock_area(fb_min=400, fb_max=550)
    a2 = _mock_area(fb_min=420, fb_max=570)
    a3 = _mock_area(fb_min=410, fb_max=560)
    result = LeebHardnessResult(
        test_areas=(a1, a2, a3),
        comp_fb_min_avg=410.0,
        comp_fb_max_avg=560.0,
        comp_fb_est=485.0,
        batch_fb_char_avg=410.0,
    )
    assert len(result.test_areas) == 3
    assert result.comp_fb_est == pytest.approx((410 + 560) / 2)


def test_leeb_result_requires_at_least_one_area() -> None:
    with pytest.raises(ValueError, match="不少于"):
        LeebHardnessResult(
            test_areas=(),
            comp_fb_min_avg=0.0,
            comp_fb_max_avg=0.0,
            comp_fb_est=0.0,
            batch_fb_char_avg=0.0,
        )


# ── CoreDrillingResult ───────────────────────────────────────────
def test_core_drilling_result_basic() -> None:
    r = CoreDrillingResult(
        f_cu_cor_values=(28.5, 30.1, 31.7, 29.4, 28.9, 30.6, 31.2, 29.8, 30.0, 29.6),
        n=10,
        f_cu_cor_m=30.0,
        s_cu=1.05,
        k1=1.01730,
        k2=2.91096,
        f_cu_e1=28.9,
        f_cu_e2=27.0,
        f_cu_est=27.0,
        take="lower",
        passed=True,
    )
    assert r.n == 10
    assert r.f_cu_e1 > r.f_cu_e2  # 上限 > 下限


def test_core_drilling_requires_n_ge_10() -> None:
    """JGJ/T 384-2016 表 A.0.2 起始 n=10。"""
    with pytest.raises(ValueError, match="n"):
        CoreDrillingResult(
            f_cu_cor_values=(28.0, 30.0),
            n=2,
            f_cu_cor_m=29.0,
            s_cu=1.0,
            k1=1.0,
            k2=2.0,
            f_cu_e1=28.0,
            f_cu_e2=27.0,
            f_cu_est=27.0,
            take="lower",
            passed=True,
        )


def test_core_drilling_take_validates() -> None:
    with pytest.raises(ValueError, match="take"):
        CoreDrillingResult(
            f_cu_cor_values=tuple([30.0] * 10),
            n=10,
            f_cu_cor_m=30.0,
            s_cu=1.0,
            k1=1.0,
            k2=2.0,
            f_cu_e1=29.0,
            f_cu_e2=28.0,
            f_cu_est=28.0,
            take="middle",  # 非法
            passed=True,
        )


def test_core_drilling_values_count_matches_n() -> None:
    with pytest.raises(ValueError, match="长度"):
        CoreDrillingResult(
            f_cu_cor_values=(30.0, 31.0),  # 2 个，但 n=10
            n=10,
            f_cu_cor_m=30.5,
            s_cu=0.5,
            k1=1.0,
            k2=2.0,
            f_cu_e1=29.5,
            f_cu_e2=29.0,
            f_cu_est=29.0,
            take="lower",
            passed=True,
        )


# ── ReboundTestArea + Result ─────────────────────────────────────
def test_rebound_test_area_basic() -> None:
    """每测区固定 16 个点。"""
    area = ReboundTestArea(
        raw_rebound_values=tuple(range(30, 46)),
        r_m=37.5,
        d_m=2.0,
        f_cu_i=28.6,
    )
    assert len(area.raw_rebound_values) == 16


def test_rebound_test_area_requires_16_values() -> None:
    with pytest.raises(ValueError, match="16"):
        ReboundTestArea(
            raw_rebound_values=tuple(range(15)),  # 15 个
            r_m=37.0,
            d_m=2.0,
            f_cu_i=28.0,
        )


def test_rebound_result_single_mode() -> None:
    """n<10：单个构件，取最小值；m_fcu/s_fcu 不参与判定。"""
    areas = (
        _mock_rebound_area(f_cu_i=28.0),
        _mock_rebound_area(f_cu_i=30.0),
        _mock_rebound_area(f_cu_i=29.0),
    )
    r = ReboundResult(
        test_areas=areas,
        n=3,
        mode="single",
        m_fcu=29.0,
        s_fcu=1.0,
        f_cu_e=28.0,
    )
    assert r.mode == "single"
    assert r.f_cu_e == 28.0  # min


def test_rebound_result_batch_mode() -> None:
    """n>=10：批量检测，f_cu_e = m_fcu - 1.645 * s_fcu。"""
    areas = tuple(_mock_rebound_area(f_cu_i=30.0) for _ in range(10))
    r = ReboundResult(
        test_areas=areas,
        n=10,
        mode="batch",
        m_fcu=30.0,
        s_fcu=2.0,
        f_cu_e=26.71,
    )
    assert r.mode == "batch"
    assert r.f_cu_e == pytest.approx(30.0 - 1.645 * 2.0, abs=0.01)


def test_rebound_mode_validates() -> None:
    with pytest.raises(ValueError, match="mode"):
        ReboundResult(
            test_areas=(_mock_rebound_area(),),
            n=1,
            mode="bogus",
            m_fcu=0.0,
            s_fcu=0.0,
            f_cu_e=0.0,
        )


# ── helpers ──────────────────────────────────────────────────────
def _mock_area(*, fb_min: float, fb_max: float) -> LeebHardnessTestArea:
    return LeebHardnessTestArea(
        raw_hl_values=tuple([400] * 9),
        hl_m=400,
        hl_t=0.0,
        hl_a=0.0,
        hl_corrected=400.0,
        fb_min=fb_min,
        fb_max=fb_max,
    )


def _mock_rebound_area(*, f_cu_i: float = 30.0) -> ReboundTestArea:
    return ReboundTestArea(
        raw_rebound_values=tuple(range(30, 46)),
        r_m=37.5,
        d_m=2.0,
        f_cu_i=f_cu_i,
    )
