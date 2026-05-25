// xlsx.* RPC 方法注册与实现 —— Excel 重资产场景（合并单元格 / 复杂样式 / 列宽 / 字体）。
//
// 当前方法：
//   xlsx.write_leeb_report_table(output_path, batches)
//     把里氏硬度的「报告插入表」sheet 追加到指定 xlsx（如果文件存在则追加 sheet，
//     不存在则新建）。每批一个 sheet，sheet 名 = batch.SheetName。
//
// 设计约束：
//   - 同一个 output_path 可能由 Python 端先写了「过程数据」sheet，C# 端追加「报告插入表」sheet
//   - 用 ClosedXML 的 XLWorkbook(path) 读已有工作簿，追加 sheet，再保存

using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.ReportTables;
using CivCore.Doc.Server;
using static CivCore.Doc.Server.AtomicFile;

namespace CivCore.Doc.Handlers;

public static class XlsxHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("xlsx.write_leeb_report_table", WriteLeebReportTable);
    }

    /// <summary>
    /// 把多个批的「报告插入表」追加到 output_path 指定的 xlsx。
    ///
    /// 入参（JSON object）：
    ///   {
    ///     "output_path": "...",
    ///     "batches": [
    ///       {
    ///         "sheet_name": "检测批1-报告插入表",
    ///         "components": [
    ///           {
    ///             "name": "地上一层1/A×（4~1/4）轴钢梁",
    ///             "thickness_mm": 6.0,
    ///             "test_areas_raw": [[454,461,446,...], [...], [...]],  // 3 测区 × 9 次
    ///             "comp_fb_min_avg": 534.3
    ///           }, ...
    ///         ],
    ///         "batch_fb_char_avg": 515.3
    ///       }, ...
    ///     ]
    ///   }
    ///
    /// 返回：{ "ok": true, "sheets_written": [str, ...] }
    /// </summary>
    public static object WriteLeebReportTable(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var outputPath = p.GetProperty("output_path").GetString()
            ?? throw new ArgumentException("未指定输出文件路径");
        var batchesEl = p.GetProperty("batches");
        if (batchesEl.ValueKind != JsonValueKind.Array)
            throw new ArgumentException("检测批数据格式错误");
        if (batchesEl.GetArrayLength() == 0)
            throw new ArgumentException("没有可写的报告数据（未检测到任何批次）");

        var batches = new List<LeebReportBatch>();
        foreach (var b in batchesEl.EnumerateArray())
        {
            batches.Add(ParseBatch(b));
        }

        // 文件存在则读已有 workbook 追加 sheet；否则新建
        XLWorkbook wb;
        if (File.Exists(outputPath))
        {
            wb = new XLWorkbook(outputPath);
        }
        else
        {
            wb = new XLWorkbook();
        }

        var sheetsWritten = new List<string>();
        using (wb)
        {
            foreach (var batch in batches)
            {
                // 如果同名 sheet 已存在（重复跑），先删除再加（覆盖语义）
                if (wb.Worksheets.TryGetWorksheet(batch.SheetName, out var existing))
                    existing.Delete();
                var ws = wb.Worksheets.Add(batch.SheetName);
                LeebReportTable.Write(ws, batch);
                sheetsWritten.Add(batch.SheetName);
            }
            SaveWorkbook(wb, outputPath);
        }

        return new Dictionary<string, object?>
        {
            ["ok"] = true,
            ["sheets_written"] = sheetsWritten,
        };
    }

    private static LeebReportBatch ParseBatch(JsonElement b)
    {
        var sheetName = b.GetProperty("sheet_name").GetString()
            ?? throw new ArgumentException("检测批名称缺失");
        var batchAvg = b.GetProperty("batch_fb_char_avg").GetDouble();

        var compsEl = b.GetProperty("components");
        if (compsEl.ValueKind != JsonValueKind.Array)
            throw new ArgumentException($"检测批「{sheetName}」的构件数据格式错误");
        if (compsEl.GetArrayLength() == 0)
            throw new ArgumentException($"检测批「{sheetName}」没有构件数据");

        var components = new List<LeebComponent>();
        foreach (var c in compsEl.EnumerateArray())
        {
            var name = c.GetProperty("name").GetString() ?? "";
            var thickness = c.GetProperty("thickness_mm").GetDouble();
            var compAvg = c.GetProperty("comp_fb_min_avg").GetDouble();

            var areasEl = c.GetProperty("test_areas_raw");
            if (areasEl.ValueKind != JsonValueKind.Array)
                throw new ArgumentException($"构件「{name}」的测区读数格式错误");
            if (areasEl.GetArrayLength() == 0)
                throw new ArgumentException($"构件「{name}」无测区原始读数，无法生成报告");

            var areas = new List<int[]>();
            foreach (var area in areasEl.EnumerateArray())
            {
                var readings = new List<int>();
                foreach (var r in area.EnumerateArray())
                    readings.Add(r.GetInt32());
                areas.Add(readings.ToArray());
            }

            components.Add(new LeebComponent(name, thickness, areas.ToArray(), compAvg));
        }

        return new LeebReportBatch(sheetName, components.ToArray(), batchAvg);
    }
}
