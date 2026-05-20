"""LeebHardnessView 工具页测试。

只验证关键路径：可构造 + 导入数据更新模型 + 计算填结果 + 清空。
不涉及对话框（QFileDialog / QInputDialog）的真实弹出 —— 直接调内部 setter
设状态，省得 mock 复杂。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.domain.calc_schema import LeebHardnessComponentInput  # noqa: E402
from civ_core.infra_io.standards_db import (  # noqa: E402
    StandardsDB,
    seed_all_leeb_tables,
)
from civ_core.ui.windows.leeb_hardness_view import LeebHardnessView  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    import sys

    inst = QApplication.instance() or QApplication(sys.argv)
    return inst  # type: ignore[return-value]


@pytest.fixture
def db() -> StandardsDB:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    d = StandardsDB(conn)
    d.create_tables()
    seed_all_leeb_tables(d)
    return d


def _mock_components() -> list[LeebHardnessComponentInput]:
    return [
        LeebHardnessComponentInput(
            seq=1,
            name="Z-1",
            thickness=12.0,
            angle_degrees=90.0,
            test_areas_raw=((400,) * 9, (410,) * 9, (405,) * 9),
            batch_name="批1",
        ),
        LeebHardnessComponentInput(
            seq=2,
            name="Z-2",
            thickness=12.0,
            angle_degrees=90.0,
            test_areas_raw=((420,) * 9, (415,) * 9, (425,) * 9),
            batch_name="批1",
        ),
    ]


# ── 构造 + 初始状态 ──────────────────────────────────────────────
def test_view_constructible(app: QApplication, db: StandardsDB) -> None:
    v = LeebHardnessView(db)
    assert v.objectName() == "leebHardnessPage"
    # 初始空状态：导出/计算按钮 disabled
    assert not v.btn_calc.isEnabled()
    assert not v.btn_export.isEnabled()
    v.deleteLater()


# ── 设构件 → 计算 → 结果模型更新 ────────────────────────────────
def test_calculate_populates_result(app: QApplication, db: StandardsDB) -> None:
    v = LeebHardnessView(db)
    v._components = _mock_components()
    v._comp_model.set_components(v._components)
    v._refresh_buttons()
    assert v.btn_calc.isEnabled()

    v._on_calculate()
    assert v._batch_result is not None
    assert v._batch_result.n_components == 2
    # 详细结果表格行数 = 总测区数 = 3 + 3 = 6
    assert v._res_model.rowCount() == 6
    # 批级摘要更新
    assert "批级抗拉强度" in v.lbl_batch_summary.text()
    assert "MPa" in v.lbl_batch_summary.text()
    # 导出按钮启用
    assert v.btn_export.isEnabled()
    v.deleteLater()


# ── 角度切换 → 结果作废 ──────────────────────────────────────────
def test_angle_change_invalidates_result(app: QApplication, db: StandardsDB) -> None:
    v = LeebHardnessView(db)
    v._components = _mock_components()
    v._comp_model.set_components(v._components)
    v._on_calculate()
    assert v._batch_result is not None

    # 切换到 -90°（默认 +90° 是 index 4）
    v.cmb_angle.setCurrentIndex(0)  # -90°
    # 触发 _on_angle_changed 后 batch_result 被作废
    assert v._batch_result is None
    assert not v.btn_export.isEnabled()
    # 但构件还在，且每个构件的 angle_degrees 已更新到 -90
    assert all(c.angle_degrees == -90.0 for c in v._components)
    v.deleteLater()


# ── 清空 ─────────────────────────────────────────────────────────
def test_clear_resets_all(app: QApplication, db: StandardsDB) -> None:
    v = LeebHardnessView(db)
    v._components = _mock_components()
    v._comp_model.set_components(v._components)
    v._on_calculate()
    v._on_clear()
    assert v._components == []
    assert v._batch_result is None
    assert v._comp_model.rowCount() == 0
    assert v._res_model.rowCount() == 0
    assert not v.btn_calc.isEnabled()
    v.deleteLater()


# ── 端到端：真实报检单 → 导出 ────────────────────────────────────
REAL_REPORT = Path("data/training_materials/防火厚度报检单(D号站房)新.xlsx")


@pytest.mark.skipif(not REAL_REPORT.exists(), reason="真实报检单未到位")
def test_full_workflow_with_real_data(
    app: QApplication, db: StandardsDB, tmp_path: Path
) -> None:
    """模拟用户：导入真实报检单 → 计算 → 导出 → 验证文件。"""
    from civ_core.infra_io.leeb_excel import read_leeb_components, write_leeb_results

    v = LeebHardnessView(db)
    # 模拟导入按钮的内部流程
    components = read_leeb_components(
        REAL_REPORT, "里氏硬度（钢柱）", default_angle_degrees=v._current_angle()
    )
    v._components = components
    v._comp_model.set_components(components)
    v._refresh_buttons()
    v._on_calculate()
    assert v._batch_result is not None
    assert v._batch_result.n_components > 10  # 报检单含 28 个钢柱左右

    # 模拟导出
    out = tmp_path / "leeb_real.xlsx"
    write_leeb_results(out, v._batch_result, angle_degrees=v._current_angle())
    assert out.exists()
    v.deleteLater()
