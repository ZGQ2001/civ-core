"""检测计算函数集合（INSP-001/002/003）。

为什么单文件而不是按规范拆 3 个：
  - 3 个公式都是"统计 + 规范表查找"模式，共用 _trim_mean / _lookup_interp 等工具
  - 后续可能再加 INSP-004/005，到 ~10 个函数时再按域拆模块也来得及

设计要点：
  - 纯 Python（不引 numpy/scipy）：用 statistics + 手写线性插值
  - StandardsDB 由外部传入（沿用 project_db / chart_writer 等的模式）
  - 出参全部走 domain/calc_schema 的 frozen dataclass
  - 异常用 utils/exceptions 的 InputError（用户输入不合规）
  - 数据精度严格按公式文档要求做 round（避免下游再 round 一遍）

模块结构：
  ── 工具函数 ──
    _trim_mean / _round_half_up / _lookup_with_interp / _stdev_sample
  ── INSP-002 钻芯法 ──
    calc_core_drilling_concrete
  ── INSP-001 / INSP-003 骨架 ──（占位；查表数据待用户提供后实现）
"""

from __future__ import annotations

import statistics
from typing import Literal, Sequence

from civ_core.domain.calc_schema import (
    CoreDrillingResult,
    LeebHardnessResult,
    LeebHardnessTestArea,
)
from civ_core.infra_io.standards_db import (
    TABLE_CORE_DRILLING_K,
    TABLE_LEEB_ANGLE,
    TABLE_LEEB_STRENGTH,
    TABLE_LEEB_THICKNESS,
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


def _trim_mean_leeb(values: Sequence[int]) -> int:
    """INSP-001 §1.1 截尾平均：9 个里氏值剔除 2 高 2 低，对剩 5 个取均值并四舍五入取整。

    对应 Excel `ROUND(TRIMMEAN(..., 4/9), 0)`。
    """
    if len(values) != 9:
        raise InputError(
            cause=f"里氏硬度截尾平均需 9 个测点，得到 {len(values)}",
            location="_trim_mean_leeb",
            hint="GB/T 50344-2019 附录 N 规定每测区 9 测点",
        )
    sorted_vals = sorted(values)
    middle_five = sorted_vals[2:7]  # 剔除前 2 + 后 2，剩 5 个
    mean = sum(middle_five) / 5.0
    # Python round 半数向偶，与规范"四舍五入"不完全一致；用 +0.5 后向下取整确保 .5 向上
    return int(mean + 0.5) if mean >= 0 else -int(-mean + 0.5)


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
# INSP-001 钢材里氏硬度
# ════════════════════════════════════════════════════════════════
# INSP-001 §1.4：fb_max = fb_min + 150（GB/T 17394.4-2014）
_LEEB_FB_RANGE = 150.0


def calc_leeb_hardness_steel(
    *,
    test_areas_raw: Sequence[Sequence[int]],
    thickness: float,
    angle_category: int,
    db: StandardsDB,
    design_fb_min: float | None = None,
) -> LeebHardnessResult:
    """钢材里氏硬度推算抗拉强度（INSP-001 / GB/T 50344-2019 附录 N）。

    单构件（多测区）算一遍：每个测区独立做截尾平均 + 厚度/角度修正 + 强度查表，
    最后按 INSP-001 §2 聚合得构件下/上限与推定值。

    参数:
        test_areas_raw: 多测区原始 HL 列表，每测区固定 9 个 int 测点。
        thickness: 构件厚度（mm），用于查厚度修正表 leeb_thickness_correction。
        angle_category: 角度档（1=向上垂直 / 2=向上45° / 3=水平 / 4=向下45° / 5=向下垂直），
                        用于查角度修正表 leeb_angle_correction。
        db: 已 seed 过 leeb_thickness / leeb_angle / leeb_strength 三表的 StandardsDB。
        design_fb_min: 设计抗拉强度下限（MPa）。当前版本暂不写回 result（结果 dataclass
                       未带 passed 字段，由调用方拿 comp_fb_est 自行判定）。

    返回:
        LeebHardnessResult：含每测区详情 + 构件下/上限平均 + 推定值 + 批级特征值平均。

    异常:
        InputError —— 测区为空 / 角度档非法 / 厚度越表 / 强度查表越界。

    注意:
        本函数依赖 standards_db 中的 leeb_thickness_correction / leeb_angle_correction
        / leeb_strength_conversion 三表，目前需要由用户从 GB/T 17394.4-2014 与
        GB/T 50344-2019 附录 N 录入。骨架已就绪，加 seed_leeb_*_table 即可上线。
    """
    if not test_areas_raw:
        raise InputError(
            cause="至少需要 1 个测区",
            location="calc_leeb_hardness_steel",
            hint="GB/T 50344-2019 附录 N.2.2 要求每构件测区数量 >= 3",
        )

    areas: list[LeebHardnessTestArea] = []
    for raw in test_areas_raw:
        # 截尾平均
        hl_m = _trim_mean_leeb(raw)
        # 厚度修正（1D 查表 + 线性插值）
        hl_t = _lookup_with_interp(
            db, TABLE_LEEB_THICKNESS, thickness, value_idx="value1"
        )
        # 角度修正（2D 查表：角度档精确 + HL_m 插值）
        hl_a = _lookup_2d_fixed_key1_interp_key2(
            db,
            TABLE_LEEB_ANGLE,
            float(angle_category),
            float(hl_m),
            value_idx="value1",
            key1_label="角度档",
        )
        hl_corrected = float(hl_m) + hl_t + hl_a
        # 强度换算（1D 查表 HL_corr → fb_min）
        fb_min = _lookup_with_interp(
            db, TABLE_LEEB_STRENGTH, hl_corrected, value_idx="value1"
        )
        fb_max = fb_min + _LEEB_FB_RANGE

        areas.append(
            LeebHardnessTestArea(
                raw_hl_values=tuple(raw),
                hl_m=hl_m,
                hl_t=hl_t,
                hl_a=hl_a,
                hl_corrected=hl_corrected,
                fb_min=fb_min,
                fb_max=fb_max,
            )
        )

    # 构件级聚合（INSP-001 §2）
    fb_min_list = [a.fb_min for a in areas]
    fb_max_list = [a.fb_max for a in areas]
    comp_fb_min_avg = sum(fb_min_list) / len(fb_min_list)
    comp_fb_max_avg = sum(fb_max_list) / len(fb_max_list)
    # §2.2：推定值 = AVERAGE(下限集合 ∪ 上限集合) = (下限均值 + 上限均值) / 2
    comp_fb_est = (comp_fb_min_avg + comp_fb_max_avg) / 2.0
    # §3：批级特征值平均；单构件场景 = comp_fb_min_avg
    batch_fb_char_avg = comp_fb_min_avg

    # design_fb_min 当前版本暂存（结果 dataclass 无 passed 字段；由调用方判定）
    _ = design_fb_min

    return LeebHardnessResult(
        test_areas=tuple(areas),
        comp_fb_min_avg=comp_fb_min_avg,
        comp_fb_max_avg=comp_fb_max_avg,
        comp_fb_est=comp_fb_est,
        batch_fb_char_avg=batch_fb_char_avg,
    )


# ════════════════════════════════════════════════════════════════
# INSP-003 回弹法（骨架占位）
# 等用户提供 JGJ/T 23-2011 附录 A（测强曲线表）+ 附录 C（角度/表面修正）
# 数据后，按 _lookup_2d_fixed_key1_interp_key2 接口实现并加 seed_rebound_*_table。
# ════════════════════════════════════════════════════════════════
