"""plot_curves filename_prefix 测试 —— build_jobs 的多批次防撞名前缀。

多批次（多 sheet）出图时各批相同标识列值（如锚杆编号 1/2/3）会撞文件名；
调用方传 filename_prefix='<批次>_' 给每批的图加前缀。前缀是字面字符串，
不参与 {id} 替换，且不影响标题。
"""

from __future__ import annotations

from civ_core.core.plot_curves import build_jobs


def _minimal_preset() -> dict:
    return {
        "id_column": "编号",
        "filename_template": "{id}.png",
        "title_template": "图{id}",
        "x_axis": {"label": "X", "range": None},
        "y_axis": {"label": "Y", "range": None},
        "curves": [
            {
                "name": "c",
                "points": [{"var_column": "x", "fixed_axis": "y", "fixed_value": 1.0}],
            }
        ],
    }


def test_filename_prefix_拼在文件名最前():
    rows = [{"编号": "1", "x": 0.5}, {"编号": "2", "x": 0.6}]
    jobs, _ = build_jobs(_minimal_preset(), rows, "/out", filename_prefix="批次A_")
    assert [j.output_path.name for j in jobs] == ["批次A_1.png", "批次A_2.png"]
    # 前缀不影响标题（标题只用 {id}）
    assert jobs[0].title == "图1"


def test_无prefix_默认行为不变():
    rows = [{"编号": "1", "x": 0.5}]
    jobs, _ = build_jobs(_minimal_preset(), rows, "/out")
    assert jobs[0].output_path.name == "1.png"
