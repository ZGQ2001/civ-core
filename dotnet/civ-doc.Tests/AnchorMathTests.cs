// AnchorMath 单测 —— 黄金值来自 docs/civil_kb/formulas/test_pj/数据/数据.xlsx 第 2 行。
//
// xlsx 行 2：P=180000, Lf=500, La=7500, A=804.25, E=200000
//   位移读数（mm）= [0.56, 1.25, 1.96, 2.6, 2.61, 2.63, 2.65... wait
// 实际 xlsx data_only 读出：H2=2.63, L2=0.58, M2=2.05
//   Q = 0.9·180000·500 / (200000·804.25) = 0.503574...
//   R = (500 + 7500/3)·180000 / (200000·804.25) = 3000·180000/160850000 = 3.357165...
//   判定：0.504 < 2.05 < 3.357 → 合格

using CivCore.Doc.Calc.Anchor;
using Xunit;

namespace CivCore.Doc.Tests;

public class AnchorMathTests
{
    private static readonly AnchorParams DefaultParams =
        AnchorParams.Create(p: 180000, lf: 500, la: 7500, a: 804.25, e: 200000);

    [Fact]
    public void ComputeRow_xlsx_行2_弹性位移量_等于_2_05()
    {
        var d = new AnchorDisplacements(
            D01Nt: 0, D04Nt: 0.56, D07Nt: 1.25, D10Nt: 1.96,
            D12Nt1Min: 2.6, D12Nt3Min: 2.61, D12Nt5Min: 2.63,
            U10Nt: 2.35, U07Nt: 1.83, U04Nt: 1.21, U01Nt: 0.58);

        var r = AnchorMath.ComputeRow(d, DefaultParams);

        Assert.Equal(2.05, r.ElasticDisplacement, precision: 6);
    }

    [Fact]
    public void ComputeRow_下限_等于_0_5035747()
    {
        var d = new AnchorDisplacements(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        var r = AnchorMath.ComputeRow(d, DefaultParams);

        // 0.9·180000·500 / (200000·804.25) = 81000000 / 160850000
        Assert.Equal(81000000.0 / 160850000.0, r.LowerLimit, precision: 9);
    }

    [Fact]
    public void ComputeRow_上限_等于_3_3571651()
    {
        var d = new AnchorDisplacements(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        var r = AnchorMath.ComputeRow(d, DefaultParams);

        // (500 + 7500/3)·180000 / (200000·804.25) = 540000000 / 160850000
        Assert.Equal(540000000.0 / 160850000.0, r.UpperLimit, precision: 9);
    }

    [Fact]
    public void ComputeRow_xlsx_行2_应判定为合格()
    {
        var d = new AnchorDisplacements(
            0, 0.56, 1.25, 1.96, 2.6, 2.61, 2.63, 2.35, 1.83, 1.21, 0.58);
        var r = AnchorMath.ComputeRow(d, DefaultParams);

        Assert.True(r.Qualified);
    }

    [Fact]
    public void ComputeRow_M_小于等于下限_应判不合格()
    {
        // M = H - L 太小（弹性段没充分发挥）→ 不合格
        var d = new AnchorDisplacements(
            0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.5, 0.4, 0.3, 0.2);
        var r = AnchorMath.ComputeRow(d, DefaultParams);

        Assert.Equal(0.4, r.ElasticDisplacement, precision: 6);
        Assert.False(r.Qualified);  // 0.4 < Q≈0.504
    }

    [Fact]
    public void ComputeRow_M_大于等于上限_应判不合格()
    {
        // M 超过上限（自由段+1/3锚固段已全屈服）→ 不合格
        var d = new AnchorDisplacements(
            0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 3.5, 3.0, 2.0, 0.5);
        var r = AnchorMath.ComputeRow(d, DefaultParams);

        Assert.Equal(3.5, r.ElasticDisplacement, precision: 6);
        Assert.False(r.Qualified);  // 3.5 > R≈3.357
    }

    [Fact]
    public void ComputeRow_M_恰等于下限_开区间_应判不合格()
    {
        // 沿用 xlsx 的 IF(AND(M>Q, M<R)) 开区间语义：M == Q 时不合格
        var q = 0.9 * 180000 * 500 / (200000 * 804.25);
        var d = new AnchorDisplacements(
            0, 0, 0, 0, 0, 0, q, 0, 0, 0, 0);  // M = q - 0 = q
        var r = AnchorMath.ComputeRow(d, DefaultParams);

        Assert.Equal(q, r.ElasticDisplacement, precision: 9);
        Assert.False(r.Qualified);
    }
}
