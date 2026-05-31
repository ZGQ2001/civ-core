// CoatingAnalysisSheet 单测：宽表结果写入（涂层类型列 + 精度 + 厚型/膨胀型判定）。

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
    public void Write_宽表_含涂层类型列_厚型与膨胀型判定()
    {
        var beamFaces = new[] { "梁侧面", "梁侧面", "梁底面" };
        var workbook = new CoatingWorkbookInput(
            CoatingStandards.GB_50205_2020,
            new[]
            {
                new CoatingBatchInput("B1", new[]
                {
                    Member("梁1", "梁", 20, 2, beamFaces, new double[] { 25, 26, 27, 24, 25, 28 }), // 厚型 合格
                    Member("梁2", "梁", 20, 2, beamFaces, new double[] { 10, 10, 10, 25, 26, 28 }), // 厚型 不合格
                    Member("梁3", "梁", 5, 1, beamFaces, new double[] { 4.8, 5.1, 4.9 }),            // 薄型 合格（均值4.933 ≥ 下限4.8）
                }),
            });
        var result = CoatingCalculator.Calc(workbook);

        string path = Path.Combine(Path.GetTempPath(), $"coating_sheet_{Guid.NewGuid():N}.xlsx");
        try
        {
            using (var wb = new XLWorkbook())
            {
                var ws = wb.Worksheets.Add("B1-数据分析");
                CoatingAnalysisSheet.Write(ws, result.BatchResults[0], CoatingStandards.GB_50205_2020);
                wb.SaveAs(path);
            }

            using var read = new XLWorkbook(path);
            var sheet = read.Worksheet("B1-数据分析");

            // 列(K=3)：序号|位置|类型|涂层类型|截面号|梁侧面|梁侧面|梁底面|本段均值|构件均值|设计厚度|判定下限|合格率|最薄处|判定
            Assert.Equal("涂层类型", sheet.Cell(1, 4).GetString());
            Assert.Equal("截面号", sheet.Cell(1, 5).GetString());
            Assert.Equal("梁底面", sheet.Cell(1, 8).GetString());
            Assert.Equal("本段均值", sheet.Cell(1, 9).GetString());
            Assert.Equal("构件均值", sheet.Cell(1, 10).GetString());
            Assert.Equal("判定下限", sheet.Cell(1, 12).GetString());
            Assert.Equal("判定", sheet.Cell(1, 15).GetString());

            // 梁1（行2 起，跨 2 截面）厚型 合格；判定下限=设计×0.85=17
            Assert.Equal("梁1", sheet.Cell(2, 2).GetString());
            Assert.Equal("厚型", sheet.Cell(2, 4).GetString());
            Assert.Equal(17.0, sheet.Cell(2, 12).GetDouble(), precision: 9);
            Assert.Equal("合格", sheet.Cell(2, 15).GetString());

            // 梁2（行4 起）不合格
            Assert.Equal("梁2", sheet.Cell(4, 2).GetString());
            Assert.Contains("不合格", sheet.Cell(4, 15).GetString());

            // 梁3（行6）薄型 合格（均值4.933≥下限4.8）；合格率列「—」；
            // 判定下限=max(5×0.95=4.75, 5−0.2=4.8)=4.8（设计>4mm，−200µm 兜底更严）
            Assert.Equal("梁3", sheet.Cell(6, 2).GetString());
            Assert.Equal("薄型", sheet.Cell(6, 4).GetString());
            Assert.Equal("—", sheet.Cell(6, 13).GetString());
            Assert.Equal(4.8, sheet.Cell(6, 12).GetDouble(), precision: 9);
            Assert.Equal("合格", sheet.Cell(6, 15).GetString());
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Write_国标全膨胀型_表头截面号改测点号_本段均值改测点均值()
    {
        // 国标 + 全超薄型（5 测点×3 次，列头 第一次/二次/三次）→ 索引列「测点号」、每行均值「测点均值」
        var times = new[] { "第一次", "第二次", "第三次" };
        var thk = new double[15];
        for (int i = 0; i < 15; i++) thk[i] = 1.95;
        var workbook = new CoatingWorkbookInput(
            CoatingStandards.GB_50205_2020,
            new[]
            {
                new CoatingBatchInput("B1", new[]
                {
                    Member("超薄柱1", "柱", 2, 5, times, thk), // 超薄型 合格（均值1.95 ≥ 下限max(1.9,1.8)=1.9）
                }),
            });
        var result = CoatingCalculator.Calc(workbook);

        string path = Path.Combine(Path.GetTempPath(), $"coating_sheet_{Guid.NewGuid():N}.xlsx");
        try
        {
            using (var wb = new XLWorkbook())
            {
                var ws = wb.Worksheets.Add("B1-数据分析");
                CoatingAnalysisSheet.Write(ws, result.BatchResults[0], CoatingStandards.GB_50205_2020);
                wb.SaveAs(path);
            }

            using var read = new XLWorkbook(path);
            var sheet = read.Worksheet("B1-数据分析");

            // 列(K=3)：序号|位置|类型|涂层类型|测点号|第一次|第二次|第三次|测点均值|构件均值|…
            Assert.Equal("测点号", sheet.Cell(1, 5).GetString());
            Assert.Equal("第一次", sheet.Cell(1, 6).GetString());
            Assert.Equal("第三次", sheet.Cell(1, 8).GetString());
            Assert.Equal("测点均值", sheet.Cell(1, 9).GetString());
            Assert.Equal("超薄型", sheet.Cell(2, 4).GetString());
            Assert.Equal("合格", sheet.Cell(2, 15).GetString());
        }
        finally { File.Delete(path); }
    }
}
