// 防火涂层「数据分析」sheet 写入：宽表版式（贴合用户现有「防火（钢梁/钢柱）」sheet）。
//
//   序号 | 构件位置 | 构件类型 | 涂层类型 | 截面号 | 测点1..K | 本段均值 | 构件均值 | 设计厚度 | 判定下限 | 合格率 | 最薄处 | 判定
//   （国标全膨胀型时：「截面号」→「处号」、「本段均值」→「本处均值」，测点列=测点1/2/3）
//
// 一个构件跨多行（每截面/处一行），构件级列按构件合并；测点列展开各面/各点实测值，本段均值=每行均值。
// 厚度按涂层类型显示精度四舍五入（厚型 2 位/游标卡尺、薄型超薄型 3 位/涂层测厚仪）。
// 判定：厚型 合格率+最薄处；膨胀型(薄/超薄) 构件均值 ≥ 设计×0.95。判定下限列随类型给对应下限。
// 合格率厚型专用（膨胀型显示「—」）。末尾按出现的涂层类型分别标注判定依据（可追溯）。

using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;

namespace CivCore.Doc.ReportTables;

public static class CoatingAnalysisSheet
{
    private sealed record SectionView(int SectionNo, List<CoatingPoint> Points);

    private sealed record MemberView(
        CoatingMemberInput Input, CoatingMemberResult Result, List<SectionView> Sections);

    public static void Write(IXLWorksheet ws, CoatingBatchResult batch, string standard)
    {
        var members = batch.MembersWithResults
            .Select(mr => new MemberView(mr.Input, mr.Result, GroupSections(mr.Input)))
            .ToList();

        int k = members.Count == 0
            ? 1
            : Math.Max(1, members.SelectMany(m => m.Sections).Select(s => s.Points.Count).DefaultIfEmpty(1).Max());

        var pointHeaders = ResolvePointHeaders(members, k);

        // 国标 + 本批全膨胀型(薄/超薄)：索引列叫「处号」、每行均值叫「本处均值」（对齐 5 处×3 点模板）。
        // 厚型/地标/混排退回「截面号」「本段均值」（单表头无法两栖）。
        bool allExpansionNational =
            standard == CoatingStandards.GB_50205_2020
            && members.Count > 0
            && members.All(m => CoatingStandards.IsExpansion(m.Result.Category));
        string sectionHeader = allExpansionNational ? CoatingColumns.LocationNo : CoatingColumns.SectionNo;
        string rowMeanHeader = allExpansionNational ? "本处均值" : "本段均值";

        // 列布局：厚型/膨胀型统一一套列。本段均值=每行该截面/处均值；构件均值=全部测点均值；
        // 判定下限=厚型 设计×0.85（配最薄处）/ 膨胀型 设计×0.95兜底（配构件均值）；合格率厚型专用。
        const int colSerial = 1, colLoc = 2, colType = 3, colCat = 4, colSection = 5;
        int colPointStart = 6;
        int colSecMean = colPointStart + k;
        int colMean = colSecMean + 1;
        int colDesign = colMean + 1;
        int colLimit = colDesign + 1;
        int colRatio = colLimit + 1;
        int colMin = colRatio + 1;
        int colVerdict = colMin + 1;
        int totalCols = colVerdict;

        var headers = new string[totalCols];
        headers[colSerial - 1] = "序号";
        headers[colLoc - 1] = "构件位置";
        headers[colType - 1] = "构件类型";
        headers[colCat - 1] = "涂层类型";
        headers[colSection - 1] = sectionHeader;
        for (int i = 0; i < k; i++) headers[colPointStart - 1 + i] = pointHeaders[i];
        headers[colSecMean - 1] = rowMeanHeader;
        headers[colMean - 1] = "构件均值";
        headers[colDesign - 1] = "设计厚度";
        headers[colLimit - 1] = "判定下限";
        headers[colRatio - 1] = "合格率";
        headers[colMin - 1] = "最薄处";
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
            int dec = CoatingStandards.ThicknessDecimals(m.Result.Category);
            bool isExpansion = CoatingStandards.IsExpansion(m.Result.Category);
            int memberStart = row;

            if (m.Sections.Count == 0)
            {
                ws.Cell(row, colSection).Value = 1;
                row++;
            }
            else
            {
                foreach (var sec in m.Sections)
                {
                    ws.Cell(row, colSection).Value = sec.SectionNo;
                    for (int i = 0; i < sec.Points.Count && i < k; i++)
                        ws.Cell(row, colPointStart + i).Value = Math.Round(sec.Points[i].Thickness, dec);
                    if (sec.Points.Count > 0)
                        ws.Cell(row, colSecMean).Value = Math.Round(sec.Points.Average(p => p.Thickness), dec);
                    row++;
                }
            }
            int memberEnd = row - 1;

            SetMerged(ws, memberStart, memberEnd, colSerial, serial);
            SetMerged(ws, memberStart, memberEnd, colLoc, m.Input.Location);
            SetMerged(ws, memberStart, memberEnd, colType, m.Input.MemberType);
            SetMerged(ws, memberStart, memberEnd, colCat, m.Result.Category.ToString());
            SetMerged(ws, memberStart, memberEnd, colMean, Math.Round(m.Result.MeanThickness, dec));
            SetMerged(ws, memberStart, memberEnd, colDesign, Math.Round(m.Input.DesignThickness, dec));
            SetMerged(ws, memberStart, memberEnd, colMin, Math.Round(m.Result.MinThickness, dec));

            // 判定下限：膨胀型 设计×0.95兜底（构件均值下限）；厚型 设计×0.85（最薄处下限）。
            double limit = isExpansion ? m.Result.MeanLowerLimit : m.Result.LowerLimit;
            SetMerged(ws, memberStart, memberEnd, colLimit, Math.Round(limit, dec));

            // 合格率：厚型才有意义；膨胀型显示「—」
            var ratioCell = MergedTopLeft(ws, memberStart, memberEnd, colRatio);
            ratioCell.Value = isExpansion
                ? "—"
                : $"{m.Result.NQualifiedPoints}/{m.Result.NPoints} ({m.Result.QualifiedRatio * 100:F1}%)";

            var verdictCell = MergedTopLeft(ws, memberStart, memberEnd, colVerdict);
            verdictCell.Value = m.Result.Verdict switch
            {
                CoatingVerdict.合格 => "合格",
                CoatingVerdict.不合格 => $"不合格（{m.Result.FailReason}）",
                _ => $"待接入（{m.Result.Category}）",
            };
            if (m.Result.Verdict == CoatingVerdict.不合格)
                verdictCell.Style.Font.FontColor = XLColor.Red;
            else if (m.Result.Verdict == CoatingVerdict.待判定)
                verdictCell.Style.Font.FontColor = XLColor.Gray;

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

        // 汇总 + 判定依据（按出现的涂层类型分别标注，可追溯）
        int notQualified = batch.NTotal - batch.NQualified - batch.NPending;
        ws.Cell(lastRow + 2, 1).Value =
            $"合格 {batch.NQualified}/{batch.NTotal}"
            + (notQualified > 0 ? $"，不合格 {notQualified}" : "")
            + (batch.NPending > 0 ? $"，待判定 {batch.NPending}" : "");
        ws.Cell(lastRow + 2, 1).Style.Font.Bold = true;

        int basisRow = lastRow + 3;
        if (members.Any(m => m.Result.Category == CoatingCategory.厚型))
            ws.Cell(basisRow++, 1).Value =
                $"判定依据：{standard} 厚涂型 —— ≥{CoatingStandards.RatioThreshold * 100:F0}% 测点 ≥ 设计厚度，"
                + $"且最薄处 ≥ 设计 × {CoatingStandards.MinFactor:F2}";
        if (members.Any(m => CoatingStandards.IsExpansion(m.Result.Category)))
            ws.Cell(basisRow++, 1).Value =
                $"判定依据：{standard} 膨胀型(薄/超薄) —— 构件均值 ≥ 设计 × {CoatingStandards.ExpansionMeanFactor:F2}（偏差 −5%），"
                + $"且 ≥ 设计 − {CoatingStandards.AbsoluteFloorMm * 1000:F0}µm";
    }

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
