// 锚杆「数据分析」sheet 写入：横排表格，每行一根锚杆。
// 列 = 输入 11 列位移读数 + 弹性位移量 M + 下限 Q + 上限 R + 判定。
//
// 对应 docs/civil_kb/formulas/test_pj/数据/数据.xlsx 第 2 个 sheet「数据分析结果」的输出。

using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;

namespace CivCore.Doc.ReportTables;

public static class AnchorAnalysisSheet
{
    /// <summary>把一批锚杆结果写到 sheet。</summary>
    public static void Write(IXLWorksheet ws, AnchorBatchResult batch)
    {
        var headers = new[]
        {
            "锚杆编号",
            "0.1Nt", "0.4Nt", "0.7Nt", "1.0Nt",
            "1.2Nt-1min", "1.2Nt-3min", "1.2Nt-5min",
            "卸载1.0Nt", "卸载0.7Nt", "卸载0.4Nt", "卸载0.1Nt",
            "弹性位移量 M (mm)",
            "下限 Q (mm)", "上限 R (mm)", "判定",
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
        foreach (var (input, result) in batch.RowsWithResults)
        {
            var d = input.Displacements;
            ws.Cell(row, 1).Value = input.AnchorId;
            ws.Cell(row, 2).Value = d.D01Nt;
            ws.Cell(row, 3).Value = d.D04Nt;
            ws.Cell(row, 4).Value = d.D07Nt;
            ws.Cell(row, 5).Value = d.D10Nt;
            ws.Cell(row, 6).Value = d.D12Nt1Min;
            ws.Cell(row, 7).Value = d.D12Nt3Min;
            ws.Cell(row, 8).Value = d.D12Nt5Min;
            ws.Cell(row, 9).Value = d.U10Nt;
            ws.Cell(row, 10).Value = d.U07Nt;
            ws.Cell(row, 11).Value = d.U04Nt;
            ws.Cell(row, 12).Value = d.U01Nt;
            ws.Cell(row, 13).Value = Math.Round(result.ElasticDisplacement, 2);
            ws.Cell(row, 14).Value = Math.Round(result.LowerLimit, 2);
            ws.Cell(row, 15).Value = Math.Round(result.UpperLimit, 2);
            var verdict = ws.Cell(row, 16);
            verdict.Value = result.Qualified ? "合格" : "不合格";
            if (!result.Qualified)
                verdict.Style.Font.FontColor = XLColor.Red;
            row++;
        }

        int lastRow = row - 1;

        ws.Column(1).Width = 10;
        for (int c = 2; c <= 12; c++) ws.Column(c).Width = 10;
        ws.Column(13).Width = 14;
        ws.Column(14).Width = 12;
        ws.Column(15).Width = 12;
        ws.Column(16).Width = 8;

        var all = ws.Range(1, 1, lastRow, headers.Length);
        all.Style.Border.InsideBorder = XLBorderStyleValues.Thin;
        all.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
        all.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
        all.Style.Alignment.Vertical = XLAlignmentVerticalValues.Center;

        // 汇总行
        ws.Cell(lastRow + 2, 1).Value = $"合格率：{batch.NQualified}/{batch.NTotal}" +
            (batch.NTotal > 0 ? $" ({100.0 * batch.NQualified / batch.NTotal:F1}%)" : "");
        ws.Cell(lastRow + 2, 1).Style.Font.Bold = true;
    }
}
