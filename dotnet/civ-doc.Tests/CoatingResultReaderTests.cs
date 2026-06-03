// CoatingResultReader 往返：coating.run 产出的结果 xlsx，机读 sheet 反读 == 原算（read==compute）。
// 验证「出报告读结果不重算」的核心契约——CoatingResultReader.Read(结果xlsx) 和 CoatingCalculator.Calc 等价。

using System.IO;
using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;
using CivCore.Doc.Handlers;
using CivCore.Doc.ReportTables;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingResultReaderTests
{
    private const string GB = CoatingStandards.GB_50205_2020;

    private static string TempXlsx() =>
        Path.Combine(Path.GetTempPath(), $"coating_rr_{Guid.NewGuid():N}.xlsx");
    private static JsonElement P(string json) => JsonDocument.Parse(json).RootElement.Clone();
    private static string Esc(string path) => path.Replace("\\", "\\\\");

    // ── fixtures（复刻 CoatingHandlersTests 精简版）──

    private static void WriteThickInput(string path)
    {
        using var wb = new XLWorkbook();
        var preset = wb.Worksheets.Add(CoatingColumns.TypePresetSheet);
        var ph = new[] { "构件类型", "测点位置", "默认设计厚度" };
        for (int c = 0; c < ph.Length; c++) preset.Cell(1, c + 1).Value = ph[c];
        preset.Cell(2, 1).Value = "梁"; preset.Cell(2, 2).Value = "梁侧面,梁侧面,梁底面"; preset.Cell(2, 3).Value = 20;
        preset.Cell(3, 1).Value = "柱"; preset.Cell(3, 2).Value = "东侧面,西侧面,南侧面,北侧面"; preset.Cell(3, 3).Value = 24;
        var list = wb.Worksheets.Add(CoatingColumns.MemberListSheet);
        var lh = new[] { "批次", "构件位置", "构件类型", "长度(m)", "截面数", "设计厚度" };
        for (int c = 0; c < lh.Length; c++) list.Cell(1, c + 1).Value = lh[c];
        list.Cell(2, 1).Value = "B1"; list.Cell(2, 2).Value = "钢梁1"; list.Cell(2, 5).Value = 2;
        list.Cell(3, 1).Value = "B1"; list.Cell(3, 2).Value = "钢柱1"; list.Cell(3, 5).Value = 2;
        wb.SaveAs(path);
    }

    private static void WriteUltraThinInput(string path)
    {
        using var wb = new XLWorkbook();
        var preset = wb.Worksheets.Add(CoatingColumns.TypePresetSheet);
        preset.Cell(1, 1).Value = "构件类型"; preset.Cell(1, 2).Value = "测点位置"; preset.Cell(1, 3).Value = "默认设计厚度";
        preset.Cell(2, 1).Value = "梁"; preset.Cell(2, 2).Value = "梁侧面,梁侧面,梁底面"; preset.Cell(2, 3).Value = 2.0;
        var list = wb.Worksheets.Add(CoatingColumns.MemberListSheet);
        list.Cell(1, 1).Value = "批次"; list.Cell(1, 2).Value = "构件位置"; list.Cell(1, 5).Value = "截面数";
        list.Cell(2, 1).Value = "B1"; list.Cell(2, 2).Value = "超薄梁1"; list.Cell(2, 5).Value = 1;
        wb.SaveAs(path);
    }

    private static void FillPoints(string path, double value)
    {
        using var wb = new XLWorkbook(path);
        foreach (var ws in wb.Worksheets.Where(w => w.Name.StartsWith(CoatingColumns.PointDataSheet)))
        {
            int lastCol = ws.Row(1).LastCellUsed()!.Address.ColumnNumber;
            int lastRow = ws.LastRowUsed()!.RowNumber();
            int sectionCol = 0;
            for (int c = 1; c <= lastCol; c++)
            {
                var h = ws.Cell(1, c).GetString();
                if (h == "截面号" || h == "处号" || h == "测点号") { sectionCol = c; break; }
            }
            for (int r = 2; r <= lastRow; r++)
                for (int c = sectionCol + 1; c <= lastCol; c++)
                    ws.Cell(r, c).Value = value;
        }
        wb.Save();
    }

    /// <summary>真值：从输入 xlsx 直接算（和 coating.run 内部走同一个 CoatingCalculator.Calc）。</summary>
    private static CoatingWorkbookResult Compute(string input, string standard)
    {
        var bm = CoatingExcelReader.ReadRows(input, null, CoatingColumns.Batch);
        var batches = bm.Select(b => new CoatingBatchInput(b.BatchId, b.Members.ToArray())).ToArray();
        return CoatingCalculator.Calc(new CoatingWorkbookInput(standard, batches));
    }

    private static void AssertEqual(CoatingWorkbookResult exp, CoatingWorkbookResult act)
    {
        Assert.Equal(exp.Standard, act.Standard);
        Assert.Equal(exp.NBatches, act.NBatches);
        Assert.Equal(exp.NMembersTotal, act.NMembersTotal);
        Assert.Equal(exp.NQualifiedTotal, act.NQualifiedTotal);
        Assert.Equal(exp.NPendingTotal, act.NPendingTotal);
        Assert.Equal(exp.BatchResults.Length, act.BatchResults.Length);
        for (int i = 0; i < exp.BatchResults.Length; i++)
        {
            var eb = exp.BatchResults[i];
            var ab = act.BatchResults[i];
            Assert.Equal(eb.BatchId, ab.BatchId);
            Assert.Equal(eb.NQualified, ab.NQualified);
            Assert.Equal(eb.NPending, ab.NPending);
            Assert.Equal(eb.NTotal, ab.NTotal);
            Assert.Equal(eb.MembersWithResults.Length, ab.MembersWithResults.Length);
            for (int j = 0; j < eb.MembersWithResults.Length; j++)
            {
                var (ei, er) = eb.MembersWithResults[j];
                var (ai, ar) = ab.MembersWithResults[j];
                // input（含逐测点全精度）
                Assert.Equal(ei.Location, ai.Location);
                Assert.Equal(ei.MemberType, ai.MemberType);
                Assert.Equal(ei.DesignThickness, ai.DesignThickness, 9);
                Assert.Equal(ei.Points.Length, ai.Points.Length);
                for (int k = 0; k < ei.Points.Length; k++)
                {
                    Assert.Equal(ei.Points[k].SectionNo, ai.Points[k].SectionNo);
                    Assert.Equal(ei.Points[k].Position, ai.Points[k].Position);
                    Assert.Equal(ei.Points[k].Thickness, ai.Points[k].Thickness, 9);
                }
                // result（判定 + 各聚合值 + 不合格原因）
                Assert.Equal(er.Category, ar.Category);
                Assert.Equal(er.NPoints, ar.NPoints);
                Assert.Equal(er.NQualifiedPoints, ar.NQualifiedPoints);
                Assert.Equal(er.QualifiedRatio, ar.QualifiedRatio, 9);
                Assert.Equal(er.MinThickness, ar.MinThickness, 9);
                Assert.Equal(er.LowerLimit, ar.LowerLimit, 9);
                Assert.Equal(er.MeanThickness, ar.MeanThickness, 9);
                Assert.Equal(er.RatioPass, ar.RatioPass);
                Assert.Equal(er.MinPass, ar.MinPass);
                Assert.Equal(er.MeanLowerLimit, ar.MeanLowerLimit, 9);
                Assert.Equal(er.MeanPass, ar.MeanPass);
                Assert.Equal(er.Verdict, ar.Verdict);
                Assert.Equal(er.FailReason, ar.FailReason);
            }
        }
    }

    [Fact]
    public void RoundTrip_厚型_读结果等于算结果()
    {
        string input = TempXlsx();
        string output = TempXlsx();
        try
        {
            WriteThickInput(input);
            CoatingHandlers.ExpandTemplate(P($"{{\"input_xlsx\":\"{Esc(input)}\"}}"));
            FillPoints(input, 25); // 梁≥20、柱≥24 → 都厚型合格

            var expected = Compute(input, GB);
            CoatingHandlers.Run(P($@"{{""input_xlsx"":""{Esc(input)}"",""output_xlsx"":""{Esc(output)}""}}"));
            var actual = CoatingResultReader.Read(output, GB);

            AssertEqual(expected, actual);
            Assert.Equal(2, actual.NMembersTotal);
            Assert.Equal(2, actual.NQualifiedTotal);
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
            if (File.Exists(output)) File.Delete(output);
        }
    }

    [Fact]
    public void RoundTrip_超薄型不合格_含不合格原因_读结果等于算结果()
    {
        string input = TempXlsx();
        string output = TempXlsx();
        try
        {
            WriteUltraThinInput(input);
            CoatingHandlers.ExpandTemplate(P($"{{\"input_xlsx\":\"{Esc(input)}\"}}"));
            FillPoints(input, 1.8); // 均值 1.8 < 下限 max(2×0.95=1.9, 2−0.2=1.8)=1.9 → 不合格（带 FailReason）

            var expected = Compute(input, GB);
            CoatingHandlers.Run(P($@"{{""input_xlsx"":""{Esc(input)}"",""output_xlsx"":""{Esc(output)}""}}"));
            var actual = CoatingResultReader.Read(output, GB);

            AssertEqual(expected, actual);
            var r = actual.BatchResults[0].MembersWithResults[0].Result;
            Assert.Equal(CoatingVerdict.不合格, r.Verdict);
            Assert.False(string.IsNullOrEmpty(r.FailReason)); // 不合格原因非空且往返一致（"程序不能是黑盒"）
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
            if (File.Exists(output)) File.Delete(output);
        }
    }

    [Fact]
    public void Read_缺机读sheet_报清晰错误()
    {
        string path = TempXlsx();
        try
        {
            using (var wb = new XLWorkbook())
            {
                wb.Worksheets.Add("随便").Cell(1, 1).Value = "x"; // 不含 _结果数据 sheet
                wb.SaveAs(path);
            }
            var ex = Assert.Throws<InvalidOperationException>(() => CoatingResultReader.Read(path, GB));
            Assert.Contains(CoatingResultMetadataSheet.SheetName, ex.Message);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }
}
