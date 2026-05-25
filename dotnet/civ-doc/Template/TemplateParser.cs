// Word 模板解析器 —— 通用引擎层。
//
// 职责：读 docx → 定位锚点段落 [[数据绑定区]] → 找其后第一张 Table → 展开成 ParsedTable。
//
// 不知道的事：
//   - 字段是什么（FieldDef 由调用方提供）
//   - 模板存哪、要不要保存（这是 TemplateConfig 的事）
//   - RPC 协议（这是 TemplateHandlers 的事）
//
// 关键算法 —— OpenXML 合并单元格的展开规则：
//   横向合并：master cell 上有 <w:gridSpan w:val="N"/>，占视觉网格 N 列；
//             同一行的下一个 TableCell 起始列 = 当前列 + N（不是 +1）。
//   纵向合并：每行都有一个对应列的 TableCell；首行带 <w:vMerge w:val="restart"/>，
//             后续行的对应 TableCell 带 <w:vMerge/>（无 val 默认 "continue"），
//             内容可能为空。需要 lookahead 数下方有多少连续 continue 行得到 rowSpan。
//
// 签名（防模板被偷改）：rows:{N}_cols:{M}_hash:{前 100 格 InnerText 拼起来 MD5 前 6 位}。

using System.Security.Cryptography;
using System.Text;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace CivCore.Doc.Template;

/// <summary>模板解析的特定异常 —— 给上层 handler 翻译成 RPC -32602（参数错）。</summary>
public class TemplateParseException : Exception
{
    public TemplateParseException(string message) : base(message) { }
}

public static class TemplateParser
{
    /// <summary>模板锚点关键字 —— 用户在 docx 里目标表格前插入一段包含此文字的段落。</summary>
    public const string AnchorMarker = "[[数据绑定区]]";

    /// <summary>
    /// 解析 docx 模板：定位锚点 → 抓首张表 → 展开网格 → 算签名。
    /// </summary>
    /// <exception cref="TemplateParseException">文件缺失 / 锚点缺失 / 锚点后无表 / 表为空。</exception>
    public static ParsedTable Parse(string docxPath)
    {
        if (string.IsNullOrWhiteSpace(docxPath))
            throw new TemplateParseException("未指定 Word 模板文件路径");
        if (!File.Exists(docxPath))
            throw new TemplateParseException($"Word 模板文件不存在：{docxPath}");

        using var doc = WordprocessingDocument.Open(docxPath, false);
        var body = doc.MainDocumentPart?.Document?.Body
            ?? throw new TemplateParseException("Word 文件结构异常：缺少 MainDocumentPart 或 Body");

        // 1. 找含锚点关键字的段落（body 级别 —— 不深入表格内部）
        var anchorPara = body.Elements<Paragraph>()
            .FirstOrDefault(p => p.InnerText.Contains(AnchorMarker));
        if (anchorPara == null)
            throw new TemplateParseException(
                $"模板缺少锚点：请在目标表格前插入一段，内容含 {AnchorMarker}");

        // 2. 锚点段落之后的第一个 Table（body 直接子节点中）
        var table = anchorPara.ElementsAfter().OfType<Table>().FirstOrDefault()
            ?? throw new TemplateParseException(
                $"锚点 {AnchorMarker} 之后未找到表格，请把表格紧跟在该段落后面");

        // 3. 展开表格
        var rows = table.Elements<TableRow>().ToList();
        if (rows.Count == 0)
            throw new TemplateParseException("模板表格为空（没有行）");

        var result = new ParsedTable { RowCount = rows.Count };

        for (int r = 0; r < rows.Count; r++)
        {
            int c = 0;
            foreach (var cell in rows[r].Elements<TableCell>())
            {
                int gridSpan = GetGridSpan(cell);
                var vMergeKind = GetVMergeKind(cell);

                if (vMergeKind == VMergeKind.Continue)
                {
                    // 这个 TableCell 是纵向合并的延续 —— 不是主格，只占网格不显示
                    for (int dc = 0; dc < gridSpan; dc++) result.MarkHidden(r, c + dc);
                    c += gridSpan;
                    continue;
                }

                int rowSpan = vMergeKind == VMergeKind.Restart
                    ? CountVMergeContinuations(rows, r, c, gridSpan) + 1
                    : 1;

                result.PutCell(r, c, new ParsedCell
                {
                    Text = cell.InnerText,
                    RowSpan = rowSpan,
                    ColSpan = gridSpan,
                    Bold = cell.Descendants<Bold>().Any(),
                    FontSize = TryGetFontSize(cell),
                });

                // 主格内部的覆盖格全部标 hidden（左上角除外）
                for (int dr = 0; dr < rowSpan; dr++)
                    for (int dc = 0; dc < gridSpan; dc++)
                        if (dr != 0 || dc != 0)
                            result.MarkHidden(r + dr, c + dc);

                if (c + gridSpan > result.ColCount) result.ColCount = c + gridSpan;
                c += gridSpan;
            }
        }

        result.TableSignature = ComputeSignature(table, result.RowCount, result.ColCount);
        return result;
    }

    /// <summary>仅算签名，不展开 —— 给 ReportGenerator 做生成前校验用。</summary>
    public static string ComputeSignature(string docxPath)
    {
        var table = OpenAndFindTable(docxPath);
        var rows = table.Elements<TableRow>().Count();
        int cols = table.Elements<TableRow>().FirstOrDefault()
            ?.Elements<TableCell>().Sum(GetGridSpan) ?? 0;
        return ComputeSignature(table, rows, cols);
    }

    // ── 内部工具 ────────────────────────────────────────────

    private static Table OpenAndFindTable(string docxPath)
    {
        using var doc = WordprocessingDocument.Open(docxPath, false);
        var body = doc.MainDocumentPart?.Document?.Body
            ?? throw new TemplateParseException("Word 文件结构异常：缺少 Body");
        var anchorPara = body.Elements<Paragraph>()
            .FirstOrDefault(p => p.InnerText.Contains(AnchorMarker))
            ?? throw new TemplateParseException($"模板缺少锚点 {AnchorMarker}");
        return anchorPara.ElementsAfter().OfType<Table>().FirstOrDefault()
            ?? throw new TemplateParseException($"锚点 {AnchorMarker} 之后未找到表格");
    }

    private static string ComputeSignature(Table table, int rowCount, int colCount)
    {
        // 取前 100 个 TableCell 的 InnerText 拼接 → MD5 前 6 位（hex）
        var sb = new StringBuilder();
        foreach (var c in table.Descendants<TableCell>().Take(100))
            sb.Append(c.InnerText);
        var bytes = MD5.HashData(Encoding.UTF8.GetBytes(sb.ToString()));
        var hex = Convert.ToHexString(bytes).AsSpan(0, 6);
        return $"rows:{rowCount}_cols:{colCount}_hash:{hex.ToString()}";
    }

    private static int GetGridSpan(TableCell cell)
    {
        var v = cell.TableCellProperties?.GridSpan?.Val?.Value;
        return v.HasValue && v.Value > 0 ? v.Value : 1;
    }

    private enum VMergeKind { None, Restart, Continue }

    private static VMergeKind GetVMergeKind(TableCell cell)
    {
        var vm = cell.TableCellProperties?.VerticalMerge;
        if (vm == null) return VMergeKind.None;
        // OpenXML: val="restart" 显式标主格；无 val（默认）= continue
        var v = vm.Val?.Value;
        if (v == MergedCellValues.Restart) return VMergeKind.Restart;
        return VMergeKind.Continue;
    }

    /// <summary>从主格起向下数有多少连续 vMerge=continue 的行（gridCol 对齐）。</summary>
    private static int CountVMergeContinuations(
        List<TableRow> rows, int startRow, int gridCol, int gridSpan)
    {
        int count = 0;
        for (int r = startRow + 1; r < rows.Count; r++)
        {
            // 逐 cell 推进 gridCol 找对齐的格
            int c = 0;
            TableCell? aligned = null;
            foreach (var cell in rows[r].Elements<TableCell>())
            {
                int gs = GetGridSpan(cell);
                if (c == gridCol && gs == gridSpan) { aligned = cell; break; }
                if (c >= gridCol) break;
                c += gs;
            }
            if (aligned == null) return count;
            if (GetVMergeKind(aligned) != VMergeKind.Continue) return count;
            count++;
        }
        return count;
    }

    private static double? TryGetFontSize(TableCell cell)
    {
        // Word 用 half-points（21 = 10.5 磅），取第一个 Run 的 sz
        var sz = cell.Descendants<Run>()
            .Select(r => r.RunProperties?.FontSize?.Val?.Value)
            .FirstOrDefault(v => !string.IsNullOrEmpty(v));
        if (sz == null) return null;
        return double.TryParse(sz, out var hp) ? hp / 2.0 : null;
    }
}
