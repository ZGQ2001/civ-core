// LeebCalculator 端到端等价性测试 —— 跟 Python core/calc_functions.calc_leeb_hardness_steel
// 同样输入跑出完全相同结果。
//
// 黄金值由 Python 端用真实 ~/.civ-core/standards.db 跑出（_compute_leeb_golden.py 临时脚本）。
// 输入：钢柱A-1 厚度 12mm 角度 0° 3 测区 9 HL（来自 test_leeb_excel.py 合成数据）。

using CivCore.Doc.Calc.Leeb;
using CivCore.Doc.Standards;
using Xunit;

namespace CivCore.Doc.Tests;

public class LeebCalculatorTests
{
    private static readonly int[][] SampleTestAreas = new int[][]
    {
        new[] { 467, 465, 471, 468, 467, 468, 473, 472, 463 },
        new[] { 471, 478, 471, 470, 480, 477, 472, 475, 465 },
        new[] { 477, 481, 468, 469, 478, 470, 469, 476, 462 },
    };

    private (List<StandardsRow> thickness, List<StandardsRow> angle, List<StandardsRow> strength)
        LoadTables()
    {
        using var db = StandardsDb.OpenDefault();
        return (
            db.ReadAll(TableNames.LeebThickness),
            db.ReadAll(TableNames.LeebAngle),
            db.ReadAll(TableNames.LeebStrength)
        );
    }

    [Fact]
    public void CalcSteel_钢柱A_1_测区1_HLm_应等于_468()
    {
        // Python: 截尾 [467,465,471,468,467,468,473,472,463] 排序 [463,465,467,467,468,468,471,472,473]
        // 截尾后中间 5 个 [467,467,468,468,471] 平均 = 2341/5 = 468.2 → 468
        var (thicknessTable, angleTable, strengthTable) = LoadTables();
        var result = LeebCalculator.CalcSteel(
            SampleTestAreas, thickness: 12.0, angleDegrees: 0.0,
            thicknessTable, angleTable, strengthTable);

        Assert.Equal(468, result.TestAreas[0].HlM);
        Assert.Equal(473, result.TestAreas[1].HlM);
        Assert.Equal(472, result.TestAreas[2].HlM);
    }

    [Fact]
    public void CalcSteel_厚度12mm_HLt_应全等于_0_精确命中()
    {
        var (thicknessTable, angleTable, strengthTable) = LoadTables();
        var result = LeebCalculator.CalcSteel(
            SampleTestAreas, thickness: 12.0, angleDegrees: 0.0,
            thicknessTable, angleTable, strengthTable);

        foreach (var area in result.TestAreas)
            Assert.Equal(0.0, area.HlT);
    }

    [Fact]
    public void CalcSteel_角度0_HLa_应全等于_负10_插值匹配()
    {
        var (thicknessTable, angleTable, strengthTable) = LoadTables();
        var result = LeebCalculator.CalcSteel(
            SampleTestAreas, thickness: 12.0, angleDegrees: 0.0,
            thicknessTable, angleTable, strengthTable);

        // HL_m = 468/473/472 在 (450, -10) 和 (500, -10) 区间内，插值都是 -10
        foreach (var area in result.TestAreas)
            Assert.Equal(-10.0, area.HlA, precision: 6);
    }

    [Fact]
    public void CalcSteel_HL_corrected_应等于_458_463_462()
    {
        var (thicknessTable, angleTable, strengthTable) = LoadTables();
        var result = LeebCalculator.CalcSteel(
            SampleTestAreas, thickness: 12.0, angleDegrees: 0.0,
            thicknessTable, angleTable, strengthTable);

        // hl_m + 0 + (-10) = 458 / 463 / 462
        Assert.Equal(458.0, result.TestAreas[0].HlCorrected);
        Assert.Equal(463.0, result.TestAreas[1].HlCorrected);
        Assert.Equal(462.0, result.TestAreas[2].HlCorrected);
    }

    [Fact]
    public void CalcSteel_fb_min_应等于_Python黄金值_506_516_514()
    {
        // Python 黄金值（_compute_leeb_golden.py 跑出）：
        //   HL_corrected 458 → fb_min 506
        //   HL_corrected 463 → fb_min 516
        //   HL_corrected 462 → fb_min 514
        var (thicknessTable, angleTable, strengthTable) = LoadTables();
        var result = LeebCalculator.CalcSteel(
            SampleTestAreas, thickness: 12.0, angleDegrees: 0.0,
            thicknessTable, angleTable, strengthTable);

        Assert.Equal(506.0, result.TestAreas[0].FbMin, precision: 6);
        Assert.Equal(516.0, result.TestAreas[1].FbMin, precision: 6);
        Assert.Equal(514.0, result.TestAreas[2].FbMin, precision: 6);
    }

    [Fact]
    public void CalcSteel_构件聚合_comp_fb_min_avg_应等于_Python黄金值_512()
    {
        var (thicknessTable, angleTable, strengthTable) = LoadTables();
        var result = LeebCalculator.CalcSteel(
            SampleTestAreas, thickness: 12.0, angleDegrees: 0.0,
            thicknessTable, angleTable, strengthTable);

        // Python 黄金值：comp_fb_min_avg = 512.0, comp_fb_max_avg = 662.0, comp_fb_est = 587.0
        Assert.Equal(512.0, result.CompFbMinAvg, precision: 6);
        Assert.Equal(662.0, result.CompFbMaxAvg, precision: 6);
        Assert.Equal(587.0, result.CompFbEst, precision: 6);
        Assert.Equal(512.0, result.BatchFbCharAvg, precision: 6);  // 单构件场景 = comp_fb_min_avg
    }

    [Fact]
    public void CalcSteel_非法角度档_应抛异常()
    {
        var (thicknessTable, angleTable, strengthTable) = LoadTables();
        Assert.Throws<ArgumentException>(() =>
            LeebCalculator.CalcSteel(
                SampleTestAreas, thickness: 12.0, angleDegrees: 30.0,
                thicknessTable, angleTable, strengthTable));
    }

    [Fact]
    public void CalcBatch_单构件_批级特征值平均_应等于_构件特征值平均()
    {
        var (thicknessTable, angleTable, strengthTable) = LoadTables();
        var comp = LeebHardnessComponentInput.Create(
            seq: 1, name: "钢柱A-1", thickness: 12.0, angleDegrees: 0.0,
            testAreasRaw: SampleTestAreas, batchName: "测试批");

        var batchResult = LeebCalculator.CalcBatch(
            new[] { comp }, thicknessTable, angleTable, strengthTable);

        Assert.Equal(1, batchResult.NComponents);
        Assert.Equal(512.0, batchResult.BatchFbCharAvg, precision: 6);
        Assert.Equal("测试批", batchResult.BatchName);
    }
}
