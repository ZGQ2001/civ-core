// CoatingCalculator 单测：多批多构件聚合 + 规范校验。

using CivCore.Doc.Calc.Coating;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingCalculatorTests
{
    private static CoatingMemberInput Member(string loc, double design, params double[] thicknesses)
    {
        var pts = thicknesses
            .Select((t, i) => CoatingPoint.Create(i + 1, $"测点{i + 1}", t))
            .ToArray();
        return CoatingMemberInput.Create(loc, "梁", design, pts);
    }

    [Fact]
    public void Calc_两批_聚合计数正确()
    {
        var workbook = new CoatingWorkbookInput(
            CoatingStandards.GB_50205_2020,
            new[]
            {
                new CoatingBatchInput("B1", new[]
                {
                    Member("梁1", 20, 21, 22, 20, 23, 21),  // 合格
                    Member("梁2", 20, 16, 16, 16, 21, 18),  // 不合格
                }),
                new CoatingBatchInput("B2", new[]
                {
                    Member("梁3", 20, 20, 20, 20, 20, 17),  // 合格（边界）
                }),
            });

        var result = CoatingCalculator.Calc(workbook);

        Assert.Equal(2, result.NBatches);
        Assert.Equal(3, result.NMembersTotal);
        Assert.Equal(2, result.NQualifiedTotal);

        Assert.Equal("B1", result.BatchResults[0].BatchId);
        Assert.Equal(1, result.BatchResults[0].NQualified);
        Assert.Equal(2, result.BatchResults[0].NTotal);

        Assert.Equal("B2", result.BatchResults[1].BatchId);
        Assert.Equal(1, result.BatchResults[1].NQualified);
        Assert.Equal(1, result.BatchResults[1].NTotal);
    }

    [Fact]
    public void Calc_构件结果保序_且与输入对应()
    {
        var workbook = new CoatingWorkbookInput(
            CoatingStandards.GB_50205_2020,
            new[]
            {
                new CoatingBatchInput("B1", new[]
                {
                    Member("柱A", 24, 25, 26, 24),
                    Member("柱B", 24, 10, 10, 10),
                }),
            });

        var result = CoatingCalculator.Calc(workbook);
        var rows = result.BatchResults[0].MembersWithResults;

        Assert.Equal("柱A", rows[0].Input.Location);
        Assert.True(rows[0].Result.Qualified);
        Assert.Equal("柱B", rows[1].Input.Location);
        Assert.False(rows[1].Result.Qualified);
    }

    [Fact]
    public void Calc_不支持的规范_抛异常()
    {
        var workbook = new CoatingWorkbookInput(
            "GB 99999-9999",
            new[] { new CoatingBatchInput("B1", new[] { Member("梁1", 20, 21) }) });

        Assert.Throws<ArgumentException>(() => CoatingCalculator.Calc(workbook));
    }
}
