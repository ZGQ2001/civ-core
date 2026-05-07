"""PlotCurvesView._validate_preset_form 的单元测试。

这是一个 staticmethod，纯静态校验逻辑，无需 QApplication。直接喂测试数据
断言返回的问题列表。
"""

from __future__ import annotations

from typing import Any

from civil_auto.ui.windows.plot_curves_view import PlotCurvesView


def _good_data() -> dict[str, Any]:
    """所有字段都填好的合法预设 data（不含 name）。"""
    return {
        "id_column": "锚杆编号",
        "filename_template": "锚杆{id}.png",
        "title_template": "锚杆{id}：曲线",
        "x_axis": {"label": "位移", "range": None},
        "y_axis": {"label": "荷载", "range": [0.0, 200.0, 20.0]},
        "curves": [{"name": "加载", "color": "#1F4FE0"}],
    }


def _validate(name: str, data: dict, curves_text: str = "") -> list[str]:
    return PlotCurvesView._validate_preset_form(name, data, curves_text)


class TestValidName:
    def test_valid_passes(self) -> None:
        assert _validate("我的锚杆", _good_data()) == []

    def test_empty_name_rejected(self) -> None:
        issues = _validate("", _good_data())
        assert any("预设名称不能为空" in i for i in issues)

    def test_underscore_name_rejected(self) -> None:
        issues = _validate("_私有", _good_data())
        assert any("不能以下划线开头" in i for i in issues)


class TestStringFields:
    def test_empty_id_column(self) -> None:
        d = _good_data()
        d["id_column"] = "  "  # 全空白
        issues = _validate("X", d)
        assert any("标识列不能为空" in i for i in issues)

    def test_filename_template_missing_id_placeholder(self) -> None:
        d = _good_data()
        d["filename_template"] = "曲线.png"  # 缺 {id}
        issues = _validate("X", d)
        assert any("{id}" in i for i in issues)

    def test_empty_filename_template(self) -> None:
        d = _good_data()
        d["filename_template"] = ""
        issues = _validate("X", d)
        assert any("文件名模板" in i for i in issues)

    def test_empty_title_template(self) -> None:
        d = _good_data()
        d["title_template"] = ""
        issues = _validate("X", d)
        assert any("图标题" in i for i in issues)

    def test_empty_axis_label(self) -> None:
        d = _good_data()
        d["x_axis"]["label"] = ""
        issues = _validate("X", d)
        assert any("X 轴标签" in i for i in issues)


class TestRangeValidation:
    def test_min_greater_than_max(self) -> None:
        d = _good_data()
        d["y_axis"]["range"] = [200.0, 100.0, 10.0]
        issues = _validate("X", d)
        assert any("min" in i and "max" in i for i in issues)

    def test_min_equal_to_max(self) -> None:
        d = _good_data()
        d["y_axis"]["range"] = [50.0, 50.0, 10.0]
        issues = _validate("X", d)
        assert any("必须小于" in i for i in issues)

    def test_zero_step(self) -> None:
        d = _good_data()
        d["y_axis"]["range"] = [0.0, 100.0, 0.0]
        issues = _validate("X", d)
        assert any("step" in i and "> 0" in i for i in issues)

    def test_negative_step(self) -> None:
        d = _good_data()
        d["y_axis"]["range"] = [0.0, 100.0, -10.0]
        issues = _validate("X", d)
        assert any("step" in i for i in issues)

    def test_null_range_passes(self) -> None:
        """range=None（轴自动）是合法的，不应报错。"""
        d = _good_data()
        d["x_axis"]["range"] = None
        d["y_axis"]["range"] = None
        assert _validate("X", d) == []


class TestCurvesValidation:
    def test_curves_must_be_list(self) -> None:
        d = _good_data()
        d["curves"] = "not a list"  # type: ignore
        issues = _validate("X", d)
        assert any("列表" in i for i in issues)

    def test_curves_with_parse_error_marker(self) -> None:
        d = _good_data()
        d["curves"] = [{"_parse_error": "Expecting value", "_raw": "..."}]
        issues = _validate("X", d, curves_text="bad json")
        assert any("曲线 JSON 解析失败" in i for i in issues)

    def test_curve_missing_name(self) -> None:
        d = _good_data()
        d["curves"] = [{"color": "#fff"}]  # 没 name
        issues = _validate("X", d)
        assert any("第 1 条曲线缺少 name" in i for i in issues)

    def test_curve_not_dict(self) -> None:
        d = _good_data()
        d["curves"] = ["not a dict"]
        issues = _validate("X", d)
        assert any("第 1 条曲线必须是 JSON 对象" in i for i in issues)

    def test_empty_curves_list_allowed(self) -> None:
        """允许 curves 为空列表（用户可能正在新建，先不配曲线）。"""
        d = _good_data()
        d["curves"] = []
        assert _validate("X", d) == []


class TestIssuesCollectAll:
    def test_multiple_issues_returned(self) -> None:
        """多个问题同时存在 → 应该一次返回全部，让用户改一遍而不是反复试。"""
        d = _good_data()
        d["id_column"] = ""
        d["filename_template"] = ""
        d["x_axis"]["label"] = ""
        issues = _validate("", d)
        # 至少 4 项问题（name + id_column + filename + x label）
        assert len(issues) >= 4
