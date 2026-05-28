// ReportGenerator 占位符驱动版测试：成对 marker 定位 + 克隆 N 次"克隆区" + 项目级填一次。
// 不再需要 TemplateStorage（模板就是用户的 Word 文件，无 JSON 配置）。
//
// 占位符语法升级后只支持 {{key}}（双括号）。
// 行重复 marker 从「单 marker + 后接 1 张 Table」升级到「成对 marker 之间所有元素一起克隆」。

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

    /// <summary>
    /// 建一个 docx 模板：可选项目级段落 + 起始 marker 段 + 锚杆样表 + 结束 marker 段。
    /// 默认克隆区只含 1 张样表。
    /// </summary>
    private string MakeTemplate(
        string fileName,
        string? projectIntro,
        string startMarker = ReportGenerator.DefaultPerRowStartMarker,
        string endMarker = ReportGenerator.DefaultPerRowEndMarker,
        Action<Body>? unitContent = null)
    {
        var path = Path.Combine(_tmp.Dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mainPart = doc.AddMainDocumentPart();
        mainPart.Document = new Document(new Body());
        var body = mainPart.Document.Body!;

        if (projectIntro != null)
            body.AppendChild(MakePara(projectIntro));

        body.AppendChild(MakePara(startMarker));

        if (unitContent != null)
            unitContent(body);
        else
            AddDefaultRowTable(body);

        body.AppendChild(MakePara(endMarker));
        return path;
    }

    private static Paragraph MakePara(string text) =>
        new(new Run(new Text(text) { Space = SpaceProcessingModeValues.Preserve }));

    private static void AddDefaultRowTable(Body body)
    {
        var tb = new DocxTableBuilder();
        tb.Row(new CellSpec("锚杆编号"), new CellSpec("弹性位移"), new CellSpec("结果"));
        tb.Row(new CellSpec("{{anchor_id}}"), new CellSpec("{{elastic_displacement}}"), new CellSpec("{{judgement_result}}"));
        body.AppendChild(tb.Build());
    }

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
        var src = MakeTemplate("simple.docx", projectIntro: "项目：{{project_name}}");
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
        Assert.DoesNotContain(ReportGenerator.DefaultPerRowStartMarker, inner);
        Assert.DoesNotContain(ReportGenerator.DefaultPerRowEndMarker, inner);
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
        Assert.Equal(3, tables.Count);
        Assert.Contains("P-01", tables[0].InnerText);
        Assert.Contains("P-02", tables[1].InnerText);
        Assert.Contains("P-03", tables[2].InnerText);
    }

    [Fact]
    public void Generate_克隆区含标题段加表_两个元素一起克隆()
    {
        // 模拟用户场景：[[每根锚杆]] 标题段 + 样表 [[/每根锚杆]]
        var src = MakeTemplate("title_and_table.docx",
            projectIntro: "工程：{{project_name}}",
            unitContent: body =>
            {
                body.AppendChild(MakePara("表2.4-{{anchor_index}}  {{project_name}}"));
                var tb = new DocxTableBuilder();
                tb.Row(new CellSpec("锚杆编号"), new CellSpec("判定"));
                tb.Row(new CellSpec("{{anchor_id}}"), new CellSpec("{{judgement_result}}"));
                body.AppendChild(tb.Build());
            });
        var project = new DictResolver(new() { ["project_name"] = "示例项目" });
        var rows = new IFieldResolver[]
        {
            new DictResolver(new() { ["anchor_id"] = "A1", ["judgement_result"] = "合格", ["anchor_index"] = 1, ["project_name"] = "示例项目" }),
            new DictResolver(new() { ["anchor_id"] = "A2", ["judgement_result"] = "合格", ["anchor_index"] = 2, ["project_name"] = "示例项目" }),
        };
        var outPath = Path.Combine(_tmp.Dir, "tt_out.docx");

        var res = ReportGenerator.Generate(src, project, rows, outPath);

        Assert.Equal(2, res.RowsRendered);
        var tables = ReadTables(outPath);
        Assert.Equal(2, tables.Count);
        var inner = ReadAllText(outPath);
        Assert.Contains("工程：示例项目", inner);
        Assert.Contains("表2.4-1", inner);
        Assert.Contains("表2.4-2", inner);
        Assert.Contains("A1", inner);
        Assert.Contains("A2", inner);
    }

    [Fact]
    public void Generate_项目级和行级占位符不互相影响()
    {
        // 项目段含 {{client_name}}；行表含 {{anchor_id}}。
        // 项目级 resolver 没 anchor_id；行 resolver 没 client_name。
        // 期望：各自填各自的，没串值，没 unknown。
        var src = MakeTemplate("split.docx",
            projectIntro: "委托方：{{client_name}}");
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
    public void Generate_缺起始marker_抛异常带提示()
    {
        // 模板只放一个不含默认 startMarker 的段
        var src = MakeTemplate("no_start.docx", null,
            startMarker: "随便写点别的",
            endMarker: "也是别的");
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.Generate(
                src,
                new DictResolver(new()),
                new[] { (IFieldResolver)new DictResolver(new()) },
                Path.Combine(_tmp.Dir, "out.docx"))); // 默认 marker = [[每根锚杆]]
        Assert.Contains(ReportGenerator.DefaultPerRowStartMarker, ex.Message);
        Assert.Contains("起始锚点", ex.Message);
    }

    [Fact]
    public void Generate_有起始marker_缺结束marker_抛带提示的异常()
    {
        // 手工建：有 [[每根锚杆]] 但无 [[/每根锚杆]]
        var path = Path.Combine(_tmp.Dir, "no_end.docx");
        using (var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document))
        {
            var mp = doc.AddMainDocumentPart();
            mp.Document = new Document(new Body());
            mp.Document.Body!.AppendChild(MakePara(ReportGenerator.DefaultPerRowStartMarker));
            AddDefaultRowTable(mp.Document.Body!);
        }
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.Generate(
                path,
                new DictResolver(new()),
                new[] { (IFieldResolver)new DictResolver(new()) },
                Path.Combine(_tmp.Dir, "out.docx")));
        Assert.Contains(ReportGenerator.DefaultPerRowEndMarker, ex.Message);
        Assert.Contains("结束锚点", ex.Message);
    }

    [Fact]
    public void Generate_克隆区为空_抛带提示的异常()
    {
        // [[每根锚杆]] 紧接 [[/每根锚杆]]，中间无内容
        var path = Path.Combine(_tmp.Dir, "empty_unit.docx");
        using (var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document))
        {
            var mp = doc.AddMainDocumentPart();
            mp.Document = new Document(new Body());
            mp.Document.Body!.AppendChild(MakePara(ReportGenerator.DefaultPerRowStartMarker));
            mp.Document.Body!.AppendChild(MakePara(ReportGenerator.DefaultPerRowEndMarker));
        }
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.Generate(
                path,
                new DictResolver(new()),
                new[] { (IFieldResolver)new DictResolver(new()) },
                Path.Combine(_tmp.Dir, "out.docx")));
        Assert.Contains("克隆区为空", ex.Message);
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
        var src = MakeTemplate("zh.docx", null, unitContent: body =>
        {
            var tb = new DocxTableBuilder();
            tb.Row(new CellSpec("编号"), new CellSpec("位移"));
            tb.Row(new CellSpec("{{锚杆编号}}"), new CellSpec("{{弹性位移量 M (mm)}}"));
            body.AppendChild(tb.Build());
        });
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
    public void Generate_自定义marker对_也能识别()
    {
        var src = MakeTemplate("custom.docx", null,
            startMarker: "<<行开始>>",
            endMarker: "<<行结束>>");
        var row = new DictResolver(new()
        {
            ["anchor_id"] = "X",
            ["elastic_displacement"] = "1",
            ["judgement_result"] = "Z",
        });

        var outPath = Path.Combine(_tmp.Dir, "custom_out.docx");
        ReportGenerator.Generate(src, new DictResolver(new()), new[] { row }, outPath,
            perRowStartMarker: "<<行开始>>", perRowEndMarker: "<<行结束>>");

        var inner = ReadAllText(outPath);
        Assert.DoesNotContain("<<行开始>>", inner);
        Assert.DoesNotContain("<<行结束>>", inner);
        Assert.Contains("X", inner);
    }

    [Fact]
    public void Generate_起止marker相同_抛异常()
    {
        var src = MakeTemplate("same.docx", null,
            startMarker: "[[same]]", endMarker: "[[same]]");
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.Generate(src, new DictResolver(new()),
                new[] { (IFieldResolver)new DictResolver(new()) },
                Path.Combine(_tmp.Dir, "out.docx"),
                perRowStartMarker: "[[same]]", perRowEndMarker: "[[same]]"));
        Assert.Contains("不能用同一字符串", ex.Message);
    }

    // ── GenerateMultiBatch 三级模板（保留接口，模板内行重复也走成对 marker） ──

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
        body.AppendChild(MakePara("批次：{{batch_id}}，设计值：{{axial_design_load}}"));
        body.AppendChild(MakePara(ReportGenerator.DefaultPerRowStartMarker));

        var tb = new DocxTableBuilder();
        tb.Row(new CellSpec("编号"), new CellSpec("位移"), new CellSpec("结果"));
        tb.Row(new CellSpec("{{anchor_id}}"), new CellSpec("{{elastic_displacement}}"), new CellSpec("{{judgement_result}}"));
        body.AppendChild(tb.Build());

        body.AppendChild(MakePara(ReportGenerator.DefaultPerRowEndMarker));
        body.AppendChild(MakePara("[[/批次]]"));

        if (footer != null)
            body.AppendChild(MakePara(footer));

        return path;
    }

    [Fact]
    public void MultiBatch_单批次_等价于单级()
    {
        var src = MakeMultiBatchTemplate("mb_single.docx", globalIntro: "项目：{{project_name}}");
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
        Assert.DoesNotContain(ReportGenerator.DefaultPerRowStartMarker, inner);
        Assert.DoesNotContain(ReportGenerator.DefaultPerRowEndMarker, inner);
    }

    [Fact]
    public void MultiBatch_多批次_各批次独立填充()
    {
        var src = MakeMultiBatchTemplate("mb_multi.docx", globalIntro: "委托方：{{client_name}}");
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
        Assert.Contains("委托方：ABC集团", inner);
        Assert.Contains("批次：B1", inner);
        Assert.Contains("设计值：100", inner);
        Assert.Contains("P-01", inner);
        Assert.Contains("P-02", inner);
        Assert.Contains("批次：B2", inner);
        Assert.Contains("设计值：200", inner);
        Assert.Contains("P-03", inner);
        Assert.DoesNotContain("[[批次]]", inner);
        Assert.DoesNotContain("[[/批次]]", inner);
        var tables = ReadTables(outPath);
        Assert.Equal(3, tables.Count);
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
        // 模板只放普通段落 + 一张表 + 行重复 marker，没 [[批次]]
        var path = Path.Combine(_tmp.Dir, "mb_no_start.docx");
        using (var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document))
        {
            var mp = doc.AddMainDocumentPart();
            mp.Document = new Document(new Body());
            mp.Document.Body!.AppendChild(MakePara("没有批次 marker 的模板"));
        }
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.GenerateMultiBatch(path, new DictResolver(new()),
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

    // ── GenerateMultiDetectionItem 三层模板 ──

    /// <summary>建 [[检测项目]] > [[批次]] > [[每根锚杆]] 三层模板。</summary>
    private string MakeMultiDetectionItemTemplate(string fileName, string? globalIntro = null)
    {
        var path = Path.Combine(_tmp.Dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mainPart = doc.AddMainDocumentPart();
        mainPart.Document = new Document(new Body());
        var body = mainPart.Document.Body!;

        if (globalIntro != null)
            body.AppendChild(MakePara(globalIntro));

        body.AppendChild(MakePara("[[检测项目]]"));
        body.AppendChild(MakePara("检测项目：{{detection_type}}"));
        body.AppendChild(MakePara("[[批次]]"));
        body.AppendChild(MakePara("批次：{{batch_id}}"));
        body.AppendChild(MakePara(ReportGenerator.DefaultPerRowStartMarker));

        var tb = new DocxTableBuilder();
        tb.Row(new CellSpec("编号"), new CellSpec("结果"));
        tb.Row(new CellSpec("{{anchor_id}}"), new CellSpec("{{judgement_result}}"));
        body.AppendChild(tb.Build());

        body.AppendChild(MakePara(ReportGenerator.DefaultPerRowEndMarker));
        body.AppendChild(MakePara("[[/批次]]"));
        body.AppendChild(MakePara("[[/检测项目]]"));

        return path;
    }

    [Fact]
    public void MultiDetectionItem_单项目多批次_克隆批次保留项目级头()
    {
        var src = MakeMultiDetectionItemTemplate("mdi_single.docx", globalIntro: "委托方：{{client_name}}");
        var global = new DictResolver(new() { ["client_name"] = "甲方" });
        var item = new DetectionItemSection(
            new DictResolver(new() { ["detection_type"] = "锚杆抗拔" }),
            new BatchSection[]
            {
                new(
                    new DictResolver(new() { ["batch_id"] = "B1" }),
                    new IFieldResolver[]
                    {
                        new DictResolver(new() { ["anchor_id"] = "P-01", ["judgement_result"] = "合格" }),
                    }),
                new(
                    new DictResolver(new() { ["batch_id"] = "B2" }),
                    new IFieldResolver[]
                    {
                        new DictResolver(new() { ["anchor_id"] = "P-02", ["judgement_result"] = "合格" }),
                        new DictResolver(new() { ["anchor_id"] = "P-03", ["judgement_result"] = "不合格" }),
                    }),
            });
        var outPath = Path.Combine(_tmp.Dir, "mdi_single_out.docx");

        var res = ReportGenerator.GenerateMultiDetectionItem(
            src, global, new[] { item }, outPath);

        Assert.Equal(3, res.RowsRendered);
        var inner = ReadAllText(outPath);
        Assert.Contains("委托方：甲方", inner);
        // 检测项目级头只出现一次（不是每批一次）
        Assert.Single(System.Text.RegularExpressions.Regex.Matches(inner, "检测项目：锚杆抗拔"));
        // 批次级头每批一次
        Assert.Contains("批次：B1", inner);
        Assert.Contains("批次：B2", inner);
        // 三根锚杆都填进去
        Assert.Contains("P-01", inner);
        Assert.Contains("P-02", inner);
        Assert.Contains("P-03", inner);
        // marker 全清掉
        Assert.DoesNotContain("[[检测项目]]", inner);
        Assert.DoesNotContain("[[/检测项目]]", inner);
        Assert.DoesNotContain("[[批次]]", inner);
        Assert.DoesNotContain("[[/批次]]", inner);
        Assert.DoesNotContain(ReportGenerator.DefaultPerRowStartMarker, inner);
        // 三根锚杆 → 三张表
        Assert.Equal(3, ReadTables(outPath).Count);
    }

    [Fact]
    public void MultiDetectionItem_多项目_检测项目头各出现一次()
    {
        var src = MakeMultiDetectionItemTemplate("mdi_multi.docx");
        var global = new DictResolver(new());
        var items = new DetectionItemSection[]
        {
            new(
                new DictResolver(new() { ["detection_type"] = "锚杆抗拔" }),
                new BatchSection[]
                {
                    new(
                        new DictResolver(new() { ["batch_id"] = "锚-A" }),
                        new IFieldResolver[]
                        {
                            new DictResolver(new() { ["anchor_id"] = "A-01", ["judgement_result"] = "合格" }),
                        }),
                }),
            new(
                new DictResolver(new() { ["detection_type"] = "钻芯法" }),
                new BatchSection[]
                {
                    new(
                        new DictResolver(new() { ["batch_id"] = "芯-A" }),
                        new IFieldResolver[]
                        {
                            new DictResolver(new() { ["anchor_id"] = "C-01", ["judgement_result"] = "合格" }),
                        }),
                }),
        };
        var outPath = Path.Combine(_tmp.Dir, "mdi_multi_out.docx");

        var res = ReportGenerator.GenerateMultiDetectionItem(src, global, items, outPath);
        Assert.Equal(2, res.RowsRendered);

        var inner = ReadAllText(outPath);
        Assert.Contains("检测项目：锚杆抗拔", inner);
        Assert.Contains("检测项目：钻芯法", inner);
        Assert.Contains("批次：锚-A", inner);
        Assert.Contains("批次：芯-A", inner);
        Assert.Contains("A-01", inner);
        Assert.Contains("C-01", inner);
    }

    [Fact]
    public void MultiDetectionItem_缺起始marker_抛异常()
    {
        var path = Path.Combine(_tmp.Dir, "mdi_no_start.docx");
        using (var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document))
        {
            var mp = doc.AddMainDocumentPart();
            mp.Document = new Document(new Body());
            mp.Document.Body!.AppendChild(MakePara("没有检测项目 marker"));
        }
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.GenerateMultiDetectionItem(path, new DictResolver(new()),
                new[] { new DetectionItemSection(new DictResolver(new()),
                    new[] { new BatchSection(new DictResolver(new()), Array.Empty<IFieldResolver>()) }) },
                Path.Combine(_tmp.Dir, "out.docx")));
        Assert.Contains("[[检测项目]]", ex.Message);
    }

    [Fact]
    public void MultiDetectionItem_内层缺批次marker_抛异常()
    {
        // 只有 [[检测项目]] 没有 [[批次]]，预校验直接报错
        var path = Path.Combine(_tmp.Dir, "mdi_no_batch.docx");
        using (var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document))
        {
            var mp = doc.AddMainDocumentPart();
            mp.Document = new Document(new Body());
            var body = mp.Document.Body!;
            body.AppendChild(MakePara("[[检测项目]]"));
            body.AppendChild(MakePara("checkpoint without batch"));
            body.AppendChild(MakePara("[[/检测项目]]"));
        }
        var ex = Assert.Throws<ReportGenerateException>(() =>
            ReportGenerator.GenerateMultiDetectionItem(path, new DictResolver(new()),
                new[] { new DetectionItemSection(new DictResolver(new()),
                    new[] { new BatchSection(new DictResolver(new()), Array.Empty<IFieldResolver>()) }) },
                Path.Combine(_tmp.Dir, "out.docx")));
        Assert.Contains("[[批次]]", ex.Message);
    }
}
