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
        string path = MakeInput(new object?[] { "B1", "钢梁1", "梁", length, null, null });
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
        // 不填构件类型，名字含「梁」「柱」→ 自动识别 + 分到各自 sheet
        string path = MakeInput(
            new object?[] { "B1", "地上一层钢梁A", null, 6.0, null, null },
            new object?[] { "B1", "地上一层钢柱B", null, null, 2, null });
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
        // 梁1 不填设计 → 用类型默认 3.3（薄型）；梁2 填 8 覆盖（厚型）
        string path = MakeInput(
            new object?[] { "B1", "梁1", "梁", null, 1, null },
            new object?[] { "B1", "梁2", "梁", null, 1, 8.0 });
        try
        {
            CoatingTemplateExpander.Expand(path, path, CoatingStandards.GB_50205_2020);
            var ws = OpenSheet(path, "测点数据-梁");
            // 设计厚度列=第5列；涂层类型列=第4列
            // 梁1（行2）
            Assert.Equal(3.3, ws.Cell(2, 5).GetDouble(), 3);
            Assert.Equal("薄型", ws.Cell(2, 4).GetString());
            // 梁2（行3）
            Assert.Equal(8.0, ws.Cell(3, 5).GetDouble(), 3);
            Assert.Equal("厚型", ws.Cell(3, 4).GetString());
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Expand_缺长度且缺截面数_抛异常()
    {
        string path = MakeInput(new object?[] { "B1", "梁1", "梁", null, null, null });
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
}
