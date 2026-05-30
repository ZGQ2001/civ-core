// 防火涂层厚度检测支持的规范/地标清单 + 涂层类型分级 + 判定阈值/精度。
//
// 判定按涂层类型各遵各规范（GB 50205-2020 §13.4.3）：
//   厚涂型 —— ≥80% 测点 ≥ 设计 且 最薄处 ≥ 设计 × 0.85。
//   膨胀型（薄涂型/超薄型）—— 构件均值 ≥ 设计 × 0.95（偏差 −5%），且 ≥ 设计 − 0.2mm（−200µm 兜底）。
// 地标改截面间距（北京地标每 1m 一截面 vs 国标每 3m）；国标膨胀型按 5 处×3 点布点（参照 GB/T 50621 §12），
// 地标膨胀型仍按截面布点（截面数同厚型）—— 布点差异在 CoatingTemplateExpander 处理，不影响本类判定阈值。

namespace CivCore.Doc.Calc.Coating;

public static class CoatingStandards
{
    /// <summary>国标：GB 50205-2020，截面间距 3m。</summary>
    public const string GB_50205_2020 = "GB 50205-2020";

    /// <summary>北京地标：截面间距 1m（薄/超薄判定口径待原文，本轮只改间距）。</summary>
    public const string BeijingLocal = "北京地标";

    public static readonly string[] Supported = { GB_50205_2020, BeijingLocal };

    // ── 厚型验收阈值（GB 50205-2020 §13.4.3，不随地标变）──
    /// <summary>合格率阈值：≥80% 测点 ≥ 设计厚度（"80% 面积满足耐火极限"）。</summary>
    public const double RatioThreshold = 0.80;
    /// <summary>最薄处系数：min(测点) ≥ 设计厚度 × 0.85。</summary>
    public const double MinFactor = 0.85;

    // ── 膨胀型（薄涂型/超薄型）验收阈值（GB 50205-2020 §13.4.3，不随地标变）──
    /// <summary>均值下限系数：构件均值 ≥ 设计厚度 × 0.95（偏差 −5%）。</summary>
    public const double ExpansionMeanFactor = 0.95;
    /// <summary>绝对偏差兜底：构件均值 ≥ 设计厚度 − 0.2mm（−200µm）。与 −5% 同时成立，取较严者。</summary>
    public const double AbsoluteFloorMm = 0.2;

    // ── 涂层类型分级阈值（按设计厚度 mm，用户拍板）──
    /// <summary>≥7mm 为厚型。</summary>
    public const double ThickMinThickness = 7.0;
    /// <summary>≤3mm 为超薄型；(3, 7) 为薄型。</summary>
    public const double UltraThinMaxThickness = 3.0;

    public static void Validate(string standard)
    {
        if (!Supported.Contains(standard))
            throw new ArgumentException(
                $"不支持的规范：{standard}（当前支持：{string.Join(", ", Supported)}）");
    }

    /// <summary>截面间距（m）：国标每 3m 一截面，北京地标每 1m 一截面。</summary>
    public static double Spacing(string standard) => standard == BeijingLocal ? 1.0 : 3.0;

    /// <summary>按设计厚度分级涂层类型：≥7 厚型 / (3,7) 薄型 / ≤3 超薄型。</summary>
    public static CoatingCategory Classify(double designThickness)
        => designThickness >= ThickMinThickness ? CoatingCategory.厚型
        : designThickness <= UltraThinMaxThickness ? CoatingCategory.超薄型
        : CoatingCategory.薄型;

    /// <summary>是否膨胀型（薄涂型/超薄型）—— 走「构件均值 ≥ 设计×0.95」判定 + 国标 5 处×3 点布点。</summary>
    public static bool IsExpansion(CoatingCategory category)
        => category is CoatingCategory.薄型 or CoatingCategory.超薄型;

    /// <summary>厚度显示小数位：厚型 2 位（游标卡尺）、薄型/超薄型 3 位（涂层测厚仪）。</summary>
    public static int ThicknessDecimals(CoatingCategory category)
        => category == CoatingCategory.厚型 ? 2 : 3;
}
