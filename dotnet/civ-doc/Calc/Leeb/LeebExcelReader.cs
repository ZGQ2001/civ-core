// 里氏硬度报检单 Excel 读取（对应 Python src/civ_core/infra_io/leeb_excel.py 的 read_leeb_workbook
// 和 read_leeb_components）。用 ClosedXML，合并单元格 / 复杂格式比 Python openpyxl 强。
//
// D 号站房格式锁定列位置：
//   A (1): 序号
//   B (2): 构件位置
//   C-K (3-11): HL1..HL9（9 列）
//   L (12): 厚度（mm）
//   P (16): 检测批名（可选；多构件共享同一批名时跨行继承）
//
// 行结构：每构件占 rows_per_component（默认 3）行；第 1 行带序号/名字/厚度，
// 后 2 行只有 HL 值（A/B/L 列为空，因为 Excel 用合并单元格视觉占位）。

using ClosedXML.Excel;

namespace CivCore.Doc.Calc.Leeb;

public static class LeebExcelReader
{
    // 列位置常量（1-based，跟 ClosedXML 的 Cell(row, col) 约定一致）
    private const int ColSeq = 1;
    private const int ColName = 2;
    private const int ColHlStart = 3;
    private const int ColHlCount = 9;
    private const int ColThickness = 12;
    private const int ColBatch = 16;

    /// <summary>读整个 xlsx → LeebHardnessWorkbook（每个 sheet = 一个检测批）。</summary>
    public static LeebHardnessWorkbook ReadWorkbook(
        string path,
        double defaultAngleDegrees = 0.0,
        string? sheetNameFilter = null)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException($"文件不存在：{path}");

        using var wb = new XLWorkbook(path);
        var batches = new List<LeebHardnessBatch>();

        foreach (var ws in wb.Worksheets)
        {
            if (sheetNameFilter != null && !ws.Name.Contains(sheetNameFilter))
                continue;

            List<LeebHardnessComponentInput> components;
            try
            {
                components = ReadComponents(
                    ws,
                    rowsPerComponent: 3,
                    headerRows: 1,
                    defaultAngleDegrees: defaultAngleDegrees);
            }
            catch (ArgumentException)
            {
                // sheet 没有可解析数据（可能是元信息 sheet 如「委托信息」）—— 跳过
                continue;
            }

            if (components.Count == 0) continue;

            // 把 sheet 名注入每个构件作为 batch_name（覆盖 Excel 内可能写的旧名）
            var withBatch = components
                .Select(c => c with { BatchName = ws.Name })
                .ToArray();

            batches.Add(new LeebHardnessBatch(BatchName: ws.Name, Components: withBatch));
        }

        if (batches.Count == 0)
            throw new ArgumentException(
                $"未找到可解析的 sheet（过滤={sheetNameFilter ?? "无"}）");

        return new LeebHardnessWorkbook(batches.ToArray());
    }

    /// <summary>从一个 sheet 读多构件里氏硬度数据。</summary>
    public static List<LeebHardnessComponentInput> ReadComponents(
        IXLWorksheet ws,
        int rowsPerComponent = 3,
        int headerRows = 1,
        double defaultAngleDegrees = -90.0)
    {
        var components = new List<LeebHardnessComponentInput>();
        string currentBatchName = "";
        int maxRow = ws.LastRowUsed()?.RowNumber() ?? 0;
        int row = headerRows + 1;

        while (row <= maxRow)
        {
            var seqCell = ws.Cell(row, ColSeq);
            var hlStartCell = ws.Cell(row, ColHlStart);

            // 跳过完全空行（A 和 C 都空）
            if (seqCell.IsEmpty() && hlStartCell.IsEmpty())
            {
                row += 1;
                continue;
            }

            // 跳过子表头：A 列非数字字面量（如"序号"）
            if (!seqCell.IsEmpty() && !IsNumeric(seqCell))
            {
                row += 1;
                continue;
            }

            // 跳过 C 列非数字的异常行
            if (!IsNumeric(hlStartCell))
            {
                row += 1;
                continue;
            }

            // 读 P 列检测批名（跨行继承）
            var batchCell = ws.Cell(row, ColBatch);
            if (!batchCell.IsEmpty())
            {
                var batchStr = batchCell.GetString().Trim();
                if (batchStr.Length > 0) currentBatchName = batchStr;
            }

            // 读 rows_per_component 行 × 9 列 HL 数据
            var testAreas = new List<int[]>();
            for (int offset = 0; offset < rowsPerComponent; offset++)
            {
                int r = row + offset;
                if (r > maxRow) break;
                var hlValues = new int[ColHlCount];
                for (int cOff = 0; cOff < ColHlCount; cOff++)
                {
                    var cell = ws.Cell(r, ColHlStart + cOff);
                    if (cell.IsEmpty())
                        throw new ArgumentException(
                            $"行 {r} 列 {ColumnLetter(ColHlStart + cOff)} HL 值缺失（构件第 {offset + 1} 测区）");
                    if (!cell.TryGetValue<double>(out double hlD))
                        throw new ArgumentException(
                            $"行 {r} 列 {ColumnLetter(ColHlStart + cOff)} HL 值非数字：{cell.GetString()}");
                    hlValues[cOff] = (int)Math.Round(hlD);
                }
                testAreas.Add(hlValues);
            }

            // 序号 / 构件位置 / 厚度
            int seq = seqCell.IsEmpty()
                ? components.Count + 1
                : (int)seqCell.GetDouble();
            string name = ws.Cell(row, ColName).GetString().Trim();
            if (string.IsNullOrEmpty(name))
                throw new ArgumentException($"行 {row} 构件位置（B 列）为空");

            var thicknessCell = ws.Cell(row, ColThickness);
            if (thicknessCell.IsEmpty())
                throw new ArgumentException($"行 {row} 厚度（L 列）缺失");
            if (!thicknessCell.TryGetValue<double>(out double thickness) || thickness <= 0)
                throw new ArgumentException(
                    $"行 {row} 厚度无效：{thicknessCell.GetString()}");

            components.Add(LeebHardnessComponentInput.Create(
                seq: seq,
                name: name,
                thickness: thickness,
                angleDegrees: defaultAngleDegrees,
                testAreasRaw: testAreas.ToArray(),
                batchName: currentBatchName));

            row += rowsPerComponent;
        }

        if (components.Count == 0)
            throw new ArgumentException(
                $"sheet '{ws.Name}' 未读到任何构件数据（请确认每 {rowsPerComponent} 行一构件）");

        return components;
    }

    private static bool IsNumeric(IXLCell cell)
    {
        if (cell.IsEmpty()) return false;
        return cell.TryGetValue<double>(out _);
    }

    private static string ColumnLetter(int col)
    {
        // A=1, B=2, ..., Z=26, AA=27 ...
        string s = "";
        while (col > 0)
        {
            int rem = (col - 1) % 26;
            s = (char)('A' + rem) + s;
            col = (col - 1) / 26;
        }
        return s;
    }
}
