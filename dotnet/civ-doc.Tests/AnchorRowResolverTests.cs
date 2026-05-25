// AnchorRowResolver 单测：每个 Key 的映射 + 用户输入兜底 + 未知 key 返 null。

using CivCore.Doc.Calc.Anchor;

namespace civ_doc.Tests;

public class AnchorRowResolverTests
{
    private static (AnchorRowInput Input, AnchorRowResult Result, AnchorParams Params) Sample()
    {
        var p = AnchorParams.Create(p: 100_000, lf: 5000, la: 8000, a: 314.0, e: 200_000);
        var d = new AnchorDisplacements(
            D01Nt: 0.10, D04Nt: 0.40, D07Nt: 0.70, D10Nt: 1.00,
            D12Nt1Min: 1.20, D12Nt3Min: 1.25, D12Nt5Min: 1.30,
            U10Nt: 1.05, U07Nt: 0.75, U04Nt: 0.45, U01Nt: 0.15);
        var input = AnchorRowInput.Create("P-01", d);
        var result = new AnchorRowResult(
            ElasticDisplacement: 1.15, LowerLimit: 0.72, UpperLimit: 2.59, Qualified: true);
        return (input, result, p);
    }

    [Fact]
    public void GetValue_AnchorParams字段_直接映射()
    {
        var (i, r, p) = Sample();
        var rv = new AnchorRowResolver(i, r, p);

        Assert.Equal(100_000.0, rv.GetValue("axial_design_load"));
        Assert.Equal(5000.0, rv.GetValue("free_length"));
        Assert.Equal(8000.0, rv.GetValue("anchor_length"));
        Assert.Equal(314.0, rv.GetValue("steel_area"));
        Assert.Equal(200_000.0, rv.GetValue("elastic_modulus"));
    }

    [Fact]
    public void GetValue_RowInput字段_含编号和11个位移()
    {
        var (i, r, p) = Sample();
        var rv = new AnchorRowResolver(i, r, p);

        Assert.Equal("P-01", rv.GetValue("anchor_id"));
        Assert.Equal(0.10, rv.GetValue("disp_01nt"));
        Assert.Equal(1.20, rv.GetValue("disp_12nt_1min"));
        Assert.Equal(0.15, rv.GetValue("disp_unload_01nt"));
    }

    [Fact]
    public void GetValue_RowResult字段_含判定结果()
    {
        var (i, r, p) = Sample();
        var rv = new AnchorRowResolver(i, r, p);

        Assert.Equal(1.15, rv.GetValue("elastic_displacement"));
        Assert.Equal(0.72, rv.GetValue("lower_limit"));
        Assert.Equal(2.59, rv.GetValue("upper_limit"));
        Assert.Equal("合格", rv.GetValue("judgement_result"));
    }

    [Fact]
    public void GetValue_判定不合格_返回不合格中文()
    {
        var (i, _, p) = Sample();
        var bad = new AnchorRowResult(1.15, 0.72, 2.59, Qualified: false);
        var rv = new AnchorRowResolver(i, bad, p);
        Assert.Equal("不合格", rv.GetValue("judgement_result"));
    }

    [Fact]
    public void GetValue_用户输入字段_从userInputs拿()
    {
        var (i, r, p) = Sample();
        var userInputs = new Dictionary<string, string>
        {
            ["client_name"] = "ABC 集团",
            ["test_date"] = "2026-05-25",
        };
        var rv = new AnchorRowResolver(i, r, p, userInputs);

        Assert.Equal("ABC 集团", rv.GetValue("client_name"));
        Assert.Equal("2026-05-25", rv.GetValue("test_date"));
    }

    [Fact]
    public void GetValue_未知key_返回null()
    {
        var (i, r, p) = Sample();
        var rv = new AnchorRowResolver(i, r, p);
        Assert.Null(rv.GetValue("totally_unknown_key"));
    }
}
