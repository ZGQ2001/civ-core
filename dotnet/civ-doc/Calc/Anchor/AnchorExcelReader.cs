// 锚杆抗拔试验输入 Excel 读取。
//
// 两种格式自动识别：
//   1. 原始单 sheet：第一个 sheet 含「批次」列，所有锚杆混排，按列分组。
//   2. 数据处理多 sheet 结果：每批一个 sheet（名为「<batchId>-数据分析」），
//      无「批次」列，sheet 名即 batchId（去掉后缀）。
//
// 显式传 sheetName 时强制单 sheet 模式；不传时按第一个 sheet 有没有「批次」列
// 决定走哪条路径。列名按 AnchorColumns 契约，NormalizeHeader 抹平括号/空格/大小写差异。

using ClosedXML.Excel;

namespace CivCore.Doc.Calc.Anchor;

public static class AnchorExcelReader
{
    public record BatchRows(string BatchId, List<AnchorRowInput> Rows);

    /// <summary>多 sheet 结果文件里每个 sheet 名带的固定后缀（AnchorAnalysisSheet 写入约定）。</summary>
    private const string AnalysisSheetSuffix = "-数据分析";

    /// <summary>读 sheet 返回所有批次（不带 AnchorParams —— 那个由前端按批次输入）。</summary>
    public static List<BatchRows> ReadRows(
        string path,
        string? sheetName = null,
        string batchIdColumn = AnchorColumns.DefaultBatchIdColumn)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException($"文件不存在：{path}");

        using var wb = new XLWorkbook(path);
        if (sheetName != null || SheetHasColumn(wb.Worksheets.First(), batchIdColumn))
        {
            var ws = sheetName != null ? wb.Worksheet(sheetName) : wb.Worksheets.First();
            return ReadRowsSingleSheet(ws, batchIdColumn);
        }
        return ReadRowsMultiSheet(wb);
    }

    /// <summary>只读批次 ID 列表（前端「按批次填参数」表格需要预知 batch 列表）。</summary>
    public static List<string> ListBatchIds(
        string path,
        string? sheetName = null,
        string batchIdColumn = AnchorColumns.DefaultBatchIdColumn)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException($"文件不存在：{path}");

        using var wb = new XLWorkbook(path);
        if (sheetName != null || SheetHasColumn(wb.Worksheets.First(), batchIdColumn))
        {
            var ws = sheetName != null ? wb.Worksheet(sheetName) : wb.Worksheets.First();
            return ListBatchIdsSingleSheet(ws, batchIdColumn);
        }
        return ListBatchIdsMultiSheet(wb);
    }

    // ── 单 sheet 模式（原始输入格式） ──

    private static List<BatchRows> ReadRowsSingleSheet(IXLWorksheet ws, string batchIdColumn)
    {
        var headerMap = ReadHeaderMap(ws);
        int batchCol = RequireColumn(headerMap, batchIdColumn, "batch_id 列");
        int idCol = RequireColumn(headerMap, AnchorColumns.AnchorId, "锚杆编号列");
        int[] dispCols = AnchorColumns.DisplacementColumns
            .Select(name => RequireColumn(headerMap, name, $"位移读数列「{name}」"))
            .ToArray();

        var byBatch = new Dictionary<string, List<AnchorRowInput>>();
        var batchOrder = new List<string>();
        int lastRow = ws.LastRowUsed()?.RowNumber() ?? 0;

        for (int r = 2; r <= lastRow; r++)
        {
            var batchCell = ws.Cell(r, batchCol);
            var idCell = ws.Cell(r, idCol);
            if (batchCell.IsEmpty() && idCell.IsEmpty()) continue;

            string batchId = batchCell.IsEmpty() ? "" : batchCell.GetString().Trim();
            string anchorId = idCell.IsEmpty() ? "" : idCell.GetString().Trim();
            if (string.IsNullOrEmpty(batchId))
                throw new ArgumentException($"行 {r} 批次列为空");
            if (string.IsNullOrEmpty(anchorId))
                throw new ArgumentException($"行 {r} 锚杆编号为空");

            var disp = ReadDisplacements(ws, r, dispCols);
            var row = AnchorRowInput.Create(anchorId, disp);

            if (!byBatch.TryGetValue(batchId, out var list))
            {
                list = new List<AnchorRowInput>();
                byBatch[batchId] = list;
                batchOrder.Add(batchId);
            }
            list.Add(row);
        }

        return batchOrder.Select(b => new BatchRows(b, byBatch[b])).ToList();
    }

    private static List<string> ListBatchIdsSingleSheet(IXLWorksheet ws, string batchIdColumn)
    {
        var headerMap = ReadHeaderMap(ws);
        int batchCol = RequireColumn(headerMap, batchIdColumn, "batch_id 列");

        var seen = new HashSet<string>();
        var order = new List<string>();
        int lastRow = ws.LastRowUsed()?.RowNumber() ?? 0;
        for (int r = 2; r <= lastRow; r++)
        {
            var cell = ws.Cell(r, batchCol);
            if (cell.IsEmpty()) continue;
            string bid = cell.GetString().Trim();
            if (string.IsNullOrEmpty(bid)) continue;
            if (seen.Add(bid)) order.Add(bid);
        }
        return order;
    }

    // ── 多 sheet 模式（数据处理输出格式） ──
    //
    // 每个含「锚杆编号」列的 sheet 视为一批；sheet 名（去掉 -数据分析 后缀）= batchId。
    // 不含「锚杆编号」列的 sheet 直接跳过（容忍报告内插表等辅助 sheet 共存）。

    private static List<BatchRows> ReadRowsMultiSheet(XLWorkbook wb)
    {
        var byBatch = new Dictionary<string, List<AnchorRowInput>>();
        var batchOrder = new List<string>();
        string anchorIdKey = AnchorColumns.NormalizeHeader(AnchorColumns.AnchorId);

        foreach (var ws in wb.Worksheets)
        {
            var headerMap = ReadHeaderMap(ws);
            if (!headerMap.ContainsKey(anchorIdKey)) continue;

            string batchId = ExtractBatchIdFromSheetName(ws.Name);
            if (string.IsNullOrEmpty(batchId)) continue;

            int idCol = headerMap[anchorIdKey];
            int[] dispCols = AnchorColumns.DisplacementColumns
                .Select(name => RequireColumn(headerMap, name, $"位移读数列「{name}」（sheet「{ws.Name}」）"))
                .ToArray();

            int lastRow = ws.LastRowUsed()?.RowNumber() ?? 0;
            for (int r = 2; r <= lastRow; r++)
            {
                var idCell = ws.Cell(r, idCol);
                if (idCell.IsEmpty()) continue;
                string anchorId = idCell.GetString().Trim();
                if (string.IsNullOrEmpty(anchorId)) continue;
                // 「合格率：X/Y」汇总行没有数字位移读数 —— 跳过
                if (anchorId.StartsWith("合格率")) continue;

                var disp = ReadDisplacements(ws, r, dispCols);
                var row = AnchorRowInput.Create(anchorId, disp);

                if (!byBatch.TryGetValue(batchId, out var list))
                {
                    list = new List<AnchorRowInput>();
                    byBatch[batchId] = list;
                    batchOrder.Add(batchId);
                }
                list.Add(row);
            }
        }

        if (batchOrder.Count == 0)
            throw new ArgumentException(
                "未找到批次：第一个 sheet 无「批次」列，且没有任何 sheet 含「锚杆编号」列。" +
                "若是原始输入请加「批次」列；若是数据处理结果请检查 sheet 是否完整。");

        return batchOrder.Select(b => new BatchRows(b, byBatch[b])).ToList();
    }

    private static List<string> ListBatchIdsMultiSheet(XLWorkbook wb)
    {
        var ids = new List<string>();
        var seen = new HashSet<string>();
        string anchorIdKey = AnchorColumns.NormalizeHeader(AnchorColumns.AnchorId);

        foreach (var ws in wb.Worksheets)
        {
            var headerMap = ReadHeaderMap(ws);
            if (!headerMap.ContainsKey(anchorIdKey)) continue;
            string bid = ExtractBatchIdFromSheetName(ws.Name);
            if (string.IsNullOrEmpty(bid)) continue;
            if (seen.Add(bid)) ids.Add(bid);
        }
        return ids;
    }

    private static string ExtractBatchIdFromSheetName(string sheetName)
    {
        var name = (sheetName ?? "").Trim();
        if (name.EndsWith(AnalysisSheetSuffix))
            name = name.Substring(0, name.Length - AnalysisSheetSuffix.Length);
        return name.Trim();
    }

    // ── 共用 helpers ──

    private static bool SheetHasColumn(IXLWorksheet ws, string columnName)
    {
        var headerMap = ReadHeaderMap(ws);
        var key = AnchorColumns.NormalizeHeader(columnName);
        return headerMap.ContainsKey(key);
    }

    private static Dictionary<string, int> ReadHeaderMap(IXLWorksheet ws)
    {
        var map = new Dictionary<string, int>();
        var lastCol = ws.Row(1).LastCellUsed()?.Address.ColumnNumber ?? 0;
        for (int c = 1; c <= lastCol; c++)
        {
            var cell = ws.Cell(1, c);
            if (cell.IsEmpty()) continue;
            var key = AnchorColumns.NormalizeHeader(cell.GetString());
            if (!map.ContainsKey(key)) map[key] = c;
        }
        return map;
    }

    private static int RequireColumn(
        Dictionary<string, int> headerMap, string columnName, string description)
    {
        var key = AnchorColumns.NormalizeHeader(columnName);
        if (!headerMap.TryGetValue(key, out int col))
            throw new ArgumentException(
                $"输入 Excel 缺少{description}（列名应为「{columnName}」）");
        return col;
    }

    private static AnchorDisplacements ReadDisplacements(IXLWorksheet ws, int row, int[] cols)
    {
        var vals = new double[11];
        for (int i = 0; i < 11; i++)
        {
            var cell = ws.Cell(row, cols[i]);
            if (cell.IsEmpty())
            {
                vals[i] = 0;
                continue;
            }
            if (!cell.TryGetValue<double>(out double d))
                throw new ArgumentException(
                    $"行 {row} 列「{AnchorColumns.DisplacementColumns[i]}」位移读数非数字：{cell.GetString()}");
            vals[i] = d;
        }
        return new AnchorDisplacements(
            vals[0], vals[1], vals[2], vals[3],
            vals[4], vals[5], vals[6],
            vals[7], vals[8], vals[9], vals[10]);
    }
}
