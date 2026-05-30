// CoatingTemplateWriter 单测：模板结构（类型预设 + 构件清单）+ 可被 expander 展开。

using System.IO;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingTemplateWriterTests
{
    [Fact]
    public void Write_含类型预设梁柱_和构件清单()
    {
        string path = Path.Combine(Path.GetTempPath(), $"coating_tpl_{Guid.NewGuid():N}.xlsx");
        try
        {
            CoatingTemplateWriter.Write(path);
            using var wb = new XLWorkbook(path);

            Assert.True(wb.Worksheets.Contains(CoatingColumns.TypePresetSheet));
            Assert.True(wb.Worksheets.Contains(CoatingColumns.MemberListSheet));

            var preset = wb.Worksheet(CoatingColumns.TypePresetSheet);
            Assert.Equal("梁", preset.Cell(2, 1).GetString());
            Assert.Equal("柱", preset.Cell(3, 1).GetString());
            Assert.Contains("梁底面", preset.Cell(2, 2).GetString());
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Write_然后Expand_出梁柱测点数据网格()
    {
        string path = Path.Combine(Path.GetTempPath(), $"coating_tpl2_{Guid.NewGuid():N}.xlsx");
        try
        {
            CoatingTemplateWriter.Write(path);
            // 样例：梁 长度8（国标 ⌈8/3⌉=3 截面）、柱 截面数3
            var r = CoatingTemplateExpander.Expand(path, path, CoatingStandards.GB_50205_2020);
            Assert.Equal(2, r.Members);
            Assert.Contains("测点数据-梁", r.Sheets);
            Assert.Contains("测点数据-柱", r.Sheets);

            using var wb = new XLWorkbook(path);
            var beam = wb.Worksheet("测点数据-梁");
            Assert.Equal(3, beam.LastRowUsed()!.RowNumber() - 1); // 3 截面
        }
        finally { File.Delete(path); }
    }
}
