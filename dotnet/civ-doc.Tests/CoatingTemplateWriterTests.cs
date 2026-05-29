// CoatingTemplateWriter 单测：生成的空白模板能被 CoatingExcelReader 读回。

using System.IO;
using CivCore.Doc.Calc.Coating;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingTemplateWriterTests
{
    [Fact]
    public void Write_生成模板_可被Reader读回_含梁柱两构件()
    {
        string path = Path.Combine(Path.GetTempPath(), $"coating_tpl_{Guid.NewGuid():N}.xlsx");
        try
        {
            CoatingTemplateWriter.Write(path);

            var batches = CoatingExcelReader.ReadRows(path);
            Assert.Single(batches);
            var members = batches[0].Members;
            Assert.Equal(2, members.Count); // 1 梁 + 1 柱

            var beam = members.First(m => m.MemberType == "梁");
            var column = members.First(m => m.MemberType == "柱");
            Assert.Equal(6, beam.Points.Length);   // 2 截面 × 3 面
            Assert.Equal(8, column.Points.Length);  // 2 截面 × 4 面
            Assert.True(beam.DesignThickness > 0);
        }
        finally { File.Delete(path); }
    }
}
