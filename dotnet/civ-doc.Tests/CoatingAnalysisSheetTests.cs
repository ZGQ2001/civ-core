// CoatingAnalysisSheet 单测：宽表结果写入 + 读回关键单元格。

using System.IO;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;
using CivCore.Doc.ReportTables;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingAnalysisSheetTests
{
    private static CoatingMemberInput Member(string loc, string type, double design,
        int sections, string[] faces, double[] thicknesses)
    {
        var pts = new List<CoatingPoint>();
        int k = 0;
        for (int s = 1; s <= sections; s++)
            foreach (var f in faces)
            {
                pts.Add(CoatingPoint.Create(s, f, thicknesses[k]));
                k++;
            }
        return CoatingMemberInput.Create(loc, type, design, pts.ToArray());
    }

    [Fact]
    public void Write_宽表_表头与判定正确()
    {
        // 钢梁 2 截面 × 3 面，design=24；一个合格一个不合格
        var beamFaces = new[] { "梁侧面", "梁侧面", "梁底面" };
        var workbook = new CoatingWorkbookInput(
            CoatingStandards.GB_50205_2020,
            new[]
            {
                new CoatingBatchInput("B1", new[]
                {
                    Member("梁1", "梁", 24, 2, beamFaces, new double[] { 25, 26, 27, 24, 25, 28 }), // 合格
                    Member("梁2", "梁", 24, 2, beamFaces, new double[] { 10, 10, 10, 25, 26, 28 }), // 不合格
                }),
            });
        var result = CoatingCalculator.Calc(workbook);

        string path = Path.Combine(Path.GetTempPath(), $"coating_sheet_{Guid.NewGuid():N}.xlsx");
        try
        {
            using (var wb = new XLWorkbook())
            {
                var ws = wb.Worksheets.Add("B1-数据分析");
                CoatingAnalysisSheet.Write(ws, result.BatchResults[0]);
                wb.SaveAs(path);
            }

            using var read = new XLWorkbook(path);
            var sheet = read.Worksheet("B1-数据分析");

            // 表头：测点位置一致 → 用面名
            Assert.Equal("序号", sheet.Cell(1, 1).GetString());
            Assert.Equal("构件位置", sheet.Cell(1, 2).GetString());
            Assert.Equal("梁侧面", sheet.Cell(1, 5).GetString());
            Assert.Equal("梁底面", sheet.Cell(1, 7).GetString());
            Assert.Equal("平均值", sheet.Cell(1, 8).GetString());
            Assert.Equal("判定", sheet.Cell(1, 12).GetString());

            // 第 1 构件（梁1，行 2 起，跨 2 截面）合格
            Assert.Equal("梁1", sheet.Cell(2, 2).GetString());
            Assert.Equal("合格", sheet.Cell(2, 12).GetString());

            // 第 2 构件（梁2，行 4 起）不合格 + 原因
            Assert.Equal("梁2", sheet.Cell(4, 2).GetString());
            Assert.Contains("不合格", sheet.Cell(4, 12).GetString());
        }
        finally { File.Delete(path); }
    }
}
