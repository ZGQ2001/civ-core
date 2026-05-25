// PlaceholderRenderer 测试：单段、跨 Run、中文名反查、缺失兜底、表格内、未知字段。
// 复用 DocxTestFixtures 的 TempDocx；这里加一个能放普通段落 + 占位符的 docx 构造工具。

using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Template;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace civ_doc.Tests;

public class PlaceholderRendererTests : IDisposable
{
    private readonly TempDocx _tmp = new();
    public void Dispose() { _tmp.Dispose(); GC.SuppressFinalize(this); }

    /// <summary>测试用 resolver：字典查表。</summary>
    private class DictResolver : IFieldResolver
    {
        private readonly Dictionary<string, object?> _v;
        public DictResolver(Dictionary<string, object?> v) => _v = v;
        public object? GetValue(string key) => _v.TryGetValue(key, out var x) ? x : null;
    }

    /// <summary>建一个简单 docx：每段一行文字（可控 Run 拆分）。</summary>
    private string WriteSimpleDocx(string fileName, Action<Body> addContent)
    {
        var path = Path.Combine(_tmp.Dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mainPart = doc.AddMainDocumentPart();
        mainPart.Document = new Document(new Body());
        addContent(mainPart.Document.Body!);
        return path;
    }

    private static Paragraph SingleRunPara(string text) =>
        new(new Run(new Text(text) { Space = SpaceProcessingModeValues.Preserve }));

    /// <summary>把一段文字按指定切分点拆成多个 Run（模拟 Word 输入法拆分）。</summary>
    private static Paragraph MultiRunPara(params string[] parts)
    {
        var p = new Paragraph();
        foreach (var part in parts)
            p.AppendChild(new Run(new Text(part) { Space = SpaceProcessingModeValues.Preserve }));
        return p;
    }

    private static string ReadAllText(string path)
    {
        using var doc = WordprocessingDocument.Open(path, false);
        return doc.MainDocumentPart!.Document.Body!.InnerText;
    }

    private string OutPath(string name) => Path.Combine(_tmp.Dir, name);

    // ── 基本替换 ────────────────────────────────────────────

    [Fact]
    public void Render_单段单Run_key替换()
    {
        var src = WriteSimpleDocx("simple.docx", body =>
            body.AppendChild(SingleRunPara("锚杆 {anchor_id} 弹性位移 {elastic_displacement} mm")));
        var resolver = new DictResolver(new()
        {
            ["anchor_id"] = "P-01",
            ["elastic_displacement"] = 1.23,
        });

        var res = PlaceholderRenderer.Render(src, OutPath("out.docx"), resolver);

        Assert.Equal(2, res.Replaced);
        Assert.Empty(res.UnknownKeys);
        Assert.Equal("锚杆 P-01 弹性位移 1.23 mm", ReadAllText(OutPath("out.docx")));
    }

    [Fact]
    public void Render_跨Run拆分的占位符_仍能替换()
    {
        // Word 输入法常把 {anchor_id} 拆成 "{" / "anchor_id" / "}"
        var src = WriteSimpleDocx("split.docx", body =>
            body.AppendChild(MultiRunPara("锚杆 ", "{", "anchor_id", "}", " 完成")));
        var resolver = new DictResolver(new() { ["anchor_id"] = "P-99" });

        var res = PlaceholderRenderer.Render(src, OutPath("split_out.docx"), resolver);

        Assert.Equal(1, res.Replaced);
        Assert.Equal("锚杆 P-99 完成", ReadAllText(OutPath("split_out.docx")));
    }

    // ── 中文名反查 ──────────────────────────────────────────

    [Fact]
    public void Render_中文名占位符_通过catalog反查为Key()
    {
        var src = WriteSimpleDocx("zh.docx", body =>
            body.AppendChild(SingleRunPara("结果：{判定结果}")));
        var resolver = new DictResolver(new() { ["judgement_result"] = "合格" });

        var res = PlaceholderRenderer.Render(
            src, OutPath("zh_out.docx"), resolver, AnchorFieldCatalog.All);

        Assert.Equal(1, res.Replaced);
        Assert.Empty(res.UnknownKeys);
        Assert.Equal("结果：合格", ReadAllText(OutPath("zh_out.docx")));
    }

    [Fact]
    public void Render_无catalog时_只识别snake_case_key()
    {
        var src = WriteSimpleDocx("nocat.docx", body =>
            body.AppendChild(SingleRunPara("{judgement_result} / {判定结果}")));
        var resolver = new DictResolver(new() { ["judgement_result"] = "合格" });

        var res = PlaceholderRenderer.Render(src, OutPath("nocat_out.docx"), resolver, catalog: null);

        // {judgement_result} 替换；{判定结果} 没 catalog 反查 → 留原文
        Assert.Equal(1, res.Replaced);
        Assert.Single(res.UnknownKeys);
        Assert.Equal("合格 / {判定结果}", ReadAllText(OutPath("nocat_out.docx")));
    }

    // ── 缺失字段兜底 ────────────────────────────────────────

    [Fact]
    public void Render_未知key_留原文_unknownKeys列出()
    {
        var src = WriteSimpleDocx("missing.docx", body =>
            body.AppendChild(SingleRunPara("已知 {anchor_id}；未知 {totally_unknown}；再未知 {bogus_field}")));
        var resolver = new DictResolver(new() { ["anchor_id"] = "P-01" });

        var res = PlaceholderRenderer.Render(
            src, OutPath("missing_out.docx"), resolver, AnchorFieldCatalog.All);

        Assert.Equal(1, res.Replaced);
        Assert.Equal(2, res.UnknownKeys.Count);
        Assert.Contains("totally_unknown", res.UnknownKeys);
        Assert.Contains("bogus_field", res.UnknownKeys);
        Assert.Equal(
            "已知 P-01；未知 {totally_unknown}；再未知 {bogus_field}",
            ReadAllText(OutPath("missing_out.docx")));
    }

    // ── 表格内段落也生效 ───────────────────────────────────

    [Fact]
    public void Render_表格单元格内的占位符_也被替换()
    {
        var src = WriteSimpleDocx("table.docx", body =>
        {
            var table = new Table();
            var tr = new TableRow();
            tr.AppendChild(new TableCell(SingleRunPara("锚杆 {anchor_id}")));
            tr.AppendChild(new TableCell(SingleRunPara("M = {elastic_displacement}")));
            table.AppendChild(tr);
            body.AppendChild(table);
        });
        var resolver = new DictResolver(new()
        {
            ["anchor_id"] = "P-07",
            ["elastic_displacement"] = 1.55,
        });

        var res = PlaceholderRenderer.Render(src, OutPath("table_out.docx"), resolver);

        Assert.Equal(2, res.Replaced);
        var inner = ReadAllText(OutPath("table_out.docx"));
        Assert.Contains("P-07", inner);
        Assert.Contains("1.55", inner);
    }

    // ── 错误路径 ────────────────────────────────────────────

    [Fact]
    public void Render_源文件不存在_抛异常带路径()
    {
        var ex = Assert.Throws<PlaceholderRenderException>(() =>
            PlaceholderRenderer.Render(
                Path.Combine(_tmp.Dir, "nope.docx"),
                OutPath("out.docx"),
                new DictResolver(new())));
        Assert.Contains("不存在", ex.Message);
    }

    [Fact]
    public void Render_无占位符_零替换_零未知_文件依然产出()
    {
        var src = WriteSimpleDocx("plain.docx", body =>
            body.AppendChild(SingleRunPara("这段没有任何占位符")));
        var res = PlaceholderRenderer.Render(src, OutPath("plain_out.docx"), new DictResolver(new()));

        Assert.Equal(0, res.Replaced);
        Assert.Empty(res.UnknownKeys);
        Assert.True(File.Exists(OutPath("plain_out.docx")));
    }
}
