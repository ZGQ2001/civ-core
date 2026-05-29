// 防火涂层「数据分析」sheet 写入：宽表版式（贴合用户现有「防火（钢梁/钢柱）」sheet）。
//
//   序号 | 构件位置 | 构件类型 | 截面号 | 测点1..K | 平均值 | 合格率 | 最薄处 | 设计厚度 | 判定
//
// 一个构件跨多行（每截面一行），序号/构件位置/构件类型/平均值/合格率/最薄处/设计厚度/判定
// 按构件合并；测点列展开各面实测值。测点列数 K = 该批构件单截面最多测点数；若全批测点位置
// 标签一致则用面名做表头（钢梁：梁侧面…；钢柱：东侧面…），否则用「测点1..K」。
//
// 判定不合格时在「判定」单元格附原因（程序不能是黑盒），末尾标注判定依据（可追溯）。

using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;

namespace CivCore.Doc.ReportTables;

public static class CoatingAnalysisSheet
{
    /// <summary>一个截面：序号 + 该截面各测点（按输入顺序）。</summary>
    private sealed record SectionView(int SectionNo, List<CoatingPoint> Points);

    private sealed record MemberView(
        CoatingMemberInput Input, CoatingMemberResult Result, List<SectionView> Sections);

    public static void Write(IXLWorksheet ws, CoatingBatchResult batch)
    {
        var members = batch.MembersWithResults
            .Select(mr => new MemberView(mr.Input, mr.Result, GroupSections(mr.Input)))
            .ToList();

        int k = members.Count == 0
            ? 1
            : Math.Max(1, members.SelectMany(m => m.Sections).Select(s => s.Points.Count).DefaultIfEmpty(1).Max());

        var pointHeaders = ResolvePointHeaders(members, k);

        // 列布局
        const int colSerial = 1, colLoc = 2, colType = 3, colSection = 4;
        int colPointStart = 5;
        int colMean = colPointStart + k;
        int colRatio = colMean + 1;
        int colMin = colRatio + 1;
        int colDesign = colMin + 1;
        int colVerdict = colDesign + 1;
        int totalCols = colVerdict;

        // 表头
        var headers = new string[totalCols];
        headers[colSerial - 1] = "序号";
        headers[colLoc - 1] = "构件位置";
        headers[colType - 1] = "构件类型";
        headers[colSection - 1] = "截面号";
        for (int i = 0; i < k; i++) headers[colPointStart - 1 + i] = pointHeaders[i];
        headers[colMean - 1] = "平均值";
        headers[colRatio - 1] = "合格率";
        headers[colMin - 1] = "最薄处";
        headers[colDesign - 1] = "设计厚度";
        headers[colVerdict - 1] = "判定";
        for (int c = 0; c < totalCols; c++)
        {
            var cell = ws.Cell(1, c + 1);
            cell.Value = headers[c];
            cell.Style.Font.Bold = true;
            cell.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
            cell.Style.Fill.BackgroundColor = XLColor.LightGray;
        }

        int row = 2;
        int serial = 1;
        foreach (var m in members)
        {
            int span = Math.Max(1, m.Sections.Count);
            int memberStart = row;

            if (m.Sections.Count == 0)
            {
                // 理论上不会（Create 保证 ≥1 点），兜底写一行
                ws.Cell(row, colSection).Value = 1;
                row++;
            }
            else
            {
                foreach (var sec in m.Sections)
                {
                    ws.Cell(row, colSection).Value = sec.SectionNo;
                    for (int i = 0; i < sec.Points.Count && i < k; i++)
                        ws.Cell(row, colPointStart + i).Value = Math.Round(sec.Points[i].Thickness, 2);
                    row++;
                }
            }
            int memberEnd = row - 1;

            // 构件级（合并跨截面行）
            SetMerged(ws, memberStart, memberEnd, colSerial, serial);
            SetMerged(ws, memberStart, memberEnd, colLoc, m.Input.Location);
            SetMerged(ws, memberStart, memberEnd, colType, m.Input.MemberType);
            SetMerged(ws, memberStart, memberEnd, colMean, Math.Round(m.Result.MeanThickness, 2));
            SetMerged(ws, memberStart, memberEnd, colRatio,
                $"{m.Result.NQualifiedPoints}/{m.Result.NPoints} ({m.Result.QualifiedRatio * 100:F1}%)");
            SetMerged(ws, memberStart, memberEnd, colMin, Math.Round(m.Result.MinThickness, 2));
            SetMerged(ws, memberStart, memberEnd, colDesign, m.Input.DesignThickness);

            var verdictCell = MergedTopLeft(ws, memberStart, memberEnd, colVerdict);
            verdictCell.Value = m.Result.Qualified
                ? "合格"
                : $"不合格（{m.Result.FailReason}）";
            if (!m.Result.Qualified)
                verdictCell.Style.Font.FontColor = XLColor.Red;

            serial++;
        }

        int lastRow = row - 1;
        if (lastRow >= 1)
        {
            var all = ws.Range(1, 1, lastRow, totalCols);
            all.Style.Border.InsideBorder = XLBorderStyleValues.Thin;
            all.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
            all.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
            all.Style.Alignment.Vertical = XLAlignmentVerticalValues.Center;
        }

        ws.Column(colLoc).Width = 24;
        ws.Column(colVerdict).Width = 28;

        // 汇总 + 判定依据（可追溯）
        ws.Cell(lastRow + 2, 1).Value =
            $"合格率：{batch.NQualified}/{batch.NTotal} 构件" +
            (batch.NTotal > 0 ? $" ({100.0 * batch.NQualified / batch.NTotal:F1}%)" : "");
        ws.Cell(lastRow + 2, 1).Style.Font.Bold = true;
        ws.Cell(lastRow + 3, 1).Value =
            $"判定依据：GB 50205-2020 §13.4.3（厚涂型）—— ≥{CoatingStandards.RatioThreshold * 100:F0}% 测点 ≥ 设计厚度，且最薄处 ≥ 设计 × {CoatingStandards.MinFactor:F2}";
    }

    /// <summary>把构件的测点按截面号分组（升序），组内保持输入顺序。</summary>
    private static List<SectionView> GroupSections(CoatingMemberInput member)
    {
        var order = new List<int>();
        var map = new Dictionary<int, List<CoatingPoint>>();
        foreach (var p in member.Points)
        {
            if (!map.TryGetValue(p.SectionNo, out var list))
            {
                list = new List<CoatingPoint>();
                map[p.SectionNo] = list;
                order.Add(p.SectionNo);
            }
            list.Add(p);
        }
        order.Sort();
        return order.Select(sn => new SectionView(sn, map[sn])).ToList();
    }

    /// <summary>全批测点位置标签一致 → 用面名表头；否则「测点1..K」。</summary>
    private static string[] ResolvePointHeaders(List<MemberView> members, int k)
    {
        string[]? candidate = null;
        foreach (var sec in members.SelectMany(m => m.Sections))
        {
            if (sec.Points.Count != k) return GenericHeaders(k);
            var labels = sec.Points.Select(p => p.Position).ToArray();
            if (labels.Any(string.IsNullOrEmpty)) return GenericHeaders(k);
            if (candidate == null) candidate = labels;
            else if (!candidate.SequenceEqual(labels)) return GenericHeaders(k);
        }
        return candidate ?? GenericHeaders(k);
    }

    private static string[] GenericHeaders(int k)
        => Enumerable.Range(1, k).Select(i => $"测点{i}").ToArray();

    private static void SetMerged(IXLWorksheet ws, int r1, int r2, int col, XLCellValue value)
        => MergedTopLeft(ws, r1, r2, col).Value = value;

    private static IXLCell MergedTopLeft(IXLWorksheet ws, int r1, int r2, int col)
    {
        if (r2 > r1) ws.Range(r1, col, r2, col).Merge();
        return ws.Cell(r1, col);
    }
}
