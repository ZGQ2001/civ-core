// ReportGenerator 端到端测试 —— 用 DocxTestFixtures 构造模板 + StubResolver 喂值 +
// 真生成 docx 再用 OpenXML 读回校验。
//
// 没有锚杆专属逻辑（用通用 stub resolver），保证引擎解耦验证。
// AnchorRowResolver 的 KeySwitch 单独在 AnchorRowResolverTests.cs 测。

using CivCore.Doc.Template;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace civ_doc.Tests;

public class ReportGeneratorTests : IDisposable
{
    private readonly TempDocx _docx = new();
    private readonly string _root;
    public ReportGeneratorTests()
    {
        _root = Path.Combine(Path.GetTempPath(), "civ_core_gen_test_" + Guid.NewGuid().ToString("N"));
    }
    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, true);
        _docx.Dispose();
        GC.SuppressFinalize(this);
    }

    /// <summary>测试用 resolver：直接拿字典查。</summary>
    private class StubResolver : IFieldResolver
    {
        private readonly Dictionary<string, object?> _values;
        public StubResolver(Dictionary<string, object?> values) => _values = values;
        public object? GetValue(string fieldKey) =>
            _values.TryGetValue(fieldKey, out var v) ? v : null;
    }

    /// <summary>建模板：3 行 × 3 列，含横向合并 + 锚点；保存到 storage；返回模板名 + 输出路径。</summary>
    private (string Name, string OutputPath) PrepareTemplate(
        Action<DocxTableBuilder>? buildOverride = null,
        List<CellBinding>? bindings = null)
    {
        var src = _docx.Write("src.docx", TemplateParser.AnchorMarker,
            buildOverride ?? (b => b
                .Row(new CellSpec("标题", GridSpan: 3, Bold: true))
                .Row(new CellSpec("编号"), new CellSpec("值"), new CellSpec("状态"))
                .Row(new CellSpec("{id}"), new CellSpec("{val}"), new CellSpec("{state}"))));
        var sig = TemplateParser.ComputeSignature(src);

        var cfg = new TemplateConfig
        {
            ProjectType = "test",
            DisplayName = "测试模板",
            TableSignature = sig,
            Repeat = RepeatStrategy.PerRow,
            Bindings = bindings ?? new()
            {
                new CellBinding(2, 0, "id"),
                new CellBinding(2, 1, "value", Format: "0.00"),
                new CellBinding(2, 2, "state"),
            },
        };
        TemplateStorage.Save("test_tpl", src, cfg, _root);

        var outPath = Path.Combine(_docx.Dir, "out.docx");
        return ("test_tpl", outPath);
    }

    private static List<Table> ReadTables(string path)
    {
        using var doc = WordprocessingDocument.Open(path, false);
        return doc.MainDocumentPart!.Document.Body!.Elements<Table>().ToList();
    }

    // ── 主路径 ──────────────────────────────────────────────

    [Fact]
    public void Generate_单row_克隆一张表_填入数据()
    {
        var (name, outPath) = PrepareTemplate();
        var resolver = new StubResolver(new() { ["id"] = "P-01", ["value"] = 1.234, ["state"] = "合格" });

        ReportGenerator.Generate(name, new[] { resolver }, outPath, rootOverride: _root);

        var tables = ReadTables(outPath);
        Assert.Single(tables);
        var rows = tables[0].Elements<TableRow>().ToList();
        var dataCells = rows[2].Elements<TableCell>().ToList();
        Assert.Equal("P-01", dataCells[0].InnerText);
        Assert.Equal("1.23", dataCells[1].InnerText); // 0.00 格式
        Assert.Equal("合格", dataCells[2].InnerText);
    }

    [Fact]
    public void Generate_多row_克隆多张表_原模板表移除()
    {
        var (name, outPath) = PrepareTemplate();
        var resolvers = new IFieldResolver[]
        {
            new StubResolver(new() { ["id"] = "P-01", ["value"] = 1.0, ["state"] = "合格" }),
            new StubResolver(new() { ["id"] = "P-02", ["value"] = 2.0, ["state"] = "不合格" }),
            new StubResolver(new() { ["id"] = "P-03", ["value"] = 3.0, ["state"] = "合格" }),
        };

        ReportGenerator.Generate(name, resolvers, outPath, rootOverride: _root);

        var tables = ReadTables(outPath);
        Assert.Equal(3, tables.Count); // 一根锚杆一张表，原模板 stamp 已删
        Assert.Contains("P-01", tables[0].InnerText);
        Assert.Contains("P-02", tables[1].InnerText);
        Assert.Contains("P-03", tables[2].InnerText);
    }

    // ── 签名校验 ────────────────────────────────────────────

    [Fact]
    public void Generate_签名不匹配_抛异常带原因()
    {
        var (name, outPath) = PrepareTemplate();

        // 偷偷把 storage 里的 source.docx 换成不同结构
        var modifiedSrc = _docx.Write("modified.docx", TemplateParser.AnchorMarker, b =>
            b.Row(new CellSpec("EXTRA"), new CellSpec("CELL")));
        var storedPath = Path.Combine(TemplateStorage.GetTemplateDir(name, _root), TemplateStorage.SourceDocxName);
        File.Copy(modifiedSrc, storedPath, overwrite: true);

        var resolver = new StubResolver(new() { ["id"] = "x" });
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.Generate(name, new[] { resolver }, outPath, rootOverride: _root));
        Assert.Contains("签名", ex.Message);
    }

    // ── 解析失败兜底 ────────────────────────────────────────

    [Fact]
    public void Generate_未知fieldKey_显示未知占位()
    {
        var (name, outPath) = PrepareTemplate();
        var resolver = new StubResolver(new()); // 全部 key 返回 null

        ReportGenerator.Generate(name, new[] { resolver }, outPath, rootOverride: _root);

        var inner = string.Concat(ReadTables(outPath).Select(t => t.InnerText));
        Assert.Contains("«未知字段»", inner);
    }

    [Fact]
    public void Generate_零resolver_抛异常()
    {
        var (name, outPath) = PrepareTemplate();
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.Generate(name, Array.Empty<IFieldResolver>(), outPath, rootOverride: _root));
        Assert.Contains("没有可填", ex.Message);
    }

    [Fact]
    public void Generate_perBatch策略_当前阶段抛异常()
    {
        // 直接构造 perBatch 配置塞进 storage
        var src = _docx.Write("src.docx", TemplateParser.AnchorMarker, b =>
            b.Row(new CellSpec("A"), new CellSpec("B")));
        var sig = TemplateParser.ComputeSignature(src);
        var cfg = new TemplateConfig
        {
            ProjectType = "test",
            DisplayName = "perbatch",
            TableSignature = sig,
            Repeat = RepeatStrategy.PerBatch,
            Bindings = { new CellBinding(0, 0, "x") },
        };
        TemplateStorage.Save("perbatch_tpl", src, cfg, _root);

        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.Generate("perbatch_tpl", new[] { (IFieldResolver)new StubResolver(new()) },
                Path.Combine(_docx.Dir, "x.docx"), rootOverride: _root));
        Assert.Contains("per_row", ex.Message);
    }

    // ── DefaultFormat 走 fieldCatalog ─────────────────────

    [Fact]
    public void Generate_binding未指定format_走catalog默认格式()
    {
        var (name, outPath) = PrepareTemplate(
            bindings: new()
            {
                new CellBinding(2, 0, "id"),
                new CellBinding(2, 1, "value"), // 不指定 format
                new CellBinding(2, 2, "state"),
            });
        var resolver = new StubResolver(new() { ["id"] = "P-01", ["value"] = 1.2345, ["state"] = "ok" });
        var catalog = new Dictionary<string, FieldDef>
        {
            ["value"] = FieldDef.Create("value", "v", FieldSource.Calculated, "double", defaultFormat: "0.0"),
        };

        ReportGenerator.Generate(name, new[] { resolver }, outPath, fieldCatalog: catalog, rootOverride: _root);

        var tables = ReadTables(outPath);
        var dataCells = tables[0].Elements<TableRow>().ElementAt(2).Elements<TableCell>().ToList();
        Assert.Equal("1.2", dataCells[1].InnerText);
    }
}
