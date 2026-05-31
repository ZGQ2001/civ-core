// 防火涂层报告表 → Word 表格（OpenXML 直接建）。供报告生成时插入 docx 模板的
// 「{{表格:防火涂层}}」占位符处。表的内部格式按规范标准固定在代码里——判定数据的呈现
// 必须规范统一（判错=事故），不随甲方模板乱改；甲方要改的封面/主表/结论那层走 {{}} 占位符。
//
// 膨胀型（薄/超薄，国标 5 处×3 点）：一构件一行。
//   列：序号 | 构件编号 | (1处)~(5处)平均值 | 平均值 | 设计值 | 检测结果，单位 μm（涂层测厚仪）。
//   (N处)平均值 = 该处 3 个测点的均值；平均值 = 构件总均值；判定来自 CoatingMemberResult。
//
// 字体：中文宋体、英文 Times New Roman、五号(10.5pt)；细实线边框。内部统一 mm，μm = mm×1000。

using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Wordprocessing;
using CivCore.Doc.Calc.Coating;

namespace CivCore.Doc.ReportTables;

public static class CoatingWordTable
{
    private const string CjkFont = "SimSun";            // 宋体
    private const string LatinFont = "Times New Roman";
    private const string FontHalfPt = "21";             // 五号 = 10.5pt → 21 半磅
    private const int ExpansionLocations = 5;           // 膨胀型固定 5 处

    /// <summary>膨胀型报告表：一构件一行（μm）。返回 OpenXML Table，调用方插入占位符处。</summary>
    public static Table BuildExpansion(CoatingBatchResult batch)
    {
        var table = new Table(TableProps());

        var headers = new List<string> { "序号", "构件编号" };
        for (int i = 1; i <= ExpansionLocations; i++) headers.Add($"(第{i}处)平均值(μm)");
        headers.Add("平均值(μm)");
        headers.Add("设计值(μm)");
        headers.Add("检测结果");
        table.AppendChild(Row(headers, bold: true));

        int serial = 1;
        foreach (var (input, result) in batch.MembersWithResults)
        {
            var cells = new List<string> { serial.ToString(), input.Location };
            foreach (var avg in LocationMeansUm(input))
                cells.Add(avg is double v ? Mu(v) : "");
            cells.Add(Mu(result.MeanThickness));
            cells.Add(Mu(input.DesignThickness));
            cells.Add(VerdictText(result));
            table.AppendChild(Row(cells, bold: false));
            serial++;
        }
        return table;
    }

    /// <summary>每处（SectionNo 升序）3 测点均值（mm）；不足 5 处补 null。</summary>
    private static double?[] LocationMeansUm(CoatingMemberInput input)
    {
        var byLoc = input.Points
            .GroupBy(p => p.SectionNo)
            .OrderBy(g => g.Key)
            .Select(g => (double?)g.Average(p => p.Thickness))
            .ToList();
        var result = new double?[ExpansionLocations];
        for (int i = 0; i < ExpansionLocations; i++)
            result[i] = i < byLoc.Count ? byLoc[i] : null;
        return result;
    }

    private static string Mu(double mm) => Math.Round(mm * 1000).ToString("0"); // mm → μm 整数

    private static string VerdictText(CoatingMemberResult r) => r.Verdict switch
    {
        CoatingVerdict.合格 => "合格",
        CoatingVerdict.不合格 => "不合格",
        _ => "待判定",
    };

    // ── OpenXML 构件 ──

    private static TableProperties TableProps()
    {
        var borders = new TableBorders(
            new TopBorder { Val = BorderValues.Single, Size = 4 },
            new BottomBorder { Val = BorderValues.Single, Size = 4 },
            new LeftBorder { Val = BorderValues.Single, Size = 4 },
            new RightBorder { Val = BorderValues.Single, Size = 4 },
            new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4 },
            new InsideVerticalBorder { Val = BorderValues.Single, Size = 4 });

        return new TableProperties(
            new TableWidth { Type = TableWidthUnitValues.Pct, Width = "5000" },
            borders,
            new TableLayout { Type = TableLayoutValues.Autofit });
    }

    private static TableRow Row(IEnumerable<string> texts, bool bold)
    {
        var row = new TableRow();
        foreach (var t in texts) row.AppendChild(Cell(t, bold));
        return row;
    }

    private static TableCell Cell(string text, bool bold)
    {
        var runProps = new RunProperties(
            new RunFonts { Ascii = LatinFont, HighAnsi = LatinFont, EastAsia = CjkFont },
            new FontSize { Val = FontHalfPt },
            new FontSizeComplexScript { Val = FontHalfPt });
        if (bold) runProps.AppendChild(new Bold());

        var run = new Run(runProps, new Text(text) { Space = SpaceProcessingModeValues.Preserve });
        var para = new Paragraph(
            new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
            run);
        return new TableCell(
            new TableCellProperties(
                new TableCellVerticalAlignment { Val = TableVerticalAlignmentValues.Center }),
            para);
    }
}
