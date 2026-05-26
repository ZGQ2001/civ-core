// PlaceholderRenderer 测试：单段、跨 Run、中文名反查、别名、缺失兜底、表格内、未知字段、格式化。
// 复用 DocxTestFixtures 的 TempDocx；这里加一个能放普通段落 + 占位符的 docx 构造工具。
//
// 占位符语法升级后只支持 {{key}}（双括号）；单括号 {key} 不再识别，留原文。

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
            body.AppendChild(SingleRunPara("锚杆 {{anchor_id}} 弹性位移 {{elastic_displacement}} mm")));
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
        // Word 输入法常把 {{anchor_id}} 拆成多 Run，如 "{{" / "anchor_id" / "}}"
        var src = WriteSimpleDocx("split.docx", body =>
            body.AppendChild(MultiRunPara("锚杆 ", "{{", "anchor_id", "}}", " 完成")));
        var resolver = new DictResolver(new() { ["anchor_id"] = "P-99" });

        var res = PlaceholderRenderer.Render(src, OutPath("split_out.docx"), resolver);

        Assert.Equal(1, res.Replaced);
        Assert.Equal("锚杆 P-99 完成", ReadAllText(OutPath("split_out.docx")));
    }

    [Fact]
    public void Render_单括号_不被识别_留原文()
    {
        // {anchor_id} 单括号在新语法下不再识别；留原文，不计入 unknownKeys
        var src = WriteSimpleDocx("single.docx", body =>
            body.AppendChild(SingleRunPara("单括号 {anchor_id} 双括号 {{anchor_id}}")));
        var resolver = new DictResolver(new() { ["anchor_id"] = "P-01" });

        var res = PlaceholderRenderer.Render(src, OutPath("single_out.docx"), resolver);

        Assert.Equal(1, res.Replaced);
        Assert.Equal("单括号 {anchor_id} 双括号 P-01", ReadAllText(OutPath("single_out.docx")));
    }

    // ── 中文名反查 ──────────────────────────────────────────

    [Fact]
    public void Render_中文名占位符_通过catalog反查为Key()
    {
        var src = WriteSimpleDocx("zh.docx", body =>
            body.AppendChild(SingleRunPara("结果：{{判定结果}}")));
        var resolver = new DictResolver(new() { ["judgement_result"] = "合格" });

        var res = PlaceholderRenderer.Render(
            src, OutPath("zh_out.docx"), resolver, AnchorFieldCatalog.All);

        Assert.Equal(1, res.Replaced);
        Assert.Empty(res.UnknownKeys);
        Assert.Equal("结果：合格", ReadAllText(OutPath("zh_out.docx")));
    }

    [Fact]
    public void Render_短名别名占位符_命中Key()
    {
        // 用户模板里写 {{0.1Nt位移}} 是 disp_01nt 的别名（catalog 完整 Name 是 "0.1Nt 时位移 (mm)"）
        var src = WriteSimpleDocx("alias.docx", body =>
            body.AppendChild(SingleRunPara("0.1Nt 位移：{{0.1Nt位移}} mm; 杆体弹模：{{杆体弹模}}")));
        var resolver = new DictResolver(new()
        {
            ["disp_01nt"] = 0.45,
            ["elastic_modulus"] = 200000,
        });

        var res = PlaceholderRenderer.Render(
            src, OutPath("alias_out.docx"), resolver, AnchorFieldCatalog.All);

        Assert.Equal(2, res.Replaced);
        Assert.Empty(res.UnknownKeys);
        Assert.Equal("0.1Nt 位移：0.45 mm; 杆体弹模：200000", ReadAllText(OutPath("alias_out.docx")));
    }

    [Fact]
    public void Render_无catalog时_只识别snake_case_key()
    {
        var src = WriteSimpleDocx("nocat.docx", body =>
            body.AppendChild(SingleRunPara("{{judgement_result}} / {{判定结果}}")));
        var resolver = new DictResolver(new() { ["judgement_result"] = "合格" });

        var res = PlaceholderRenderer.Render(src, OutPath("nocat_out.docx"), resolver, catalog: null);

        // {{judgement_result}} 替换；{{判定结果}} 没 catalog 反查 → 留原文 + 计入 unknownKeys
        Assert.Equal(1, res.Replaced);
        Assert.Single(res.UnknownKeys);
        Assert.Equal("合格 / {{判定结果}}", ReadAllText(OutPath("nocat_out.docx")));
    }

    // ── 数值格式化（default_format 生效） ──────────────────────

    [Fact]
    public void Render_数值字段_按catalog的DefaultFormat格式化()
    {
        // elastic_displacement 在 catalog 标 "0.00" → 保留 2 位小数
        // anchor_id 是 string → 原样输出
        var src = WriteSimpleDocx("fmt.docx", body =>
            body.AppendChild(SingleRunPara("锚杆 {{anchor_id}} 弹性位移 {{elastic_displacement}} mm")));
        var resolver = new DictResolver(new()
        {
            ["anchor_id"] = "P-01",
            ["elastic_displacement"] = 1.23456789,
        });

        var res = PlaceholderRenderer.Render(
            src, OutPath("fmt_out.docx"), resolver, AnchorFieldCatalog.All);

        Assert.Equal(2, res.Replaced);
        Assert.Equal("锚杆 P-01 弹性位移 1.23 mm", ReadAllText(OutPath("fmt_out.docx")));
    }

    [Fact]
    public void Render_数值字段_无catalog时_回退到ToString不格式化()
    {
        var src = WriteSimpleDocx("nofmt.docx", body =>
            body.AppendChild(SingleRunPara("M = {{elastic_displacement}}")));
        var resolver = new DictResolver(new() { ["elastic_displacement"] = 1.23456789 });

        // 没传 catalog → 没法查 default_format → 原样 ToString
        var res = PlaceholderRenderer.Render(src, OutPath("nofmt_out.docx"), resolver, catalog: null);

        Assert.Equal(1, res.Replaced);
        Assert.Contains("1.23456789", ReadAllText(OutPath("nofmt_out.docx")));
    }

    // ── 缺失字段兜底 ────────────────────────────────────────

    [Fact]
    public void Render_未知key_留原文_unknownKeys列出()
    {
        var src = WriteSimpleDocx("missing.docx", body =>
            body.AppendChild(SingleRunPara("已知 {{anchor_id}}；未知 {{totally_unknown}}；再未知 {{bogus_field}}")));
        var resolver = new DictResolver(new() { ["anchor_id"] = "P-01" });

        var res = PlaceholderRenderer.Render(
            src, OutPath("missing_out.docx"), resolver, AnchorFieldCatalog.All);

        Assert.Equal(1, res.Replaced);
        Assert.Equal(2, res.UnknownKeys.Count);
        Assert.Contains("totally_unknown", res.UnknownKeys);
        Assert.Contains("bogus_field", res.UnknownKeys);
        Assert.Equal(
            "已知 P-01；未知 {{totally_unknown}}；再未知 {{bogus_field}}",
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
            tr.AppendChild(new TableCell(SingleRunPara("锚杆 {{anchor_id}}")));
            tr.AppendChild(new TableCell(SingleRunPara("M = {{elastic_displacement}}")));
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

    // ── 图片占位符 {{img:xxx}} ─────────────────────────────

    /// <summary>1x1 红色 PNG（70 字节，base64 编码）—— 测试 fixture，valid PNG。</summary>
    private const string OnePxRedPngBase64 =
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==";

    private string WritePng(string fileName)
    {
        var path = Path.Combine(_tmp.Dir, fileName);
        File.WriteAllBytes(path, Convert.FromBase64String(OnePxRedPngBase64));
        return path;
    }

    /// <summary>写一个 minimal valid SVG（带 width/height + viewBox）。</summary>
    private string WriteSvg(string fileName)
    {
        var path = Path.Combine(_tmp.Dir, fileName);
        File.WriteAllText(path,
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <svg xmlns="http://www.w3.org/2000/svg" width="100pt" height="50pt" viewBox="0 0 100 50">
              <rect width="100" height="50" fill="#1f4fe0"/>
            </svg>
            """);
        return path;
    }

    private static int CountImageParts(string docxPath)
    {
        using var doc = WordprocessingDocument.Open(docxPath, false);
        return doc.MainDocumentPart!.ImageParts.Count();
    }

    private static int CountDrawings(string docxPath)
    {
        using var doc = WordprocessingDocument.Open(docxPath, false);
        return doc.MainDocumentPart!.Document.Body!.Descendants<Drawing>().Count();
    }

    [Fact]
    public void Render_图片占位符_嵌入PNG_产出含ImagePart与Drawing()
    {
        var pngPath = WritePng("curve_a.png");
        var src = WriteSimpleDocx("img.docx", body =>
            body.AppendChild(SingleRunPara("曲线 {{img:曲线图}} 完成")));
        var resolver = new DictResolver(new() { ["curve_image"] = pngPath });
        // catalog 给 curve_image 加 alias "曲线图"，所以 {{img:曲线图}} 应能命中
        var res = PlaceholderRenderer.Render(
            src, OutPath("img_out.docx"), resolver, AnchorFieldCatalog.All);

        Assert.Equal(1, res.Replaced);
        Assert.Empty(res.UnknownKeys);
        Assert.Empty(res.MissingImages);
        Assert.Equal(1, CountImageParts(OutPath("img_out.docx")));
        Assert.Equal(1, CountDrawings(OutPath("img_out.docx")));
    }

    [Fact]
    public void Render_图片占位符_文件不存在_留原文且报missing()
    {
        var src = WriteSimpleDocx("img_miss.docx", body =>
            body.AppendChild(SingleRunPara("缺图 {{img:曲线图}}")));
        var resolver = new DictResolver(new()
        {
            ["curve_image"] = Path.Combine(_tmp.Dir, "nope.png"),
        });
        var res = PlaceholderRenderer.Render(
            src, OutPath("img_miss_out.docx"), resolver, AnchorFieldCatalog.All);

        Assert.Equal(0, res.Replaced);
        Assert.Single(res.MissingImages);
        Assert.Contains("img:曲线图", res.MissingImages);
        Assert.Contains("{{img:曲线图}}", ReadAllText(OutPath("img_miss_out.docx")));
        Assert.Equal(0, CountImageParts(OutPath("img_miss_out.docx")));
    }

    [Fact]
    public void Render_图片占位符_resolver返null_报missing()
    {
        var src = WriteSimpleDocx("img_null.docx", body =>
            body.AppendChild(SingleRunPara("{{img:curve_image}}")));
        var resolver = new DictResolver(new()); // 不提供 curve_image
        var res = PlaceholderRenderer.Render(
            src, OutPath("img_null_out.docx"), resolver, AnchorFieldCatalog.All);

        Assert.Equal(0, res.Replaced);
        Assert.Single(res.MissingImages);
        Assert.Equal(0, CountImageParts(OutPath("img_null_out.docx")));
    }

    [Fact]
    public void RenderInto_mainPart传null_图片占位符报missing不抛()
    {
        var pngPath = WritePng("curve_x.png");
        var src = WriteSimpleDocx("img_no_main.docx", body =>
            body.AppendChild(SingleRunPara("{{img:曲线图}}")));
        var resolver = new DictResolver(new() { ["curve_image"] = pngPath });

        // 直接调 RenderInto 不传 mainPart —— 即使图片真实存在也算 missing
        using var doc = WordprocessingDocument.Open(src, false);
        var body = doc.MainDocumentPart!.Document.Body!;
        var res = PlaceholderRenderer.RenderInto(
            body, resolver, AnchorFieldCatalog.All, mainPart: null);

        Assert.Single(res.MissingImages);
    }

    [Fact]
    public void Render_图片占位符_嵌入SVG_产出含SVG与PNG兜底双ImagePart()
    {
        var svgPath = WriteSvg("curve_a.svg");
        var src = WriteSimpleDocx("img_svg.docx", body =>
            body.AppendChild(SingleRunPara("曲线 {{img:曲线图}} 完成")));
        var resolver = new DictResolver(new() { ["curve_image"] = svgPath });
        var outPath = OutPath("img_svg_out.docx");
        var res = PlaceholderRenderer.Render(
            src, outPath, resolver, AnchorFieldCatalog.All);

        Assert.Equal(1, res.Replaced);
        Assert.Empty(res.MissingImages);
        // SVG 嵌入会同时产生 SVG ImagePart + 1x1 PNG 兜底 = 共 2 个
        Assert.Equal(2, CountImageParts(outPath));
        Assert.Equal(1, CountDrawings(outPath));

        // 验产物 XML 含 asvg:svgBlip 扩展元素（OpenXML SDK 序列化为带命名空间的标签）
        using var doc = WordprocessingDocument.Open(outPath, false);
        var bodyXml = doc.MainDocumentPart!.Document.Body!.OuterXml;
        Assert.Contains("svgBlip", bodyXml);
    }

    [Fact]
    public void Render_文本与图片混排_段落切多Run并嵌图()
    {
        var pngPath = WritePng("curve_mix.png");
        var src = WriteSimpleDocx("img_mix.docx", body =>
            body.AppendChild(SingleRunPara("锚杆 {{anchor_id}}：{{img:曲线图}} 已记录")));
        var resolver = new DictResolver(new()
        {
            ["anchor_id"] = "P-7",
            ["curve_image"] = pngPath,
        });

        var res = PlaceholderRenderer.Render(
            src, OutPath("img_mix_out.docx"), resolver, AnchorFieldCatalog.All);

        Assert.Equal(2, res.Replaced); // 文本 + 图片各 1
        Assert.Equal(1, CountImageParts(OutPath("img_mix_out.docx")));
        Assert.Equal(1, CountDrawings(OutPath("img_mix_out.docx")));
        var inner = ReadAllText(OutPath("img_mix_out.docx"));
        Assert.Contains("锚杆 P-7", inner);
        Assert.Contains("已记录", inner);
    }
}
