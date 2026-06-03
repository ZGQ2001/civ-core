// report.assemble 端到端：一份模板含 {{表格:锚杆}}+{{表格:防火涂层}}，
// 给锚杆结果 xlsx + 防火涂层测点 xlsx → 两段表都插入、薄壳填好、未提供的占位符清掉。

using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Calc.Coating;
using CivCore.Doc.Handlers;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using civ_doc.Tests;
using Xunit;

namespace CivCore.Doc.Tests;

public class ReportHandlersTests
{
    private static string TempXlsx() => Path.Combine(Path.GetTempPath(), $"asm_{Guid.NewGuid():N}.xlsx");
    private static JsonElement P(string json) => JsonDocument.Parse(json).RootElement.Clone();
    private static string Esc(string path) => path.Replace("\\", "\\\\");

    [Fact]
    public void Assemble_锚杆加防火涂层_双段都插入_薄壳填好_无残留占位符()
    {
        using var tmp = new TempDocx();
        var anchorResult = TempXlsx();
        var coatingResult = TempXlsx();
        try
        {
            BuildAnchorResult(anchorResult);   // 批次1 3 根
            BuildCoatingResult(coatingResult); // 梁1 + 柱1（厚型合格），coating.run 出带机读 sheet 的结果 xlsx
            var tpl = MakeBothTemplate(tmp.Dir, "both.docx");
            var output = Path.Combine(tmp.Dir, "out.docx");

            var r = (Dictionary<string, object?>)ReportHandlers.Assemble(P($@"{{
                ""word_template_path"": ""{Esc(tpl)}"",
                ""output_docx"": ""{Esc(output)}"",
                ""user_inputs"": {{ ""client_name"": ""ABC检测"" }},
                ""sections"": [
                    {{ ""type"": ""anchor"", ""result_xlsx"": ""{Esc(anchorResult)}"" }},
                    {{ ""type"": ""coating"", ""result_xlsx"": ""{Esc(coatingResult)}"" }}
                ]
            }}"))!;

            Assert.Equal(new List<string> { "anchor", "coating" }, (List<string>)r["sections"]!);
            Assert.Equal(5, (int)r["tables"]!); // 锚杆 3 根 + 涂层 梁/柱 各 1
            Assert.True(File.Exists(output));

            var text = ReadAllText(output);
            Assert.Contains("委托单位：ABC检测", text);              // 薄壳 {{委托单位}}→client_name
            Assert.Contains("委托方提供的锚杆参数", text);            // 锚杆 表2.4 版式
            Assert.Contains("防火涂层（梁）检测结果表", text);        // 防火涂层表标题
            Assert.Contains("防火涂层（柱）检测结果表", text);
            Assert.DoesNotContain("{{表格:锚杆}}", text);
            Assert.DoesNotContain("{{表格:防火涂层}}", text);
            Assert.DoesNotContain("{{委托单位}}", text);
        }
        finally
        {
            if (File.Exists(anchorResult)) File.Delete(anchorResult);
            if (File.Exists(coatingResult)) File.Delete(coatingResult);
        }
    }

    [Fact]
    public void Assemble_只给锚杆_涂层占位符被清掉()
    {
        using var tmp = new TempDocx();
        var anchorResult = TempXlsx();
        try
        {
            BuildAnchorResult(anchorResult);
            var tpl = MakeBothTemplate(tmp.Dir, "both.docx");
            var output = Path.Combine(tmp.Dir, "out.docx");

            var r = (Dictionary<string, object?>)ReportHandlers.Assemble(P($@"{{
                ""word_template_path"": ""{Esc(tpl)}"",
                ""output_docx"": ""{Esc(output)}"",
                ""sections"": [ {{ ""type"": ""anchor"", ""result_xlsx"": ""{Esc(anchorResult)}"" }} ]
            }}"))!;

            Assert.Equal(3, (int)r["tables"]!);
            var text = ReadAllText(output);
            Assert.Contains("委托方提供的锚杆参数", text);
            Assert.DoesNotContain("{{表格:防火涂层}}", text); // 未提供数据的占位符清掉
            Assert.DoesNotContain("{{表格:锚杆}}", text);
        }
        finally { if (File.Exists(anchorResult)) File.Delete(anchorResult); }
    }

    [Fact]
    public void CoatingReport_读结果xlsx_出真Word_端到端()
    {
        var demoDir = Path.Combine(Path.GetTempPath(), "civ_demo");
        Directory.CreateDirectory(demoDir);
        var result = TempXlsx();
        var tpl = MakeCoatingShell(demoDir, "防火薄壳模板_demo.docx");
        var outDocx = Path.Combine(demoDir, "防火涂层检测报告_demo.docx");
        try
        {
            BuildCoatingResult(result); // coating.run 出结果 xlsx（含机读 _结果数据 sheet）

            CoatingHandlers.Report(P($@"{{
                ""result_xlsx"": ""{Esc(result)}"",
                ""word_template_path"": ""{Esc(tpl)}"",
                ""output_docx"": ""{Esc(outDocx)}"",
                ""user_inputs"": {{ ""委托单位"": ""ABC检测公司"", ""检测结论"": ""所检防火涂层厚度合格"" }}
            }}"));

            Assert.True(File.Exists(outDocx));
            var text = ReadAllText(outDocx);
            Assert.Contains("防火涂层（梁）检测结果表", text); // 程序按规范现建的表标题
            Assert.Contains("防火涂层（柱）检测结果表", text);
            Assert.Contains("ABC检测公司", text); // {{委托单位}} 被 user_inputs 填上
            Assert.DoesNotContain("{{表格:防火涂层}}", text); // 占位符被表替换掉
            Assert.DoesNotContain("{{委托单位}}", text);
        }
        finally
        {
            if (File.Exists(result)) File.Delete(result);
            // demoDir 的模板/报告保留，供人工查看与演示
        }
    }

    [Fact]
    public void Assemble_多类型_出真Word_demo()
    {
        var demoDir = Path.Combine(Path.GetTempPath(), "civ_demo");
        Directory.CreateDirectory(demoDir);
        var anchorResult = TempXlsx();
        var coatingResult = TempXlsx();
        var tpl = MakeBothTemplate(demoDir, "联合薄壳模板_demo.docx");
        var outDocx = Path.Combine(demoDir, "联合检测报告_demo.docx");
        try
        {
            BuildAnchorResult(anchorResult);
            BuildCoatingResult(coatingResult);
            ReportHandlers.Assemble(P($@"{{
                ""word_template_path"": ""{Esc(tpl)}"",
                ""output_docx"": ""{Esc(outDocx)}"",
                ""user_inputs"": {{ ""client_name"": ""ABC检测"" }},
                ""sections"": [
                    {{ ""type"": ""anchor"", ""result_xlsx"": ""{Esc(anchorResult)}"" }},
                    {{ ""type"": ""coating"", ""result_xlsx"": ""{Esc(coatingResult)}"" }}
                ]
            }}"));
            Assert.True(File.Exists(outDocx)); // 锚杆表2.4 + 防火两表，看表名表头是否都不加粗5号
        }
        finally
        {
            if (File.Exists(anchorResult)) File.Delete(anchorResult);
            if (File.Exists(coatingResult)) File.Delete(coatingResult);
            // demoDir 的模板/报告保留，供人工查看与演示
        }
    }

    // ── fixtures ──

    /// <summary>跑 anchor.run（默认模板，批次1）产出带 metadata 的结果 xlsx。</summary>
    private static void BuildAnchorResult(string outPath)
    {
        var input = TempXlsx();
        try
        {
            AnchorTemplateWriter.Write(input);
            ReportHandlers_AnchorRun(input, outPath);
        }
        finally { if (File.Exists(input)) File.Delete(input); }
    }

    private static void ReportHandlers_AnchorRun(string input, string output)
    {
        AnchorHandlers.Run(P($@"{{
            ""input_xlsx"": ""{Esc(input)}"",
            ""output_xlsx"": ""{Esc(output)}"",
            ""standard"": ""GB 50086-2015"",
            ""params_by_batch"": {{
                ""批次1"": {{ ""P"":180000, ""Lf"":500, ""La"":7500, ""A"":804.25, ""E"":200000 }}
            }}
        }}"));
    }

    /// <summary>跑 coating.run 产出带机读结果 sheet 的结果 xlsx（梁/柱各一根，厚型填 25 → 合格）。</summary>
    private static void BuildCoatingResult(string resultPath)
    {
        var input = TempXlsx();
        try
        {
            using (var wb = new XLWorkbook())
            {
                var preset = wb.Worksheets.Add(CoatingColumns.TypePresetSheet);
                preset.Cell(1, 1).Value = "构件类型"; preset.Cell(1, 2).Value = "测点位置"; preset.Cell(1, 3).Value = "默认设计厚度";
                preset.Cell(2, 1).Value = "梁"; preset.Cell(2, 2).Value = "梁侧面,梁侧面,梁底面"; preset.Cell(2, 3).Value = 20;
                preset.Cell(3, 1).Value = "柱"; preset.Cell(3, 2).Value = "东侧面,西侧面,南侧面,北侧面"; preset.Cell(3, 3).Value = 24;

                var list = wb.Worksheets.Add(CoatingColumns.MemberListSheet);
                list.Cell(1, 1).Value = "批次"; list.Cell(1, 2).Value = "构件位置"; list.Cell(1, 5).Value = "截面数";
                list.Cell(2, 1).Value = "B1"; list.Cell(2, 2).Value = "钢梁1"; list.Cell(2, 5).Value = 2;
                list.Cell(3, 1).Value = "B1"; list.Cell(3, 2).Value = "钢柱1"; list.Cell(3, 5).Value = 2;
                wb.SaveAs(input);
            }
            CoatingHandlers.ExpandTemplate(P($"{{\"input_xlsx\":\"{Esc(input)}\"}}"));

            using (var filled = new XLWorkbook(input))
            {
                foreach (var ws in filled.Worksheets.Where(w => w.Name.StartsWith(CoatingColumns.PointDataSheet)))
                {
                    int lastCol = ws.Row(1).LastCellUsed()!.Address.ColumnNumber;
                    int lastRow = ws.LastRowUsed()!.RowNumber();
                    int sectionCol = 0;
                    for (int c = 1; c <= lastCol; c++)
                    {
                        var h = ws.Cell(1, c).GetString();
                        if (h == "截面号" || h == "处号" || h == "测点号") { sectionCol = c; break; }
                    }
                    for (int rr = 2; rr <= lastRow; rr++)
                        for (int c = sectionCol + 1; c <= lastCol; c++)
                            ws.Cell(rr, c).Value = 25;
                }
                filled.Save();
            }

            CoatingHandlers.Run(P($@"{{""input_xlsx"":""{Esc(input)}"",""output_xlsx"":""{Esc(resultPath)}""}}"));
        }
        finally { if (File.Exists(input)) File.Delete(input); }
    }

    private static string MakeBothTemplate(string dir, string fileName)
    {
        var path = Path.Combine(dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mp = doc.AddMainDocumentPart();
        mp.Document = new Document(new Body());
        var body = mp.Document.Body!;
        body.AppendChild(Para("委托单位：{{委托单位}}"));
        body.AppendChild(Para("{{表格:锚杆}}"));
        body.AppendChild(Para("{{表格:防火涂层}}"));
        return path;
    }

    /// <summary>纯防火涂层薄壳模板：项目信息 {{}} + 一段 {{表格:防火涂层}} 占位符（程序在此处按规范建表插入）。</summary>
    private static string MakeCoatingShell(string dir, string fileName)
    {
        var path = Path.Combine(dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mp = doc.AddMainDocumentPart();
        mp.Document = new Document(new Body());
        var body = mp.Document.Body!;
        body.AppendChild(Para("委托单位：{{委托单位}}"));
        body.AppendChild(Para("{{表格:防火涂层}}"));
        body.AppendChild(Para("结论：{{检测结论}}"));
        return path;
    }

    private static Paragraph Para(string text) =>
        new(new Run(new Text(text) { Space = SpaceProcessingModeValues.Preserve }));

    private static string ReadAllText(string docxPath)
    {
        using var doc = WordprocessingDocument.Open(docxPath, false);
        return doc.MainDocumentPart!.Document!.Body!.InnerText;
    }
}
