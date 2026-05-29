// 防火涂层厚度判定核心公式（GB 50205-2020 §13.4.3 厚涂型防火涂料涂层厚度验收）。
//
//   合格率 = (实测 ≥ 设计厚度 的测点数) / 测点总数      "80% 面积满足耐火极限"
//   最薄处 = min(实测)
//   下限   = 设计厚度 × 0.85
//   合格 ⇔ 合格率 ≥ 80%  且  最薄处 ≥ 下限
//
// 用 ≥（闭区间）：恰 80%、恰 85% 判合格（规范"不应低于"= 允许等于）。

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

        int n = thicknesses.Count;
        int nQualified = thicknesses.Count(t => t >= designThickness);
        double ratio = (double)nQualified / n;
        double min = thicknesses.Min();
        double mean = thicknesses.Average();
        double lower = designThickness * CoatingStandards.MinFactor;

        bool ratioPass = ratio >= CoatingStandards.RatioThreshold;
        bool minPass = min >= lower;
        bool qualified = ratioPass && minPass;
        string? reason = qualified ? null : BuildFailReason(ratioPass, minPass, ratio, min, lower);

        return new CoatingMemberResult(
            n, nQualified, ratio, min, lower, mean, ratioPass, minPass, qualified, reason);
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
}
