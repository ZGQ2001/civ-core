// CoatingMath 单测 —— 涂层类型分级 + 厚型验收判定（GB 50205-2020 §13.4.3）。
//   厚型（设计≥7）：合格率 ≥ 80% 且 最薄处 ≥ 设计 × 0.85（闭区间，恰 80%/85% 判合格）。
//   薄型(3,7)/超薄型(≤3)：本轮 Verdict=待判定。

using CivCore.Doc.Calc.Coating;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingMathTests
{
    // ── 涂层类型分级 ──

    [Theory]
    [InlineData(24, CoatingCategory.厚型)]
    [InlineData(7, CoatingCategory.厚型)]    // ≥7 边界
    [InlineData(6.99, CoatingCategory.薄型)]
    [InlineData(5, CoatingCategory.薄型)]
    [InlineData(3.01, CoatingCategory.薄型)]
    [InlineData(3, CoatingCategory.超薄型)]   // ≤3 边界
    [InlineData(2, CoatingCategory.超薄型)]
    public void Classify_按设计厚度分级(double design, CoatingCategory expected)
    {
        Assert.Equal(expected, CoatingStandards.Classify(design));
    }

    // ── 厚型判定（设计 ≥7，这里用 20）──

    [Fact]
    public void ComputeMember_厚型_全部达标_合格()
    {
        var r = CoatingMath.ComputeMember(20, new double[] { 21, 22, 20, 23, 21 });

        Assert.Equal(CoatingCategory.厚型, r.Category);
        Assert.Equal(CoatingVerdict.合格, r.Verdict);
        Assert.Equal(5, r.NQualifiedPoints);
        Assert.Equal(1.0, r.QualifiedRatio, precision: 9);
        Assert.Equal(17.0, r.LowerLimit, precision: 9);
        Assert.Null(r.FailReason);
    }

    [Fact]
    public void ComputeMember_厚型_合格率不达_不合格_原因为比例()
    {
        var r = CoatingMath.ComputeMember(20, new double[] { 18, 18, 18, 21, 22 });

        Assert.Equal(CoatingVerdict.不合格, r.Verdict);
        Assert.False(r.RatioPass);
        Assert.True(r.MinPass);
        Assert.Contains("达标测点比例", r.FailReason);
        Assert.DoesNotContain("最薄处", r.FailReason);
    }

    [Fact]
    public void ComputeMember_厚型_最薄不达_不合格_原因为最薄()
    {
        var r = CoatingMath.ComputeMember(20, new double[] { 21, 21, 21, 21, 16 });

        Assert.Equal(CoatingVerdict.不合格, r.Verdict);
        Assert.True(r.RatioPass);
        Assert.False(r.MinPass);
        Assert.Equal(16, r.MinThickness, precision: 9);
        Assert.Contains("最薄处", r.FailReason);
        Assert.DoesNotContain("达标测点比例", r.FailReason);
    }

    [Fact]
    public void ComputeMember_厚型_两者都不达_原因含两条()
    {
        var r = CoatingMath.ComputeMember(20, new double[] { 16, 16, 16, 21, 18 });

        Assert.Equal(CoatingVerdict.不合格, r.Verdict);
        Assert.Contains("达标测点比例", r.FailReason);
        Assert.Contains("最薄处", r.FailReason);
    }

    [Fact]
    public void ComputeMember_厚型_恰80百分比_且_恰85百分比下限_合格()
    {
        // 边界：design=20, lower=17；≥20 的 4/5=0.8（恰阈值），min=17（恰下限）
        var r = CoatingMath.ComputeMember(20, new double[] { 20, 20, 20, 20, 17 });

        Assert.Equal(CoatingVerdict.合格, r.Verdict);
        Assert.Equal(0.8, r.QualifiedRatio, precision: 9);
        Assert.Equal(17.0, r.MinThickness, precision: 9);
    }

    [Fact]
    public void ComputeMember_均值_等于算术平均()
    {
        var r = CoatingMath.ComputeMember(20, new double[] { 18, 20, 22 });
        Assert.Equal(20.0, r.MeanThickness, precision: 9);
        Assert.Equal(3, r.NPoints);
    }

    // ── 薄型/超薄型：本轮待判定 ──

    [Fact]
    public void ComputeMember_薄型_待判定_不出合格不合格()
    {
        var r = CoatingMath.ComputeMember(5, new double[] { 4.5, 5.1, 4.8 });
        Assert.Equal(CoatingCategory.薄型, r.Category);
        Assert.Equal(CoatingVerdict.待判定, r.Verdict);
        Assert.Null(r.FailReason);
    }

    [Fact]
    public void ComputeMember_超薄型_待判定()
    {
        var r = CoatingMath.ComputeMember(2, new double[] { 1.8, 2.1, 1.9 });
        Assert.Equal(CoatingCategory.超薄型, r.Category);
        Assert.Equal(CoatingVerdict.待判定, r.Verdict);
    }

    // ── 入参校验 ──

    [Fact]
    public void ComputeMember_空测点_抛异常()
    {
        Assert.Throws<ArgumentException>(
            () => CoatingMath.ComputeMember(20, System.Array.Empty<double>()));
    }

    [Fact]
    public void ComputeMember_设计厚度非正_抛异常()
    {
        Assert.Throws<ArgumentException>(
            () => CoatingMath.ComputeMember(0, new double[] { 20 }));
    }
}
