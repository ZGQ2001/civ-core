// CoatingTemplateExpander 单测：类型预设 + 构件清单 → 测点数据网格的解析规则。

using System.IO;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingTemplateExpanderTests
{
    // 建一个含「类型预设」+「构件清单」的输入文件。memberRows: 每行 [批次,位置,类型,长度,截面数,设计厚度]（null=空）
    private static string MakeInput(params object?[][] memberRows)
    {
        string path = Path.Combine(Path.GetTempPath(), $"coating_exp_{Guid.NewGuid():N}.xlsx");
        using var wb = new XLWorkbook();

        var preset = wb.Worksheets.Add(CoatingColumns.TypePresetSheet);
        var ph = new[] { "构件类型", "测点位置", "默认设计厚度（mm）" };
        for (int c = 0; c < ph.Length; c++) preset.Cell(1, c + 1).Value = ph[c];
        preset.Cell(2, 1).Value = "梁"; preset.Cell(2, 2).Value = "梁侧面,梁侧面,梁底面"; preset.Cell(2, 3).Value = 3.3;
        preset.Cell(3, 1).Value = "柱"; preset.Cell(3, 2).Value = "东侧面,西侧面,南侧面,北侧面"; preset.Cell(3, 3).Value = 24;

        var list = wb.Worksheets.Add(CoatingColumns.MemberListSheet);
        var lh = new[] { "批次", "构件位置", "构件类型", "长度(m)", "截面数", "设计厚度（mm）" };
        for (int c = 0; c < lh.Length; c++) list.Cell(1, c + 1).Value = lh[c];
        int r = 2;
        foreach (var row in memberRows)
        {
            for (int c = 0; c < row.Length; c++)
                if (row[c] is not null) list.Cell(r, c + 1).Value = XLCellValue.FromObject(row[c]);
            r++;
        }
        wb.SaveAs(path);
        return path;
    }

    private static IXLWorksheet OpenSheet(string path, string name)
    {
        var wb = new XLWorkbook(path);
        return wb.Worksheet(name);
    }

    [Theory]
    [InlineData(8.1, CoatingStandards.GB_50205_2020, 3)] // ⌈8.1/3⌉=3
    [InlineData(6.0, CoatingStandards.GB_50205_2020, 2)] // ⌈6/3⌉=2
    [InlineData(12.05, CoatingStandards.GB_50205_2020, 5)] // ⌈12.05/3⌉=5
    [InlineData(8.0, CoatingStandards.BeijingLocal, 8)]  // ⌈8/1⌉=8
    public void Expand_长度按间距向上取整算截面数(double length, string standard, int expectedSections)
    {
        // 设计 24（厚型）→ 走截面×面布局，才有「⌈长度/间距⌉ 算截面数」逻辑（膨胀型固定 5 处）
        string path = MakeInput(new object?[] { "B1", "钢梁1", "梁", length, null, 24.0 });
        try
        {
            var r = CoatingTemplateExpander.Expand(path, path, standard);
            Assert.Equal(1, r.Members);
            Assert.Equal(expectedSections, r.TotalSections);
            var ws = OpenSheet(path, "测点数据-梁");
            Assert.Equal(expectedSections, (ws.LastRowUsed()!.RowNumber()) - 1); // 减表头
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_类型从构件位置名识别()
    {
        // 不填构件类型，名字含「梁」「柱」→ 自动识别 + 分到各自 sheet（厚型设计，走截面布局）
        string path = MakeInput(
            new object?[] { "B1", "地上一层钢梁A", null, 6.0, null, 20.0 },
            new object?[] { "B1", "地上一层钢柱B", null, null, 2, 24.0 });
        try
        {
            var r = CoatingTemplateExpander.Expand(path, path, CoatingStandards.GB_50205_2020);
            Assert.Contains("测点数据-梁", r.Sheets);
            Assert.Contains("测点数据-柱", r.Sheets);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_设计厚度_默认与覆盖()
    {
        // 梁1 不填设计 → 用类型默认 3.3（薄型）；梁2 填 8 覆盖（厚型）。
        // 用地标（不拆 5 处×3 点），薄/厚同走截面布局留在一张「测点数据-梁」便于验默认/覆盖。
        string path = MakeInput(
            new object?[] { "B1", "梁1", "梁", null, 2, null },
            new object?[] { "B1", "梁2", "梁", null, 2, 8.0 });
        try
        {
            CoatingTemplateExpander.Expand(path, path, CoatingStandards.BeijingLocal);
            var ws = OpenSheet(path, "测点数据-梁");
            // 设计厚度列=第5列；涂层类型列=第4列
            // 梁1（行2）
            Assert.Equal(3.3, ws.Cell(2, 5).GetDouble(), 3);
            Assert.Equal("薄型", ws.Cell(2, 4).GetString());
            // 梁2（行4，梁1 占行 2-3：每构件最少 2 截面）
            Assert.Equal(8.0, ws.Cell(4, 5).GetDouble(), 3);
            Assert.Equal("厚型", ws.Cell(4, 4).GetString());
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_国标膨胀型_出5处3点膨胀型表()
    {
        // 国标 + 超薄柱（设计2）→ 5 处×3 点，sheet 名「测点数据-柱-膨胀型」，
        // 索引列=处号、测点列=测点1/测点2/测点3
        string path = MakeInput(new object?[] { "B1", "钢柱1", "柱", null, null, 2.0 });
        try
        {
            var r = CoatingTemplateExpander.Expand(path, path, CoatingStandards.GB_50205_2020);
            Assert.Contains("测点数据-柱-膨胀型", r.Sheets);
            Assert.Equal(5, r.TotalSections); // 固定 5 处（忽略长度/截面数）

            var ws = OpenSheet(path, "测点数据-柱-膨胀型");
            Assert.Equal("处号", ws.Cell(1, 6).GetString());
            Assert.Equal("测点1", ws.Cell(1, 7).GetString());
            Assert.Equal("测点3", ws.Cell(1, 9).GetString());
            Assert.Equal("超薄型", ws.Cell(2, 4).GetString());
            Assert.Equal(5, ws.LastRowUsed()!.RowNumber() - 1); // 5 处行
            Assert.Equal(5, ws.Cell(6, 6).GetValue<int>());     // 末行处号=5
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_国标厚型与膨胀型混排_拆两张表()
    {
        // 同为「柱」：厚柱(24)走截面×面、超薄柱(2)走5处×3点 → 各自一张 sheet
        string path = MakeInput(
            new object?[] { "B1", "厚柱", "柱", null, 2, 24.0 },
            new object?[] { "B1", "超薄柱", "柱", null, null, 2.0 });
        try
        {
            var r = CoatingTemplateExpander.Expand(path, path, CoatingStandards.GB_50205_2020);
            Assert.Contains("测点数据-柱", r.Sheets);
            Assert.Contains("测点数据-柱-膨胀型", r.Sheets);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_地标膨胀型_仍走截面布局()
    {
        // 地标 + 薄梁（默认3.3）→ 不拆 5 处×3 点，仍出「测点数据-梁」（面名列）
        string path = MakeInput(new object?[] { "B1", "薄涂梁", "梁", null, 2, null });
        try
        {
            var r = CoatingTemplateExpander.Expand(path, path, CoatingStandards.BeijingLocal);
            Assert.Contains("测点数据-梁", r.Sheets);
            Assert.DoesNotContain("测点数据-梁-膨胀型", r.Sheets);
            var ws = OpenSheet(path, "测点数据-梁");
            Assert.Equal("梁侧面", ws.Cell(1, 7).GetString()); // 面名列，非点1
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_相邻构件分色不同_同构件多行同色()
    {
        // 地标，两梁各 2 截面同在「测点数据-梁」：梁1(行2-3) 一色、梁2(行4-5) 另一色，相邻构件可区分。
        string path = MakeInput(
            new object?[] { "B1", "梁1", "梁", null, 2, 20.0 },
            new object?[] { "B1", "梁2", "梁", null, 2, 20.0 });
        try
        {
            CoatingTemplateExpander.Expand(path, path, CoatingStandards.BeijingLocal);
            var ws = OpenSheet(path, "测点数据-梁");
            var m1Top = ws.Cell(2, 1).Style.Fill.BackgroundColor;
            var m1Bot = ws.Cell(3, 1).Style.Fill.BackgroundColor;
            var m2Top = ws.Cell(4, 1).Style.Fill.BackgroundColor;
            Assert.Equal(m1Top, m1Bot);        // 同构件多行同色
            Assert.NotEqual(m1Top, m2Top);     // 相邻构件不同色
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_缺长度且缺截面数_抛异常()
    {
        // 厚型（设计20）走截面×面，缺长度且缺截面数无法算截面数 → 报错（膨胀型固定 5 处不报）
        string path = MakeInput(new object?[] { "B1", "梁1", "梁", null, null, 20.0 });
        try
        {
            var ex = Assert.Throws<ArgumentException>(
                () => CoatingTemplateExpander.Expand(path, path, CoatingStandards.GB_50205_2020));
            Assert.Contains("长度", ex.Message);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_展开后测点格留空_可被Reader读回结构()
    {
        string path = MakeInput(new object?[] { "B1", "柱1", "柱", null, 2, null });
        try
        {
            CoatingTemplateExpander.Expand(path, path, CoatingStandards.GB_50205_2020);
            var ws = OpenSheet(path, "测点数据-柱");
            // 表头含 4 个面名
            Assert.Equal("东侧面", ws.Cell(1, 7).GetString());
            Assert.Equal("北侧面", ws.Cell(1, 10).GetString());
            // 2 截面行，测点格空
            Assert.Equal(2, ws.LastRowUsed()!.RowNumber() - 1);
            Assert.True(ws.Cell(2, 7).IsEmpty());
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_短构件长度不足2截面_兜底到规范最少2截面()
    {
        // 国标间距 3m，2m 梁 ⌈2/3⌉=1，但规范最少 2 截面 → 兜底为 2（厚型走截面×面）
        string path = MakeInput(new object?[] { "B1", "短梁", "梁", 2.0, null, 24.0 });
        try
        {
            var r = CoatingTemplateExpander.Expand(path, path, CoatingStandards.GB_50205_2020);
            Assert.Equal(2, r.TotalSections);
            var ws = OpenSheet(path, "测点数据-梁");
            Assert.Equal(2, ws.LastRowUsed()!.RowNumber() - 1);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_显式截面数小于2_抛异常()
    {
        // 厚型（设计 24）走截面×面，显式填截面数=1 < 规范最少 2 → 报错（去黑盒，不静默改）
        string path = MakeInput(new object?[] { "B1", "单截面梁", "梁", null, 1, 24.0 });
        try
        {
            var ex = Assert.Throws<ArgumentException>(
                () => CoatingTemplateExpander.Expand(path, path, CoatingStandards.GB_50205_2020));
            Assert.Contains("最少", ex.Message);
            Assert.Contains("截面", ex.Message);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_国标膨胀型_豁免最少2截面_仍5处()
    {
        // 国标超薄柱（设计 2）走 5 处×3 点，绕过截面数逻辑 → 截面数=1 也不报、固定 5 处（除五处3点的情况）
        string path = MakeInput(new object?[] { "B1", "超薄柱X", "柱", null, 1, 2.0 });
        try
        {
            var r = CoatingTemplateExpander.Expand(path, path, CoatingStandards.GB_50205_2020);
            Assert.Equal(5, r.TotalSections);
            Assert.Contains("测点数据-柱-膨胀型", r.Sheets);
        }
        finally { File.Delete(path); }
    }
}
