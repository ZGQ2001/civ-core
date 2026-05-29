// 防火涂层 workbook 编排：按批次逐构件算，汇总 batch / total 计数。
// 单纯遍历 + 应用 CoatingMath，无 IO、无副作用（对照 AnchorCalculator）。

namespace CivCore.Doc.Calc.Coating;

public static class CoatingCalculator
{
    public static CoatingWorkbookResult Calc(CoatingWorkbookInput workbook)
    {
        CoatingStandards.Validate(workbook.Standard);

        var batchResults = new List<CoatingBatchResult>();
        int totalMembers = 0, totalQualified = 0;

        foreach (var batch in workbook.Batches)
        {
            var membersWithResults = new (CoatingMemberInput, CoatingMemberResult)[batch.Members.Length];
            int batchQualified = 0;
            for (int i = 0; i < batch.Members.Length; i++)
            {
                var member = batch.Members[i];
                var thicknesses = member.Points.Select(pt => pt.Thickness).ToArray();
                var result = CoatingMath.ComputeMember(member.DesignThickness, thicknesses);
                membersWithResults[i] = (member, result);
                if (result.Qualified) batchQualified++;
            }
            batchResults.Add(new CoatingBatchResult(
                batch.BatchId, membersWithResults, batchQualified, batch.Members.Length));
            totalMembers += batch.Members.Length;
            totalQualified += batchQualified;
        }

        return new CoatingWorkbookResult(
            workbook.Standard,
            batchResults.ToArray(),
            batchResults.Count,
            totalMembers,
            totalQualified);
    }
}
