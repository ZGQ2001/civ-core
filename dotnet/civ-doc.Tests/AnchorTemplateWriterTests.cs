// AnchorTemplateWriter 单测：生成模板 → reader 读回 → 期望首行样例数据完整。

using System.IO;
using CivCore.Doc.Calc.Anchor;
using Xunit;

namespace CivCore.Doc.Tests;

public class AnchorTemplateWriterTests
{
    [Fact]
    public void Write_生成模板_reader_可读回_样例首行()
    {
        string path = Path.Combine(Path.GetTempPath(),
            $"anchor_template_{Guid.NewGuid():N}.xlsx");
        try
        {
            AnchorTemplateWriter.Write(path);
            Assert.True(File.Exists(path));

            var batches = AnchorExcelReader.ReadRows(
                path, sheetName: AnchorTemplateWriter.TemplateSheetName);
            Assert.Single(batches);
            Assert.Equal("批次1", batches[0].BatchId);
            Assert.Equal(3, batches[0].Rows.Count);

            // 首行应是 xlsx 第 2 行的样例数据
            var d = batches[0].Rows[0].Displacements;
            Assert.Equal(0.56, d.D04Nt, precision: 6);
            Assert.Equal(2.63, d.D12Nt5Min, precision: 6);
            Assert.Equal(0.58, d.U01Nt, precision: 6);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Write_不支持的规范_抛异常()
    {
        string path = Path.Combine(Path.GetTempPath(), $"x_{Guid.NewGuid():N}.xlsx");
        Assert.Throws<ArgumentException>(() => AnchorTemplateWriter.Write(path, "ASTM-X"));
        Assert.False(File.Exists(path));
    }
}
