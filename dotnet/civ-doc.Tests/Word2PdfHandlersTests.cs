// Word2PdfHandlers 集成测试。
//
// inspect 完全走 OpenXML + ZipArchive，跨平台可测；
// convert 在非 Windows 平台 stub 抛 PlatformNotSupportedException；
// Windows 上的 COM 实测路径不在 xUnit 跑 —— Word 不一定装，且会拉起进程污染状态。

using System.Runtime.Versioning;
using System.Text.Json;
using CivCore.Doc.Handlers;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using Xunit;

namespace CivCore.Doc.Tests;

public class Word2PdfHandlersTests : IDisposable
{
    private readonly string _tmpDir;

    public Word2PdfHandlersTests()
    {
        _tmpDir = Path.Combine(Path.GetTempPath(), $"civ-doc-w2p-{Guid.NewGuid()}");
        Directory.CreateDirectory(_tmpDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tmpDir))
            Directory.Delete(_tmpDir, recursive: true);
    }

    private static JsonElement P(object obj) =>
        JsonDocument.Parse(JsonSerializer.Serialize(obj)).RootElement;

    /// <summary>用 OpenXML SDK 造一个 N 段的简单 docx 供 inspect 测试。</summary>
    private string MakeSimpleDocx(string name, int paragraphs)
    {
        var path = Path.Combine(_tmpDir, name);
        using var doc = WordprocessingDocument.Create(path, DocumentFormat.OpenXml.WordprocessingDocumentType.Document);
        var main = doc.AddMainDocumentPart();
        main.Document = new Document(new Body());
        var body = main.Document.Body!;
        for (int i = 0; i < paragraphs; i++)
            body.AppendChild(new Paragraph(new Run(new Text($"段落 {i + 1}"))));
        return path;
    }

    // ── inspect 跨平台 ────────────────────────────────────

    [Fact]
    public void Inspect_BasicDocx_ReturnsParagraphsAndSize()
    {
        var a = MakeSimpleDocx("a.docx", 5);
        var b = MakeSimpleDocx("b.docx", 12);

        var res = (Dictionary<string, object?>)Word2PdfHandlers.Inspect(
            P(new { paths = new[] { a, b } }))!;
        var files = (List<Dictionary<string, object?>>)res["files"]!;
        Assert.Equal(2, files.Count);
        Assert.Equal(5, files[0]["paragraphs"]);
        Assert.Equal(12, files[1]["paragraphs"]);
        Assert.True((double)files[0]["size_kb"]! > 0);
        Assert.False(files[0].ContainsKey("error"));
        // 纯 OpenXML 生成的 docx 没有 docProps/app.xml<Pages> 缓存
        Assert.False(files[0].ContainsKey("pages"));
    }

    [Fact]
    public void Inspect_MissingFile_RecordsErrorButContinues()
    {
        var a = MakeSimpleDocx("a.docx", 3);
        var ghost = Path.Combine(_tmpDir, "ghost.docx");

        var res = (Dictionary<string, object?>)Word2PdfHandlers.Inspect(
            P(new { paths = new[] { a, ghost } }))!;
        var files = (List<Dictionary<string, object?>>)res["files"]!;
        Assert.Equal(3, files[0]["paragraphs"]);
        Assert.False(files[0].ContainsKey("error"));
        Assert.Contains("不存在", (string)files[1]["error"]!);
        Assert.False(files[1].ContainsKey("paragraphs"));
    }

    [Fact]
    public void Inspect_GarbageFile_RecordsErrorButContinues()
    {
        var bad = Path.Combine(_tmpDir, "fake.docx");
        File.WriteAllText(bad, "not a real docx");
        var good = MakeSimpleDocx("good.docx", 2);

        var res = (Dictionary<string, object?>)Word2PdfHandlers.Inspect(
            P(new { paths = new[] { bad, good } }))!;
        var files = (List<Dictionary<string, object?>>)res["files"]!;
        Assert.Contains("error", files[0].Keys);
        Assert.Equal(2, files[1]["paragraphs"]);
    }

    [Fact]
    public void Inspect_ReadsCachedPages_WhenDocPropsAppXmlHasPagesField()
    {
        // 手动给 docx 注入 docProps/app.xml<Pages>15</Pages>，模拟 Word 保存过的文件
        var path = MakeSimpleDocx("withpages.docx", 1);
        using (var pkg = System.IO.Packaging.Package.Open(path, FileMode.Open))
        {
            var uri = new Uri("/docProps/app.xml", UriKind.Relative);
            var part = pkg.CreatePart(uri, "application/vnd.openxmlformats-officedocument.extended-properties+xml");
            using var stream = part.GetStream();
            using var writer = new StreamWriter(stream, System.Text.Encoding.UTF8);
            writer.Write(
                """
                <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
                <Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
                  <Pages>15</Pages>
                </Properties>
                """);
        }

        var res = (Dictionary<string, object?>)Word2PdfHandlers.Inspect(
            P(new { paths = new[] { path } }))!;
        var files = (List<Dictionary<string, object?>>)res["files"]!;
        Assert.Equal(15, files[0]["pages"]);
    }

    // ── convert 输入校验 ───────────────────────────────────

    [SupportedOSPlatform("windows")]
    [Fact]
    public void Convert_EmptyInputs_ThrowsArgumentException()
    {
        if (!OperatingSystem.IsWindows()) return;
        Assert.Throws<ArgumentException>(() =>
            Word2PdfHandlers.Convert(P(new
            {
                inputs = Array.Empty<string>(),
                output_dir = _tmpDir,
            })));
    }

    [Fact]
    public void Convert_NonWindows_ThrowsPlatformNotSupported()
    {
        if (OperatingSystem.IsWindows()) return;
        var ex = Assert.Throws<PlatformNotSupportedException>(() =>
            Word2PdfHandlers.Convert(P(new
            {
                inputs = new[] { "a.docx" },
                output_dir = _tmpDir,
            })));
        Assert.Contains("Windows", ex.Message);
    }
}
