// 锚杆 表2.4 Word 表 builder 测试 —— 用真实样例数据验证：
//   14 行版式 / 各级荷载行按 P 算(kN) / 工程参数单位换算(GPa·m·kN) /
//   位移·M·Q·R·判定填值 / 单表 vs 多表标题编号 / 曲线图嵌入。

using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.ReportTables;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using DW = DocumentFormat.OpenXml.Wordprocessing;
using Xunit;

namespace CivCore.Doc.Tests;

public class AnchorWordTableTests
{
    // 样例：M = 2.63 - 0.58 = 2.05；P=180kN/Lf=500/La=7500/A=804.25/E=200000 → Q≈0.50,R≈3.36 → 合格
    private static readonly double[] Sample =
        { 0, 0.56, 1.25, 1.96, 2.6, 2.61, 2.63, 2.35, 1.83, 1.21, 0.58 };
    private static readonly AnchorParams P = AnchorParams.Create(180000, 500, 7500, 804.25, 200000);

    private static AnchorWorkbookResult Calc(params (string Batch, string Id)[] anchors)
    {
        var batches = anchors
            .GroupBy(a => a.Batch)
            .Select(g => new AnchorBatchInput(g.Key, P,
                g.Select(a => AnchorRowInput.Create(a.Id, Disp(Sample))).ToArray()))
            .ToArray();
        return AnchorCalculator.Calc(new AnchorWorkbookInput(AnchorStandards.GB_50086_2015, batches));
    }

    private static AnchorDisplacements Disp(double[] d) => new(d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8], d[9], d[10]);

    [Fact]
    public void BuildSection_单根_标题不带序号_版式与数值正确()
    {
        WithMainPart(main =>
        {
            var result = Calc(("批次1", "A-1"));
            var built = AnchorWordTable.BuildSection(
                result, new Dictionary<string, string>(),
                new Dictionary<string, Dictionary<string, string>>(),
                curveImageDir: null, sectionNo: "2.4", detectionLabel: "锚杆抗拔力（验收）", mainPart: main);

            Assert.Single(built.Tables);
            Assert.Equal("表2.4  锚杆抗拔力（验收）结果表", built.Tables[0].Title);

            var rows = built.Tables[0].Table.Elements<TableRow>().ToList();
            Assert.Equal(14, rows.Count);
            string C(int r, int c) => rows[r].Elements<TableCell>().ElementAt(c).InnerText;

            Assert.Equal("委托方提供的锚杆参数", C(0, 0));
            Assert.Equal("A-1", C(1, 1));               // {{锚杆编号}}
            Assert.Equal("200", C(1, 3));               // 弹模 200000 N/mm² → 200 GPa
            Assert.Equal("0.5", C(1, 4));               // 自由段 500mm → 0.5m
            Assert.Equal("7.5", C(1, 5));               // 锚固段 7500mm → 7.5m
            Assert.Equal("180", C(3, 1));               // 轴向拉力 180000N → 180kN
            // 各级荷载行（R8）：col1/col2 续 + 9 荷载 + 锁定 /
            Assert.Equal("18", C(8, 2));                // 0.1×180
            Assert.Equal("216", C(8, 6));               // 1.2×180
            Assert.Equal("/", C(8, 11));                // 锁定荷载
            // 位移行（R9）
            Assert.Equal("位移(mm)", C(9, 1));
            Assert.Equal("2.63", C(9, 6));              // 1.2Nt 持荷 5min
            // 判定行（R11）：M / 允许范围 / 判定
            Assert.Equal("2.05", C(11, 2));             // 弹性位移量 M
            Assert.Contains("下限", C(11, 3));
            Assert.Contains("上限", C(11, 3));
            Assert.Equal("合格", C(11, 4));
        });
    }

    [Fact]
    public void BuildSection_多根_标题带序号_全局连续()
    {
        WithMainPart(main =>
        {
            var result = Calc(("批次1", "A-1"), ("批次1", "A-2"), ("批次2", "B-1"));
            var built = AnchorWordTable.BuildSection(
                result, new Dictionary<string, string>(),
                new Dictionary<string, Dictionary<string, string>>(),
                curveImageDir: null, sectionNo: "2.4", detectionLabel: "锚杆抗拔力（验收）", mainPart: main);

            Assert.Equal(3, built.Tables.Count);
            Assert.Equal("表2.4-1  锚杆抗拔力（验收）结果表", built.Tables[0].Title);
            Assert.Equal("表2.4-2  锚杆抗拔力（验收）结果表", built.Tables[1].Title);
            Assert.Equal("表2.4-3  锚杆抗拔力（验收）结果表", built.Tables[2].Title);
        });
    }

    [Fact]
    public void BuildSection_批次级灌浆日期_并入各自表()
    {
        WithMainPart(main =>
        {
            var result = Calc(("批次1", "A-1"), ("批次2", "B-1"));
            var batchInputs = new Dictionary<string, Dictionary<string, string>>
            {
                ["批次1"] = new() { ["grouting_date"] = "2026-05-01" },
                ["批次2"] = new() { ["grouting_date"] = "2026-06-15" },
            };
            var built = AnchorWordTable.BuildSection(
                result, new Dictionary<string, string>(), batchInputs,
                curveImageDir: null, sectionNo: "2.4", detectionLabel: "锚杆抗拔", mainPart: main);

            Assert.Contains("2026-05-01", built.Tables[0].Table.InnerText);
            Assert.Contains("2026-06-15", built.Tables[1].Table.InnerText);
        });
    }

    [Fact]
    public void BuildSection_有曲线图_嵌入图片不报缺图()
    {
        var dir = Path.Combine(Path.GetTempPath(), $"anchor_curve_{Guid.NewGuid():N}");
        Directory.CreateDirectory(dir);
        // 1x1 透明 PNG（合法 PNG 头，ImageInjector 能读尺寸）
        File.WriteAllBytes(Path.Combine(dir, "A-1.png"), Convert.FromBase64String(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="));
        try
        {
            WithMainPart(main =>
            {
                var result = Calc(("批次1", "A-1"));
                var built = AnchorWordTable.BuildSection(
                    result, new Dictionary<string, string>(),
                    new Dictionary<string, Dictionary<string, string>>(),
                    curveImageDir: dir, sectionNo: "2.4", detectionLabel: "锚杆抗拔", mainPart: main);

                Assert.Empty(built.MissingImages);
                var table = built.Tables[0].Table;
                Assert.DoesNotContain("{{img", table.InnerText);
                Assert.NotEmpty(table.Descendants<DW.Drawing>());
            });
        }
        finally { Directory.Delete(dir, recursive: true); }
    }

    /// <summary>建一个临时 docx 拿到 MainDocumentPart（嵌图需要），回调里跑断言。</summary>
    private static void WithMainPart(Action<MainDocumentPart> body)
    {
        var path = Path.Combine(Path.GetTempPath(), $"anchor_wt_{Guid.NewGuid():N}.docx");
        try
        {
            using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
            var main = doc.AddMainDocumentPart();
            main.Document = new Document(new Body());
            body(main);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }
}
