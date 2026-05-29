// 防火涂层厚度检测支持的规范清单 + 判定阈值。
//
// 当前只支持 GB 50205-2020《钢结构工程施工质量验收标准》§13.4.3（厚涂型防火涂料涂层厚度）。
// 判定阈值由该条文锁定，CoatingMath 不随规范扩展改动；未来加别的口径（如膨胀型 / GB/T 50621
// 现场评定）再追加常量 + 分支。

namespace CivCore.Doc.Calc.Coating;

public static class CoatingStandards
{
    public const string GB_50205_2020 = "GB 50205-2020";

    public static readonly string[] Supported = { GB_50205_2020 };

    /// <summary>合格率阈值：≥80% 测点 ≥ 设计厚度（"80% 面积满足耐火极限"）。</summary>
    public const double RatioThreshold = 0.80;

    /// <summary>最薄处系数：min(测点) ≥ 设计厚度 × 0.85。</summary>
    public const double MinFactor = 0.85;

    public static void Validate(string standard)
    {
        if (!Supported.Contains(standard))
            throw new ArgumentException(
                $"不支持的规范：{standard}（当前支持：{string.Join(", ", Supported)}）");
    }
}
