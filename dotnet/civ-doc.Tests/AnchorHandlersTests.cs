// AnchorHandlers 端到端冒烟测试：用 TemplateWriter 造输入 → 调 anchor.run → 验证输出。
// 验证范围：3 个 RPC 方法都能跑通，参数解析正确，输出 xlsx 含两个 sheet/批。

using System.IO;
using System.Linq;
using System.Text.Json;
using ClosedXML.Excel;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Handlers;
using civ_doc.Tests;
using Xunit;

namespace CivCore.Doc.Tests;

public class AnchorHandlersTests
{
    [Fact]
    public void GenerateTemplate_应生成_xlsx()
    {
        string path = TempXlsx();
        try
        {
            var p = ParseJson($"{{\"output_xlsx\":\"{Esc(path)}\"}}");
            var r = (Dictionary<string, object?>)AnchorHandlers.GenerateTemplate(p)!;
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
            AnchorTemplateWriter.Write(path);
            var p = ParseJson($"{{\"input_xlsx\":\"{Esc(path)}\"}}");
            var r = (Dictionary<string, object?>)AnchorHandlers.ListBatches(p)!;
            var batches = (List<string>)r["batches"]!;
            Assert.Single(batches);
            Assert.Equal("批次1", batches[0]);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Run_端到端_只生成数据分析sheet_报告内插表已迁Word()
    {
        string input = TempXlsx();
        string output = TempXlsx();
        try
        {
            AnchorTemplateWriter.Write(input);
            var json = $@"{{
                ""input_xlsx"": ""{Esc(input)}"",
                ""output_xlsx"": ""{Esc(output)}"",
                ""standard"": ""GB 50086-2015"",
                ""params_by_batch"": {{
                    ""批次1"": {{ ""P"":180000, ""Lf"":500, ""La"":7500, ""A"":804.25, ""E"":200000 }}
                }}
            }}";
            var p = ParseJson(json);
            var r = (Dictionary<string, object?>)AnchorHandlers.Run(p)!;

            Assert.Equal(1, (int)r["batches"]!);
            Assert.Equal(3, (int)r["anchors_total"]!);
            // 样例首行 M=2.05 合格；后两行全 0 → M=0，Q<0 不成立，不合格
            Assert.Equal(1, (int)r["anchors_qualified"]!);
            Assert.True(File.Exists(output));
            // 没传 word_template_path → 没 word_outputs 键
            Assert.False(r.ContainsKey("word_outputs"));

            using var wb = new XLWorkbook(output);
            var names = wb.Worksheets.Select(w => w.Name).ToList();
            Assert.Contains("批次1-数据分析", names);
            // 报告内插表已迁 Word —— Excel 不再有这个 sheet
            Assert.DoesNotContain("批次1-报告内插表", names);
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
            if (File.Exists(output)) File.Delete(output);
        }
    }

    [Fact]
    public void Run_缺批次参数_抛异常_提示批次名()
    {
        string input = TempXlsx();
        try
        {
            AnchorTemplateWriter.Write(input);
            // 模板现在自带「批次信息」sheet（含批次1默认参数）会被 run 当回退读取；
            // 本用例要测「参数哪都没填」→ 先删掉它，否则不会缺参数。
            using (var wb = new XLWorkbook(input))
            {
                if (wb.Worksheets.TryGetWorksheet(AnchorBatchInfoSheet.SheetName, out var bi))
                    bi.Delete();
                wb.Save();
            }
            var json = $@"{{
                ""input_xlsx"": ""{Esc(input)}"",
                ""standard"": ""GB 50086-2015"",
                ""params_by_batch"": {{}}
            }}";
            var p = ParseJson(json);
            var ex = Assert.Throws<ArgumentException>(() => AnchorHandlers.Run(p));
            Assert.Contains("批次1", ex.Message);
        }
        finally { if (File.Exists(input)) File.Delete(input); }
    }

    [Fact]
    public void ReadBatchInfo_读模板批次信息_返回批次1默认参数()
    {
        string path = TempXlsx();
        try
        {
            AnchorTemplateWriter.Write(path);
            var p = ParseJson($"{{\"input_xlsx\":\"{Esc(path)}\"}}");
            var r = (Dictionary<string, object?>)AnchorHandlers.ReadBatchInfo(p)!;
            var batches = (List<Dictionary<string, object?>>)r["batches"]!;
            Assert.Single(batches);
            Assert.Equal("批次1", batches[0]["batch_id"]);
            Assert.NotNull(batches[0]["params"]);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Run_省略params_by_batch_从批次信息sheet读参数()
    {
        string input = TempXlsx();
        string output = TempXlsx();
        try
        {
            // 模板自带「批次信息」sheet（批次1 默认参数）；run 不传 params_by_batch 应能从中回退。
            AnchorTemplateWriter.Write(input);
            var json = $@"{{
                ""input_xlsx"": ""{Esc(input)}"",
                ""output_xlsx"": ""{Esc(output)}"",
                ""standard"": ""GB 50086-2015""
            }}";
            var p = ParseJson(json);
            var r = (Dictionary<string, object?>)AnchorHandlers.Run(p)!;

            Assert.Equal(1, (int)r["batches"]!);
            Assert.Equal(3, (int)r["anchors_total"]!);
            Assert.True(File.Exists(output));
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
            if (File.Exists(output)) File.Delete(output);
        }
    }

    // ── 批次维度 user_inputs (grouting_date) 端到端测试 ──────────────────

    [Fact]
    public void Run_多批不同灌浆日期_各批锚杆表出各自日期()
    {
        using var tmp = new TempDocx();
        string input = TempXlsx();
        try
        {
            WriteTwoBatchInput(input);
            var tpl = MakeShellTemplate(tmp.Dir, "shell.docx");
            var outDir = Path.Combine(tmp.Dir, "out");

            var json = $@"{{
                ""input_xlsx"": ""{Esc(input)}"",
                ""standard"": ""GB 50086-2015"",
                ""params_by_batch"": {{
                    ""批次1"": {{ ""P"":180000, ""Lf"":500, ""La"":7500, ""A"":804.25, ""E"":200000 }},
                    ""批次2"": {{ ""P"":180000, ""Lf"":500, ""La"":7500, ""A"":804.25, ""E"":200000 }}
                }},
                ""user_inputs"": {{ ""client_name"":""ABC集团"" }},
                ""batch_user_inputs"": {{
                    ""批次1"": {{ ""grouting_date"": ""2026-05-01"" }},
                    ""批次2"": {{ ""grouting_date"": ""2026-06-15"" }}
                }},
                ""word_template_path"": ""{Esc(tpl)}"",
                ""word_output_dir"": ""{Esc(outDir)}""
            }}";
            var p = ParseJson(json);
            var r = (Dictionary<string, object?>)AnchorHandlers.Run(p)!;

            Assert.True(r.ContainsKey("word_outputs"));
            var wordOuts = (List<string>)r["word_outputs"]!;
            Assert.Single(wordOuts);
            var text = ReadAllText(wordOuts[0]);

            // 薄壳 {{委托单位}}→client_name
            Assert.Contains("ABC集团", text);
            // 两批的 grouting_date 各自出现在本批锚杆表的「灌浆日期」格
            Assert.Contains("2026-05-01", text);
            Assert.Contains("2026-06-15", text);
            // 数据表占位符已被程序建好的表替换
            Assert.DoesNotContain("{{表格:锚杆}}", text);
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
        }
    }

    [Fact]
    public void Run_单批_灌浆日期出现在锚杆表()
    {
        using var tmp = new TempDocx();
        string input = TempXlsx();
        try
        {
            AnchorTemplateWriter.Write(input);  // 默认 1 批
            var tpl = MakeShellTemplate(tmp.Dir, "shell.docx");
            var outDir = Path.Combine(tmp.Dir, "out");

            var json = $@"{{
                ""input_xlsx"": ""{Esc(input)}"",
                ""standard"": ""GB 50086-2015"",
                ""params_by_batch"": {{
                    ""批次1"": {{ ""P"":180000, ""Lf"":500, ""La"":7500, ""A"":804.25, ""E"":200000 }}
                }},
                ""user_inputs"": {{ ""client_name"":""ABC集团"" }},
                ""batch_user_inputs"": {{
                    ""批次1"": {{ ""grouting_date"": ""2026-05-01"" }}
                }},
                ""word_template_path"": ""{Esc(tpl)}"",
                ""word_output_dir"": ""{Esc(outDir)}""
            }}";
            var p = ParseJson(json);
            var r = (Dictionary<string, object?>)AnchorHandlers.Run(p)!;

            var wordOuts = (List<string>)r["word_outputs"]!;
            var text = ReadAllText(wordOuts[0]);

            Assert.Contains("ABC集团", text);
            Assert.Contains("2026-05-01", text);
            Assert.DoesNotContain("{{表格:锚杆}}", text);
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
        }
    }

    // ── report.run_from_result 消费持久化灌浆日期 ──────────────────────

    [Fact]
    public void RunFromResult_结果xlsx自带灌浆日期_无batch_user_inputs也出日期()
    {
        using var tmp = new TempDocx();
        string input = TempXlsx();
        string resultXlsx = TempXlsx();
        try
        {
            WriteTwoBatchInput(input);
            var outDir = Path.Combine(tmp.Dir, "out");

            // 1) anchor.run：batch_user_inputs 给两批灌浆日期 → 持久化进结果 xlsx。
            //    不出 Word，这步只为产生带日期的结果 xlsx。
            var runJson = $@"{{
                ""input_xlsx"": ""{Esc(input)}"",
                ""output_xlsx"": ""{Esc(resultXlsx)}"",
                ""standard"": ""GB 50086-2015"",
                ""params_by_batch"": {{
                    ""批次1"": {{ ""P"":180000, ""Lf"":500, ""La"":7500, ""A"":804.25, ""E"":200000 }},
                    ""批次2"": {{ ""P"":180000, ""Lf"":500, ""La"":7500, ""A"":804.25, ""E"":200000 }}
                }},
                ""batch_user_inputs"": {{
                    ""批次1"": {{ ""grouting_date"": ""2026-05-01"" }},
                    ""批次2"": {{ ""grouting_date"": ""2026-06-15"" }}
                }}
            }}";
            AnchorHandlers.Run(ParseJson(runJson));

            // metadata sheet 已带日期（直接断言一次，证明持久化生效）
            var persisted = AnchorResultReader.Read(resultXlsx, "GB 50086-2015", out var dates);
            Assert.Equal(2, persisted.NBatches);
            Assert.Equal("2026-05-01", dates["批次1"]);
            Assert.Equal("2026-06-15", dates["批次2"]);

            // 2) report.run_from_result：关键 —— 不传 batch_user_inputs，日期从结果 xlsx 回退。
            var tpl = MakeShellTemplate(tmp.Dir, "shell.docx");
            var rfrJson = $@"{{
                ""result_xlsx"": ""{Esc(resultXlsx)}"",
                ""standard"": ""GB 50086-2015"",
                ""word_template_path"": ""{Esc(tpl)}"",
                ""word_output_dir"": ""{Esc(outDir)}""
            }}";
            var r = (Dictionary<string, object?>)ReportHandlers.RunFromResult(ParseJson(rfrJson))!;
            var text = ReadAllText(((List<string>)r["word_outputs"]!)[0]);

            Assert.Contains("2026-05-01", text);
            Assert.Contains("2026-06-15", text);
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
            if (File.Exists(resultXlsx)) File.Delete(resultXlsx);
        }
    }

    [Fact]
    public void RunFromResult_GUI传入日期_覆盖结果xlsx持久化日期()
    {
        using var tmp = new TempDocx();
        string input = TempXlsx();
        string resultXlsx = TempXlsx();
        try
        {
            WriteTwoBatchInput(input);
            var outDir = Path.Combine(tmp.Dir, "out");
            var runJson = $@"{{
                ""input_xlsx"": ""{Esc(input)}"",
                ""output_xlsx"": ""{Esc(resultXlsx)}"",
                ""standard"": ""GB 50086-2015"",
                ""params_by_batch"": {{
                    ""批次1"": {{ ""P"":180000, ""Lf"":500, ""La"":7500, ""A"":804.25, ""E"":200000 }},
                    ""批次2"": {{ ""P"":180000, ""Lf"":500, ""La"":7500, ""A"":804.25, ""E"":200000 }}
                }},
                ""batch_user_inputs"": {{
                    ""批次1"": {{ ""grouting_date"": ""2026-05-01"" }}
                }}
            }}";
            AnchorHandlers.Run(ParseJson(runJson));

            var tpl = MakeShellTemplate(tmp.Dir, "shell.docx");
            // GUI 传 批次1 一个不同日期 → 应覆盖持久化的 2026-05-01（GUI/预设优先）
            var rfrJson = $@"{{
                ""result_xlsx"": ""{Esc(resultXlsx)}"",
                ""standard"": ""GB 50086-2015"",
                ""word_template_path"": ""{Esc(tpl)}"",
                ""word_output_dir"": ""{Esc(outDir)}"",
                ""batch_user_inputs"": {{
                    ""批次1"": {{ ""grouting_date"": ""2030-12-31"" }}
                }}
            }}";
            var r = (Dictionary<string, object?>)ReportHandlers.RunFromResult(ParseJson(rfrJson))!;
            var text = ReadAllText(((List<string>)r["word_outputs"]!)[0]);

            Assert.Contains("2030-12-31", text);      // GUI 覆盖生效
            Assert.DoesNotContain("2026-05-01", text); // 持久化的被覆盖
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
            if (File.Exists(resultXlsx)) File.Delete(resultXlsx);
        }
    }

    /// <summary>2 批输入：在 AnchorTemplateWriter 默认 1 批基础上追加 1 行批次2。</summary>
    private static void WriteTwoBatchInput(string path)
    {
        AnchorTemplateWriter.Write(path);
        // 默认布局：第 1 行表头，第 2-4 行批次1（3 锚杆）。第 5 行起追加批次2。
        var sample = new double[] { 0, 0.56, 1.25, 1.96, 2.6, 2.61, 2.63, 2.35, 1.83, 1.21, 0.58 };
        using var wb = new XLWorkbook(path);
        var ws = wb.Worksheet(AnchorTemplateWriter.TemplateSheetName);
        ws.Cell(5, 1).Value = "批次2";
        ws.Cell(5, 2).Value = "B2-001";
        for (int j = 0; j < sample.Length; j++)
            ws.Cell(5, 3 + j).Value = sample[j];
        wb.Save();
    }

    /// <summary>薄壳模板：项目信息 {{委托单位}} + 锚杆数据表占位符 {{表格:锚杆}}。</summary>
    private static string MakeShellTemplate(string dir, string fileName)
    {
        var path = Path.Combine(dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mp = doc.AddMainDocumentPart();
        mp.Document = new Document(new Body());
        var body = mp.Document.Body!;
        body.AppendChild(Para("委托单位：{{委托单位}}"));
        body.AppendChild(Para("{{表格:锚杆}}"));
        return path;
    }

    private static Paragraph Para(string text) =>
        new(new Run(new Text(text) { Space = SpaceProcessingModeValues.Preserve }));

    private static string ReadAllText(string docxPath)
    {
        using var doc = WordprocessingDocument.Open(docxPath, false);
        return doc.MainDocumentPart!.Document!.Body!.InnerText;
    }

    private static string TempXlsx() =>
        Path.Combine(Path.GetTempPath(), $"anchor_h_{Guid.NewGuid():N}.xlsx");

    /// <summary>转义 Windows 路径里的反斜杠以放进 JSON 字面量。</summary>
    private static string Esc(string s) => s.Replace("\\", "\\\\");

    private static JsonElement ParseJson(string raw)
    {
        // JsonDocument 释放后 root 失效；为测试方便我们让它逃逸（测试结束 GC 回收即可）
        var doc = JsonDocument.Parse(raw);
        return doc.RootElement.Clone();
    }
}
