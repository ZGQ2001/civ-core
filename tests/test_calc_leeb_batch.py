"""INSP-001 批级计算测试。

验证 calc_leeb_hardness_batch 多构件聚合：
  - 输入顺序保持
  - 单构件 batch == 该构件的 comp_fb_min_avg
  - 多构件 batch_fb_char_avg = 各构件 comp_fb_min_avg 的算术平均
  - 空列表抛 InputError
"""

from __future__ import annotations

import sqlite3

import pytest

from civ_core.core.calc_functions import calc_leeb_hardness_batch
from civ_core.domain.calc_schema import LeebHardnessComponentInput
from civ_core.infra_io.standards_db import StandardsDB, seed_all_leeb_tables
from civ_core.utils.exceptions import InputError


@pytest.fixture
def db() -> StandardsDB:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    d = StandardsDB(conn)
    d.create_tables()
    seed_all_leeb_tables(d)
    return d


def _comp(seq: int, name: str, zones: list[tuple[int, ...]]) -> LeebHardnessComponentInput:
    return LeebHardnessComponentInput(
        seq=seq,
        name=name,
        thickness=12.0,
        angle_degrees=-90.0,  # 向上垂直，HL_a = 0（最简）
        test_areas_raw=tuple(zones),
    )


def test_batch_single_component(db: StandardsDB) -> None:
    """单构件 → batch_fb_char_avg == 该构件 comp_fb_min_avg。"""
    comp = _comp(1, "GKZ-1", [(400,) * 9, (400,) * 9, (400,) * 9])
    result = calc_leeb_hardness_batch([comp], db=db)
    assert result.n_components == 1
    assert result.batch_fb_char_avg == pytest.approx(
        result.components_with_results[0][1].comp_fb_min_avg, abs=0.001
    )


def test_batch_multiple_components(db: StandardsDB) -> None:
    """多构件 batch = 各 comp_fb_min_avg 的算术平均。"""
    components = [
        _comp(1, "GKZ-1", [(400,) * 9, (400,) * 9, (400,) * 9]),
        _comp(2, "GKZ-2", [(420,) * 9, (420,) * 9, (420,) * 9]),
        _comp(3, "GKZ-3", [(440,) * 9, (440,) * 9, (440,) * 9]),
    ]
    result = calc_leeb_hardness_batch(components, db=db)
    assert result.n_components == 3
    avgs = [r.comp_fb_min_avg for _, r in result.components_with_results]
    assert result.batch_fb_char_avg == pytest.approx(sum(avgs) / 3, abs=0.001)


def test_batch_preserves_input_order(db: StandardsDB) -> None:
    """输入顺序保持（按 seq 字段对应回去）。"""
    components = [
        _comp(10, "Z-10", [(400,) * 9]),
        _comp(2, "Z-2", [(400,) * 9]),
        _comp(5, "Z-5", [(400,) * 9]),
    ]
    result = calc_leeb_hardness_batch(components, db=db)
    seqs = [comp.seq for comp, _ in result.components_with_results]
    assert seqs == [10, 2, 5]


def test_batch_empty_raises(db: StandardsDB) -> None:
    with pytest.raises(InputError, match="构件"):
        calc_leeb_hardness_batch([], db=db)


def test_batch_component_validation_errors_bubble_up(db: StandardsDB) -> None:
    """单构件输入非法（非法角度）→ 整批级抛 InputError。"""
    comp = LeebHardnessComponentInput(
        seq=1,
        name="bad-angle",
        thickness=12.0,
        angle_degrees=30.0,  # 不在 5 档
        test_areas_raw=((400,) * 9,),
    )
    with pytest.raises(InputError, match="角度"):
        calc_leeb_hardness_batch([comp], db=db)
