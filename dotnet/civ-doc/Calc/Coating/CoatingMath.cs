// 防火涂层厚度判定核心（GB 50205-2020 §13.4.3 防火涂料涂层厚度验收）。
//
//   涂层类型按设计厚度分级（CoatingStandards.Classify）：厚型 / 薄型 / 超薄型。
//   厚型判定：合格率 = (实测 ≥ 设计厚度 的测点数)/总数 ≥ 80%  且  最薄处 ≥ 设计 × 0.85
//             两者都满足 → 合格（≥ 闭区间，恰 80%/85% 判合格）。
//   膨胀型（薄型/超薄型）判定：构件均值 ≥ max(设计 × 0.95, 设计 − 0.2mm)
//             即偏差 ≥ −5% 且 ≥ −200µm（两条同时成立，取较严下限）。
//
// 判定按原始值算（不先四舍五入）；显示精度由 CoatingStandards.ThicknessDecimals 控制（在报告表里 round）。

namespace CivCore.Doc.Calc.Coating;

public static class CoatingMath
{
    /// <summary>按一个构件的所有测点厚度 + 设计厚度算判定结果。</summary>
    public static CoatingMemberResult ComputeMember(double designThickness, IReadOnlyList<double> thicknesses)
    {
        if (thicknesses == null || thicknesses.Count == 0)
            throw new ArgumentException("测点厚度列表为空");
        if (designThickness <= 0)
            throw new ArgumentException($"设计厚度必须 > 0，得到 {designThickness}");

        var category = CoatingStandards.Classify(designThickness);

        int n = thicknesses.Count;
        int nQualified = thicknesses.Count(t => t >= designThickness);
        double ratio = (double)nQualified / n;
        double min = thicknesses.Min();
        double mean = thicknesses.Average();
        double lower = designThickness * CoatingStandards.MinFactor;

        bool ratioPass = ratio >= CoatingStandards.RatioThreshold;
        bool minPass = min >= lower;

        // 膨胀型均值下限 = max(设计×0.95, 设计−0.2)；厚型不适用，置 0/true 占位。
        double meanLower = 0;
        bool meanPass = true;

        CoatingVerdict verdict;
        string? reason = null;
        if (CoatingStandards.IsExpansion(category))
        {
            meanLower = Math.Max(
                designThickness * CoatingStandards.ExpansionMeanFactor,
                designThickness - CoatingStandards.AbsoluteFloorMm);
            meanPass = mean >= meanLower;
            verdict = meanPass ? CoatingVerdict.合格 : CoatingVerdict.不合格;
            if (!meanPass) reason = BuildExpansionFailReason(designThickness, mean, meanLower);
        }
        else
        {
            bool qualified = ratioPass && minPass;
            verdict = qualified ? CoatingVerdict.合格 : CoatingVerdict.不合格;
            if (!qualified) reason = BuildFailReason(ratioPass, minPass, ratio, min, lower);
        }

        return new CoatingMemberResult(
            category, n, nQualified, ratio, min, lower, mean, ratioPass, minPass,
            meanLower, meanPass, verdict, reason);
    }

    private static string BuildFailReason(
        bool ratioPass, bool minPass, double ratio, double min, double lower)
    {
        var parts = new List<string>();
        if (!ratioPass)
            parts.Add($"达标测点比例 {ratio * 100:F1}% < {CoatingStandards.RatioThreshold * 100:F0}%");
        if (!minPass)
            parts.Add($"最薄处 {min:F2}mm < 下限 {lower:F2}mm（设计×{CoatingStandards.MinFactor:F2}）");
        return string.Join("；", parts);
    }

    private static string BuildExpansionFailReason(double design, double mean, double meanLower)
    {
        double byFactor = design * CoatingStandards.ExpansionMeanFactor;
        double byFloor = design - CoatingStandards.AbsoluteFloorMm;
        return $"构件均值 {mean:F3}mm < 下限 {meanLower:F3}mm"
            + $"（设计×{CoatingStandards.ExpansionMeanFactor:F2}={byFactor:F3}，"
            + $"−{CoatingStandards.AbsoluteFloorMm * 1000:F0}µm 兜底={byFloor:F3}，取较严者）";
    }
}
