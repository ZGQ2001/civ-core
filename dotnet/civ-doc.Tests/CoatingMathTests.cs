// CoatingMath 单测 —— 厚涂型验收判定（GB 50205-2020 §13.4.3）。
//   合格 ⇔ 合格率 ≥ 80% 且 最薄处 ≥ 设计 × 0.85（闭区间，恰 80%/85% 判合格）。

using CivCore.Doc.Calc.Coating;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingMathTests
{
    [Fact]
    public void ComputeMember_全部达标_合格()
    {
        // design=20, lower=17；全 ≥20 → ratio=1.0, min=21
        var r = CoatingMath.ComputeMember(20, new double[] { 21, 22, 20, 23, 21 });

        Assert.True(r.Qualified);
        Assert.Equal(5, r.NQualifiedPoints);
        Assert.Equal(1.0, r.QualifiedRatio, precision: 9);
        Assert.Equal(20, r.MinThickness, precision: 9);
        Assert.Equal(17.0, r.LowerLimit, precision: 9);
        Assert.Null(r.FailReason);
    }

    [Fact]
    public void ComputeMember_合格率不达_最薄达标_不合格()
    {
        // design=20, lower=17；≥20 的只有 2/5=0.4 < 0.8（不达），但 min=18 ≥17（达）
        var r = CoatingMath.ComputeMember(20, new double[] { 18, 18, 18, 21, 22 });

        Assert.False(r.Qualified);
        Assert.False(r.RatioPass);
        Assert.True(r.MinPass);
        Assert.Equal(2, r.NQualifiedPoints);
        Assert.Contains("达标测点比例", r.FailReason);
        Assert.DoesNotContain("最薄处", r.FailReason);
    }

    [Fact]
    public void ComputeMember_合格率达标_最薄不达_不合格()
    {
        // design=20, lower=17；≥20 的 4/5=0.8（达），但 min=16 < 17（不达）
        var r = CoatingMath.ComputeMember(20, new double[] { 21, 21, 21, 21, 16 });

        Assert.False(r.Qualified);
        Assert.True(r.RatioPass);
        Assert.False(r.MinPass);
        Assert.Equal(16, r.MinThickness, precision: 9);
        Assert.Contains("最薄处", r.FailReason);
        Assert.DoesNotContain("达标测点比例", r.FailReason);
    }

    [Fact]
    public void ComputeMember_两者都不达_原因含两条()
    {
        // design=20, lower=17；≥20 的 1/5=0.2（不达），min=16 < 17（不达）
        var r = CoatingMath.ComputeMember(20, new double[] { 16, 16, 16, 21, 18 });

        Assert.False(r.Qualified);
        Assert.False(r.RatioPass);
        Assert.False(r.MinPass);
        Assert.Contains("达标测点比例", r.FailReason);
        Assert.Contains("最薄处", r.FailReason);
    }

    [Fact]
    public void ComputeMember_恰80百分比_且_恰85百分比下限_合格()
    {
        // 边界：design=20, lower=17；≥20 的 4/5=0.8（恰阈值），min=17（恰下限）
        var r = CoatingMath.ComputeMember(20, new double[] { 20, 20, 20, 20, 17 });

        Assert.True(r.Qualified);
        Assert.True(r.RatioPass);
        Assert.True(r.MinPass);
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
