// LeebMath 核心算法测试 —— 跟 Python core/calc_functions.py 等价性验证。
//
// 测试值是手算 + 对照 Python `_LEEB_THICKNESS_DATA` / `_LEEB_ANGLE_RAW` 数据得来的，
// 同一组输入 C# 和 Python 必须算出完全相同的结果。

using CivCore.Doc.Calc.Leeb;
using CivCore.Doc.Standards;
using Xunit;

namespace CivCore.Doc.Tests;

public class LeebMathTests
{
    // ── LookupWithInterp（1D 查表 + 插值，对应 leeb_thickness）──────────

    [Fact]
    public void LookupWithInterp_精确命中_6mm_HLt_等于_30()
    {
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebThickness);
        var result = LeebMath.LookupWithInterp(rows, 6.0);
        Assert.Equal(30.0, result);
    }

    [Fact]
    public void LookupWithInterp_插值_6_5mm_应等于_26()
    {
        // Python _LEEB_THICKNESS_DATA: (6.0, 30) → (7.0, 22)，6.5 中点 = (30+22)/2 = 26
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebThickness);
        var result = LeebMath.LookupWithInterp(rows, 6.5);
        Assert.Equal(26.0, result, precision: 6);
    }

    [Fact]
    public void LookupWithInterp_插值_9mm_应等于_14()
    {
        // (8, 18) → (10, 10)，9 中点 = (18+10)/2 = 14
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebThickness);
        var result = LeebMath.LookupWithInterp(rows, 9.0);
        Assert.Equal(14.0, result, precision: 6);
    }

    [Fact]
    public void LookupWithInterp_12mm_精确命中_HLt_等于_0()
    {
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebThickness);
        var result = LeebMath.LookupWithInterp(rows, 12.0);
        Assert.Equal(0.0, result);
    }

    [Fact]
    public void LookupWithInterp_厚度_999mm_哨兵_HLt_等于_0()
    {
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebThickness);
        var result = LeebMath.LookupWithInterp(rows, 999.0);
        Assert.Equal(0.0, result);
    }

    [Fact]
    public void LookupWithInterp_厚度_5mm_越界_应抛异常()
    {
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebThickness);
        var ex = Assert.Throws<ArgumentException>(() =>
            LeebMath.LookupWithInterp(rows, 5.0));
        Assert.Contains("超出范围", ex.Message);
    }

    // ── Lookup2dFixedKey1InterpKey2（2D 查表，对应 leeb_angle）──────────

    [Fact]
    public void Lookup2d_角度0_HLm500_精确命中_HLa_等于_负10()
    {
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebAngle);
        var result = LeebMath.Lookup2dFixedKey1InterpKey2(
            rows, key1: 0.0, key2: 500.0, key1Label: "测量角度");
        Assert.Equal(-10.0, result);
    }

    [Fact]
    public void Lookup2d_角度0_HLm525_插值_HLa_等于_负95()
    {
        // (0°, 500, -10) → (0°, 550, -9)，525 中点 = -9.5
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebAngle);
        var result = LeebMath.Lookup2dFixedKey1InterpKey2(
            rows, key1: 0.0, key2: 525.0, key1Label: "测量角度");
        Assert.Equal(-9.5, result, precision: 6);
    }

    [Fact]
    public void Lookup2d_角度负90_HLm任意_基线档_HLa_全等于_0()
    {
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebAngle);
        var result = LeebMath.Lookup2dFixedKey1InterpKey2(
            rows, key1: -90.0, key2: 500.0, key1Label: "测量角度");
        Assert.Equal(0.0, result);
    }

    [Fact]
    public void Lookup2d_非法角度档60_应抛异常()
    {
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebAngle);
        var ex = Assert.Throws<ArgumentException>(() =>
            LeebMath.Lookup2dFixedKey1InterpKey2(
                rows, key1: 60.0, key2: 500.0, key1Label: "测量角度"));
        Assert.Contains("测量角度", ex.Message);
    }

    // ── TrimMeanLeeb（9 点截尾平均，对应 Python _trim_mean_leeb）──────────

    [Fact]
    public void TrimMeanLeeb_用户实数据_应等于_452()
    {
        // 用户给的 D 号站房 里氏硬度（钢梁）测区 1：第一行数据
        // 排序：[441, 444, 446, 451, 454, 454, 456, 457, 461]
        // 截尾：[446, 451, 454, 454, 456] mean = 2261/5 = 452.2 → 452
        var values = new[] { 454, 461, 446, 451, 441, 456, 457, 444, 454 };
        var result = LeebMath.TrimMeanLeeb(values);
        Assert.Equal(452, result);
    }

    [Fact]
    public void TrimMeanLeeb_全相同_9个450_应等于_450()
    {
        var values = Enumerable.Repeat(450, 9).ToArray();
        var result = LeebMath.TrimMeanLeeb(values);
        Assert.Equal(450, result);
    }

    [Fact]
    public void TrimMeanLeeb_等差数列_应等于_中位数5()
    {
        // [1..9]，截尾后 [3,4,5,6,7] mean=5
        var values = new[] { 1, 2, 3, 4, 5, 6, 7, 8, 9 };
        var result = LeebMath.TrimMeanLeeb(values);
        Assert.Equal(5, result);
    }

    [Fact]
    public void TrimMeanLeeb_四舍五入半数向上_应等于_5()
    {
        // 制造一个 mean 为 4.6（非整数）：剩 5 个值是 [4,4,5,5,5] mean=4.6 → 5
        // 整组：[1,2,4,4,5,5,5,9,9] 排序后 [1,2,4,4,5,5,5,9,9]
        // 截尾后 [4,4,5,5,5] → mean = 23/5 = 4.6 → round 5
        var values = new[] { 1, 2, 4, 4, 5, 5, 5, 9, 9 };
        var result = LeebMath.TrimMeanLeeb(values);
        Assert.Equal(5, result);
    }

    [Fact]
    public void TrimMeanLeeb_测点数不对_应抛异常()
    {
        Assert.Throws<ArgumentException>(() =>
            LeebMath.TrimMeanLeeb(new[] { 1, 2, 3, 4, 5 }));
    }
}
