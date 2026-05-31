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

    /// <summary>
    /// 厚型（及地标膨胀型）报告表：截面×面版式。一构件跨 N 截面行，
    /// 序号/构件位置/平均值 跨该构件所有行 vMerge 合并；2 行表头（实测涂层厚度 hMerge 跨各面 + 面名）。
    /// 单位随涂层类型：厚型 mm（游标卡尺）/ 薄·超薄 μm（测厚仪）。本表无设计/判定列（照母版）。
    /// 要求传入构件同一面布局（梁 3 面 / 柱 4 面），混排请由调用方按构件类型分表。
    /// </summary>
    public static Table BuildThick(
        IReadOnlyList<(CoatingMemberInput Input, CoatingMemberResult Result)> members)
    {
        if (members.Count == 0)
            throw new ArgumentException("厚型报告表没有构件");

        var faces = FaceNames(members[0].Input);
        int k = faces.Count;
        var category = members[0].Result.Category;
        string unit = UnitLabel(category);

        var table = new Table(TableProps());

        // 表头行 1：序号 | 构件位置 | 测点 |〔实测涂层厚度(unit) 跨 k 列〕| 平均值(unit)
        var h1 = new TableRow();
        h1.AppendChild(Cell("序号", bold: true, vMerge: MergedCellValues.Restart));
        h1.AppendChild(Cell("构件位置", bold: true, vMerge: MergedCellValues.Restart));
        h1.AppendChild(Cell("测点", bold: true, vMerge: MergedCellValues.Restart));
        h1.AppendChild(Cell($"实测涂层厚度({unit})", bold: true, gridSpan: k));
        h1.AppendChild(Cell($"平均值({unit})", bold: true, vMerge: MergedCellValues.Restart));
        table.AppendChild(h1);

        // 表头行 2：前三列与平均值列 vMerge 续；中间是各面名
        var h2 = new TableRow();
        h2.AppendChild(Cell("", bold: true, vMerge: MergedCellValues.Continue));
        h2.AppendChild(Cell("", bold: true, vMerge: MergedCellValues.Continue));
        h2.AppendChild(Cell("", bold: true, vMerge: MergedCellValues.Continue));
        foreach (var f in faces) h2.AppendChild(Cell(f, bold: true));
        h2.AppendChild(Cell("", bold: true, vMerge: MergedCellValues.Continue));
        table.AppendChild(h2);

        int serial = 1;
        foreach (var (input, result) in members)
        {
            var sections = input.Points
                .GroupBy(p => p.SectionNo).OrderBy(g => g.Key).ToList();

            for (int si = 0; si < sections.Count; si++)
            {
                bool first = si == 0;
                var vm = first ? MergedCellValues.Restart : MergedCellValues.Continue;
                var row = new TableRow();

                row.AppendChild(Cell(first ? serial.ToString() : "", vMerge: vm));
                row.AppendChild(Cell(first ? input.Location : "", vMerge: vm));
                row.AppendChild(Cell($"截面{sections[si].Key}"));

                var pts = sections[si].ToList();
                for (int fi = 0; fi < k; fi++)
                    row.AppendChild(Cell(fi < pts.Count ? Val(pts[fi].Thickness, category) : ""));

                row.AppendChild(Cell(first ? Val(result.MeanThickness, category) : "", vMerge: vm));
                table.AppendChild(row);
            }
            serial++;
        }
        return table;
    }

    /// <summary>首截面各测点的面名（保留重复，如梁「梁侧面/梁侧面/梁底面」）。</summary>
    private static List<string> FaceNames(CoatingMemberInput input)
        => input.Points
            .GroupBy(p => p.SectionNo).OrderBy(g => g.Key).First()
            .Select(p => p.Position).ToList();

    /// <summary>显示单位：厚型 mm（游标卡尺）/ 薄·超薄 μm（测厚仪）。</summary>
    private static string UnitLabel(CoatingCategory c)
        => c == CoatingCategory.厚型 ? "mm" : "μm";

    /// <summary>按涂层类型格式化厚度：厚型 mm（2 位）/ 膨胀型 μm（整数）。</summary>
    private static string Val(double mm, CoatingCategory c)
        => c == CoatingCategory.厚型
            ? Math.Round(mm, 2).ToString("0.##")
            : Math.Round(mm * 1000).ToString("0");

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

    /// <summary>统一单元格：宋体+Times 五号居中；可选加粗 / 横跨 gridSpan 列 / 纵向合并 vMerge。</summary>
    private static TableCell Cell(
        string text, bool bold = false, int gridSpan = 1, MergedCellValues? vMerge = null)
    {
        // RunProperties 按 OOXML schema 顺序：rFonts → b → sz → szCs
        var runProps = new RunProperties();
        runProps.AppendChild(new RunFonts { Ascii = LatinFont, HighAnsi = LatinFont, EastAsia = CjkFont });
        if (bold) runProps.AppendChild(new Bold());
        runProps.AppendChild(new FontSize { Val = FontHalfPt });
        runProps.AppendChild(new FontSizeComplexScript { Val = FontHalfPt });

        var run = new Run(runProps, new Text(text) { Space = SpaceProcessingModeValues.Preserve });
        var para = new Paragraph(
            new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
            run);

        // TableCellProperties 按 schema 顺序：gridSpan → vMerge → vAlign
        var cellProps = new TableCellProperties();
        if (gridSpan > 1) cellProps.AppendChild(new GridSpan { Val = gridSpan });
        if (vMerge is { } vm) cellProps.AppendChild(new VerticalMerge { Val = vm });
        cellProps.AppendChild(new TableCellVerticalAlignment { Val = TableVerticalAlignmentValues.Center });

        return new TableCell(cellProps, para);
    }
}
