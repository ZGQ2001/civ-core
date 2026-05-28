// 反向解析锚杆结果 xlsx —— 让 report.run_from_result 不重新计算就能出 Word。
//
// 来源 xlsx 由 anchor.run 产出（AnchorAnalysisSheet + AnchorResultMetadataSheet）。
// 读出来直接拼成 AnchorWorkbookResult，绕开 AnchorCalculator.Calc 那一步。
//
// 兼容性：
//   - sheet 名约定 "<batchId>-数据分析"；缺 metadata sheet 时报清晰错误
//     提示用户「这份 xlsx 不是 anchor.run 出的，请重新跑装配线」
//   - 列顺序按 AnchorAnalysisSheet.Write 的约定硬编码：1=编号 + 2..12=11 位移 +
//     13=M + 14=Q + 15=R + 16=判定文字。后续如果改 sheet 列序，本 reader 同步改。

using ClosedXML.Excel;
using CivCore.Doc.ReportTables;

namespace CivCore.Doc.Calc.Anchor;

public static class AnchorResultReader
{
    public static AnchorWorkbookResult Read(string resultXlsxPath, string standard)
    {
        if (!File.Exists(resultXlsxPath))
            throw new ArgumentException($"结果 xlsx 文件不存在：{resultXlsxPath}");

        using var wb = new XLWorkbook(resultXlsxPath);
        var paramsByBatch = AnchorResultMetadataSheet.Read(wb);
        if (paramsByBatch.Count == 0)
            throw new InvalidOperationException(
                $"结果 xlsx 缺「{AnchorResultMetadataSheet.SheetName}」sheet —— 无法重建工程参数。" +
                "请重新跑「数据处理」生成结果 xlsx（旧版本生成的不带 metadata）。");

        var batchResults = new List<AnchorBatchResult>();
        foreach (var (batchId, anchorParams) in paramsByBatch)
        {
            var sheetName = $"{batchId}-数据分析";
            // sheet 名可能被 SafeSheetName 截断到 31 字符，按前缀匹配 fallback
            var ws = wb.Worksheets.FirstOrDefault(s => s.Name == sheetName)
                ?? wb.Worksheets.FirstOrDefault(s => s.Name.StartsWith($"{TruncForSheetName(batchId)}-"))
                ?? throw new InvalidOperationException(
                    $"结果 xlsx 缺「{sheetName}」sheet —— 跟 metadata 不一致");

            var rowsWithResults = ReadBatchRows(ws);
            int qualified = rowsWithResults.Count(rwr => rwr.Result.Qualified);
            batchResults.Add(new AnchorBatchResult(
                BatchId: batchId,
                Params: anchorParams,
                RowsWithResults: rowsWithResults.ToArray(),
                NQualified: qualified,
                NTotal: rowsWithResults.Count));
        }

        return new AnchorWorkbookResult(
            Standard: standard,
            BatchResults: batchResults.ToArray(),
            NBatches: batchResults.Count,
            NRowsTotal: batchResults.Sum(b => b.NTotal),
            NQualifiedTotal: batchResults.Sum(b => b.NQualified));
    }

    private static List<(AnchorRowInput Input, AnchorRowResult Result)> ReadBatchRows(IXLWorksheet ws)
    {
        var rows = new List<(AnchorRowInput, AnchorRowResult)>();
        var lastRow = ws.LastRowUsed()?.RowNumber() ?? 1;
        for (int r = 2; r <= lastRow; r++)
        {
            var idCell = ws.Cell(r, 1);
            var anchorId = idCell.GetString();
            // 数据行结束于汇总行（首列是「合格率：X/Y ...」非锚杆编号）—— 按首列含 ':' 终止
            if (string.IsNullOrWhiteSpace(anchorId)) continue;
            if (anchorId.Contains('：') || anchorId.Contains(':')) break;

            try
            {
                var d = new AnchorDisplacements(
                    D01Nt: ws.Cell(r, 2).GetDouble(),
                    D04Nt: ws.Cell(r, 3).GetDouble(),
                    D07Nt: ws.Cell(r, 4).GetDouble(),
                    D10Nt: ws.Cell(r, 5).GetDouble(),
                    D12Nt1Min: ws.Cell(r, 6).GetDouble(),
                    D12Nt3Min: ws.Cell(r, 7).GetDouble(),
                    D12Nt5Min: ws.Cell(r, 8).GetDouble(),
                    U10Nt: ws.Cell(r, 9).GetDouble(),
                    U07Nt: ws.Cell(r, 10).GetDouble(),
                    U04Nt: ws.Cell(r, 11).GetDouble(),
                    U01Nt: ws.Cell(r, 12).GetDouble());
                var input = AnchorRowInput.Create(anchorId, d);
                var elasticDisp = ws.Cell(r, 13).GetDouble();
                var lower = ws.Cell(r, 14).GetDouble();
                var upper = ws.Cell(r, 15).GetDouble();
                // sheet 里写 "合格"/"不合格"，按字面解析；防止 GetString 含尾空白
                var verdict = ws.Cell(r, 16).GetString().Trim();
                var qualified = verdict == "合格";
                var result = new AnchorRowResult(elasticDisp, lower, upper, qualified);
                rows.Add((input, result));
            }
            catch
            {
                // 单行解析失败跳过（容错：用户可能手改了空白行）
            }
        }
        return rows;
    }

    /// <summary>跟 AnchorHandlers.SafeSheetName 的截断逻辑对齐（31 字符）。</summary>
    private static string TruncForSheetName(string batchId)
    {
        return batchId.Length > 27 ? batchId.Substring(0, 27) : batchId;
    }
}
