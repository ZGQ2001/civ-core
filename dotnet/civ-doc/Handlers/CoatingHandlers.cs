// coating.* RPC 方法注册与实现（GB 50205-2020 §13.4.3 厚涂型防火涂料涂层厚度验收）。
//
// 方法清单：
//   coating.generate_template(output_xlsx, standard?)
//     -> {ok, path}
//   coating.list_batches(input_xlsx, sheet?, batch_id_column?)
//     -> {batches: [str, ...]}
//   coating.run(input_xlsx, output_xlsx?, standard?, sheet?, batch_id_column?)
//     -> {batches, members_total, members_qualified, output}
//
// 与 anchor 的差异：设计厚度在输入 Excel 列里（按构件），不需要前端按批次填工程参数，
// 故无 params_by_batch / read_batch_info。输出每批一个「<批>-数据分析」宽表 sheet。

using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;
using CivCore.Doc.ReportTables;
using CivCore.Doc.Server;
using static CivCore.Doc.Server.AtomicFile;

namespace CivCore.Doc.Handlers;

public static class CoatingHandlers
{
    private const string CalcTypeSuffix = "防火涂层";

    public static void RegisterAll(Dispatcher d)
    {
        d.Register("coating.generate_template", GenerateTemplate);
        d.Register("coating.list_batches", ListBatches);
        d.Register("coating.run", Run);
    }

    /// <summary>生成空白输入模板。前端「生成模板」按钮调。</summary>
    public static object GenerateTemplate(JsonElement? @params)
    {
        var p = RequireObject(@params);

        var outputXlsx = p.GetProperty("output_xlsx").GetString()
            ?? throw new ArgumentException("未指定输出文件路径");
        string standard = OptString(p, "standard") ?? CoatingStandards.GB_50205_2020;

        var outDir = Path.GetDirectoryName(outputXlsx);
        if (!string.IsNullOrEmpty(outDir) && !Directory.Exists(outDir))
            throw new ArgumentException($"输出目录不存在：{outDir}");

        CoatingTemplateWriter.Write(outputXlsx, standard);

        return new Dictionary<string, object?> { ["ok"] = true, ["path"] = outputXlsx };
    }

    /// <summary>读输入 Excel 返回所有批次 ID（信息性；批次列缺失时返回单元素默认批）。</summary>
    public static object ListBatches(JsonElement? @params)
    {
        var p = RequireObject(@params);

        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        string? sheet = OptString(p, "sheet");
        string batchCol = OptString(p, "batch_id_column") ?? CoatingColumns.DefaultBatchIdColumn;

        FileGuard.CheckExcelSize(inputXlsx);
        var batches = CoatingExcelReader.ListBatchIds(inputXlsx, sheet, batchCol);
        return new Dictionary<string, object?> { ["batches"] = batches };
    }

    /// <summary>读 Excel + 按构件聚合判定 + 每批写一个宽表 sheet。</summary>
    public static object Run(JsonElement? @params)
    {
        var p = RequireObject(@params);

        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        string? outputXlsx = OptString(p, "output_xlsx");
        string standard = OptString(p, "standard") ?? CoatingStandards.GB_50205_2020;
        string? sheet = OptString(p, "sheet");
        string batchCol = OptString(p, "batch_id_column") ?? CoatingColumns.DefaultBatchIdColumn;

        FileGuard.CheckExcelSize(inputXlsx);
        CoatingStandards.Validate(standard);

        var src = new FileInfo(inputXlsx);
        string outPath = outputXlsx
            ?? Path.Combine(src.DirectoryName ?? "",
                $"{Path.GetFileNameWithoutExtension(src.Name)}_{CalcTypeSuffix}_结果.xlsx");

        var batchMembers = CoatingExcelReader.ReadRows(inputXlsx, sheet, batchCol);
        var batches = batchMembers
            .Select(b => new CoatingBatchInput(b.BatchId, b.Members.ToArray()))
            .ToArray();
        var workbook = new CoatingWorkbookInput(standard, batches);

        var result = CoatingCalculator.Calc(workbook);

        XLWorkbook wb = File.Exists(outPath) ? new XLWorkbook(outPath) : new XLWorkbook();
        using (wb)
        {
            foreach (var br in result.BatchResults)
            {
                var name = SafeSheetName($"{br.BatchId}-数据分析");
                if (wb.Worksheets.TryGetWorksheet(name, out var old)) old.Delete();
                CoatingAnalysisSheet.Write(wb.Worksheets.Add(name), br);
            }
            SaveWorkbook(wb, outPath);
        }

        return new Dictionary<string, object?>
        {
            ["batches"] = result.NBatches,
            ["members_total"] = result.NMembersTotal,
            ["members_qualified"] = result.NQualifiedTotal,
            ["output"] = outPath,
        };
    }

    // ── helpers ──

    private static JsonElement RequireObject(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        return @params.Value;
    }

    private static string? OptString(JsonElement p, string name)
        => p.TryGetProperty(name, out var el) && el.ValueKind == JsonValueKind.String
            ? el.GetString()
            : null;

    private static string SafeSheetName(string name)
    {
        var sb = new System.Text.StringBuilder();
        foreach (var c in name)
            sb.Append("/\\?*[]:".Contains(c) ? '_' : c);
        var safe = sb.ToString();
        return safe.Length > 31 ? safe.Substring(0, 31) : safe;
    }
}
