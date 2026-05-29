// 防火涂层厚度输入 Excel 列名契约（GB 50205-2020 厚涂型验收）。
//
// 长表格式：每行一个测点。1 个 sheet 放所有构件，按「批次」+「构件位置」分组，
// 同一构件的多个测点（跨截面、跨面）排成多行。设计厚度按构件填（同构件各行一致）。
//
// 列名容错：trim + 大小写不敏感；中英文括号差异由 NormalizeHeader 抹平
// （与 AnchorColumns.NormalizeHeader 同口径）。

namespace CivCore.Doc.Calc.Coating;

public static class CoatingColumns
{
    public const string DefaultBatchIdColumn = "批次";
    public const string MemberLocation = "构件位置";
    public const string MemberType = "构件类型";
    public const string DesignThickness = "设计厚度";
    public const string SectionNo = "截面号";
    public const string PointPosition = "测点位置";
    public const string MeasuredThickness = "实测厚度";

    /// <summary>除「批次」外的数据列（reader 必需）。</summary>
    public static readonly string[] DataColumns =
    {
        MemberLocation, MemberType, DesignThickness,
        SectionNo, PointPosition, MeasuredThickness,
    };

    /// <summary>列名归一化：trim + 全角括号/连字符替换 + 小写比较用。</summary>
    public static string NormalizeHeader(string s)
    {
        if (s == null) return "";
        return s.Trim()
            .Replace('（', '(').Replace('）', ')')
            .Replace('–', '-').Replace('—', '-')
            .Replace(" ", "")
            .ToLowerInvariant();
    }
}
