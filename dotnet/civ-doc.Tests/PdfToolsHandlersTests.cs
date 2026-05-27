// PdfToolsHandlers + PageRangeParser 集成测试 —— 对齐 tests/test_pdf_*.py 用例。

using System.Text.Json;
using CivCore.Doc.Handlers;
using CivCore.Doc.Pdf;
using PdfSharp.Pdf;
using Xunit;

namespace CivCore.Doc.Tests;

public class PdfToolsHandlersTests : IDisposable
{
    private readonly string _tmpDir;

    public PdfToolsHandlersTests()
    {
        _tmpDir = Path.Combine(Path.GetTempPath(), $"civ-doc-pdf-{Guid.NewGuid()}");
        Directory.CreateDirectory(_tmpDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tmpDir))
            Directory.Delete(_tmpDir, recursive: true);
    }

    private static JsonElement P(object obj) =>
        JsonDocument.Parse(JsonSerializer.Serialize(obj)).RootElement;

    private string MakeBlankPdf(string name, int pages)
    {
        var path = Path.Combine(_tmpDir, name);
        using var doc = new PdfDocument();
        for (int i = 0; i < pages; i++)
            doc.AddPage();
        doc.Save(path);
        return path;
    }

    // ── inspect ────────────────────────────────────────

    [Fact]
    public void Inspect_BasicPdfs_ReturnsPagesAndSize()
    {
        var a = MakeBlankPdf("a.pdf", 3);
        var b = MakeBlankPdf("b.pdf", 7);

        var res = (Dictionary<string, object?>)PdfToolsHandlers.Inspect(
            P(new { paths = new[] { a, b } }))!;
        Assert.Equal(10, res["total_pages"]);
        var files = (List<Dictionary<string, object?>>)res["files"]!;
        Assert.Equal(2, files.Count);
        Assert.Equal(3, files[0]["pages"]);
        Assert.Equal(7, files[1]["pages"]);
        Assert.True((double)files[0]["size_kb"]! > 0);
        Assert.False(files[0].ContainsKey("error"));
    }

    [Fact]
    public void Inspect_MissingFile_RecordsErrorButContinues()
    {
        var a = MakeBlankPdf("a.pdf", 2);
        var ghost = Path.Combine(_tmpDir, "ghost.pdf");

        var res = (Dictionary<string, object?>)PdfToolsHandlers.Inspect(
            P(new { paths = new[] { a, ghost } }))!;
        Assert.Equal(2, res["total_pages"]); // 只算成功的
        var files = (List<Dictionary<string, object?>>)res["files"]!;
        Assert.Contains("不存在", (string)files[1]["error"]!);
        Assert.False(files[1].ContainsKey("pages"));
    }

    // ── merge ──────────────────────────────────────────

    [Fact]
    public void Merge_PageCountSumsCorrectly()
    {
        var a = MakeBlankPdf("a.pdf", 2);
        var b = MakeBlankPdf("b.pdf", 3);
        var c = MakeBlankPdf("c.pdf", 1);
        var output = Path.Combine(_tmpDir, "merged.pdf");

        var res = (Dictionary<string, object?>)PdfToolsHandlers.Merge(
            P(new { inputs = new[] { a, b, c }, output }))!;
        Assert.Equal(output, res["output"]);
        Assert.Equal(3, res["count"]);

        var (pages, _) = PdfMerger.ReadPageCount(output);
        Assert.Equal(6, pages);
    }

    [Fact]
    public void Merge_EmptyInputs_Throws()
    {
        Assert.Throws<ArgumentException>(() =>
            PdfToolsHandlers.Merge(P(new
            {
                inputs = Array.Empty<string>(),
                output = Path.Combine(_tmpDir, "merged.pdf"),
            })));
    }

    [Fact]
    public void Merge_MissingInput_Throws()
    {
        var a = MakeBlankPdf("a.pdf", 1);
        var ghost = Path.Combine(_tmpDir, "ghost.pdf");
        Assert.Throws<ArgumentException>(() =>
            PdfToolsHandlers.Merge(P(new
            {
                inputs = new[] { a, ghost },
                output = Path.Combine(_tmpDir, "merged.pdf"),
            })));
    }

    // ── split per page ────────────────────────────────

    [Fact]
    public void SplitPerPage_WritesOnePerPage_WithZeroPaddedNumbers()
    {
        var src = MakeBlankPdf("report.pdf", 12);
        var outDir = Path.Combine(_tmpDir, "out");
        var res = (Dictionary<string, object?>)PdfToolsHandlers.SplitPerPage(
            P(new { input = src, output_dir = outDir }))!;
        Assert.Equal(12, res["count"]);
        var written = (List<string>)res["written"]!;
        // 12 页 → width=2 → p01..p12
        Assert.Equal(Path.Combine(outDir, "report_p01.pdf"), written[0]);
        Assert.Equal(Path.Combine(outDir, "report_p12.pdf"), written[11]);
        foreach (var p in written)
            Assert.True(File.Exists(p));
    }

    [Fact]
    public void SplitPerPage_CustomTemplate()
    {
        var src = MakeBlankPdf("data.pdf", 3);
        var outDir = Path.Combine(_tmpDir, "out");
        var res = (Dictionary<string, object?>)PdfToolsHandlers.SplitPerPage(
            P(new { input = src, output_dir = outDir, name_template = "{stem}-{n}.pdf" }))!;
        var written = (List<string>)res["written"]!;
        Assert.Equal(Path.Combine(outDir, "data-01.pdf"), written[0]);
        Assert.Equal(Path.Combine(outDir, "data-03.pdf"), written[2]);
    }

    // ── split by ranges ───────────────────────────────

    [Fact]
    public void SplitByRanges_HandlesMultipleSegments()
    {
        var src = MakeBlankPdf("doc.pdf", 10);
        var outDir = Path.Combine(_tmpDir, "out");
        var res = (Dictionary<string, object?>)PdfToolsHandlers.SplitByRanges(
            P(new { input = src, output_dir = outDir, expr = "1-3,5,7-9" }))!;
        Assert.Equal(3, res["count"]);
        var written = (List<string>)res["written"]!;
        Assert.Equal(Path.Combine(outDir, "doc_1-3.pdf"), written[0]);
        Assert.Equal(Path.Combine(outDir, "doc_5-5.pdf"), written[1]);
        Assert.Equal(Path.Combine(outDir, "doc_7-9.pdf"), written[2]);

        var (p0, _) = PdfMerger.ReadPageCount(written[0]);
        var (p1, _) = PdfMerger.ReadPageCount(written[1]);
        var (p2, _) = PdfMerger.ReadPageCount(written[2]);
        Assert.Equal(3, p0);
        Assert.Equal(1, p1);
        Assert.Equal(3, p2);
    }

    // ── PageRangeParser 纯函数 ────────────────────────

    [Fact]
    public void PageRangeParser_BasicMixed()
    {
        var ranges = PageRangeParser.Parse("1-3,5,7-9", 10);
        Assert.Equal(3, ranges.Count);
        Assert.Equal((0, 3), (ranges[0].StartIndex, ranges[0].EndIndex));
        Assert.Equal((4, 5), (ranges[1].StartIndex, ranges[1].EndIndex));
        Assert.Equal((6, 9), (ranges[2].StartIndex, ranges[2].EndIndex));
    }

    [Theory]
    [InlineData("")]
    [InlineData("  ")]
    [InlineData("1-2,,3")]
    [InlineData("abc")]
    [InlineData("0")]
    [InlineData("0-3")]
    [InlineData("5-3")]
    [InlineData("1-15")] // 超过 total=10
    [InlineData("1-2-3")]
    public void PageRangeParser_RejectsBadExpressions(string expr)
    {
        Assert.Throws<ArgumentException>(() => PageRangeParser.Parse(expr, 10));
    }

    [Fact]
    public void PageRangeParser_ZeroTotal_Throws()
    {
        Assert.Throws<ArgumentException>(() => PageRangeParser.Parse("1", 0));
    }

    [Fact]
    public void PageRangeParser_SinglePageEquivalentToRange()
    {
        var single = PageRangeParser.Parse("5", 10);
        Assert.Single(single);
        Assert.Equal((4, 5), (single[0].StartIndex, single[0].EndIndex));
        Assert.Equal(5, single[0].Start1);
        Assert.Equal(5, single[0].End1);
    }
}
