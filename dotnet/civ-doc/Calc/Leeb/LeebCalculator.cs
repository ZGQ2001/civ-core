// 里氏硬度计算入口（对应 Python src/civ_core/core/calc_functions.py 的三层：
//   calc_leeb_hardness_steel    单构件
//   calc_leeb_hardness_batch    单批
//   calc_leeb_hardness_workbook 整文件
//
// 算法（INSP-001 / GB/T 50344-2019 附录 N）：
//   每测区:
//     hl_m         = TrimMeanLeeb(9 个原始 HL)
//     hl_t         = LookupWithInterp(thickness_table, 构件厚度)
//     hl_a         = Lookup2dFixedKey1InterpKey2(angle_table, 角度档, hl_m)
//     hl_corrected = hl_m + hl_t + hl_a
//     fb_min       = LookupWithInterp(strength_table, hl_corrected)
//     fb_max       = fb_min + 150
//   单构件聚合（§2）:
//     comp_fb_min_avg = avg(测区的 fb_min)
//     comp_fb_max_avg = avg(测区的 fb_max)
//     comp_fb_est     = (comp_fb_min_avg + comp_fb_max_avg) / 2
//   单批聚合（§3）:
//     batch_fb_char_avg = avg(批内构件的 comp_fb_min_avg)

using CivCore.Doc.Standards;

namespace CivCore.Doc.Calc.Leeb;

public static class LeebCalculator
{
    private const double LeebFbRange = 150.0;
    private static readonly HashSet<double> LeebValidAngles = new() { -90, -45, 0, 45, 90 };

    /// <summary>单构件里氏硬度计算（N 测区聚合）。</summary>
    public static LeebHardnessResult CalcSteel(
        int[][] testAreasRaw,
        double thickness,
        double angleDegrees,
        IReadOnlyList<StandardsRow> thicknessTable,
        IReadOnlyList<StandardsRow> angleTable,
        IReadOnlyList<StandardsRow> strengthTable)
    {
        if (testAreasRaw.Length == 0)
            throw new ArgumentException("至少需要 1 个测区（规范要求 ≥ 3）");
        if (!LeebValidAngles.Contains(angleDegrees))
            throw new ArgumentException(
                $"测量角度 {angleDegrees}° 不在规范允许档 {{-90, -45, 0, 45, 90}}");

        var areas = new LeebHardnessTestArea[testAreasRaw.Length];
        for (int i = 0; i < testAreasRaw.Length; i++)
        {
            var raw = testAreasRaw[i];
            int hlM = LeebMath.TrimMeanLeeb(raw);
            double hlT = LeebMath.LookupWithInterp(thicknessTable, thickness);
            double hlA = LeebMath.Lookup2dFixedKey1InterpKey2(
                angleTable, angleDegrees, hlM, key1Label: "测量角度");
            double hlCorrected = hlM + hlT + hlA;
            double fbMin = LeebMath.LookupWithInterp(strengthTable, hlCorrected);
            double fbMax = fbMin + LeebFbRange;
            areas[i] = LeebHardnessTestArea.Create(raw, hlM, hlT, hlA, hlCorrected, fbMin, fbMax);
        }

        // 构件级聚合
        double compFbMinAvg = areas.Average(a => a.FbMin);
        double compFbMaxAvg = areas.Average(a => a.FbMax);
        double compFbEst = (compFbMinAvg + compFbMaxAvg) / 2.0;
        double batchFbCharAvg = compFbMinAvg;  // 单构件场景

        return new LeebHardnessResult(
            TestAreas: areas,
            CompFbMinAvg: compFbMinAvg,
            CompFbMaxAvg: compFbMaxAvg,
            CompFbEst: compFbEst,
            BatchFbCharAvg: batchFbCharAvg
        );
    }

    /// <summary>单批多构件批级计算。</summary>
    public static LeebHardnessBatchResult CalcBatch(
        IReadOnlyList<LeebHardnessComponentInput> components,
        IReadOnlyList<StandardsRow> thicknessTable,
        IReadOnlyList<StandardsRow> angleTable,
        IReadOnlyList<StandardsRow> strengthTable)
    {
        if (components.Count == 0)
            throw new ArgumentException("批级计算至少需要 1 个构件");

        var pairs = new (LeebHardnessComponentInput, LeebHardnessResult)[components.Count];
        for (int i = 0; i < components.Count; i++)
        {
            var comp = components[i];
            var r = CalcSteel(
                comp.TestAreasRaw,
                comp.Thickness,
                comp.AngleDegrees,
                thicknessTable, angleTable, strengthTable);
            pairs[i] = (comp, r);
        }

        double batchFbCharAvg = pairs.Average(p => p.Item2.CompFbMinAvg);
        string batchName = components[0].BatchName;

        return new LeebHardnessBatchResult(
            BatchName: batchName,
            ComponentsWithResults: pairs,
            BatchFbCharAvg: batchFbCharAvg,
            NComponents: pairs.Length
        );
    }

    /// <summary>整文件多批计算入口。</summary>
    public static LeebHardnessWorkbookResult CalcWorkbook(
        LeebHardnessWorkbook workbook,
        StandardsDb db)
    {
        var thicknessTable = db.ReadAll(TableNames.LeebThickness);
        var angleTable = db.ReadAll(TableNames.LeebAngle);
        var strengthTable = db.ReadAll(TableNames.LeebStrength);

        var results = new LeebHardnessBatchResult[workbook.Batches.Length];
        for (int i = 0; i < workbook.Batches.Length; i++)
        {
            var batch = workbook.Batches[i];
            var br = CalcBatch(batch.Components, thicknessTable, angleTable, strengthTable);
            // 用 sheet 名（batch.BatchName）覆盖（确保与 sheet 一致，不依赖构件 BatchName）
            results[i] = br with { BatchName = batch.BatchName };
        }

        return new LeebHardnessWorkbookResult(
            BatchResults: results,
            NBatches: results.Length,
            NComponentsTotal: results.Sum(r => r.NComponents)
        );
    }
}
