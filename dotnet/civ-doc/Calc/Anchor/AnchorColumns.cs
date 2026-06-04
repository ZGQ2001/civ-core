// 锚杆输入 Excel 列名契约（GB 50086-2015）。
// 1 个 sheet 放所有锚杆，BatchIdColumn 区分批次。
//
// 列名容错：trim + 大小写不敏感；中英文括号差异由 NormalizeHeader 抹平。

namespace CivCore.Doc.Calc.Anchor;

public static class AnchorColumns
{
    public const string DefaultBatchIdColumn = "批次";
    public const string AnchorId = "锚杆编号";

    public const string D01 = "0.1Nt";
    public const string D04 = "0.4Nt";
    public const string D07 = "0.7Nt";
    public const string D10 = "1.0Nt";
    public const string D12_1Min = "1.2Nt-1min";
    public const string D12_3Min = "1.2Nt-3min";
    public const string D12_5Min = "1.2Nt-5min";
    public const string U10 = "卸载1.0Nt";
    public const string U07 = "卸载0.7Nt";
    public const string U04 = "卸载0.4Nt";
    public const string U01 = "卸载0.1Nt";

    /// <summary>11 个位移读数列，按加载-持荷-卸载顺序。</summary>
    public static readonly string[] DisplacementColumns =
    {
        D01, D04, D07, D10,
        D12_1Min, D12_3Min, D12_5Min,
        U10, U07, U04, U01,
    };

    /// <summary>列名归一化：共用 HeaderNormalizer.Core（trim + 括号/连字符归一 + 去空格 + 小写）。</summary>
    public static string NormalizeHeader(string s) => HeaderNormalizer.Core(s);
}
