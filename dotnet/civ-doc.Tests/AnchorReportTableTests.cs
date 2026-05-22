// AnchorReportTable + AnchorAnalysisSheet 写入冒烟测试：
// 用计算结果跑写入流程，确认能生成合法 xlsx + 关键 cell 内容正确。

using System.IO;
using System.Linq;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.ReportTables;
using Xunit;

namespace CivCore.Doc.Tests;

public class AnchorReportTableTests
{
    private static AnchorBatchResult MakeBatch()
    {
        var p = AnchorParams.Create(180000, 500, 7500, 804.25, 200000);
        var d = new AnchorDisplacements(
            0, 0.56, 1.25, 1.96, 2.6, 2.61, 2.63, 2.35, 1.83, 1.21, 0.58);
        var input = AnchorRowInput.Create("1", d);
        var result = AnchorMath.ComputeRow(d, p);
        return new AnchorBatchResult("B1", p, new[] { (input, result) }, 1, 1);
    }

    [Fact]
    public void AnalysisSheet_写入_含弹性位移量_2_05_列()
    {
        string path = Path.Combine(Path.GetTempPath(), $"a_{Guid.NewGuid():N}.xlsx");
        try
        {
            using (var wb = new XLWorkbook())
            {
                var ws = wb.Worksheets.Add("数据分析");
                AnchorAnalysisSheet.Write(ws, MakeBatch());
                wb.SaveAs(path);
            }

            using var read = new XLWorkbook(path);
            var ws2 = read.Worksheets.First();
            Assert.Equal("锚杆编号", ws2.Cell(1, 1).GetString());
            Assert.Equal("1", ws2.Cell(2, 1).GetString());
            Assert.Equal(2.05, ws2.Cell(2, 13).GetDouble(), precision: 3);
            Assert.Equal("合格", ws2.Cell(2, 16).GetString());
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReportTable_写入_含标题_及弹性位移量单元格()
    {
        string path = Path.Combine(Path.GetTempPath(), $"r_{Guid.NewGuid():N}.xlsx");
        try
        {
            using (var wb = new XLWorkbook())
            {
                var ws = wb.Worksheets.Add("报告内插表");
                AnchorReportTable.Write(ws, MakeBatch());
                wb.SaveAs(path);
            }

            using var read = new XLWorkbook(path);
            var ws2 = read.Worksheets.First();
            // 第 1 行标题
            Assert.Contains("锚杆抗拔力试验结果表", ws2.Cell(1, 1).GetString());
            Assert.Contains("1", ws2.Cell(1, 1).GetString());
            // 第 13 行（试验结果及判定，第一根锚杆 base=1，所以 base+12=13）「实测值」单元格
            Assert.Equal("2.05", ws2.Cell(13, 7).GetString());
            // 判定单元格（行 13 列 16）
            Assert.Equal("合格", ws2.Cell(13, 16).GetString());
        }
        finally { File.Delete(path); }
    }
}
