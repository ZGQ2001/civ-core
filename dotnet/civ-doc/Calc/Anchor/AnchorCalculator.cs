// 锚杆 workbook 编排：按批次套用各自参数逐行算，汇总 batch / total 计数。
// 单纯遍历 + 应用 AnchorMath，无 IO、无副作用。

namespace CivCore.Doc.Calc.Anchor;

public static class AnchorCalculator
{
    public static AnchorWorkbookResult Calc(AnchorWorkbookInput workbook)
    {
        AnchorStandards.Validate(workbook.Standard);

        var batchResults = new List<AnchorBatchResult>();
        int totalRows = 0, totalQualified = 0;

        foreach (var batch in workbook.Batches)
        {
            var rowsWithResults = new (AnchorRowInput, AnchorRowResult)[batch.Rows.Length];
            int batchQualified = 0;
            for (int i = 0; i < batch.Rows.Length; i++)
            {
                var row = batch.Rows[i];
                var result = AnchorMath.ComputeRow(row.Displacements, batch.Params);
                rowsWithResults[i] = (row, result);
                if (result.Qualified) batchQualified++;
            }
            batchResults.Add(new AnchorBatchResult(
                batch.BatchId, batch.Params, rowsWithResults,
                batchQualified, batch.Rows.Length));
            totalRows += batch.Rows.Length;
            totalQualified += batchQualified;
        }

        return new AnchorWorkbookResult(
            workbook.Standard,
            batchResults.ToArray(),
            batchResults.Count,
            totalRows,
            totalQualified);
    }
}
