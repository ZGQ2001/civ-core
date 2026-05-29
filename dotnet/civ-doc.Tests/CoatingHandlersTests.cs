// CoatingHandlers 端到端冒烟：generate_template → 填数据 → coating.run → 验证输出 sheet。

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

    private static readonly string[] LongHeaders =
        { "批次", "构件位置", "构件类型", "设计厚度", "截面号", "测点位置", "实测厚度" };

    [Fact]
    public void GenerateTemplate_应生成_xlsx()
    {
        string path = TempXlsx();
        try
        {
            var r = (Dictionary<string, object?>)CoatingHandlers.GenerateTemplate(
                P($"{{\"output_xlsx\":\"{Esc(path)}\"}}"))!;
            Assert.True((bool)r["ok"]!);
            Assert.True(File.Exists(path));
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ListBatches_模板默认含_批次1()
    {
        string path = TempXlsx();
        try
        {
            CoatingTemplateWriter.Write(path);
            var r = (Dictionary<string, object?>)CoatingHandlers.ListBatches(
                P($"{{\"input_xlsx\":\"{Esc(path)}\"}}"))!;
            var batches = (List<string>)r["batches"]!;
            Assert.Contains("批次1", batches);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Run_模板样例_两构件全合格()
    {
        string input = TempXlsx();
        string output = TempXlsx();
        try
        {
            CoatingTemplateWriter.Write(input);
            var r = (Dictionary<string, object?>)CoatingHandlers.Run(P($@"{{
                ""input_xlsx"": ""{Esc(input)}"",
                ""output_xlsx"": ""{Esc(output)}""
            }}"))!;

            Assert.Equal(1, (int)r["batches"]!);
            Assert.Equal(2, (int)r["members_total"]!);
            Assert.Equal(2, (int)r["members_qualified"]!); // 样例梁/柱都达标
            Assert.True(File.Exists(output));

            using var wb = new XLWorkbook(output);
            Assert.Contains("批次1-数据分析", wb.Worksheets.Select(w => w.Name));
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
            if (File.Exists(output)) File.Delete(output);
        }
    }

    [Fact]
    public void Run_含不合格构件_合格计数正确_判定写入sheet()
    {
        string input = TempXlsx();
        string output = TempXlsx();
        try
        {
            // 自建长表：梁1 合格，梁2 不合格（多数测点 < 设计 24）
            using (var wb = new XLWorkbook())
            {
                var ws = wb.Worksheets.Add("Sheet1");
                for (int c = 0; c < LongHeaders.Length; c++) ws.Cell(1, c + 1).Value = LongHeaders[c];
                int row = 2;
                void Pt(string loc, double design, int sec, string pos, double t)
                {
                    ws.Cell(row, 1).Value = "B1";
                    ws.Cell(row, 2).Value = loc;
                    ws.Cell(row, 3).Value = "梁";
                    ws.Cell(row, 4).Value = design;
                    ws.Cell(row, 5).Value = sec;
                    ws.Cell(row, 6).Value = pos;
                    ws.Cell(row, 7).Value = t;
                    row++;
                }
                // 梁1：全 ≥24 → 合格
                Pt("梁1", 24, 1, "梁侧面", 25); Pt("梁1", 24, 1, "梁侧面", 26); Pt("梁1", 24, 1, "梁底面", 27);
                // 梁2：多数 < 24 → 合格率不达 → 不合格
                Pt("梁2", 24, 1, "梁侧面", 10); Pt("梁2", 24, 1, "梁侧面", 11); Pt("梁2", 24, 1, "梁底面", 12);
                wb.SaveAs(input);
            }

            var r = (Dictionary<string, object?>)CoatingHandlers.Run(P($@"{{
                ""input_xlsx"": ""{Esc(input)}"",
                ""output_xlsx"": ""{Esc(output)}""
            }}"))!;

            Assert.Equal(2, (int)r["members_total"]!);
            Assert.Equal(1, (int)r["members_qualified"]!);

            using var read = new XLWorkbook(output);
            var sheet = read.Worksheet("B1-数据分析");
            int verdictCol = sheet.LastColumnUsed()!.ColumnNumber();
            // 梁1 行2 合格；梁2 行3 不合格
            Assert.Equal("合格", sheet.Cell(2, verdictCol).GetString());
            Assert.Contains("不合格", sheet.Cell(3, verdictCol).GetString());
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
            if (File.Exists(output)) File.Delete(output);
        }
    }
}
