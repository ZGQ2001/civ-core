// 生成「防火涂层厚度」输入 Excel 空白模板（长表：每行一个测点）。
// 用户点「生成模板」→ 下载 xlsx → 照样例填数据 → 跑计算。
//
// 表头（按 CoatingColumns 契约）：
//   批次 | 构件位置 | 构件类型 | 设计厚度 | 截面号 | 测点位置 | 实测厚度
// 样例：1 根钢梁（2 截面 × 3 面）+ 1 根钢柱（2 截面 × 4 面），演示长表怎么填。

using ClosedXML.Excel;
using CivCore.Doc.Server;

namespace CivCore.Doc.Calc.Coating;

public static class CoatingTemplateWriter
{
    public const string TemplateSheetName = "防火涂层厚度数据";

    // 钢梁 3 面、钢柱 4 面（GB 50205-2020 附录 E 测点布置）
    private static readonly string[] BeamFaces = { "梁侧面", "梁侧面", "梁底面" };
    private static readonly string[] ColumnFaces = { "东侧面", "西侧面", "南侧面", "北侧面" };

    /// <summary>写空白模板到 path（覆盖已存在文件）。</summary>
    public static void Write(string path, string standard = CoatingStandards.GB_50205_2020)
    {
        CoatingStandards.Validate(standard);

        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add(TemplateSheetName);

        var headers = new[]
        {
            CoatingColumns.DefaultBatchIdColumn,
            CoatingColumns.MemberLocation,
            CoatingColumns.MemberType,
            CoatingColumns.DesignThickness,
            CoatingColumns.SectionNo,
            CoatingColumns.PointPosition,
            CoatingColumns.MeasuredThickness,
        };

        for (int c = 0; c < headers.Length; c++)
        {
            var cell = ws.Cell(1, c + 1);
            cell.Value = headers[c];
            cell.Style.Font.Bold = true;
            cell.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
            cell.Style.Fill.BackgroundColor = XLColor.LightGray;
        }

        int row = 2;
        // 样例钢梁：设计 24mm，2 截面 × 3 面（厚涂型）
        row = WriteSample(ws, row, "批次1", "地上一层1/A轴钢梁", "梁", 24, sections: 2, BeamFaces,
            sampleThicknesses: new double[] { 25, 24, 30, 26, 22, 28 });
        // 样例钢柱：设计 24mm，2 截面 × 4 面
        row = WriteSample(ws, row, "批次1", "地上一层1/4×4/A轴钢柱", "柱", 24, sections: 2, ColumnFaces,
            sampleThicknesses: new double[] { 25, 26, 24, 27, 31, 28, 27, 26 });

        for (int c = 1; c <= headers.Length; c++) ws.Column(c).AdjustToContents();
        ws.Column(2).Width = 24;

        var range = ws.Range(1, 1, row - 1, headers.Length);
        range.Style.Border.InsideBorder = XLBorderStyleValues.Thin;
        range.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
        range.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;

        // 说明 sheet
        var help = wb.Worksheets.Add("说明");
        help.Cell(1, 1).Value = $"防火涂层厚度检测数据模板（{standard} §13.4.3 厚涂型）";
        help.Cell(1, 1).Style.Font.Bold = true;
        help.Cell(1, 1).Style.Font.FontSize = 14;
        help.Cell(3, 1).Value = "1. 长表：每行一个测点。同一构件的多个测点（多截面、多面）排成多行，每行都填「构件位置」。";
        help.Cell(4, 1).Value = "2. 「批次」可不填（不分批时所有构件归入「全部」批）。";
        help.Cell(5, 1).Value = "3. 厚度单位统一 mm；「设计厚度」按构件填（同一构件各行应一致）。";
        help.Cell(6, 1).Value = "4. 测点布置（附录 E）：钢梁每截面 3 面（两侧面+底面），钢柱每截面 4 面（东/西/南/北）；梁柱每隔 3m（北京地标 1m）取一截面。";
        help.Cell(7, 1).Value = "5. 判定（按构件）：≥80% 测点 ≥ 设计厚度，且最薄处 ≥ 设计 × 85%，两者都满足为合格。";
        help.Column(1).Width = 110;

        AtomicFile.SaveWorkbook(wb, path);
    }

    private static int WriteSample(
        IXLWorksheet ws, int startRow, string batch, string location, string type,
        double design, int sections, string[] faces, double[] sampleThicknesses)
    {
        int row = startRow;
        int k = 0;
        for (int s = 1; s <= sections; s++)
        {
            foreach (var face in faces)
            {
                ws.Cell(row, 1).Value = batch;
                ws.Cell(row, 2).Value = location;
                ws.Cell(row, 3).Value = type;
                ws.Cell(row, 4).Value = design;
                ws.Cell(row, 5).Value = s;
                ws.Cell(row, 6).Value = face;
                ws.Cell(row, 7).Value = k < sampleThicknesses.Length ? sampleThicknesses[k] : design;
                k++;
                row++;
            }
        }
        return row;
    }
}
