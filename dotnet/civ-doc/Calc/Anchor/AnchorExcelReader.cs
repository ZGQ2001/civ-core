// 锚杆抗拔试验输入 Excel 读取：所有锚杆在 1 个 sheet，按 batchIdColumn 列分组。
// 列名按 AnchorColumns 契约，NormalizeHeader 抹平括号/空格/大小写差异。

using ClosedXML.Excel;

namespace CivCore.Doc.Calc.Anchor;

public static class AnchorExcelReader
{
    public record BatchRows(string BatchId, List<AnchorRowInput> Rows);

    /// <summary>读 sheet 返回所有批次（不带 AnchorParams —— 那个由前端按批次输入）。</summary>
    public static List<BatchRows> ReadRows(
        string path,
        string? sheetName = null,
        string batchIdColumn = AnchorColumns.DefaultBatchIdColumn)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException($"文件不存在：{path}");

        using var wb = new XLWorkbook(path);
        var ws = sheetName != null
            ? wb.Worksheet(sheetName)
            : wb.Worksheets.First();

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

    /// <summary>只读批次 ID 列表（前端「按批次填参数」表格需要预知 batch 列表）。</summary>
    public static List<string> ListBatchIds(
        string path,
        string? sheetName = null,
        string batchIdColumn = AnchorColumns.DefaultBatchIdColumn)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException($"文件不存在：{path}");

        using var wb = new XLWorkbook(path);
        var ws = sheetName != null ? wb.Worksheet(sheetName) : wb.Worksheets.First();

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
