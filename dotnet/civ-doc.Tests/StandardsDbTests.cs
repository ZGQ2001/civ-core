// StandardsDb 读取测试：用 ~/.civ-core/standards.db（Python 端已 seed 过）验证 C# 读出与
// Python 一致。
//
// 期望行数（来自 Python src/civ_core/infra_io/standards_db.py 的 seed 函数）：
//   leeb_thickness_correction: 6 行（5 真实数据 + 1 哨兵）
//   leeb_angle_correction:     70 行（5 角度档 × 14 HL_m）
//   leeb_strength_conversion: 100 行（HL_dm 255~480）

using CivCore.Doc.Standards;
using Xunit;

namespace CivCore.Doc.Tests;

public class StandardsDbTests
{
    [Fact]
    public void OpenDefault_应该能打开用户家目录下的_standards_db()
    {
        // 测试假设 Python 端已经跑过 init_standards_db / healthcheck，db 文件存在。
        using var db = StandardsDb.OpenDefault();
        // 能打开就是成功；不抛 FileNotFoundException
        Assert.NotNull(db);
    }

    [Fact]
    public void LeebThicknessCorrection_应该返回_6_行()
    {
        using var db = StandardsDb.OpenDefault();
        var count = db.CountRows(TableNames.LeebThickness);
        Assert.Equal(6, count);
    }

    [Fact]
    public void LeebAngleCorrection_应该返回_70_行()
    {
        using var db = StandardsDb.OpenDefault();
        var count = db.CountRows(TableNames.LeebAngle);
        Assert.Equal(70, count);
    }

    [Fact]
    public void LeebStrengthConversion_应该返回_100_行()
    {
        using var db = StandardsDb.OpenDefault();
        var count = db.CountRows(TableNames.LeebStrength);
        Assert.Equal(100, count);
    }

    [Fact]
    public void LeebThickness_读出_6mm_应该是_30_点_HLt_修正值()
    {
        // 来自 Python _LEEB_THICKNESS_DATA：(6.0, 30.0) 是表的第一行
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebThickness);
        Assert.NotEmpty(rows);

        var row6mm = rows.Find(r => r.Key1 == 6.0);
        Assert.NotNull(row6mm);
        Assert.Equal(30.0, row6mm!.Value1);
        Assert.Null(row6mm.Key2);  // 1D 表
    }

    [Fact]
    public void LeebAngle_读出_角度档_0_HLm_500_应该是_负10()
    {
        // 来自 Python _LEEB_ANGLE_RAW: HL_m=500, 0° → HL_a=-10
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebAngle);
        Assert.NotEmpty(rows);

        var row = rows.Find(r => r.Key1 == 0.0 && r.Key2 == 500.0);
        Assert.NotNull(row);
        Assert.Equal(-10.0, row!.Value1);
    }

    [Fact]
    public void LeebStrength_读出_HL_400_应该是_407()
    {
        // 来自 Python _LEEB_STRENGTH_DATA: (400.0, 407.0)
        using var db = StandardsDb.OpenDefault();
        var rows = db.ReadAll(TableNames.LeebStrength);
        Assert.NotEmpty(rows);

        var row = rows.Find(r => r.Key1 == 400.0);
        Assert.NotNull(row);
        Assert.Equal(407.0, row!.Value1);
    }
}
