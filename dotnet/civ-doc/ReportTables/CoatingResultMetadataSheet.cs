// 防火涂层结果 xlsx 的「_结果数据」隐藏 sheet —— 机读友好的全精度长表，让
// coating.report / report.assemble 仅凭结果 xlsx 就重建 CoatingWorkbookResult，
// 出报告读结果、不重算（对齐锚杆 AnchorResultReader 的「读结果不重算」）。
//
// 为什么不反读「<批>-数据分析」人看宽表：那张是展示表（合并单元格 + 动态测点列 +
// 国标膨胀型可变表头 + 厚度圆整丢精度），当数据交换格式既脆弱又有损。本表是它的机读
// 兄弟：一测点一行的长表、全精度、列序固定按位置解析、Hidden 防误删（去黑盒：用户可在 Excel 取消隐藏核对）。
//
// 跟 AnchorResultMetadataSheet 同构（机读 / 人看分离）；区别是防火逐测点变长，故用长表
// （一测点一行），构件级字段每行重复——免去「找首个非空行」的歧义，reader 极简且抗行乱序。
//
// 布局（每构件的测点逐行展开）：
//   batch_id | 构件位置 | 构件类型 | 设计厚度 | 涂层类型 | 截面号 | 测点位置 | 实测厚度
//   | 测点数 | 合格测点数 | 合格率 | 最薄处 | 厚型下限 | 构件均值
//   | 合格率达标 | 最薄达标 | 均值下限 | 均值达标 | 判定 | 不合格原因
// reader 按 (batch_id, 构件位置) 分组重建构件；批次/文件级计数由分组聚合（纯计数，不重判定）。

using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;

namespace CivCore.Doc.ReportTables;

public static class CoatingResultMetadataSheet
{
    public const string SheetName = "_结果数据";

    // 列序固定，解析按位置（与标题文字解耦，兼容中英文标题）
    private const int ColBatch = 1;
    private const int ColLoc = 2;
    private const int ColType = 3;
    private const int ColDesign = 4;
    private const int ColCat = 5;
    private const int ColSection = 6;
    private const int ColPos = 7;
    private const int ColThick = 8;
    private const int ColNPoints = 9;
    private const int ColNQualified = 10;
    private const int ColRatio = 11;
    private const int ColMin = 12;
    private const int ColLower = 13;
    private const int ColMean = 14;
    private const int ColRatioPass = 15;
    private const int ColMinPass = 16;
    private const int ColMeanLower = 17;
    private const int ColMeanPass = 18;
    private const int ColVerdict = 19;
    private const int ColFailReason = 20;
    private const int ColCount = 20;

    private static readonly string[] Headers =
    {
        "batch_id", "构件位置", "构件类型", "设计厚度", "涂层类型", "截面号", "测点位置", "实测厚度",
        "测点数", "合格测点数", "合格率", "最薄处", "厚型下限", "构件均值",
        "合格率达标", "最薄达标", "均值下限", "均值达标", "判定", "不合格原因",
    };

    /// <summary>写入/覆盖机读结果 sheet（写完置 Hidden —— 默认隐藏避免误删，用户可在 Excel 取消隐藏核对）。一测点一行，构件级字段每行重复。</summary>
    public static void Write(XLWorkbook wb, CoatingWorkbookResult result)
    {
        if (wb.Worksheets.TryGetWorksheet(SheetName, out var old)) old.Delete();
        var ws = wb.Worksheets.Add(SheetName);
        for (int c = 0; c < ColCount; c++) ws.Cell(1, c + 1).Value = Headers[c];

        int row = 2;
        foreach (var batch in result.BatchResults)
        {
            foreach (var (input, res) in batch.MembersWithResults)
            {
                foreach (var pt in input.Points)
                {
                    ws.Cell(row, ColBatch).Value = batch.BatchId;
                    ws.Cell(row, ColLoc).Value = input.Location;
                    ws.Cell(row, ColType).Value = input.MemberType;
                    ws.Cell(row, ColDesign).Value = input.DesignThickness;
                    ws.Cell(row, ColCat).Value = res.Category.ToString();
                    ws.Cell(row, ColSection).Value = pt.SectionNo;
                    ws.Cell(row, ColPos).Value = pt.Position;
                    ws.Cell(row, ColThick).Value = pt.Thickness;
                    ws.Cell(row, ColNPoints).Value = res.NPoints;
                    ws.Cell(row, ColNQualified).Value = res.NQualifiedPoints;
                    ws.Cell(row, ColRatio).Value = res.QualifiedRatio;
                    ws.Cell(row, ColMin).Value = res.MinThickness;
                    ws.Cell(row, ColLower).Value = res.LowerLimit;
                    ws.Cell(row, ColMean).Value = res.MeanThickness;
                    ws.Cell(row, ColRatioPass).Value = res.RatioPass;
                    ws.Cell(row, ColMinPass).Value = res.MinPass;
                    ws.Cell(row, ColMeanLower).Value = res.MeanLowerLimit;
                    ws.Cell(row, ColMeanPass).Value = res.MeanPass;
                    ws.Cell(row, ColVerdict).Value = res.Verdict.ToString();
                    if (!string.IsNullOrEmpty(res.FailReason))
                        ws.Cell(row, ColFailReason).Value = res.FailReason;
                    row++;
                }
            }
        }
        ws.Visibility = XLWorksheetVisibility.Hidden;
    }

    /// <summary>
    /// 读机读 sheet 重建 CoatingWorkbookResult。sheet 缺失/空 → 返回空结果（NBatches=0），
    /// 由 CoatingResultReader 据此报清晰错误。standard 由调用方传入（与本 sheet 不绑定，对齐锚杆）。
    /// </summary>
    public static CoatingWorkbookResult Read(XLWorkbook wb, string standard)
    {
        if (!wb.Worksheets.TryGetWorksheet(SheetName, out var ws))
            return new CoatingWorkbookResult(standard, Array.Empty<CoatingBatchResult>(), 0, 0, 0, 0);

        var batchOrder = new List<string>();
        var byBatch = new Dictionary<string, (List<string> LocOrder, Dictionary<string, MemberAccum> Members)>();

        int lastRow = ws.LastRowUsed()?.RowNumber() ?? 1;
        for (int r = 2; r <= lastRow; r++)
        {
            string batchId = ws.Cell(r, ColBatch).GetString().Trim();
            string loc = ws.Cell(r, ColLoc).GetString().Trim();
            if (string.IsNullOrWhiteSpace(batchId) || string.IsNullOrWhiteSpace(loc)) continue;
            try
            {
                if (!byBatch.TryGetValue(batchId, out var grp))
                {
                    grp = (new List<string>(), new Dictionary<string, MemberAccum>());
                    byBatch[batchId] = grp;
                    batchOrder.Add(batchId);
                }
                if (!grp.Members.TryGetValue(loc, out var m))
                {
                    m = new MemberAccum();
                    grp.Members[loc] = m;
                    grp.LocOrder.Add(loc);
                }
                if (!m.HeaderFilled)
                {
                    m.MemberType = ws.Cell(r, ColType).GetString();
                    m.Design = ws.Cell(r, ColDesign).GetDouble();
                    m.Category = Enum.Parse<CoatingCategory>(ws.Cell(r, ColCat).GetString().Trim());
                    m.NPoints = (int)ws.Cell(r, ColNPoints).GetDouble();
                    m.NQualifiedPoints = (int)ws.Cell(r, ColNQualified).GetDouble();
                    m.QualifiedRatio = ws.Cell(r, ColRatio).GetDouble();
                    m.MinThickness = ws.Cell(r, ColMin).GetDouble();
                    m.LowerLimit = ws.Cell(r, ColLower).GetDouble();
                    m.MeanThickness = ws.Cell(r, ColMean).GetDouble();
                    m.RatioPass = ws.Cell(r, ColRatioPass).GetValue<bool>();
                    m.MinPass = ws.Cell(r, ColMinPass).GetValue<bool>();
                    m.MeanLowerLimit = ws.Cell(r, ColMeanLower).GetDouble();
                    m.MeanPass = ws.Cell(r, ColMeanPass).GetValue<bool>();
                    m.Verdict = Enum.Parse<CoatingVerdict>(ws.Cell(r, ColVerdict).GetString().Trim());
                    var fr = ws.Cell(r, ColFailReason).GetString();
                    m.FailReason = string.IsNullOrEmpty(fr) ? null : fr;
                    m.HeaderFilled = true;
                }
                int sectionNo = (int)ws.Cell(r, ColSection).GetDouble();
                string pos = ws.Cell(r, ColPos).GetString();
                double thick = ws.Cell(r, ColThick).GetDouble();
                m.Points.Add(CoatingPoint.Create(sectionNo, pos, thick));
            }
            catch (Exception ex)
            {
                // 单行解析失败跳过（容错：用户可能手改了空白行）；
                // 不静默——记到 stderr 便于排查
                Console.Error.WriteLine($"[_结果数据] 第 {r} 行（batch={batchId}, loc={loc}）解析失败，已跳过：{ex.Message}");
            }
        }

        var batchResults = new List<CoatingBatchResult>();
        foreach (var batchId in batchOrder)
        {
            var grp = byBatch[batchId];
            var mwr = new List<(CoatingMemberInput Input, CoatingMemberResult Result)>();
            foreach (var loc in grp.LocOrder)
            {
                var m = grp.Members[loc];
                if (m.Points.Count == 0) continue; // 防御：无测点构件跳过（CoatingMemberInput 要求 ≥1 点）
                var input = CoatingMemberInput.Create(loc, m.MemberType, m.Design, m.Points.ToArray());
                var res = new CoatingMemberResult(
                    m.Category, m.NPoints, m.NQualifiedPoints, m.QualifiedRatio, m.MinThickness,
                    m.LowerLimit, m.MeanThickness, m.RatioPass, m.MinPass, m.MeanLowerLimit,
                    m.MeanPass, m.Verdict, m.FailReason);
                mwr.Add((input, res));
            }
            int nQualified = mwr.Count(x => x.Result.Verdict == CoatingVerdict.合格);
            int nPending = mwr.Count(x => x.Result.Verdict == CoatingVerdict.待判定);
            batchResults.Add(new CoatingBatchResult(batchId, mwr.ToArray(), nQualified, nPending, mwr.Count));
        }

        return new CoatingWorkbookResult(
            standard,
            batchResults.ToArray(),
            batchResults.Count,
            batchResults.Sum(b => b.NTotal),
            batchResults.Sum(b => b.NQualified),
            batchResults.Sum(b => b.NPending));
    }

    /// <summary>读取期间的构件累加器（构件级字段取首行，测点逐行累加）。</summary>
    private sealed class MemberAccum
    {
        public bool HeaderFilled;
        public string MemberType = "";
        public double Design;
        public CoatingCategory Category;
        public int NPoints;
        public int NQualifiedPoints;
        public double QualifiedRatio;
        public double MinThickness;
        public double LowerLimit;
        public double MeanThickness;
        public double MeanLowerLimit;
        public bool RatioPass;
        public bool MinPass;
        public bool MeanPass;
        public CoatingVerdict Verdict;
        public string? FailReason;
        public readonly List<CoatingPoint> Points = new();
    }
}
