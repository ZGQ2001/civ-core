"""plot_curves 输出格式覆盖测试 —— _override_output_format()。

为什么单独测：用户从前端选 SVG/PNG/JPG 时不修改预设文件，只是临时覆盖
filename_template 的后缀。这条捷径与"用户编辑预设"是两条不同路径，需独立测试。
"""

from __future__ import annotations

import pytest

from civ_core.core.plot_curves import PlotCurvesError, _override_output_format


def test_svg后缀_被png覆盖():
    preset = {"filename_template": "{id}_曲线.svg", "other": "keep"}
    new_preset = _override_output_format(preset, "png")
    assert new_preset["filename_template"] == "{id}_曲线.png"
    # 其余字段不动
    assert new_preset["other"] == "keep"
    # 原 dict 不被修改（防止误污染共享 preset）
    assert preset["filename_template"] == "{id}_曲线.svg"


def test_无点的扩展名_被加上():
    new_preset = _override_output_format({"filename_template": "{id}.svg"}, "jpg")
    assert new_preset["filename_template"] == "{id}.jpg"


def test_带点前缀的格式参数_也接受():
    """允许 ".jpg" / "jpg" 两种写法（前端可能两种都传）。"""
    new_preset = _override_output_format({"filename_template": "{id}.png"}, ".jpeg")
    assert new_preset["filename_template"] == "{id}.jpeg"


def test_大小写不敏感():
    new_preset = _override_output_format({"filename_template": "{id}.svg"}, "PNG")
    assert new_preset["filename_template"] == "{id}.png"


def test_不支持的格式_抛PlotCurvesError带hint():
    with pytest.raises(PlotCurvesError) as ei:
        _override_output_format({"filename_template": "{id}.svg"}, "bmp")
    assert "bmp" in str(ei.value)
    assert "svg" in ei.value.hint  # 提示里列了支持的格式


def test_预设缺filename_template_用默认svg兜底():
    """预设字段不全时（极端情况）不应崩溃。"""
    new_preset = _override_output_format({}, "png")
    assert new_preset["filename_template"] == "{id}.png"
