// AnchorHandlers 端到端冒烟测试：用 TemplateWriter 造输入 → 调 anchor.run → 验证输出。
// 验证范围：3 个 RPC 方法都能跑通，参数解析正确，输出 xlsx 含两个 sheet/批。

using System.IO;
using System.Linq;
using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Handlers;
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
