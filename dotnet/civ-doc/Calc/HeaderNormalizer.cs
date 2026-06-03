// 列名归一化公共核心 —— 锚杆/防火/未来检测类型共用一份（"同一类型功能、不同内容、统一意识"）。
// 各检测类型如需额外步骤（如防火再剥尾部单位括注「(mm)」），在各自 *Columns.NormalizeHeader
// 里于本核心之上组合，不改本核心行为。原 AnchorColumns / CoatingColumns 各抄一份，现归并到此。

namespace CivCore.Doc.Calc;

public static class HeaderNormalizer
{
    /// <summary>列名归一化核心：trim + 全角括号/连字符→半角 + 去空格 + 小写。null → ""。</summary>
    public static string Core(string s)
    {
        if (s == null) return "";
        return s.Trim()
            .Replace('（', '(').Replace('）', ')')
            .Replace('–', '-').Replace('—', '-')
            .Replace(" ", "")
            .ToLowerInvariant();
    }
}
