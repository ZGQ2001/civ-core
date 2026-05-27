// "1-3,5,7-9" → 0-based 半开区间 [(start, end), ...]。
//
// 与 src/civ_core/infra_io/pdf_io.py: parse_page_ranges 对齐：
//   • 1-based 输入 → 0-based 半开输出（PdfSharp 切片用）
//   • 1 <= start <= end <= totalPages 校验
//   • 空 expr / 多余逗号 / 颠倒区间 / 非法 token 全部报错
//
// 单页 "5" 等同 "5-5" → (4, 5)；范围 "1-3" → (0, 3)。

using System.Text.RegularExpressions;

namespace CivCore.Doc.Pdf;

public static class PageRangeParser
{
    private static readonly Regex TokenRx =
        new(@"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$", RegexOptions.Compiled);

    public record Range(int StartIndex, int EndIndex)
    {
        /// <summary>1-based 起始页号（包含）。</summary>
        public int Start1 => StartIndex + 1;
        /// <summary>1-based 结束页号（包含）。EndIndex 是半开 → end_1based = EndIndex。</summary>
        public int End1 => EndIndex;
    }

    public static List<Range> Parse(string expr, int totalPages)
    {
        if (totalPages <= 0)
            throw new ArgumentException("PDF 没有任何页可供拆分（请确认输入 PDF 至少 1 页）");
        if (string.IsNullOrWhiteSpace(expr))
            throw new ArgumentException(
                "页号表达式不能为空。示例：\"1-3,5,7-9\" 代表三段：1~3 页、第 5 页、7~9 页");

        var ranges = new List<Range>();
        foreach (var raw in expr.Split(','))
        {
            var token = raw.Trim();
            if (string.IsNullOrEmpty(token))
                throw new ArgumentException($"页号表达式中有空项（多余逗号？）：'{expr}'");

            var m = TokenRx.Match(token);
            if (!m.Success)
                throw new ArgumentException(
                    $"无法解析的页号片段：'{token}'。合法格式：单页 '5' 或范围 '1-3'，多段用逗号分隔");

            int start = int.Parse(m.Groups[1].Value);
            int end = m.Groups[2].Success ? int.Parse(m.Groups[2].Value) : start;
            if (start < 1 || end < 1)
                throw new ArgumentException($"页号必须 >= 1（PDF 页号从 1 开始）：'{token}'");
            if (start > totalPages || end > totalPages)
                throw new ArgumentException($"页号超过 PDF 总页数 {totalPages}：'{token}'");
            if (start > end)
                throw new ArgumentException($"范围起止颠倒（{start} > {end}）：'{token}'。范围必须是「小-大」");

            ranges.Add(new Range(start - 1, end));
        }
        return ranges;
    }
}
