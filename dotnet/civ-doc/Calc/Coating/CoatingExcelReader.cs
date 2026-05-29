// 防火涂层厚度输入 Excel 读取（长表：每行一个测点）。
//
// 单 sheet，列按 CoatingColumns 契约。按「批次」+「构件位置」分组：同一构件的多行
// = 该构件跨截面/跨面的多个测点。设计厚度 / 构件类型按构件取首个非空（同构件应一致，
// 不一致直接报错——避免"数据串位"工程风险）。
//
// 「批次」列可选：缺列时所有构件归入单批（沿用锚杆批次模式，但允许不分批）。
// 判定无关的展示列（构件类型 / 截面号 / 测点位置）可缺，缺则回退默认值；
// 判定相关列（构件位置 / 设计厚度 / 实测厚度）必填。
// 列名容错由 CoatingColumns.NormalizeHeader 抹平（与锚杆同口径）。

using ClosedXML.Excel;

namespace CivCore.Doc.Calc.Coating;

public static class CoatingExcelReader
{
    public record BatchMembers(string BatchId, List<CoatingMemberInput> Members);

    /// <summary>批次列缺失时所有构件归入的默认批次名。</summary>
    public const string DefaultBatchId = "全部";

    public static List<BatchMembers> ReadRows(
        string path,
        string? sheetName = null,
        string batchIdColumn = CoatingColumns.DefaultBatchIdColumn)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException($"文件不存在：{path}");

        using var wb = new XLWorkbook(path);
        var ws = sheetName != null ? wb.Worksheet(sheetName) : wb.Worksheets.First();
        return ReadRowsSingleSheet(ws, batchIdColumn);
    }

    /// <summary>只读批次 ID 列表（前端 / agent 预览用）。批次列缺失时返回单元素 [默认批次]。</summary>
    public static List<string> ListBatchIds(
        string path,
        string? sheetName = null,
        string batchIdColumn = CoatingColumns.DefaultBatchIdColumn)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException($"文件不存在：{path}");

        using var wb = new XLWorkbook(path);
        var ws = sheetName != null ? wb.Worksheet(sheetName) : wb.Worksheets.First();
        return ListBatchIdsSingleSheet(ws, batchIdColumn);
    }

    // ── 实现 ──

    private sealed class MemberAccum
    {
        public string Location = "";
        public string MemberType = "";
        public double? Design;
        public readonly List<CoatingPoint> Points = new();
    }

    private static List<BatchMembers> ReadRowsSingleSheet(IXLWorksheet ws, string batchIdColumn)
    {
        var headerMap = ReadHeaderMap(ws);
        int? batchCol = TryColumn(headerMap, batchIdColumn);
        int locCol = RequireColumn(headerMap, CoatingColumns.MemberLocation, "构件位置列");
        int designCol = RequireColumn(headerMap, CoatingColumns.DesignThickness, "设计厚度列");
        int thickCol = RequireColumn(headerMap, CoatingColumns.MeasuredThickness, "实测厚度列");
        int? typeCol = TryColumn(headerMap, CoatingColumns.MemberType);
        int? sectionCol = TryColumn(headerMap, CoatingColumns.SectionNo);
        int? posCol = TryColumn(headerMap, CoatingColumns.PointPosition);

        // batchId -> (memberOrder, memberLocation -> accum)
        var batchOrder = new List<string>();
        var byBatch = new Dictionary<string, (List<string> Order, Dictionary<string, MemberAccum> Map)>();

        int lastRow = ws.LastRowUsed()?.RowNumber() ?? 0;
        for (int r = 2; r <= lastRow; r++)
        {
            var locCell = ws.Cell(r, locCol);
            var thickCell = ws.Cell(r, thickCol);
            if (locCell.IsEmpty() && thickCell.IsEmpty()) continue; // 整行空 → 跳过

            string loc = locCell.IsEmpty() ? "" : locCell.GetString().Trim();
            if (string.IsNullOrEmpty(loc))
                throw new ArgumentException($"行 {r} 构件位置为空（长表每行都要填构件位置）");

            string batchId = batchCol is int bc && !ws.Cell(r, bc).IsEmpty()
                ? ws.Cell(r, bc).GetString().Trim()
                : DefaultBatchId;
            if (string.IsNullOrEmpty(batchId)) batchId = DefaultBatchId;

            double design = ParseNumber(ws.Cell(r, designCol), $"构件「{loc}」行 {r} 设计厚度");
            double thickness = ParseNumber(ws.Cell(r, thickCol), $"构件「{loc}」行 {r} 实测厚度");
            string memberType = typeCol is int tc && !ws.Cell(r, tc).IsEmpty()
                ? ws.Cell(r, tc).GetString().Trim() : "";
            string position = posCol is int pc && !ws.Cell(r, pc).IsEmpty()
                ? ws.Cell(r, pc).GetString().Trim() : "";

            if (!byBatch.TryGetValue(batchId, out var bucket))
            {
                bucket = (new List<string>(), new Dictionary<string, MemberAccum>());
                byBatch[batchId] = bucket;
                batchOrder.Add(batchId);
            }

            if (!bucket.Map.TryGetValue(loc, out var accum))
            {
                accum = new MemberAccum { Location = loc, MemberType = memberType };
                bucket.Map[loc] = accum;
                bucket.Order.Add(loc);
            }

            // 设计厚度按构件一致性校验（数据串位防线）
            if (accum.Design is double prev && Math.Abs(prev - design) > 1e-9)
                throw new ArgumentException(
                    $"构件「{loc}」设计厚度不一致：{prev} 与 {design}（同一构件各行设计厚度应相同）");
            accum.Design = design;
            if (string.IsNullOrEmpty(accum.MemberType) && !string.IsNullOrEmpty(memberType))
                accum.MemberType = memberType;

            int sectionNo = ParseSectionNo(sectionCol is int sc ? ws.Cell(r, sc) : null,
                fallback: accum.Points.Count + 1);
            accum.Points.Add(CoatingPoint.Create(sectionNo, position, thickness));
        }

        if (batchOrder.Count == 0)
            throw new ArgumentException("输入 Excel 没有数据行（表头下无构件测点）");

        return batchOrder.Select(b =>
        {
            var (order, map) = byBatch[b];
            var members = order.Select(loc =>
            {
                var a = map[loc];
                return CoatingMemberInput.Create(a.Location, a.MemberType, a.Design ?? 0, a.Points.ToArray());
            }).ToList();
            return new BatchMembers(b, members);
        }).ToList();
    }

    private static List<string> ListBatchIdsSingleSheet(IXLWorksheet ws, string batchIdColumn)
    {
        var headerMap = ReadHeaderMap(ws);
        int? batchCol = TryColumn(headerMap, batchIdColumn);
        int locCol = RequireColumn(headerMap, CoatingColumns.MemberLocation, "构件位置列");

        if (batchCol is not int bc)
            return new List<string> { DefaultBatchId };

        var seen = new HashSet<string>();
        var order = new List<string>();
        int lastRow = ws.LastRowUsed()?.RowNumber() ?? 0;
        for (int r = 2; r <= lastRow; r++)
        {
            if (ws.Cell(r, locCol).IsEmpty()) continue;
            var cell = ws.Cell(r, bc);
            string bid = cell.IsEmpty() ? DefaultBatchId : cell.GetString().Trim();
            if (string.IsNullOrEmpty(bid)) bid = DefaultBatchId;
            if (seen.Add(bid)) order.Add(bid);
        }
        return order.Count == 0 ? new List<string> { DefaultBatchId } : order;
    }

    // ── 共用 helpers（对照 AnchorExcelReader）──

    private static Dictionary<string, int> ReadHeaderMap(IXLWorksheet ws)
    {
        var map = new Dictionary<string, int>();
        var lastCol = ws.Row(1).LastCellUsed()?.Address.ColumnNumber ?? 0;
        for (int c = 1; c <= lastCol; c++)
        {
            var cell = ws.Cell(1, c);
            if (cell.IsEmpty()) continue;
            var key = CoatingColumns.NormalizeHeader(cell.GetString());
            if (!map.ContainsKey(key)) map[key] = c;
        }
        return map;
    }

    private static int RequireColumn(Dictionary<string, int> headerMap, string columnName, string description)
    {
        var key = CoatingColumns.NormalizeHeader(columnName);
        if (!headerMap.TryGetValue(key, out int col))
            throw new ArgumentException($"输入 Excel 缺少{description}（列名应为「{columnName}」）");
        return col;
    }

    private static int? TryColumn(Dictionary<string, int> headerMap, string columnName)
    {
        var key = CoatingColumns.NormalizeHeader(columnName);
        return headerMap.TryGetValue(key, out int col) ? col : null;
    }

    /// <summary>读数字单元格，容错去掉单位后缀（如 "24mm" → 24）。</summary>
    private static double ParseNumber(IXLCell cell, string what)
    {
        if (cell.IsEmpty())
            throw new ArgumentException($"{what}为空");
        if (cell.TryGetValue<double>(out double d)) return d;
        var s = cell.GetString().Trim();
        var num = new string(s.TakeWhile(c => char.IsDigit(c) || c == '.' || c == '-').ToArray());
        if (double.TryParse(num, out double v)) return v;
        throw new ArgumentException($"{what}非数字：{s}");
    }

    /// <summary>截面号容错解析：数字 / "截面3" 抽数字 / 否则回退序号。</summary>
    private static int ParseSectionNo(IXLCell? cell, int fallback)
    {
        if (cell is null || cell.IsEmpty()) return fallback;
        if (cell.TryGetValue<int>(out int iv)) return iv;
        if (cell.TryGetValue<double>(out double dv)) return (int)dv;
        var digits = new string(cell.GetString().Where(char.IsDigit).ToArray());
        return int.TryParse(digits, out int n) ? n : fallback;
    }
}
