// 锚杆结果 xlsx 的「_批次参数」隐藏 sheet —— 把 AnchorParams (P/Lf/La/A/E) + 灌浆日期
// 持久化，让 report.run_from_result 能仅凭结果 xlsx 就重建工程参数 + 拿到灌浆日期，
// 无需用户在生成报告时再输入一次。
//
// 设计：
//   - Sheet 名固定为 SheetName 常量，AnchorResultReader 按此查找
//   - Sheet 状态设为 VeryHidden，普通用户在 Excel 里看不到（避免误删）；
//     程序读取不受影响
//   - 列顺序固定（batch_id, P, Lf, La, A, E, 灌浆日期）；解析按位置而非标题，
//     对中英文标题兼容。灌浆日期列后加，旧结果 xlsx（无第 7 列）读出来为空 —— 向后兼容。
//
// 跟「<批>-数据分析」sheet 是兄弟关系：前者用于报告填充和人工查看，本表只给程序读。
// 跟输入 xlsx 的可见「批次信息」(AnchorBatchInfoSheet) 分工：后者是用户/agent 录入来源，
// 本表是算完持久化、供 report.run_from_result 复用（两表都含灌浆日期，口径一致）。

using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;

namespace CivCore.Doc.ReportTables;

public static class AnchorResultMetadataSheet
{
    public const string SheetName = "_批次参数";

    private const int ColBatch = 1;
    private const int ColP = 2;
    private const int ColLf = 3;
    private const int ColLa = 4;
    private const int ColA = 5;
    private const int ColE = 6;
    private const int ColDate = 7;

    /// <summary>
    /// 写入/覆盖 metadata sheet（写完置 VeryHidden）。
    /// groutingDateByBatch 为按 batch_id 的灌浆日期（yyyy-MM-dd 字符串，可空 / 缺省）；
    /// 无日期的批次留空，与「批次信息」sheet 一致。
    /// </summary>
    public static void Write(
        XLWorkbook wb,
        IReadOnlyDictionary<string, AnchorParams> paramsByBatch,
        IReadOnlyDictionary<string, string>? groutingDateByBatch = null)
    {
        if (wb.Worksheets.TryGetWorksheet(SheetName, out var old)) old.Delete();
        var ws = wb.Worksheets.Add(SheetName);
        ws.Cell(1, ColBatch).Value = "batch_id";
        ws.Cell(1, ColP).Value = "P (N)";
        ws.Cell(1, ColLf).Value = "Lf (mm)";
        ws.Cell(1, ColLa).Value = "La (mm)";
        ws.Cell(1, ColA).Value = "A (mm²)";
        ws.Cell(1, ColE).Value = "E (N/mm²)";
        ws.Cell(1, ColDate).Value = "灌浆日期";

        int row = 2;
        foreach (var (batchId, p) in paramsByBatch)
        {
            ws.Cell(row, ColBatch).Value = batchId;
            ws.Cell(row, ColP).Value = p.AxialDesignLoad;
            ws.Cell(row, ColLf).Value = p.FreeLength;
            ws.Cell(row, ColLa).Value = p.AnchorLength;
            ws.Cell(row, ColA).Value = p.SteelArea;
            ws.Cell(row, ColE).Value = p.ElasticModulus;
            if (groutingDateByBatch is not null
                && groutingDateByBatch.TryGetValue(batchId, out var date)
                && !string.IsNullOrWhiteSpace(date))
                ws.Cell(row, ColDate).Value = date;
            row++;
        }
        ws.Visibility = XLWorksheetVisibility.VeryHidden;
    }

    /// <summary>读取 metadata sheet 的工程参数；缺则返空 dict（调用方据此决定要不要 fallback）。</summary>
    public static Dictionary<string, AnchorParams> Read(XLWorkbook wb)
    {
        var result = new Dictionary<string, AnchorParams>();
        if (!wb.Worksheets.TryGetWorksheet(SheetName, out var ws)) return result;

        var lastRow = ws.LastRowUsed()?.RowNumber() ?? 1;
        for (int r = 2; r <= lastRow; r++)
        {
            var batchId = ws.Cell(r, ColBatch).GetString();
            if (string.IsNullOrWhiteSpace(batchId)) continue;
            try
            {
                var p = ws.Cell(r, ColP).GetDouble();
                var lf = ws.Cell(r, ColLf).GetDouble();
                var la = ws.Cell(r, ColLa).GetDouble();
                var a = ws.Cell(r, ColA).GetDouble();
                var e = ws.Cell(r, ColE).GetDouble();
                result[batchId] = AnchorParams.Create(p, lf, la, a, e);
            }
            catch
            {
                // 单行解析失败不阻断整体；report.run_from_result 会在 batch 缺参数时报错
            }
        }
        return result;
    }

    /// <summary>
    /// 读取 metadata sheet 的灌浆日期（batch_id → yyyy-MM-dd 字符串）。
    /// 只收非空日期的批次；sheet 缺失 / 旧结果 xlsx（无第 7 列）→ 返回空 dict。
    /// report.run_from_result 据此回退灌浆日期（GUI/预设优先，本表兜底）。
    /// </summary>
    public static Dictionary<string, string> ReadGroutingDates(XLWorkbook wb)
    {
        var result = new Dictionary<string, string>();
        if (!wb.Worksheets.TryGetWorksheet(SheetName, out var ws)) return result;

        var lastRow = ws.LastRowUsed()?.RowNumber() ?? 1;
        for (int r = 2; r <= lastRow; r++)
        {
            var batchId = ws.Cell(r, ColBatch).GetString().Trim();
            if (string.IsNullOrWhiteSpace(batchId)) continue;
            var date = ReadDate(ws.Cell(r, ColDate));
            if (!string.IsNullOrWhiteSpace(date)) result[batchId] = date;
        }
        return result;
    }

    /// <summary>日期单元格 → yyyy-MM-dd 字符串；DateTime 单元格归一化，否则取原文。</summary>
    private static string ReadDate(IXLCell cell)
    {
        if (cell.IsEmpty()) return "";
        if (cell.DataType == XLDataType.DateTime && cell.TryGetValue<DateTime>(out var dt))
            return dt.ToString("yyyy-MM-dd");
        return cell.GetString().Trim();
    }
}
