// 输入 xlsx 的可见「批次信息」sheet —— 把按批次的工程参数 (P/Lf/La/A/E) + 灌浆日期
// 放进用户直接编辑的输入文件，作为这些批次级元数据的唯一来源：
//   - anchor.generate_template 写表头 + 样例批次（默认参数）让用户照填
//   - anchor.read_batch_info 读它给前端预填表单（填过一次不必在 GUI 重输）
//   - anchor.run 在 params_by_batch 缺批次 / 缺灌浆日期时回退读它（agent 只写一个 xlsx 即可跑）
//
// 跟结果 xlsx 的隐藏「_批次参数」(AnchorResultMetadataSheet) 分工：
//   - 本表在输入文件、可见 —— 是用户 / agent 录入的来源
//   - _批次参数 在结果文件、隐藏 —— 是算完持久化供 report.run_from_result 复用
//   两表都含灌浆日期（口径一致）：录入走本表，结果路径走 _批次参数 兜底。
//
// 列顺序固定（批次, P, Lf, La, A, E, 灌浆日期），按位置解析，对中英文标题兼容。

using ClosedXML.Excel;

namespace CivCore.Doc.Calc.Anchor;

/// <summary>批次信息一行：批次号 + 工程参数（解析失败为 null）+ 灌浆日期（yyyy-MM-dd 字符串，可空）。</summary>
public record AnchorBatchInfo(string BatchId, AnchorParams? Params, string GroutingDate);

public static class AnchorBatchInfoSheet
{
    public const string SheetName = "批次信息";

    private const int ColBatch = 1;
    private const int ColP = 2;
    private const int ColLf = 3;
    private const int ColLa = 4;
    private const int ColA = 5;
    private const int ColE = 6;
    private const int ColDate = 7;

    private static readonly string[] Headers =
        { "批次", "P (N)", "Lf (mm)", "La (mm)", "A (mm²)", "E (N/mm²)", "灌浆日期" };

    /// <summary>写「批次信息」sheet（覆盖同名）。空 infos 也写表头，方便用户照填。</summary>
    public static void Write(XLWorkbook wb, IReadOnlyList<AnchorBatchInfo> infos)
    {
        if (wb.Worksheets.TryGetWorksheet(SheetName, out var old)) old.Delete();
        var ws = wb.Worksheets.Add(SheetName);

        for (int c = 0; c < Headers.Length; c++)
        {
            var cell = ws.Cell(1, c + 1);
            cell.Value = Headers[c];
            cell.Style.Font.Bold = true;
            cell.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
            cell.Style.Fill.BackgroundColor = XLColor.LightGray;
        }

        int row = 2;
        foreach (var info in infos)
        {
            ws.Cell(row, ColBatch).Value = info.BatchId;
            if (info.Params is { } p)
            {
                ws.Cell(row, ColP).Value = p.AxialDesignLoad;
                ws.Cell(row, ColLf).Value = p.FreeLength;
                ws.Cell(row, ColLa).Value = p.AnchorLength;
                ws.Cell(row, ColA).Value = p.SteelArea;
                ws.Cell(row, ColE).Value = p.ElasticModulus;
            }
            if (!string.IsNullOrWhiteSpace(info.GroutingDate))
                ws.Cell(row, ColDate).Value = info.GroutingDate;
            row++;
        }

        ws.Column(ColBatch).Width = 10;
        ws.Column(ColP).Width = 12;
        ws.Column(ColLf).Width = 10;
        ws.Column(ColLa).Width = 10;
        ws.Column(ColA).Width = 10;
        ws.Column(ColE).Width = 12;
        ws.Column(ColDate).Width = 14;

        int lastRow = Math.Max(1, row - 1);
        var range = ws.Range(1, 1, lastRow, Headers.Length);
        range.Style.Border.InsideBorder = XLBorderStyleValues.Thin;
        range.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
    }

    /// <summary>读 sheet → 批次信息列表；文件 / sheet 缺失返回空列表（旧模板兼容）。</summary>
    public static List<AnchorBatchInfo> Read(string path)
    {
        if (!File.Exists(path)) return new List<AnchorBatchInfo>();
        using var wb = new XLWorkbook(path);
        return Read(wb);
    }

    public static List<AnchorBatchInfo> Read(XLWorkbook wb)
    {
        var result = new List<AnchorBatchInfo>();
        if (!wb.Worksheets.TryGetWorksheet(SheetName, out var ws)) return result;

        int lastRow = ws.LastRowUsed()?.RowNumber() ?? 1;
        for (int r = 2; r <= lastRow; r++)
        {
            var batchId = ws.Cell(r, ColBatch).GetString().Trim();
            if (string.IsNullOrWhiteSpace(batchId)) continue;

            AnchorParams? prm = null;
            if (TryGetDouble(ws.Cell(r, ColP), out var p)
                && TryGetDouble(ws.Cell(r, ColLf), out var lf)
                && TryGetDouble(ws.Cell(r, ColLa), out var la)
                && TryGetDouble(ws.Cell(r, ColA), out var a)
                && TryGetDouble(ws.Cell(r, ColE), out var e))
            {
                // 值不合法（<=0 等）→ 留 null：前端回退默认，run 走「缺参数」报错路径
                try { prm = AnchorParams.Create(p, lf, la, a, e); }
                catch { prm = null; }
            }

            result.Add(new AnchorBatchInfo(batchId, prm, ReadDate(ws.Cell(r, ColDate))));
        }
        return result;
    }

    private static bool TryGetDouble(IXLCell cell, out double v)
    {
        if (cell.IsEmpty()) { v = 0; return false; }
        return cell.TryGetValue(out v);
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
