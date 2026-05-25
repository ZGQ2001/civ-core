// leeb.* RPC 方法注册与实现（对应 Python src/civ_core/api/handlers/leeb.py）。
//
// 当前方法：
//   leeb.run(input_xlsx, output_xlsx?, angle_degrees=0.0)
//     -> {batches, components, output, report_table_data}
//   leeb.preview_excel(path, sheet?, header_row=1, max_rows=50)
//     -> {sheets, sheet, headers, rows, total_rows, shown_rows}
//
// 行为契约跟 Python 端完全一致：只算数据不写文件，输出 xlsx 由前端串行调
// xlsx.write_leeb_report_table 创建。

using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Leeb;
using CivCore.Doc.Server;
using CivCore.Doc.Standards;

namespace CivCore.Doc.Handlers;

public static class LeebHandlers
{
    private const string CalcTypeSuffix = "里氏";  // 输出文件名检测类型段

    public static void RegisterAll(Dispatcher d)
    {
        d.Register("leeb.run", Run);
        d.Register("leeb.preview_excel", PreviewExcel);
    }

    /// <summary>
    /// 读 Excel → 套规范 → 算硬度 → 返回 report_table_data（不写文件）。
    /// 前端拿到后串行调 xlsx.write_leeb_report_table 让 C# ClosedXML 写精致 xlsx。
    /// </summary>
    public static object Run(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        string? outputXlsx = p.TryGetProperty("output_xlsx", out var outEl)
            && outEl.ValueKind == JsonValueKind.String
            ? outEl.GetString() : null;
        double angleDegrees = p.TryGetProperty("angle_degrees", out var angEl)
            ? angEl.GetDouble() : 0.0;

        // 默认输出路径：<input 同级>/<stem>_里氏_结果.xlsx
        var src = new FileInfo(inputXlsx);
        string outPath = outputXlsx
            ?? Path.Combine(src.DirectoryName ?? "",
                $"{Path.GetFileNameWithoutExtension(src.Name)}_{CalcTypeSuffix}_结果.xlsx");

        // 读 Excel + 算
        var workbook = LeebExcelReader.ReadWorkbook(
            inputXlsx, defaultAngleDegrees: angleDegrees);
        LeebHardnessWorkbookResult result;
        using (var db = StandardsDb.OpenDefault())
        {
            result = LeebCalculator.CalcWorkbook(workbook, db);
        }

        // 组装 report_table_data（前端转交 xlsx.write_leeb_report_table）
        var reportTableData = new List<Dictionary<string, object?>>();
        foreach (var br in result.BatchResults)
        {
            var components = new List<Dictionary<string, object?>>();
            foreach (var (input, compResult) in br.ComponentsWithResults)
            {
                components.Add(new Dictionary<string, object?>
                {
                    ["name"] = input.Name,
                    ["thickness_mm"] = input.Thickness,
                    ["test_areas_raw"] = input.TestAreasRaw.Select(a => (object)a).ToList(),
                    ["comp_fb_min_avg"] = compResult.CompFbMinAvg,
                });
            }
            reportTableData.Add(new Dictionary<string, object?>
            {
                ["sheet_name"] = SafeSheetName(br.BatchName),
                ["components"] = components,
                ["batch_fb_char_avg"] = br.BatchFbCharAvg,
            });
        }

        return new Dictionary<string, object?>
        {
            ["batches"] = result.NBatches,
            ["components"] = result.NComponentsTotal,
            ["output"] = outPath,
            ["report_table_data"] = reportTableData,
        };
    }

    /// <summary>读 Excel 前 N 行预览（data_processing 工具页中间表格用）。</summary>
    public static object PreviewExcel(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var path = p.GetProperty("path").GetString()
            ?? throw new ArgumentException("未指定 Excel 文件路径");
        if (!File.Exists(path))
            throw new ArgumentException($"文件不存在：{path}");
        string? sheetParam = p.TryGetProperty("sheet", out var sEl)
            && sEl.ValueKind == JsonValueKind.String ? sEl.GetString() : null;
        int headerRow = p.TryGetProperty("header_row", out var hEl) ? hEl.GetInt32() : 1;
        int maxRows = p.TryGetProperty("max_rows", out var mEl) ? mEl.GetInt32() : 50;
        if (maxRows < 1) maxRows = 1;

        using var wb = new XLWorkbook(path);
        var sheets = wb.Worksheets.Select(w => w.Name).ToList();
        if (sheets.Count == 0)
        {
            return new Dictionary<string, object?>
            {
                ["sheets"] = sheets, ["sheet"] = "",
                ["headers"] = new List<string>(), ["rows"] = new List<object>(),
                ["total_rows"] = 0, ["shown_rows"] = 0,
            };
        }

        string actualSheet = sheetParam != null && sheets.Contains(sheetParam)
            ? sheetParam : sheets[0];
        var ws = wb.Worksheet(actualSheet);

        // 表头行
        var headers = new List<string>();
        int maxCol = 0;
        var lastCol = ws.Row(headerRow).LastCellUsed()?.Address.ColumnNumber ?? 0;
        for (int c = 1; c <= lastCol; c++)
        {
            var cell = ws.Cell(headerRow, c);
            if (!cell.IsEmpty())
            {
                headers.Add(cell.GetString().Trim());
                maxCol = c;
            }
            else
            {
                headers.Add("");
            }
        }
        // 去掉末尾空 header（保持跟 Python get_column_headers 一致：只返非空表头）
        var nonEmptyHeaders = headers.Where(h => !string.IsNullOrEmpty(h)).ToList();

        // 数据行
        var rows = new List<Dictionary<string, object?>>();
        int totalRows = 0;
        int lastUsedRow = ws.LastRowUsed()?.RowNumber() ?? 0;
        for (int r = headerRow + 1; r <= lastUsedRow; r++)
        {
            // 整行空跳过（跟 Python 行为一致）
            bool allEmpty = true;
            for (int c = 1; c <= maxCol; c++)
            {
                if (!ws.Cell(r, c).IsEmpty()) { allEmpty = false; break; }
            }
            if (allEmpty) continue;

            totalRows++;
            if (rows.Count >= maxRows) continue;

            var rowDict = new Dictionary<string, object?>();
            for (int c = 1; c <= maxCol; c++)
            {
                if (string.IsNullOrEmpty(headers[c - 1])) continue;
                var cell = ws.Cell(r, c);
                rowDict[headers[c - 1]] = JsonifyCellValue(cell);
            }
            rows.Add(rowDict);
        }

        return new Dictionary<string, object?>
        {
            ["sheets"] = sheets,
            ["sheet"] = actualSheet,
            ["headers"] = nonEmptyHeaders,
            ["rows"] = rows,
            ["total_rows"] = totalRows,
            ["shown_rows"] = rows.Count,
        };
    }

    private static object? JsonifyCellValue(IXLCell cell)
    {
        if (cell.IsEmpty()) return null;
        // 优先数字，其次布尔，其次字符串
        if (cell.TryGetValue<double>(out double d))
        {
            // 整数判断（避免 12.0 显示成 12.0）
            if (d == Math.Truncate(d) && !double.IsInfinity(d) && Math.Abs(d) < 1e15)
                return (long)d;
            return d;
        }
        if (cell.TryGetValue<bool>(out bool b)) return b;
        return cell.GetString();
    }

    /// <summary>Excel sheet 名长度上限 31 字符，且不能含 / \ ? * [ ] : —— 跟 Python _safe_sheet_name 等价。</summary>
    private static string SafeSheetName(string name)
    {
        var sb = new System.Text.StringBuilder();
        foreach (var c in name)
            sb.Append("/\\?*[]:".Contains(c) ? '_' : c);
        var safe = sb.ToString();
        return safe.Length > 31 ? safe.Substring(0, 31) : safe;
    }
}
