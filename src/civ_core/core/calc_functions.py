"""检测计算函数集合（Python 端：INSP-002 钻芯法 + INSP-003 回弹法）。

INSP-001 钢材里氏硬度已迁 C# sidecar (civ-doc)；本模块只剩 Python 端继续承担的：
  - INSP-002 钻芯法 calc_core_drilling_concrete
  - INSP-003 回弹法 calc_rebound_concrete
共享 _stdev_sample / _lookup_with_interp / _lookup_2d_fixed_key1_interp_key2 等工具。

设计要点：
  - 纯 Python（不引 numpy/scipy）：用 statistics + 手写线性插值
  - StandardsDB 由外部传入（沿用 chart_writer 等的模式）
  - 出参全部走 domain/calc_schema 的 frozen dataclass
  - 异常用 utils/exceptions 的 InputError（用户输入不合规）
"""

from __future__ import annotations

import statistics
from typing import Literal, Sequence

from civ_core.domain.calc_schema import (
    CoreDrillingResult,
    ReboundResult,
    ReboundTestArea,
)
from civ_core.infra_io.standards_db import (
    TABLE_CORE_DRILLING_K,
    TABLE_REBOUND_STRENGTH,
    StandardsDB,
)
from civ_core.utils.exceptions import InputError


# ════════════════════════════════════════════════════════════════
# 通用工具
# ════════════════════════════════════════════════════════════════
def _stdev_sample(values: Sequence[float]) -> float:
    """样本标准差（n-1 自由度）；n<2 返回 0。"""
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def _lookup_with_interp(
    db: StandardsDB,
    table_name: str,
    key: float,
    *,
    value_idx: Literal["value1", "value2", "value3"],
) -> float:
    """在 standards_tables 的某逻辑表上按 key1 查找 value，超出/未命中点用线性插值。

    要求：表内所有行 key2 IS NULL（1D 表）；key 必须落在 [min(key1), max(key1)] 内。
    超出范围抛 InputError（不外推，更安全）。
    """
    rows = db.list_rows(table_name)
    if not rows:
        raise InputError(
            cause=f"规范查表 {table_name!r} 为空",
            location=f"_lookup_with_interp({table_name})",
            hint="请先用 seed_*_table 函数初始化该规范表的数据",
        )

    # rows 已按 key1 升序；先做精确命中
    for row in rows:
        if row.key1 == key:
            v = getattr(row, value_idx)
            if v is None:
                raise InputError(
                    cause=f"规范表 {table_name!r} 的 key={key} 行 {value_idx} 为空",
                    location=f"_lookup_with_interp({table_name})",
                )
            return float(v)

    # 越界检查
    if key < rows[0].key1 or key > rows[-1].key1:
        raise InputError(
            cause=f"查表 key={key} 超出规范表 {table_name!r} 范围 [{rows[0].key1}, {rows[-1].key1}]",
            location=f"_lookup_with_interp({table_name})",
            hint="请检查输入是否在规范允许范围内",
        )

    # 线性插值：找前后两点
    for i in range(len(rows) - 1):
        lo, hi = rows[i], rows[i + 1]
        if lo.key1 < key < hi.key1:
            v_lo = getattr(lo, value_idx)
            v_hi = getattr(hi, value_idx)
            if v_lo is None or v_hi is None:
                raise InputError(
                    cause=f"规范表 {table_name!r} 插值区间内 {value_idx} 缺值",
                    location=f"_lookup_with_interp({table_name})",
                )
            t = (key - lo.key1) / (hi.key1 - lo.key1)
            return float(v_lo) + t * (float(v_hi) - float(v_lo))

    # 理论上走不到这里（精确命中或区间内插值已覆盖）；兜底抛 InputError
    raise InputError(
        cause=f"查表 key={key} 在 {table_name!r} 内未找到匹配行",
        location=f"_lookup_with_interp({table_name})",
    )


def _lookup_2d_fixed_key1_interp_key2(
    db: StandardsDB,
    table_name: str,
    key1: float,
    key2: float,
    *,
    value_idx: Literal["value1", "value2", "value3"] = "value1",
    key1_label: str = "key1",
) -> float:
    """2D 查表：固定 key1 精确匹配，再在该 key1 的所有行中按 key2 线性插值 value。

    用于 INSP-001 角度修正表（角度档精确匹配 + HL_m 插值）和 INSP-003 测强曲线表
    （碳化深度档精确匹配 + R_m 插值）这类"分类 + 数值插值"场景。

    key1 找不到 → InputError 用 key1_label 描述（如"角度档"/"碳化深度档"），
    便于上层把规范术语带进错误信息。
    """
    rows = [r for r in db.list_rows(table_name) if r.key1 == key1]
    if not rows:
        raise InputError(
            cause=f"{key1_label} {key1} 在规范表 {table_name!r} 中不存在",
            location=f"_lookup_2d({table_name})",
            hint=f"请确认 {key1_label} 取值是否在规范允许范围内",
        )
    # rows 已按 key2 升序（list_rows 用 ORDER BY key1, key2）
    rows.sort(key=lambda r: r.key2 if r.key2 is not None else 0.0)

    # 精确命中
    for row in rows:
        if row.key2 == key2:
            v = getattr(row, value_idx)
            if v is None:
                raise InputError(
                    cause=f"规范表 {table_name!r} ({key1_label}={key1}, key2={key2}) 行 {value_idx} 为空",
                    location=f"_lookup_2d({table_name})",
                )
            return float(v)

    # 单行场景：无法插值，但若用户传 key2 落在该单行附近也无法外推 → 直接返回该值
    # （只 1 个分档时，常规做法是把 value 视作常量；规范表里这种情况就是常数项）
    if len(rows) == 1:
        v = getattr(rows[0], value_idx)
        return float(v) if v is not None else 0.0

    # 越界检查
    key2_min = rows[0].key2 or 0.0
    key2_max = rows[-1].key2 or 0.0
    if key2 < key2_min or key2 > key2_max:
        raise InputError(
            cause=f"查表 key2={key2} 超出 ({key1_label}={key1}) 区间 [{key2_min}, {key2_max}]",
            location=f"_lookup_2d({table_name})",
        )

    # 线性插值
    for i in range(len(rows) - 1):
        lo, hi = rows[i], rows[i + 1]
        k2_lo = lo.key2 or 0.0
        k2_hi = hi.key2 or 0.0
        if k2_lo < key2 < k2_hi:
            v_lo = getattr(lo, value_idx)
            v_hi = getattr(hi, value_idx)
            if v_lo is None or v_hi is None:
                raise InputError(
                    cause=f"规范表 {table_name!r} 插值区间 {value_idx} 缺值",
                    location=f"_lookup_2d({table_name})",
                )
            t = (key2 - k2_lo) / (k2_hi - k2_lo)
            return float(v_lo) + t * (float(v_hi) - float(v_lo))

    raise InputError(
        cause=f"查表 ({key1_label}={key1}, key2={key2}) 在 {table_name!r} 内未匹配",
        location=f"_lookup_2d({table_name})",
    )


# ════════════════════════════════════════════════════════════════
# INSP-002 钻芯法
# ════════════════════════════════════════════════════════════════
_CORE_DRILLING_N_MIN = 10
_CORE_DRILLING_N_MAX = 500
_CORE_DRILLING_TAKES = ("upper", "lower")


def calc_core_drilling_concrete(
    values: Sequence[float],
    *,
    db: StandardsDB,
    take: Literal["upper", "lower"] = "lower",
    small_diameter: bool = False,
    design_fcu: float | None = None,
) -> CoreDrillingResult:
    """钻芯法混凝土抗压强度推定（INSP-002 / JGJ/T 384-2016 §6.3.2 + 附录 A）。

    参数:
        values: 单个芯样试件抗压强度 f_cu,cor,i 列表（MPa）。
                数量 n 必须 ∈ [10, 500]（JGJ/T 384-2016 表 A.0.2 适用范围）。
        db: 已 seed 过 core_drilling_k 表的 StandardsDB 实例。
        take: 推定值取上限还是下限；批量验收常用 "lower"（保守），上限多用于争议复检。
        small_diameter: True → 小直径芯样，k2 用漏判概率 0.10 列；
                        False → 常规芯样，k2 用漏判概率 0.05 列。
        design_fcu: 设计强度等级（MPa）。提供则自动判定 passed = (f_cu_est >= design_fcu)。

    返回:
        CoreDrillingResult，含统计量 + 推定上下限 + 推定值 + passed。

    异常:
        InputError —— n 越界 / take 非法 / 查表失败时抛出（带规范定位）。
    """
    n = len(values)

    # ── 输入校验 ──────────────────────────────────────────────
    if n < _CORE_DRILLING_N_MIN:
        raise InputError(
            cause=f"芯样数量 n={n} 小于规范最低 {_CORE_DRILLING_N_MIN}",
            location="calc_core_drilling_concrete",
            hint=f"JGJ/T 384-2016 表 A.0.2 起始 n={_CORE_DRILLING_N_MIN}；请补足芯样或改用单值判定",
        )
    if n > _CORE_DRILLING_N_MAX:
        raise InputError(
            cause=f"芯样数量 n={n} 超过规范上限 {_CORE_DRILLING_N_MAX}",
            location="calc_core_drilling_concrete",
            hint=f"JGJ/T 384-2016 表 A.0.2 仅给到 n={_CORE_DRILLING_N_MAX}；请按多批分别评定",
        )
    if take not in _CORE_DRILLING_TAKES:
        raise InputError(
            cause=f"take={take!r} 不在 {_CORE_DRILLING_TAKES}",
            location="calc_core_drilling_concrete",
            hint="批量验收 take='lower'（推定下限），争议复检常用 take='upper'（推定上限）",
        )

    # ── 统计量（按规范精度 round）──────────────────────────────
    f_cu_cor_m = round(statistics.mean(values), 1)
    s_cu = round(_stdev_sample(values), 2)

    # ── 查 k1 / k2（小直径用 k2_010 = value3，常规用 k2_005 = value2）──
    k1 = _lookup_with_interp(db, TABLE_CORE_DRILLING_K, float(n), value_idx="value1")
    k2_col: Literal["value2", "value3"] = "value3" if small_diameter else "value2"
    k2 = _lookup_with_interp(db, TABLE_CORE_DRILLING_K, float(n), value_idx=k2_col)

    # ── 推定区间（INSP-002 §3）─────────────────────────────────
    f_cu_e1 = round(f_cu_cor_m - k1 * s_cu, 1)
    f_cu_e2 = round(f_cu_cor_m - k2 * s_cu, 1)
    f_cu_est = f_cu_e1 if take == "upper" else f_cu_e2

    # ── 合规判定 ──────────────────────────────────────────────
    passed = True if design_fcu is None else (f_cu_est >= design_fcu)

    return CoreDrillingResult(
        f_cu_cor_values=tuple(values),
        n=n,
        f_cu_cor_m=f_cu_cor_m,
        s_cu=s_cu,
        k1=k1,
        k2=k2,
        f_cu_e1=f_cu_e1,
        f_cu_e2=f_cu_e2,
        f_cu_est=f_cu_est,
        take=take,
        passed=passed,
    )


# ════════════════════════════════════════════════════════════════
# INSP-003 回弹法
# ════════════════════════════════════════════════════════════════
_REBOUND_BATCH_THRESHOLD = 10
# JGJ/T 23-2011 §7.3.5：批量推定区间上限的标准正态分位数（95% 单侧）
_REBOUND_K_QUANTILE = 1.645
# §3：碳化深度归一化阈值
_CARB_MIN = 0.5
_CARB_MAX = 6.0


def _trim_mean_rebound(values: Sequence[int]) -> float:
    """INSP-003 §1.1 截尾平均：16 个回弹值剔 3 高 3 低取 10 个均值，精确至 0.1。"""
    if len(values) != 16:
        raise InputError(
            cause=f"回弹法截尾平均需 16 个测点，得到 {len(values)}",
            location="_trim_mean_rebound",
            hint="JGJ/T 23-2011 §4.2.1 规定每测区 16 测点",
        )
    sorted_vals = sorted(values)
    middle = sorted_vals[3:13]  # 剔 3 高 3 低，剩 10
    return round(sum(middle) / 10.0, 1)


def _normalize_carbonation_depth(d: float) -> float:
    """INSP-003 §2：碳化深度归一化（< 0.5 → 0；≥ 6 → 6；其余原样）。"""
    if d < 0:
        raise InputError(
            cause=f"碳化深度不能为负数，得到 {d}",
            location="_normalize_carbonation_depth",
        )
    if d < _CARB_MIN:
        return 0.0
    if d >= _CARB_MAX:
        return _CARB_MAX
    return d


def calc_rebound_concrete(
    test_areas_raw: Sequence[Sequence[int]],
    *,
    carbonation_depth: float,
    db: StandardsDB,
    angle_correction: float = 0.0,
    surface_correction: float = 0.0,
) -> ReboundResult:
    """回弹法混凝土抗压强度推定（INSP-003 / JGJ/T 23-2011 §7）。

    参数:
        test_areas_raw: 多测区原始回弹值列表，每测区固定 16 个 int 测点。
        carbonation_depth: 碳化深度 d_m（mm），函数内部按 §2 归一化（< 0.5→0; ≥6→6）。
        db: 已 seed 过 rebound_strength_curve 表的 StandardsDB 实例。
        angle_correction: 角度修正量 ΔR_α（mm），用户传入；不传则视为水平方向（=0）。
                          后续如启用 rebound_angle_correction 查表，可在外层包装计算。
        surface_correction: 表面修正量 ΔR_s（mm），同上。

    返回:
        ReboundResult：n<10 → mode=single, f_cu_e=min(f_cu_i)；
                       n>=10 → mode=batch, f_cu_e = m_fcu - 1.645·s_fcu。

    异常:
        InputError —— 测区为空 / R_m 超出测强曲线表范围 / 碳化深度负数。

    注意:
        JGJ/T 23-2011 附录 A 测强曲线（R_m × d_m 二维表）目前需要由用户录入；
        附录 C 角度/表面修正表暂用用户直接传值替代。骨架已就绪，加 seed 即上线。
    """
    if not test_areas_raw:
        raise InputError(
            cause="至少需要 1 个测区",
            location="calc_rebound_concrete",
            hint="JGJ/T 23-2011 §4.1.3 要求批量检测测区数 >= 10 且 >= 30% 总数",
        )

    d_m = _normalize_carbonation_depth(carbonation_depth)

    areas: list[ReboundTestArea] = []
    for raw in test_areas_raw:
        r_m_raw = _trim_mean_rebound(raw)
        # 应用用户提供的角度 + 表面修正（INSP-003 §1.2、§1.3）
        r_m = round(r_m_raw + angle_correction + surface_correction, 1)
        # 测强曲线查表：d_m 分档精确匹配 + R_m 插值
        f_cu_i = round(
            _lookup_2d_fixed_key1_interp_key2(
                db,
                TABLE_REBOUND_STRENGTH,
                key1=d_m,
                key2=r_m,
                value_idx="value1",
                key1_label="碳化深度档",
            ),
            1,
        )
        areas.append(
            ReboundTestArea(
                raw_rebound_values=tuple(raw),
                r_m=r_m,
                d_m=d_m,
                f_cu_i=f_cu_i,
            )
        )

    fcus = [a.f_cu_i for a in areas]
    n = len(areas)
    m_fcu = round(statistics.mean(fcus), 1)
    s_fcu = round(_stdev_sample(fcus), 2)

    if n < _REBOUND_BATCH_THRESHOLD:
        mode = "single"
        f_cu_e = round(min(fcus), 1)
    else:
        mode = "batch"
        f_cu_e = round(m_fcu - _REBOUND_K_QUANTILE * s_fcu, 1)

    return ReboundResult(
        test_areas=tuple(areas),
        n=n,
        mode=mode,
        m_fcu=m_fcu,
        s_fcu=s_fcu,
        f_cu_e=f_cu_e,
    )
