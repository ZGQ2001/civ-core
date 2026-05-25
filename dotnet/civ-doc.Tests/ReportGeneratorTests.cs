// ReportGenerator 占位符驱动版测试：marker 段定位 + 克隆 N 张 + 项目级填一次。
// 不再需要 TemplateStorage（模板就是用户的 Word 文件，无 JSON 配置）。

using CivCore.Doc.Template;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace civ_doc.Tests;

public class ReportGeneratorTests : IDisposable
{
    private readonly TempDocx _tmp = new();
    public void Dispose() { _tmp.Dispose(); GC.SuppressFinalize(this); }

    private class DictResolver : IFieldResolver
    {
        private readonly Dictionary<string, object?> _v;
        public DictResolver(Dictionary<string, object?> v) => _v = v;
        public object? GetValue(string key) => _v.TryGetValue(key, out var x) ? x : null;
    }

    /// <summary>建 docx 模板：可选项目级段落 + marker 段 + 锚杆样表。</summary>
    private string MakeTemplate(
        string fileName,
        string? projectIntro,
        string marker = ReportGenerator.DefaultPerRowMarker,
        Action<DocxTableBuilder>? rowTable = null)
    {
        var path = Path.Combine(_tmp.Dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mainPart = doc.AddMainDocumentPart();
        mainPart.Document = new Document(new Body());
        var body = mainPart.Document.Body!;

        if (projectIntro != null)
            body.AppendChild(new Paragraph(new Run(new Text(projectIntro) { Space = SpaceProcessingModeValues.Preserve })));

        body.AppendChild(new Paragraph(new Run(new Text(marker) { Space = SpaceProcessingModeValues.Preserve })));

        var tb = new DocxTableBuilder();
        (rowTable ?? DefaultRowTable())(tb);
        body.AppendChild(tb.Build());

        return path;
    }

    private static Action<DocxTableBuilder> DefaultRowTable() => b => b
        .Row(new CellSpec("锚杆编号"), new CellSpec("弹性位移"), new CellSpec("结果"))
        .Row(new CellSpec("{anchor_id}"), new CellSpec("{elastic_displacement}"), new CellSpec("{judgement_result}"));

    private static List<Table> ReadTables(string path)
    {
        using var doc = WordprocessingDocument.Open(path, false);
        return doc.MainDocumentPart!.Document.Body!.Elements<Table>().ToList();
    }

    private static string ReadAllText(string path)
    {
        using var doc = WordprocessingDocument.Open(path, false);
        return doc.MainDocumentPart!.Document.Body!.InnerText;
    }

    // ── 主路径 ──────────────────────────────────────────────

    [Fact]
    public void Generate_单row_克隆一张表_项目段不动()
    {
        var src = MakeTemplate("simple.docx", projectIntro: "项目：{project_name}");
        var project = new DictResolver(new() { ["project_name"] = "测试工程" });
        var row = new DictResolver(new()
        {
            ["anchor_id"] = "P-01",
            ["elastic_displacement"] = "1.23",
            ["judgement_result"] = "合格",
        });
        var outPath = Path.Combine(_tmp.Dir, "out.docx");

        var res = ReportGenerator.Generate(src, project, new[] { row }, outPath);

        Assert.Equal(1, res.RowsRendered);
        var tables = ReadTables(outPath);
        Assert.Single(tables);
        var inner = ReadAllText(outPath);
        Assert.Contains("项目：测试工程", inner);
        Assert.Contains("P-01", inner);
        Assert.Contains("合格", inner);
        Assert.DoesNotContain(ReportGenerator.DefaultPerRowMarker, inner); // marker 段已删
    }

    [Fact]
    public void Generate_多row_克隆N张表_原模板表移除()
    {
        var src = MakeTemplate("multi.docx", null);
        var project = new DictResolver(new());
        var resolvers = new IFieldResolver[]
        {
            new DictResolver(new() { ["anchor_id"] = "P-01", ["elastic_displacement"] = "1.0", ["judgement_result"] = "合格" }),
            new DictResolver(new() { ["anchor_id"] = "P-02", ["elastic_displacement"] = "2.0", ["judgement_result"] = "不合格" }),
            new DictResolver(new() { ["anchor_id"] = "P-03", ["elastic_displacement"] = "3.0", ["judgement_result"] = "合格" }),
        };
        var outPath = Path.Combine(_tmp.Dir, "multi_out.docx");

        var res = ReportGenerator.Generate(src, project, resolvers, outPath);

        Assert.Equal(3, res.RowsRendered);
        var tables = ReadTables(outPath);
        Assert.Equal(3, tables.Count); // 一根一张，原模板 stamp 已删
        Assert.Contains("P-01", tables[0].InnerText);
        Assert.Contains("P-02", tables[1].InnerText);
        Assert.Contains("P-03", tables[2].InnerText);
    }

    [Fact]
    public void Generate_项目级和行级占位符不互相影响()
    {
        // 项目段含 {client_name}；行表含 {anchor_id}。
        // 项目级 resolver 没 anchor_id；行 resolver 没 client_name。
        // 期望：各自填各自的，没串值，没 unknown。
        var src = MakeTemplate("split.docx",
            projectIntro: "委托方：{client_name}");
        var project = new DictResolver(new() { ["client_name"] = "ABC 集团" });
        var row = new DictResolver(new()
        {
            ["anchor_id"] = "P-9",
            ["elastic_displacement"] = "X",
            ["judgement_result"] = "Y",
        });

        var outPath = Path.Combine(_tmp.Dir, "split_out.docx");
        var res = ReportGenerator.Generate(src, project, new[] { row }, outPath);

        var inner = ReadAllText(outPath);
        Assert.Contains("委托方：ABC 集团", inner);
        Assert.Contains("P-9", inner);
        Assert.Empty(res.UnknownKeys);
    }

    // ── 错误路径 ────────────────────────────────────────────

    [Fact]
    public void Generate_无文件_抛带路径的异常()
    {
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.Generate(
                Path.Combine(_tmp.Dir, "nope.docx"),
                new DictResolver(new()),
                new[] { (IFieldResolver)new DictResolver(new()) },
                Path.Combine(_tmp.Dir, "out.docx")));
        Assert.Contains("不存在", ex.Message);
    }

    [Fact]
    public void Generate_缺marker_抛异常带提示()
    {
        // 用 marker="不存在的标记" 让模板里不含此 marker
        var src = MakeTemplate("no_marker.docx", null, marker: "随便写点别的");
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.Generate(
                src,
                new DictResolver(new()),
                new[] { (IFieldResolver)new DictResolver(new()) },
                Path.Combine(_tmp.Dir, "out.docx"))); // 默认 marker = [[每根锚杆]]
        Assert.Contains("锚点", ex.Message);
        Assert.Contains(ReportGenerator.DefaultPerRowMarker, ex.Message);
    }

    [Fact]
    public void Generate_零resolver_抛异常()
    {
        var src = MakeTemplate("empty.docx", null);
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.Generate(src, new DictResolver(new()),
                Array.Empty<IFieldResolver>(),
                Path.Combine(_tmp.Dir, "out.docx")));
        Assert.Contains("没有可填", ex.Message);
    }

    // ── 中文名 + catalog ───────────────────────────────────

    [Fact]
    public void Generate_中文占位符_经catalog反查Key()
    {
        var src = MakeTemplate("zh.docx", null, rowTable: b => b
            .Row(new CellSpec("编号"), new CellSpec("位移"))
            .Row(new CellSpec("{锚杆编号}"), new CellSpec("{弹性位移量 M (mm)}")));
        var row = new DictResolver(new()
        {
            ["anchor_id"] = "P-77",
            ["elastic_displacement"] = "1.99",
        });

        var outPath = Path.Combine(_tmp.Dir, "zh_out.docx");
        var res = ReportGenerator.Generate(src, new DictResolver(new()), new[] { row }, outPath,
            catalog: CivCore.Doc.Calc.Anchor.AnchorFieldCatalog.All);

        var inner = ReadAllText(outPath);
        Assert.Contains("P-77", inner);
        Assert.Contains("1.99", inner);
        Assert.Empty(res.UnknownKeys);
    }

    // ── 自定义 marker ──────────────────────────────────────

    [Fact]
    public void Generate_自定义marker_也能识别()
    {
        var customMarker = "<<行重复>>";
        var src = MakeTemplate("custom.docx", null, marker: customMarker);
        var row = new DictResolver(new()
        {
            ["anchor_id"] = "X",
            ["elastic_displacement"] = "1",
            ["judgement_result"] = "Z",
        });

        var outPath = Path.Combine(_tmp.Dir, "custom_out.docx");
        ReportGenerator.Generate(src, new DictResolver(new()), new[] { row }, outPath,
            perRowMarker: customMarker);

        var inner = ReadAllText(outPath);
        Assert.DoesNotContain(customMarker, inner); // 自定义 marker 段也已删
        Assert.Contains("X", inner);
    }

    // ── GenerateMultiBatch 三级模板 ────────────────────────

    private string MakeMultiBatchTemplate(
        string fileName,
        string? globalIntro = null,
        string? footer = null)
    {
        var path = Path.Combine(_tmp.Dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mainPart = doc.AddMainDocumentPart();
        mainPart.Document = new Document(new Body());
        var body = mainPart.Document.Body!;

        if (globalIntro != null)
            body.AppendChild(MakePara(globalIntro));

        body.AppendChild(MakePara("[[批次]]"));
        body.AppendChild(MakePara("批次：{batch_id}，设计值：{axial_design_load}"));
        body.AppendChild(MakePara(ReportGenerator.DefaultPerRowMarker));

        var tb = new DocxTableBuilder();
        tb.Row(new CellSpec("编号"), new CellSpec("位移"), new CellSpec("结果"));
        tb.Row(new CellSpec("{anchor_id}"), new CellSpec("{elastic_displacement}"), new CellSpec("{judgement_result}"));
        body.AppendChild(tb.Build());

        body.AppendChild(MakePara("[[/批次]]"));

        if (footer != null)
            body.AppendChild(MakePara(footer));

        return path;
    }

    private static Paragraph MakePara(string text)
        => new(new Run(new Text(text) { Space = SpaceProcessingModeValues.Preserve }));

    [Fact]
    public void MultiBatch_单批次_等价于单级()
    {
        var src = MakeMultiBatchTemplate("mb_single.docx", globalIntro: "项目：{project_name}");
        var global = new DictResolver(new() { ["project_name"] = "测试工程" });
        var batch = new BatchSection(
            new DictResolver(new() { ["batch_id"] = "B1", ["axial_design_load"] = "180000" }),
            new IFieldResolver[]
            {
                new DictResolver(new() { ["anchor_id"] = "P-01", ["elastic_displacement"] = "1.23", ["judgement_result"] = "合格" }),
            });
        var outPath = Path.Combine(_tmp.Dir, "mb_single_out.docx");

        var res = ReportGenerator.GenerateMultiBatch(src, global, new[] { batch }, outPath);

        Assert.Equal(1, res.RowsRendered);
        var inner = ReadAllText(outPath);
        Assert.Contains("项目：测试工程", inner);
        Assert.Contains("批次：B1", inner);
        Assert.Contains("P-01", inner);
        Assert.Contains("合格", inner);
        Assert.DoesNotContain("[[批次]]", inner);
        Assert.DoesNotContain("[[/批次]]", inner);
        Assert.DoesNotContain(ReportGenerator.DefaultPerRowMarker, inner);
    }

    [Fact]
    public void MultiBatch_多批次_各批次独立填充()
    {
        var src = MakeMultiBatchTemplate("mb_multi.docx", globalIntro: "委托方：{client_name}");
        var global = new DictResolver(new() { ["client_name"] = "ABC集团" });
        var batches = new BatchSection[]
        {
            new(
                new DictResolver(new() { ["batch_id"] = "B1", ["axial_design_load"] = "100" }),
                new IFieldResolver[]
                {
                    new DictResolver(new() { ["anchor_id"] = "P-01", ["elastic_displacement"] = "1.0", ["judgement_result"] = "合格" }),
                    new DictResolver(new() { ["anchor_id"] = "P-02", ["elastic_displacement"] = "2.0", ["judgement_result"] = "不合格" }),
                }),
            new(
                new DictResolver(new() { ["batch_id"] = "B2", ["axial_design_load"] = "200" }),
                new IFieldResolver[]
                {
                    new DictResolver(new() { ["anchor_id"] = "P-03", ["elastic_displacement"] = "3.0", ["judgement_result"] = "合格" }),
                }),
        };
        var outPath = Path.Combine(_tmp.Dir, "mb_multi_out.docx");

        var res = ReportGenerator.GenerateMultiBatch(src, global, batches, outPath);

        Assert.Equal(3, res.RowsRendered);
        var inner = ReadAllText(outPath);
        // 全局
        Assert.Contains("委托方：ABC集团", inner);
        // B1 批次区块
        Assert.Contains("批次：B1", inner);
        Assert.Contains("设计值：100", inner);
        Assert.Contains("P-01", inner);
        Assert.Contains("P-02", inner);
        // B2 批次区块
        Assert.Contains("批次：B2", inner);
        Assert.Contains("设计值：200", inner);
        Assert.Contains("P-03", inner);
        // marker 全部已删
        Assert.DoesNotContain("[[批次]]", inner);
        Assert.DoesNotContain("[[/批次]]", inner);
        // 表数量 = 3（B1 两张 + B2 一张）
        var tables = ReadTables(outPath);
        Assert.Equal(3, tables.Count);
    }

    [Fact]
    public void MultiBatch_全局字段不侵入批次区块()
    {
        var src = MakeMultiBatchTemplate("mb_scope.docx", globalIntro: "项目：{project_name}");
        var global = new DictResolver(new() { ["project_name"] = "全局值" });
        var batch = new BatchSection(
            new DictResolver(new() { ["batch_id"] = "X", ["axial_design_load"] = "999" }),
            new IFieldResolver[]
            {
                new DictResolver(new() { ["anchor_id"] = "R1", ["elastic_displacement"] = "0", ["judgement_result"] = "Y" }),
            });
        var outPath = Path.Combine(_tmp.Dir, "mb_scope_out.docx");

        var res = ReportGenerator.GenerateMultiBatch(src, global, new[] { batch }, outPath);

        Assert.Empty(res.UnknownKeys);
        var inner = ReadAllText(outPath);
        Assert.Contains("项目：全局值", inner);
        Assert.Contains("批次：X", inner);
    }

    [Fact]
    public void MultiBatch_模板后有尾部内容_保留()
    {
        var src = MakeMultiBatchTemplate("mb_footer.docx",
            globalIntro: "头部", footer: "检测结论：全部合格");
        var global = new DictResolver(new());
        var batch = new BatchSection(
            new DictResolver(new() { ["batch_id"] = "B1", ["axial_design_load"] = "0" }),
            new IFieldResolver[]
            {
                new DictResolver(new() { ["anchor_id"] = "A", ["elastic_displacement"] = "0", ["judgement_result"] = "OK" }),
            });
        var outPath = Path.Combine(_tmp.Dir, "mb_footer_out.docx");

        ReportGenerator.GenerateMultiBatch(src, global, new[] { batch }, outPath);

        var inner = ReadAllText(outPath);
        Assert.Contains("头部", inner);
        Assert.Contains("检测结论：全部合格", inner);
        Assert.Contains("批次：B1", inner);
    }

    [Fact]
    public void MultiBatch_缺起始marker_抛异常()
    {
        var src = MakeTemplate("mb_no_start.docx", null); // 没有 [[批次]]
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.GenerateMultiBatch(src, new DictResolver(new()),
                new[] { new BatchSection(new DictResolver(new()), Array.Empty<IFieldResolver>()) },
                Path.Combine(_tmp.Dir, "out.docx")));
        Assert.Contains("[[批次]]", ex.Message);
    }

    [Fact]
    public void MultiBatch_零批次_抛异常()
    {
        var src = MakeMultiBatchTemplate("mb_empty.docx");
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.GenerateMultiBatch(src, new DictResolver(new()),
                Array.Empty<BatchSection>(),
                Path.Combine(_tmp.Dir, "out.docx")));
        Assert.Contains("没有可填", ex.Message);
    }
}
