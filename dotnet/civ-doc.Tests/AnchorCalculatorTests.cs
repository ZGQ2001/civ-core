// AnchorCalculator 单测：编排层（聚合 batch / total 计数），不验算法本身。

using CivCore.Doc.Calc.Anchor;
using Xunit;

namespace CivCore.Doc.Tests;

public class AnchorCalculatorTests
{
    private static AnchorParams MakeParams() =>
        AnchorParams.Create(p: 180000, lf: 500, la: 7500, a: 804.25, e: 200000);

    private static AnchorRowInput MakeRow(string id, bool qualified)
    {
        // qualified=true: M=2.05 在 (0.504, 3.357)；false: M=0.4 < 0.504
        var d = qualified
            ? new AnchorDisplacements(0, 0.56, 1.25, 1.96, 2.6, 2.61, 2.63, 2.35, 1.83, 1.21, 0.58)
            : new AnchorDisplacements(0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.5, 0.4, 0.3, 0.2);
        return AnchorRowInput.Create(id, d);
    }

    [Fact]
    public void Calc_单批_3合格_2不合格_计数正确()
    {
        var batch = new AnchorBatchInput(
            BatchId: "B1",
            Params: MakeParams(),
            Rows: new[]
            {
                MakeRow("1", true), MakeRow("2", true), MakeRow("3", true),
                MakeRow("4", false), MakeRow("5", false),
            });
        var workbook = new AnchorWorkbookInput(
            AnchorStandards.GB_50086_2015, new[] { batch });

        var result = AnchorCalculator.Calc(workbook);

        Assert.Equal(1, result.NBatches);
        Assert.Equal(5, result.NRowsTotal);
        Assert.Equal(3, result.NQualifiedTotal);
        Assert.Single(result.BatchResults);
        Assert.Equal(3, result.BatchResults[0].NQualified);
        Assert.Equal(5, result.BatchResults[0].NTotal);
    }

    [Fact]
    public void Calc_多批_每批不同参数_独立汇总()
    {
        var p1 = MakeParams();
        var p2 = AnchorParams.Create(p: 200000, lf: 600, la: 8000, a: 1000, e: 200000);
        var workbook = new AnchorWorkbookInput(
            AnchorStandards.GB_50086_2015,
            new[]
            {
                new AnchorBatchInput("B1", p1, new[] { MakeRow("1", true), MakeRow("2", true) }),
                new AnchorBatchInput("B2", p2, new[] { MakeRow("1", false) }),
            });

        var result = AnchorCalculator.Calc(workbook);

        Assert.Equal(2, result.NBatches);
        Assert.Equal(3, result.NRowsTotal);
        Assert.Equal(2, result.BatchResults[0].NQualified);
        Assert.Same(p1, result.BatchResults[0].Params);
        Assert.Same(p2, result.BatchResults[1].Params);
    }

    [Fact]
    public void Calc_不支持的规范_抛异常()
    {
        var workbook = new AnchorWorkbookInput("ASTM-XYZ", Array.Empty<AnchorBatchInput>());
        Assert.Throws<ArgumentException>(() => AnchorCalculator.Calc(workbook));
    }

    [Fact]
    public void Calc_空批次_返回零计数()
    {
        var workbook = new AnchorWorkbookInput(
            AnchorStandards.GB_50086_2015, Array.Empty<AnchorBatchInput>());

        var result = AnchorCalculator.Calc(workbook);

        Assert.Equal(0, result.NBatches);
        Assert.Equal(0, result.NRowsTotal);
        Assert.Equal(0, result.NQualifiedTotal);
    }
}
