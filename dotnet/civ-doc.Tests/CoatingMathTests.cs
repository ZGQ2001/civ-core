// CoatingMath 单测 —— 涂层类型分级 + 验收判定（GB 50205-2020 §13.4.3）。
//   厚型（设计≥7）：合格率 ≥ 80% 且 最薄处 ≥ 设计 × 0.85（闭区间，恰 80%/85% 判合格）。
//   膨胀型 薄型(3,7)/超薄型(≤3)：构件均值 ≥ max(设计×0.95, 设计−0.2mm)（−5% 且 −200µm 兜底）。

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

    // ── 膨胀型（薄型/超薄型）判定：构件均值 ≥ max(设计×0.95, 设计−0.2) ──

    [Fact]
    public void ComputeMember_薄型_均值恰下限_合格()
    {
        // 设计 3.5（<4，−5% 起作用）：下限 = max(3.325, 3.3) = 3.325；均值恰 3.325 → 合格（闭区间）
        var r = CoatingMath.ComputeMember(3.5, new double[] { 3.325, 3.325, 3.325 });

        Assert.Equal(CoatingCategory.薄型, r.Category);
        Assert.Equal(CoatingVerdict.合格, r.Verdict);
        Assert.True(r.MeanPass);
        Assert.Equal(3.325, r.MeanLowerLimit, precision: 9);
        Assert.Null(r.FailReason);
    }

    [Fact]
    public void ComputeMember_薄型_均值略低_不合格_原因含构件均值()
    {
        var r = CoatingMath.ComputeMember(3.5, new double[] { 3.2, 3.3, 3.3 }); // 均值 ≈3.267 < 3.325

        Assert.Equal(CoatingVerdict.不合格, r.Verdict);
        Assert.False(r.MeanPass);
        Assert.Contains("构件均值", r.FailReason);
    }

    [Fact]
    public void ComputeMember_超薄型_均值达标_合格()
    {
        // 设计 2：下限 = max(1.9, 1.8) = 1.9；均值 ≈1.923 → 合格
        var r = CoatingMath.ComputeMember(2, new double[] { 1.95, 1.9, 1.92 });

        Assert.Equal(CoatingCategory.超薄型, r.Category);
        Assert.Equal(CoatingVerdict.合格, r.Verdict);
        Assert.Equal(1.9, r.MeanLowerLimit, precision: 9);
    }

    [Fact]
    public void ComputeMember_超薄型_均值不达_不合格()
    {
        var r = CoatingMath.ComputeMember(2, new double[] { 1.8, 1.85, 1.9 }); // 均值 1.85 < 1.9

        Assert.Equal(CoatingCategory.超薄型, r.Category);
        Assert.Equal(CoatingVerdict.不合格, r.Verdict);
    }

    [Fact]
    public void ComputeMember_膨胀型_设计大于4mm_200µm兜底比5百分比更严()
    {
        // 设计 5（>4）：×0.95=4.75，−0.2=4.8 → 下限取 4.8（兜底更严）。
        // 均值 4.78：过了 −5%(≥4.75) 但没过 −200µm(≥4.8) → 不合格，证明兜底起作用。
        var r = CoatingMath.ComputeMember(5, new double[] { 4.78, 4.78, 4.78 });

        Assert.Equal(CoatingCategory.薄型, r.Category);
        Assert.Equal(4.8, r.MeanLowerLimit, precision: 9);
        Assert.Equal(CoatingVerdict.不合格, r.Verdict);
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
