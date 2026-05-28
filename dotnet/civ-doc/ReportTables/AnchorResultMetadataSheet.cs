// 锚杆结果 xlsx 的「_批次参数」隐藏 sheet —— 把 AnchorParams (P/Lf/La/A/E) 持久化，
// 让 report.run_from_result 能仅凭结果 xlsx 就重建 AnchorWorkbookResult，无需用户
// 在生成报告时再输入一次工程参数。
//
// 设计：
//   - Sheet 名固定为 SheetName 常量，AnchorResultReader 按此查找
//   - Sheet 状态设为 VeryHidden，普通用户在 Excel 里看不到（避免误删）；
//     程序读取不受影响
//   - 列顺序固定（batch_id, P, Lf, La, A, E）；解析按位置而非标题，对中英文标题兼容
//
// 跟「<批>-数据分析」sheet 是兄弟关系：前者用于报告填充和人工查看，本表只给程序读。

using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;

namespace CivCore.Doc.ReportTables;

public static class AnchorResultMetadataSheet
{
    public const string SheetName = "_批次参数";

    /// <summary>写入/覆盖 metadata sheet（写完置 VeryHidden）。</summary>
    public static void Write(XLWorkbook wb, IReadOnlyDictionary<string, AnchorParams> paramsByBatch)
    {
        if (wb.Worksheets.TryGetWorksheet(SheetName, out var old)) old.Delete();
        var ws = wb.Worksheets.Add(SheetName);
        ws.Cell(1, 1).Value = "batch_id";
        ws.Cell(1, 2).Value = "P (N)";
        ws.Cell(1, 3).Value = "Lf (mm)";
        ws.Cell(1, 4).Value = "La (mm)";
        ws.Cell(1, 5).Value = "A (mm²)";
        ws.Cell(1, 6).Value = "E (N/mm²)";

        int row = 2;
        foreach (var (batchId, p) in paramsByBatch)
        {
            ws.Cell(row, 1).Value = batchId;
            ws.Cell(row, 2).Value = p.AxialDesignLoad;
            ws.Cell(row, 3).Value = p.FreeLength;
            ws.Cell(row, 4).Value = p.AnchorLength;
            ws.Cell(row, 5).Value = p.SteelArea;
            ws.Cell(row, 6).Value = p.ElasticModulus;
            row++;
        }
        ws.Visibility = XLWorksheetVisibility.VeryHidden;
    }

    /// <summary>读取 metadata sheet；缺则返空 dict（调用方据此决定要不要 fallback）。</summary>
    public static Dictionary<string, AnchorParams> Read(XLWorkbook wb)
    {
        var result = new Dictionary<string, AnchorParams>();
        if (!wb.Worksheets.TryGetWorksheet(SheetName, out var ws)) return result;

        var lastRow = ws.LastRowUsed()?.RowNumber() ?? 1;
        for (int r = 2; r <= lastRow; r++)
        {
            var batchId = ws.Cell(r, 1).GetString();
            if (string.IsNullOrWhiteSpace(batchId)) continue;
            try
            {
                var p = ws.Cell(r, 2).GetDouble();
                var lf = ws.Cell(r, 3).GetDouble();
                var la = ws.Cell(r, 4).GetDouble();
                var a = ws.Cell(r, 5).GetDouble();
                var e = ws.Cell(r, 6).GetDouble();
                result[batchId] = AnchorParams.Create(p, lf, la, a, e);
            }
            catch
            {
                // 单行解析失败不阻断整体；report.run_from_result 会在 batch 缺参数时报错
            }
        }
        return result;
    }
}
