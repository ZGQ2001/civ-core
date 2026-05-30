// CoatingHandlers 端到端：generate_template → expand_template → 填数字 → coating.run。

using System.IO;
using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;
using CivCore.Doc.Handlers;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingHandlersTests
{
    private static string TempXlsx() =>
        Path.Combine(Path.GetTempPath(), $"coating_h_{Guid.NewGuid():N}.xlsx");

    private static JsonElement P(string json) => JsonDocument.Parse(json).RootElement.Clone();
    private static string Esc(string path) => path.Replace("\\", "\\\\");

    /// <summary>建含「类型预设」+「构件清单」的输入（梁/柱各一根，设计厚型）。</summary>
    private static void WriteListInput(string path)
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

    /// <summary>把所有「测点数据」sheet 的测点格（截面号右侧）填上 value。</summary>
    private static void FillPoints(string path, double value)
    {
        using var wb = new XLWorkbook(path);
        foreach (var ws in wb.Worksheets.Where(w => w.Name.StartsWith(CoatingColumns.PointDataSheet)))
        {
            int lastCol = ws.Row(1).LastCellUsed()!.Address.ColumnNumber;
            int lastRow = ws.LastRowUsed()!.RowNumber();
            // 截面号列号
            int sectionCol = 0;
            for (int c = 1; c <= lastCol; c++)
                if (ws.Cell(1, c).GetString() == "截面号") { sectionCol = c; break; }
            for (int r = 2; r <= lastRow; r++)
                for (int c = sectionCol + 1; c <= lastCol; c++)
                    ws.Cell(r, c).Value = value;
        }
        wb.Save();
    }

    [Fact]
    public void GenerateTemplate_生成模板含类型预设构件清单()
    {
        string path = TempXlsx();
        try
        {
            var r = (Dictionary<string, object?>)CoatingHandlers.GenerateTemplate(
                P($"{{\"output_xlsx\":\"{Esc(path)}\"}}"))!;
            Assert.True((bool)r["ok"]!);
            using var wb = new XLWorkbook(path);
            Assert.True(wb.Worksheets.Contains(CoatingColumns.TypePresetSheet));
            Assert.True(wb.Worksheets.Contains(CoatingColumns.MemberListSheet));
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ExpandTemplate_出梁柱测点数据网格()
    {
        string path = TempXlsx();
        try
        {
            WriteListInput(path);
            var r = (Dictionary<string, object?>)CoatingHandlers.ExpandTemplate(
                P($"{{\"input_xlsx\":\"{Esc(path)}\"}}"))!;
            Assert.True((bool)r["ok"]!);
            Assert.Equal(2, (int)r["members"]!);
            Assert.Equal(4, (int)r["total_sections"]!); // 梁2 + 柱2 截面

            using var wb = new XLWorkbook(path);
            Assert.True(wb.Worksheets.Contains("测点数据-梁"));
            Assert.True(wb.Worksheets.Contains("测点数据-柱"));
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Run_展开填数字后_厚型出合格()
    {
        string input = TempXlsx();
        string output = TempXlsx();
        try
        {
            WriteListInput(input);
            CoatingHandlers.ExpandTemplate(P($"{{\"input_xlsx\":\"{Esc(input)}\"}}"));
            FillPoints(input, 25); // 梁≥20、柱≥24 → 都厚型合格

            var r = (Dictionary<string, object?>)CoatingHandlers.Run(P($@"{{
                ""input_xlsx"": ""{Esc(input)}"",
                ""output_xlsx"": ""{Esc(output)}""
            }}"))!;

            Assert.Equal(2, (int)r["members_total"]!);
            Assert.Equal(2, (int)r["members_qualified"]!);
            Assert.Equal(0, (int)r["members_pending"]!);
            Assert.True(File.Exists(output));

            using var wb = new XLWorkbook(output);
            Assert.Contains("B1-数据分析", wb.Worksheets.Select(w => w.Name));
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
            if (File.Exists(output)) File.Delete(output);
        }
    }

    [Fact]
    public void Run_薄型构件_待判定_不计入合格()
    {
        string input = TempXlsx();
        try
        {
            // 类型预设默认设计 3.3（薄型），构件清单不覆盖
            using (var wb = new XLWorkbook())
            {
                var preset = wb.Worksheets.Add(CoatingColumns.TypePresetSheet);
                preset.Cell(1, 1).Value = "构件类型"; preset.Cell(1, 2).Value = "测点位置"; preset.Cell(1, 3).Value = "默认设计厚度";
                preset.Cell(2, 1).Value = "梁"; preset.Cell(2, 2).Value = "梁侧面,梁侧面,梁底面"; preset.Cell(2, 3).Value = 3.3;
                var list = wb.Worksheets.Add(CoatingColumns.MemberListSheet);
                list.Cell(1, 1).Value = "批次"; list.Cell(1, 2).Value = "构件位置"; list.Cell(1, 5).Value = "截面数";
                list.Cell(2, 1).Value = "B1"; list.Cell(2, 2).Value = "薄涂梁1"; list.Cell(2, 5).Value = 1;
                wb.SaveAs(input);
            }
            CoatingHandlers.ExpandTemplate(P($"{{\"input_xlsx\":\"{Esc(input)}\"}}"));
            FillPoints(input, 3.5);

            var r = (Dictionary<string, object?>)CoatingHandlers.Run(P($"{{\"input_xlsx\":\"{Esc(input)}\"}}"))!;
            Assert.Equal(1, (int)r["members_total"]!);
            Assert.Equal(0, (int)r["members_qualified"]!);
            Assert.Equal(1, (int)r["members_pending"]!);
        }
        finally { if (File.Exists(input)) File.Delete(input); }
    }
}
