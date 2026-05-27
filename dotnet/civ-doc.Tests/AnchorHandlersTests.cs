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

    // ── 批次维度 user_inputs (grouting_date) 端到端测试 ──────────────────

    [Fact]
    public void Run_新模板含批次marker_多批不同灌浆日期_批次段独立替换()
    {
        using var tmp = new TempDocx();
        string input = TempXlsx();
        try
        {
            WriteTwoBatchInput(input);
            var tpl = MakeNewTemplate(tmp.Dir, "new.docx");
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

            // 项目级
            Assert.Contains("ABC集团", text);
            // 两批的 grouting_date 都要在输出里
            Assert.Contains("2026-05-01", text);
            Assert.Contains("2026-06-15", text);
            // 批次 marker 应被清理
            Assert.DoesNotContain("[[批次]]", text);
            Assert.DoesNotContain("[[/批次]]", text);
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
        }
    }

    [Fact]
    public void Run_旧模板无批次marker_单批fallback_注入第一批灌浆日期()
    {
        using var tmp = new TempDocx();
        string input = TempXlsx();
        try
        {
            AnchorTemplateWriter.Write(input);  // 默认 1 批
            var tpl = MakeOldTemplate(tmp.Dir, "old.docx");
            var outDir = Path.Combine(tmp.Dir, "out");

            // 关键：user_inputs 没传 grouting_date，仅 batch_user_inputs 传了
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
            // fallback 把 batch_user_inputs.批次1.grouting_date 注入项目级
            Assert.Contains("2026-05-01", text);
            // 旧模板没批次 marker，确实没产生 [[批次]] 残留
            Assert.DoesNotContain("[[批次]]", text);
        }
        finally
        {
            if (File.Exists(input)) File.Delete(input);
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

    /// <summary>新模板：含 [[批次]]...[[/批次]] 段，段内嵌 {{灌浆日期}} + 行重复。</summary>
    private static string MakeNewTemplate(string dir, string fileName)
    {
        var path = Path.Combine(dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mp = doc.AddMainDocumentPart();
        mp.Document = new Document(new Body());
        var body = mp.Document.Body!;
        body.AppendChild(Para("委托单位：{{委托单位}}"));
        body.AppendChild(Para("[[批次]]"));
        body.AppendChild(Para("批次：{{batch_id}}，灌浆日期：{{灌浆日期}}"));
        body.AppendChild(Para("[[每根锚杆]]"));
        body.AppendChild(Para("锚杆 {{锚杆序号}}：{{锚杆编号}}"));
        body.AppendChild(Para("[[/每根锚杆]]"));
        body.AppendChild(Para("[[/批次]]"));
        return path;
    }

    /// <summary>旧模板：只有 [[每根锚杆]] 行重复，灌浆日期写在项目级位置。</summary>
    private static string MakeOldTemplate(string dir, string fileName)
    {
        var path = Path.Combine(dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mp = doc.AddMainDocumentPart();
        mp.Document = new Document(new Body());
        var body = mp.Document.Body!;
        body.AppendChild(Para("委托单位：{{委托单位}}，灌浆日期：{{灌浆日期}}"));
        body.AppendChild(Para("[[每根锚杆]]"));
        body.AppendChild(Para("锚杆 {{锚杆序号}}：{{锚杆编号}}"));
        body.AppendChild(Para("[[/每根锚杆]]"));
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
