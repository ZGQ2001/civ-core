// 防火涂层厚度检测数据契约（GB 50205-2020 §13.4.3 厚涂型验收）。
//
// 三层结构：构件 → 截面（沿长度每 3m[国标]/1m[北京地标] 一个）→ 截面内测点
// （钢梁 3 点：两侧面 + 底面；钢柱 4 点：东/西/南/北侧面）。
// 判定按「构件」聚合：合格率 ≥ 80% 且 最薄处 ≥ 设计 × 85%。
//
// 单位统一 mm（计算 + 报告同单位）。

namespace CivCore.Doc.Calc.Coating;

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
    string MemberType,       // 构件类型（梁/柱…，信息性）
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

/// <summary>单构件结果。FailReason 在不合格时写清哪条没过（"程序不能是黑盒"）。</summary>
public record CoatingMemberResult(
    int NPoints,             // 测点总数
    int NQualifiedPoints,    // ≥ 设计厚度的测点数
    double QualifiedRatio,   // 合格率
    double MinThickness,     // 最薄处
    double LowerLimit,       // 下限 = 设计 × 0.85
    double MeanThickness,    // 构件总均值（宽表「平均值」列用）
    bool RatioPass,          // 合格率 ≥ 80%
    bool MinPass,            // 最薄 ≥ 下限
    bool Qualified,          // 两者皆满足
    string? FailReason       // 不合格原因（合格时为 null）
);

/// <summary>单批输入（同一批次的所有构件）。</summary>
public record CoatingBatchInput(string BatchId, CoatingMemberInput[] Members);

/// <summary>单批结果。</summary>
public record CoatingBatchResult(
    string BatchId,
    (CoatingMemberInput Input, CoatingMemberResult Result)[] MembersWithResults,
    int NQualified,
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
    int NQualifiedTotal
);
