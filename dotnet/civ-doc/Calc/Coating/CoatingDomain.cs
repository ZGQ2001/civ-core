// 防火涂层厚度检测数据契约（GB 50205-2020 §13.4.3 厚涂型验收）。
//
// 两个维度：
//   - 构件类型（梁/柱…）：决定每截面测点面数 + 面名（来自「类型预设」）。
//   - 涂层类型（厚型/薄型/超薄型）：按设计厚度自动分级，决定判定口径 + 显示精度。
//
// 三层结构：构件 → 截面（沿长度每 3m[国标]/1m[北京地标]）→ 截面内测点。
// 判定按「构件」聚合；本轮只厚型出合格/不合格，薄型/超薄型 Verdict=待判定。单位统一 mm。

namespace CivCore.Doc.Calc.Coating;

/// <summary>涂层类型（按设计厚度分级）。</summary>
public enum CoatingCategory
{
    厚型,
    薄型,
    超薄型,
}

/// <summary>构件判定结论。薄型/超薄型本轮不出判定 → 待判定。</summary>
public enum CoatingVerdict
{
    合格,
    不合格,
    待判定,
}

/// <summary>单个测点 = 一个截面上的一个面。</summary>
public record CoatingPoint(int SectionNo, string Position, double Thickness)
{
    public static CoatingPoint Create(int sectionNo, string position, double thickness)
    {
        if (thickness < 0)
            throw new ArgumentException($"实测厚度不可为负，得到 {thickness}");
        return new CoatingPoint(sectionNo, position ?? "", thickness);
    }
}

/// <summary>单构件输入：一个构件的所有测点 + 设计厚度（同构件共享）。</summary>
public record CoatingMemberInput(
    string Location,         // 构件位置
    string MemberType,       // 构件类型（梁/柱，定测点面数）
    double DesignThickness,  // 设计厚度 (mm)
    CoatingPoint[] Points    // 所有测点（跨截面、跨面）
)
{
    public static CoatingMemberInput Create(
        string location, string memberType, double designThickness, CoatingPoint[] points)
    {
        if (string.IsNullOrWhiteSpace(location))
            throw new ArgumentException("构件位置不可为空");
        if (designThickness <= 0)
            throw new ArgumentException($"构件「{location}」设计厚度必须 > 0，得到 {designThickness}");
        if (points == null || points.Length == 0)
            throw new ArgumentException($"构件「{location}」至少要有一个测点");
        return new CoatingMemberInput(location, memberType ?? "", designThickness, points);
    }
}

/// <summary>单构件结果。厚型走合格率+最薄；膨胀型（薄/超薄）走构件均值；不合格时 FailReason 写清哪条没过（"程序不能是黑盒"）。</summary>
public record CoatingMemberResult(
    CoatingCategory Category, // 涂层类型（厚/薄/超薄）
    int NPoints,              // 测点总数
    int NQualifiedPoints,     // ≥ 设计厚度的测点数（厚型用）
    double QualifiedRatio,    // 合格率（厚型用）
    double MinThickness,      // 最薄处
    double LowerLimit,        // 下限 = 设计 × 0.85（厚型用）
    double MeanThickness,     // 构件总均值
    bool RatioPass,           // 合格率 ≥ 80%（厚型用）
    bool MinPass,             // 最薄 ≥ 下限（厚型用）
    double MeanLowerLimit,    // 均值下限 = max(设计×0.95, 设计−0.2)（膨胀型用；厚型置 0）
    bool MeanPass,            // 构件均值 ≥ 均值下限（膨胀型用；厚型置 true 占位）
    CoatingVerdict Verdict,   // 合格 / 不合格 / 待判定
    string? FailReason        // 不合格原因（合格/待判定时为 null）
);

/// <summary>单批输入（同一批次的所有构件）。</summary>
public record CoatingBatchInput(string BatchId, CoatingMemberInput[] Members);

/// <summary>单批结果。NQualified=合格构件数，NPending=待判定（薄/超薄）构件数。</summary>
public record CoatingBatchResult(
    string BatchId,
    (CoatingMemberInput Input, CoatingMemberResult Result)[] MembersWithResults,
    int NQualified,
    int NPending,
    int NTotal
);

/// <summary>整文件输入（含规范 + 多批）。</summary>
public record CoatingWorkbookInput(string Standard, CoatingBatchInput[] Batches);

/// <summary>整文件结果。</summary>
public record CoatingWorkbookResult(
    string Standard,
    CoatingBatchResult[] BatchResults,
    int NBatches,
    int NMembersTotal,
    int NQualifiedTotal,
    int NPendingTotal
);

// ── 模板展开用的轻量录入契约（「类型预设」+「构件清单」→「测点数据」）──

/// <summary>「类型预设」一行：构件类型 → 测点面布置 + 默认设计厚度。</summary>
public record CoatingTypePreset(string MemberType, string[] PointPositions, double? DefaultDesignThickness);

/// <summary>「构件清单」一行（原始录入，未解析）。空字段在 expander 里按规则解析。</summary>
public record CoatingMemberSpec(
    string BatchId,
    string Location,
    string? MemberType,
    double? LengthM,
    int? SectionCount,
    double? DesignThickness
);
