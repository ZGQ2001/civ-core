"""LeebHardnessView 工具页测试（2026-05-20 多批格式版）。

只验证关键路径：构造 + 多批导入 + 切批 + 计算 + 清空 + 端到端真实数据。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.domain.calc_schema import (  # noqa: E402
    LeebHardnessBatch,
    LeebHardnessComponentInput,
    LeebHardnessWorkbook,
)
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


def _mock_workbook() -> LeebHardnessWorkbook:
    """2 批，每批 2 构件。"""

    def _comp(seq: int, name: str, batch: str) -> LeebHardnessComponentInput:
        return LeebHardnessComponentInput(
            seq=seq,
            name=name,
            thickness=12.0,
            angle_degrees=0.0,
            test_areas_raw=((400,) * 9, (410,) * 9, (405,) * 9),
            batch_name=batch,
        )

    b1 = LeebHardnessBatch(
        batch_name="检测批1",
        components=(_comp(1, "钢柱-1", "检测批1"), _comp(2, "钢柱-2", "检测批1")),
    )
    b2 = LeebHardnessBatch(
        batch_name="检测批2",
        components=(_comp(1, "钢梁-1", "检测批2"),),
    )
    return LeebHardnessWorkbook(batches=(b1, b2), file_label="测试-D栋")


# ── 构造 + 初始状态 ──────────────────────────────────────────────
def test_view_constructible(app: QApplication, db: StandardsDB) -> None:
    v = LeebHardnessView(db)
    assert v.objectName() == "leebHardnessPage"
    assert not v.btn_calc.isEnabled()
    assert not v.btn_export.isEnabled()
    # 默认角度 0° (index 2)
    assert v._current_angle() == 0.0
    v.deleteLater()


# ── 多批导入 → 批选择器填充 ──────────────────────────────────────
def test_workbook_populates_batch_selector(app: QApplication, db: StandardsDB) -> None:
    v = LeebHardnessView(db)
    v._workbook = _mock_workbook()
    # 手动模拟 _on_import 的"填批选择器 + 默认 idx 0 + 刷新视图"
    v.cmb_batch.blockSignals(True)
    v.cmb_batch.clear()
    for b in v._workbook.batches:
        v.cmb_batch.addItem(f"{b.batch_name} ({len(b.components)} 构件)")
    v.cmb_batch.setCurrentIndex(0)
    v.cmb_batch.blockSignals(False)
    v._refresh_current_batch_views()
    v._refresh_buttons()

    assert v.cmb_batch.count() == 2
    assert v._current_batch_idx == 0
    # 当前批左栏构件数
    assert v._comp_model.rowCount() == 2
    assert v.btn_calc.isEnabled()
    v.deleteLater()


# ── 计算后所有批结果都缓存，切批不重算 ─────────────────────────
def test_calculate_then_switch_batches(app: QApplication, db: StandardsDB) -> None:
    v = LeebHardnessView(db)
    v._workbook = _mock_workbook()
    v.cmb_batch.blockSignals(True)
    for b in v._workbook.batches:
        v.cmb_batch.addItem(b.batch_name)
    v.cmb_batch.setCurrentIndex(0)
    v.cmb_batch.blockSignals(False)
    v._refresh_buttons()

    v._on_calculate()
    assert v._workbook_result is not None
    assert v._workbook_result.n_batches == 2
    assert v._workbook_result.n_components_total == 3

    # 当前批 1：左栏 2 构件，右栏 6 测区行
    assert v._res_model.rowCount() == 6
    assert "MPa" in v.lbl_batch_summary.text()
    assert "检测批1" in v.lbl_batch_summary.text()

    # 切到批 2
    v.cmb_batch.setCurrentIndex(1)
    assert v._current_batch_idx == 1
    assert v._comp_model.rowCount() == 1
    assert v._res_model.rowCount() == 3
    assert "检测批2" in v.lbl_batch_summary.text()
    v.deleteLater()


# ── 角度切换 → 作废结果但保留 workbook ─────────────────────────
def test_angle_change_invalidates_result(app: QApplication, db: StandardsDB) -> None:
    v = LeebHardnessView(db)
    v._workbook = _mock_workbook()
    v.cmb_batch.blockSignals(True)
    for b in v._workbook.batches:
        v.cmb_batch.addItem(b.batch_name)
    v.cmb_batch.setCurrentIndex(0)
    v.cmb_batch.blockSignals(False)
    v._on_calculate()
    assert v._workbook_result is not None

    v.cmb_angle.setCurrentIndex(0)  # -90°
    assert v._workbook_result is None
    assert not v.btn_export.isEnabled()
    assert v._workbook is not None  # 保留
    # 所有构件 angle_degrees 被更新
    for b in v._workbook.batches:
        for c in b.components:
            assert c.angle_degrees == -90.0
    v.deleteLater()


# ── 清空 ─────────────────────────────────────────────────────────
def test_clear_resets_all(app: QApplication, db: StandardsDB) -> None:
    v = LeebHardnessView(db)
    v._workbook = _mock_workbook()
    v.cmb_batch.blockSignals(True)
    for b in v._workbook.batches:
        v.cmb_batch.addItem(b.batch_name)
    v.cmb_batch.setCurrentIndex(0)
    v.cmb_batch.blockSignals(False)
    v._on_calculate()
    v._on_clear()
    assert v._workbook is None
    assert v._workbook_result is None
    assert v.cmb_batch.count() == 0
    assert v._comp_model.rowCount() == 0
    assert v._res_model.rowCount() == 0
    v.deleteLater()


# ── 端到端：新格式模板 → 导入 → 计算 → 导出 ───────────────────
TEMPLATE_PATH = Path("templates/leeb_hardness/原始数据模板.xlsx")


@pytest.mark.skipif(not TEMPLATE_PATH.exists(), reason="模板文件未到位")
def test_full_workflow_with_template(
    app: QApplication, db: StandardsDB, tmp_path: Path
) -> None:
    """直接读模板（含示例 2 构件）→ 计算 → 导出结果文件。"""
    from civ_core.core.calc_functions import calc_leeb_hardness_workbook
    from civ_core.infra_io.leeb_excel import (
        read_leeb_workbook,
        write_leeb_results_workbook,
    )

    v = LeebHardnessView(db)
    wb = read_leeb_workbook(TEMPLATE_PATH, default_angle_degrees=v._current_angle())
    v._workbook = wb
    v.cmb_batch.blockSignals(True)
    for b in wb.batches:
        v.cmb_batch.addItem(b.batch_name)
    v.cmb_batch.setCurrentIndex(0)
    v.cmb_batch.blockSignals(False)
    v._refresh_buttons()
    v._on_calculate()
    assert v._workbook_result is not None
    # 模板里只有 1 批有数据（检测批1 含 2 个示例构件）
    assert v._workbook_result.n_components_total >= 2

    out = tmp_path / "result.xlsx"
    write_leeb_results_workbook(out, v._workbook_result, angle_degrees=v._current_angle())
    assert out.exists()
    v.deleteLater()
    # 静态检查：calc_leeb_hardness_workbook 链路也能直接用
    _ = calc_leeb_hardness_workbook(wb, db=db)
