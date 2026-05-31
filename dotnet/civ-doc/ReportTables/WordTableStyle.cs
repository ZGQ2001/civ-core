// 报告 Word 表的共用样式 helper —— 宋体+Times New Roman、五号、细实线边框、居中。
//
// 防火涂层表(CoatingWordTable)、锚杆表(AnchorWordTable)、装配引擎(DocxReportAssembler)
// 三处共用同一套单元格/边框/标题样式（rule of three：抽到唯一来源，改样式只改这里）。
// 表内单位/数据呈现仍由各 builder 负责——这里只管「长什么样」，不管「填什么」。

using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Wordprocessing;

namespace CivCore.Doc.ReportTables;

internal static class WordTableStyle
{
    public const string CjkFont = "SimSun";              // 宋体
    public const string LatinFont = "Times New Roman";
    public const string FontHalfPt = "21";               // 五号 = 10.5pt → 21 半磅
    private const string TitleHalfPt = "24";             // 小四 = 12pt（表标题）

    /// <summary>细实线四周 + 内部边框（size 4 = 0.5pt）。</summary>
    public static TableBorders Borders() => new(
        new TopBorder { Val = BorderValues.Single, Size = 4 },
        new BottomBorder { Val = BorderValues.Single, Size = 4 },
        new LeftBorder { Val = BorderValues.Single, Size = 4 },
        new RightBorder { Val = BorderValues.Single, Size = 4 },
        new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4 },
        new InsideVerticalBorder { Val = BorderValues.Single, Size = 4 });

    /// <summary>整宽 100% + autofit + 细边框（行式表用，如防火涂层）。</summary>
    public static TableProperties PctTableProps() => new(
        new TableWidth { Type = TableWidthUnitValues.Pct, Width = "5000" },
        Borders(),
        new TableLayout { Type = TableLayoutValues.Autofit });

    /// <summary>一行：每个文本一个单元格，可统一加粗。</summary>
    public static TableRow Row(IEnumerable<string> texts, bool bold)
    {
        var row = new TableRow();
        foreach (var t in texts) row.AppendChild(Cell(t, bold));
        return row;
    }

    /// <summary>单行文本单元格：宋体+Times 五号居中；可选加粗 / 横跨 gridSpan 列 / 纵向合并 vMerge。</summary>
    public static TableCell Cell(
        string text, bool bold = false, int gridSpan = 1, MergedCellValues? vMerge = null)
        => CellOf(new[] { Paragraph(text, bold) }, gridSpan, vMerge);

    /// <summary>多段文本单元格（每个 line 一段）——给「下限/上限」这类一格两行的单元格用。</summary>
    public static TableCell CellMulti(
        IReadOnlyList<string> lines, bool bold = false, int gridSpan = 1, MergedCellValues? vMerge = null)
        => CellOf(lines.Select(l => Paragraph(l, bold)), gridSpan, vMerge);

    /// <summary>表标题段：居中、宋体+Times、小四加粗。</summary>
    public static Paragraph TitleParagraph(string text) => new(
        new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
        new Run(
            new RunProperties(
                Fonts(),
                new Bold(),
                new FontSize { Val = TitleHalfPt }),
            new Text(text) { Space = SpaceProcessingModeValues.Preserve }));

    // ── 内部 ──

    private static RunFonts Fonts()
        => new() { Ascii = LatinFont, HighAnsi = LatinFont, EastAsia = CjkFont };

    /// <summary>居中段落，含一个宋体+Times 五号 Run（可加粗）。</summary>
    private static Paragraph Paragraph(string text, bool bold)
    {
        // RunProperties 按 OOXML schema 顺序：rFonts → b → sz → szCs
        var runProps = new RunProperties();
        runProps.AppendChild(Fonts());
        if (bold) runProps.AppendChild(new Bold());
        runProps.AppendChild(new FontSize { Val = FontHalfPt });
        runProps.AppendChild(new FontSizeComplexScript { Val = FontHalfPt });

        return new Paragraph(
            new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
            new Run(runProps, new Text(text) { Space = SpaceProcessingModeValues.Preserve }));
    }

    private static TableCell CellOf(IEnumerable<Paragraph> paragraphs, int gridSpan, MergedCellValues? vMerge)
    {
        // TableCellProperties 按 schema 顺序：gridSpan → vMerge → vAlign
        var cellProps = new TableCellProperties();
        if (gridSpan > 1) cellProps.AppendChild(new GridSpan { Val = gridSpan });
        if (vMerge is { } vm) cellProps.AppendChild(new VerticalMerge { Val = vm });
        cellProps.AppendChild(new TableCellVerticalAlignment { Val = TableVerticalAlignmentValues.Center });

        var cell = new TableCell(cellProps);
        foreach (var p in paragraphs) cell.AppendChild(p);
        return cell;
    }
}
