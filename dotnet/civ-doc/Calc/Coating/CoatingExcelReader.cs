// 防火涂层「测点数据」宽表读取（expand 生成、用户填数字的那些表）。
//
// 每个构件类型一张 sheet：「测点数据-梁」「测点数据-柱」… 列头按该类型测点面名。
// 列：批次 / 构件位置 / 构件类型 / 涂层类型(忽略,由设计厚度重算) / 设计厚度 / 截面号 / <测点面名列…>。
// 截面号右侧各列为测点（非空读入，列头=面名）。按(批次,构件位置)跨 sheet 分组，空白单元格向上继承
// （容忍合并/手工留空）。设计厚度按构件取首个非空。

using ClosedXML.Excel;

namespace CivCore.Doc.Calc.Coating;

public static class CoatingExcelReader
{
    public record BatchMembers(string BatchId, List<CoatingMemberInput> Members);

    public const string DefaultBatchId = CoatingColumns.DefaultBatchId;

    public static List<BatchMembers> ReadRows(
        string path, string? sheetName = null, string batchIdColumn = CoatingColumns.Batch)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException($"文件不存在：{path}");
        using var wb = new XLWorkbook(path);

        var batchOrder = new List<string>();
        var byBatch = new Dictionary<string, (List<string> Order, Dictionary<string, Accum> Map)>();

        foreach (var ws in PointDataSheets(wb, sheetName))
            ParseSheetInto(ws, batchIdColumn, batchOrder, byBatch);

        if (batchOrder.Count == 0)
            throw new ArgumentException("没有已填数字的测点行——请先用 coating.expand_template 展开模板再填数据");

        return batchOrder.Select(b =>
        {
            var (order, m) = byBatch[b];
            var members = order.Select(loc =>
            {
                var a = m[loc];
                if (a.Design is not double d)
                    throw new ArgumentException($"构件「{loc}」缺设计厚度");
                return CoatingMemberInput.Create(a.Location, a.MemberType, d, a.Points.ToArray());
            }).ToList();
            return new BatchMembers(b, members);
        }).ToList();
    }

    /// <summary>只读批次 ID 列表（信息性）。批次列缺失→单元素默认批。</summary>
    public static List<string> ListBatchIds(
        string path, string? sheetName = null, string batchIdColumn = CoatingColumns.Batch)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException($"文件不存在：{path}");
        using var wb = new XLWorkbook(path);

        var seen = new HashSet<string>();
        var order = new List<string>();
        foreach (var ws in PointDataSheets(wb, sheetName))
        {
            var map = CoatingSheetUtil.ReadHeaderMap(ws);
            int? batchCol = CoatingSheetUtil.TryColumn(map, batchIdColumn);
            int locCol = CoatingSheetUtil.RequireColumn(map, CoatingColumns.MemberLocation, "构件位置列");
            string cur = DefaultBatchId;
            int lastRow = ws.LastRowUsed()?.RowNumber() ?? 0;
            for (int r = 2; r <= lastRow; r++)
            {
                if (batchCol is int bc)
                {
                    var b = CoatingSheetUtil.ReadString(ws.Cell(r, bc));
                    if (b.Length > 0) cur = b;
                }
                if (CoatingSheetUtil.ReadString(ws.Cell(r, locCol)).Length == 0) continue;
                if (seen.Add(cur)) order.Add(cur);
            }
        }
        return order.Count == 0 ? new List<string> { DefaultBatchId } : order;
    }

    // ── 实现 ──

    /// <summary>选目标 sheet：显式名优先；否则所有「测点数据」开头的 sheet。</summary>
    private static List<IXLWorksheet> PointDataSheets(XLWorkbook wb, string? sheetName)
    {
        if (sheetName != null) return new List<IXLWorksheet> { wb.Worksheet(sheetName) };
        var sheets = wb.Worksheets
            .Where(w => w.Name.StartsWith(CoatingColumns.PointDataSheet))
            .ToList();
        if (sheets.Count == 0)
            throw new ArgumentException(
                $"未找到「{CoatingColumns.PointDataSheet}」表——请先用 coating.expand_template 展开模板");
        return sheets;
    }

    private sealed class Accum
    {
        public string Location = "";
        public string MemberType = "";
        public double? Design;
        public readonly List<CoatingPoint> Points = new();
    }

    private static void ParseSheetInto(
        IXLWorksheet ws, string batchIdColumn,
        List<string> batchOrder,
        Dictionary<string, (List<string> Order, Dictionary<string, Accum> Map)> byBatch)
    {
        var map = CoatingSheetUtil.ReadHeaderMap(ws);
        int? batchCol = CoatingSheetUtil.TryColumn(map, batchIdColumn);
        int locCol = CoatingSheetUtil.RequireColumn(map, CoatingColumns.MemberLocation, "构件位置列");
        int designCol = CoatingSheetUtil.RequireColumn(map, CoatingColumns.DesignThickness, "设计厚度列");
        int sectionCol = CoatingSheetUtil.RequireColumn(map, CoatingColumns.SectionNo, "截面号列");
        int? typeCol = CoatingSheetUtil.TryColumn(map, CoatingColumns.MemberType);

        int lastCol = ws.Row(1).LastCellUsed()?.Address.ColumnNumber ?? 0;
        var pointCols = new List<(int Col, string Name)>();
        for (int c = sectionCol + 1; c <= lastCol; c++)
        {
            var h = CoatingSheetUtil.ReadString(ws.Cell(1, c));
            if (h.Length > 0) pointCols.Add((c, h));
        }
        if (pointCols.Count == 0)
            throw new ArgumentException(
                $"sheet「{ws.Name}」在「截面号」右侧没有测点列——请重新展开模板");

        string curBatch = DefaultBatchId, curLoc = "", curType = "";
        double? curDesign = null;
        int lastRow = ws.LastRowUsed()?.RowNumber() ?? 0;

        for (int r = 2; r <= lastRow; r++)
        {
            if (batchCol is int bc)
            {
                var b = CoatingSheetUtil.ReadString(ws.Cell(r, bc));
                if (b.Length > 0) curBatch = b;
            }
            var loc = CoatingSheetUtil.ReadString(ws.Cell(r, locCol));
            if (loc.Length > 0) curLoc = loc;
            if (typeCol is int tc)
            {
                var t = CoatingSheetUtil.ReadString(ws.Cell(r, tc));
                if (t.Length > 0) curType = t;
            }
            var design = CoatingSheetUtil.ReadOptDouble(ws.Cell(r, designCol), $"sheet「{ws.Name}」行 {r} 设计厚度");
            if (design.HasValue) curDesign = design;

            int sectionNo = CoatingSheetUtil.ReadOptInt(ws.Cell(r, sectionCol), $"行 {r} 截面号") ?? 0;

            var rowPoints = new List<(string Name, double Val)>();
            foreach (var (col, name) in pointCols)
            {
                var v = CoatingSheetUtil.ReadOptDouble(ws.Cell(r, col), $"sheet「{ws.Name}」行 {r}「{name}」实测厚度");
                if (v.HasValue) rowPoints.Add((name, v.Value));
            }
            if (rowPoints.Count == 0) continue;
            if (string.IsNullOrEmpty(curLoc))
                throw new ArgumentException($"sheet「{ws.Name}」行 {r} 有测点但缺构件位置");

            if (!byBatch.TryGetValue(curBatch, out var bucket))
            {
                bucket = (new List<string>(), new Dictionary<string, Accum>());
                byBatch[curBatch] = bucket;
                batchOrder.Add(curBatch);
            }
            if (!bucket.Map.TryGetValue(curLoc, out var accum))
            {
                accum = new Accum { Location = curLoc, MemberType = curType, Design = curDesign };
                bucket.Map[curLoc] = accum;
                bucket.Order.Add(curLoc);
            }
            foreach (var (name, val) in rowPoints)
                accum.Points.Add(CoatingPoint.Create(sectionNo, name, val));
        }
    }
}
