// DocxReportAssembler 多 section 装配引擎测试：
//   · 一份模板含两个 {{表格:xxx}} 占位符，两段都提供 → 两段表都插入、占位符不残留；
//   · 只提供一类 → 没提供的占位符段被清掉；
//   · 提供了数据但模板缺对应占位符 → 抛清晰错误；
//   · 薄壳 {{}} 项目字段按 userInputs 填。

using CivCore.Doc.ReportTables;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using Xunit;

namespace CivCore.Doc.Tests;

public class DocxReportAssemblerTests
{
    private const string AnchorPh = "{{表格:锚杆}}";
    private const string CoatingPh = "{{表格:防火涂层}}";

    [Fact]
    public void Generate_双占位符两段都提供_两段表插入且占位符不残留()
    {
        WithTemplate(
            new[] { "委托单位：{{委托单位}}", AnchorPh, CoatingPh, "结论：{{检测结论}}" },
            (template, output) =>
            {
                var sections = new[]
                {
                    new ReportSection(AnchorPh, _ => SectionBuild.Plain(
                        new[] { ("锚杆表标题", OneCellTable("锚杆数据X")) })),
                    new ReportSection(CoatingPh, _ => SectionBuild.Plain(
                        new[] { ("涂层表标题", OneCellTable("涂层数据Y")) })),
                };
                var r = DocxReportAssembler.Generate(template, output, sections,
                    new Dictionary<string, string> { ["委托单位"] = "某检测公司", ["检测结论"] = "合格" });

                Assert.Equal(2, r.TablesInserted);

                var (text, tableTexts) = ReadDoc(output);
                Assert.DoesNotContain(AnchorPh, text);
                Assert.DoesNotContain(CoatingPh, text);
                Assert.Contains("委托单位：某检测公司", text);
                Assert.Contains("结论：合格", text);
                Assert.Contains("锚杆表标题", text);
                Assert.Contains("涂层表标题", text);
                Assert.Contains(tableTexts, t => t.Contains("锚杆数据X"));
                Assert.Contains(tableTexts, t => t.Contains("涂层数据Y"));
            });
    }

    [Fact]
    public void Generate_只提供锚杆_未提供的涂层占位符被清掉()
    {
        WithTemplate(
            new[] { AnchorPh, CoatingPh },
            (template, output) =>
            {
                var sections = new[]
                {
                    new ReportSection(AnchorPh, _ => SectionBuild.Plain(
                        new[] { ("锚杆表标题", OneCellTable("锚杆数据X")) })),
                };
                var r = DocxReportAssembler.Generate(template, output, sections,
                    new Dictionary<string, string>());

                Assert.Equal(1, r.TablesInserted);

                var (text, tableTexts) = ReadDoc(output);
                Assert.Contains("锚杆表标题", text);
                Assert.Contains(tableTexts, t => t.Contains("锚杆数据X"));
                // 没提供的涂层占位符被清掉，且不会插涂层表
                Assert.DoesNotContain(CoatingPh, text);
                Assert.DoesNotContain(AnchorPh, text);
            });
    }

    [Fact]
    public void Generate_提供数据但模板缺占位符_抛清晰错误()
    {
        WithTemplate(
            new[] { "只有薄壳，没有表格占位符" },
            (template, output) =>
            {
                var sections = new[]
                {
                    new ReportSection(AnchorPh, _ => SectionBuild.Plain(
                        new[] { ("锚杆表标题", OneCellTable("锚杆数据X")) })),
                };
                var ex = Assert.Throws<ArgumentException>(() =>
                    DocxReportAssembler.Generate(template, output, sections,
                        new Dictionary<string, string>()));
                Assert.Contains(AnchorPh, ex.Message);
            });
    }

    [Fact]
    public void Generate_无section_仅填薄壳_清掉所有表格占位符()
    {
        WithTemplate(
            new[] { "委托单位：{{委托单位}}", AnchorPh, CoatingPh },
            (template, output) =>
            {
                var r = DocxReportAssembler.Generate(template, output,
                    Array.Empty<ReportSection>(),
                    new Dictionary<string, string> { ["委托单位"] = "ABC" });

                Assert.Equal(0, r.TablesInserted);
                var (text, _) = ReadDoc(output);
                Assert.Contains("委托单位：ABC", text);
                Assert.DoesNotContain(AnchorPh, text);
                Assert.DoesNotContain(CoatingPh, text);
            });
    }

    // ── helpers ──

    /// <summary>建一张 1 行 1 列、单元格含给定文本的表（用作 section 的最小 table）。</summary>
    private static Table OneCellTable(string text) => new(
        new TableRow(new TableCell(
            new Paragraph(new Run(new Text(text) { Space = SpaceProcessingModeValues.Preserve })))));

    private static void WithTemplate(string[] paragraphs, Action<string, string> body)
    {
        var tmp = Path.GetTempPath();
        var template = Path.Combine(tmp, $"asm_tpl_{Guid.NewGuid():N}.docx");
        var output = Path.Combine(tmp, $"asm_out_{Guid.NewGuid():N}.docx");
        try
        {
            using (var doc = WordprocessingDocument.Create(template, WordprocessingDocumentType.Document))
            {
                var main = doc.AddMainDocumentPart();
                var b = new Body();
                foreach (var p in paragraphs)
                    b.AppendChild(new Paragraph(new Run(
                        new Text(p) { Space = SpaceProcessingModeValues.Preserve })));
                main.Document = new Document(b);
                main.Document.Save();
            }
            body(template, output);
        }
        finally
        {
            if (File.Exists(template)) File.Delete(template);
            if (File.Exists(output)) File.Delete(output);
        }
    }

    private static (string Text, List<string> TableTexts) ReadDoc(string path)
    {
        using var doc = WordprocessingDocument.Open(path, false);
        var body = doc.MainDocumentPart!.Document!.Body!;
        return (body.InnerText, body.Descendants<Table>().Select(t => t.InnerText).ToList());
    }
}
