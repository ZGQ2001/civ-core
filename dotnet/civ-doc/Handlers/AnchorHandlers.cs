// anchor.* RPC 方法注册与实现（GB 50086-2015 锚杆抗拔试验）。
//
// 方法清单：
//   anchor.generate_template(output_xlsx, standard?)
//     -> {ok, path}
//   anchor.list_batches(input_xlsx, sheet?, batch_id_column?)
//     -> {batches: [str, ...]}
//   anchor.run(input_xlsx, output_xlsx?, standard, batch_id_column?, params_by_batch)
//     -> {batches, anchors_total, anchors_qualified, output}
//
// 输出 xlsx 由 anchor.run 直接写（不像 leeb 那样拆 Python+C# 两步——这里全 C#，
// 没有跨 sidecar 协作）。每批 2 sheet：「<批>-数据分析」+「<批>-报告内插表」。

using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.ReportTables;
using CivCore.Doc.Server;
using static CivCore.Doc.Server.AtomicFile;

namespace CivCore.Doc.Handlers;

public static class AnchorHandlers
{
    private const string CalcTypeSuffix = "锚杆";

    public static void RegisterAll(Dispatcher d)
    {
        d.Register("anchor.generate_template", GenerateTemplate);
        d.Register("anchor.list_batches", ListBatches);
        d.Register("anchor.read_batch_info", ReadBatchInfo);
        d.Register("anchor.run", Run);
    }

    /// <summary>生成空白输入模板。前端「生成模板」按钮调。</summary>
    public static object GenerateTemplate(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var outputXlsx = p.GetProperty("output_xlsx").GetString()
            ?? throw new ArgumentException("未指定输出文件路径");
        string standard = p.TryGetProperty("standard", out var sEl)
            && sEl.ValueKind == JsonValueKind.String
            ? sEl.GetString() ?? AnchorStandards.GB_50086_2015
            : AnchorStandards.GB_50086_2015;

        var outDir = Path.GetDirectoryName(outputXlsx);
        if (!string.IsNullOrEmpty(outDir) && !Directory.Exists(outDir))
            throw new ArgumentException($"输出目录不存在：{outDir}");

        AnchorTemplateWriter.Write(outputXlsx, standard);

        return new Dictionary<string, object?>
        {
            ["ok"] = true,
            ["path"] = outputXlsx,
        };
    }

    /// <summary>读输入 Excel 返回所有批次 ID（前端 SettingsForm 按批次填参数前用）。</summary>
    public static object ListBatches(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        string? sheet = p.TryGetProperty("sheet", out var sEl)
            && sEl.ValueKind == JsonValueKind.String ? sEl.GetString() : null;
        string batchCol = p.TryGetProperty("batch_id_column", out var bEl)
            && bEl.ValueKind == JsonValueKind.String
            ? bEl.GetString() ?? AnchorColumns.DefaultBatchIdColumn
            : AnchorColumns.DefaultBatchIdColumn;

        FileGuard.CheckExcelSize(inputXlsx);
        var batches = AnchorExcelReader.ListBatchIds(inputXlsx, sheet, batchCol);
        return new Dictionary<string, object?> { ["batches"] = batches };
    }

    /// <summary>
    /// 读输入 Excel 的「批次信息」sheet → 各批工程参数 + 灌浆日期，给前端预填表单。
    /// sheet 缺失（旧模板 / 别人给的 Excel）返回空列表，前端回退默认值。
    /// </summary>
    public static object ReadBatchInfo(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");

        FileGuard.CheckExcelSize(inputXlsx);
        var infos = AnchorBatchInfoSheet.Read(inputXlsx);

        return new Dictionary<string, object?>
        {
            ["batches"] = infos.Select(i => new Dictionary<string, object?>
            {
                ["batch_id"] = i.BatchId,
                ["params"] = i.Params is { } prm
                    ? new Dictionary<string, object?>
                    {
                        ["P"] = prm.AxialDesignLoad,
                        ["Lf"] = prm.FreeLength,
                        ["La"] = prm.AnchorLength,
                        ["A"] = prm.SteelArea,
                        ["E"] = prm.ElasticModulus,
                    }
                    : null,
                ["grouting_date"] = i.GroutingDate,
            }).ToList(),
        };
    }

    /// <summary>读 Excel + 按批次套参数 + 算 + 写两个 sheet/批 输出。</summary>
    public static object Run(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        string? outputXlsx = p.TryGetProperty("output_xlsx", out var outEl)
            && outEl.ValueKind == JsonValueKind.String ? outEl.GetString() : null;
        string standard = p.TryGetProperty("standard", out var sEl)
            && sEl.ValueKind == JsonValueKind.String
            ? sEl.GetString() ?? AnchorStandards.GB_50086_2015
            : AnchorStandards.GB_50086_2015;
        string? sheet = p.TryGetProperty("sheet", out var shEl)
            && shEl.ValueKind == JsonValueKind.String ? shEl.GetString() : null;
        string batchCol = p.TryGetProperty("batch_id_column", out var bEl)
            && bEl.ValueKind == JsonValueKind.String
            ? bEl.GetString() ?? AnchorColumns.DefaultBatchIdColumn
            : AnchorColumns.DefaultBatchIdColumn;

        FileGuard.CheckExcelSize(inputXlsx);

        // 可选 Word 模板路径（带占位符 + [[每根锚杆]] 锚点）。给了就出 Word 报告。
        string? wordTemplatePath = p.TryGetProperty("word_template_path", out var wtEl)
            && wtEl.ValueKind == JsonValueKind.String ? wtEl.GetString() : null;
        string? wordOutputDir = p.TryGetProperty("word_output_dir", out var woEl)
            && woEl.ValueKind == JsonValueKind.String ? woEl.GetString() : null;
        // 曲线图目录（可选）：传给 AnchorRowResolver，{{img:曲线图}} 自动按 anchor_id 拼路径
        string? curveImageDir = p.TryGetProperty("curve_image_dir", out var ciEl)
            && ciEl.ValueKind == JsonValueKind.String ? ciEl.GetString() : null;
        // 报告名称（可选）：影响 Word 输出文件名；留空走默认「锚杆抗拔报告.docx」
        string? reportName = p.TryGetProperty("report_name", out var rnEl)
            && rnEl.ValueKind == JsonValueKind.String ? rnEl.GetString() : null;
        // 报告里锚杆结果表的节号（可选）：单根→「表{节号}」/多根→「表{节号}-1…」，缺省 2.4
        string sectionNo = p.TryGetProperty("section_no", out var snEl)
            && snEl.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(snEl.GetString())
            ? snEl.GetString()!
            : AnchorWordTable.DefaultSectionNo;
        // 项目级用户输入字段（可选）：{ client_name, project_name, test_date, ... }
        var userInputs = p.TryGetProperty("user_inputs", out var uiEl) && uiEl.ValueKind == JsonValueKind.Object
            ? ParseUserInputs(uiEl)
            : new Dictionary<string, string>();
        // 批次级用户输入（可选）：{ "B1": { "grouting_date": "2026-05-01" }, "B2": {...} }
        // 模板有 [[批次]]...[[/批次]] 时按批次注入；没有时退化为单批模式（取第一个有值的批
        // 的 grouting_date 灌到项目级，兼容旧模板）。
        var batchUserInputs = p.TryGetProperty("batch_user_inputs", out var buiEl)
            && buiEl.ValueKind == JsonValueKind.Object
            ? ParseBatchUserInputs(buiEl)
            : new Dictionary<string, Dictionary<string, string>>();

        // params_by_batch（可选）: { "B1": {P,Lf,La,A,E}, ... }。前端 GUI 填了就传。
        var paramsByBatch = p.TryGetProperty("params_by_batch", out var pbEl)
            && pbEl.ValueKind == JsonValueKind.Object
            ? ParseParamsByBatch(pbEl)
            : new Dictionary<string, AnchorParams>();

        // 「批次信息」sheet 回退：GUI 没传的批次工程参数 / 灌浆日期，从输入 xlsx 的
        // 「批次信息」sheet 补上 —— 让「填到 xlsx 就不用在 GUI 再填」成立，也让 agent
        // 只写一个 xlsx 即可跑。优先级：GUI 传入 > sheet（TryAdd 不覆盖已有）。
        foreach (var info in AnchorBatchInfoSheet.Read(inputXlsx))
        {
            if (info.Params is { } prm)
                paramsByBatch.TryAdd(info.BatchId, prm);
            if (!string.IsNullOrWhiteSpace(info.GroutingDate))
            {
                if (!batchUserInputs.TryGetValue(info.BatchId, out var bui))
                {
                    bui = new Dictionary<string, string>();
                    batchUserInputs[info.BatchId] = bui;
                }
                bui.TryAdd("grouting_date", info.GroutingDate);
            }
        }

        AnchorStandards.Validate(standard);

        var src = new FileInfo(inputXlsx);
        string outPath = outputXlsx
            ?? Path.Combine(src.DirectoryName ?? "",
                $"{Path.GetFileNameWithoutExtension(src.Name)}_{CalcTypeSuffix}_结果.xlsx");

        // 读输入
        var batchRows = AnchorExcelReader.ReadRows(inputXlsx, sheet, batchCol);

        // 缺参数批次 → 报错（前端应在 list_batches 后引导用户填齐）
        var missing = batchRows.Where(b => !paramsByBatch.ContainsKey(b.BatchId))
            .Select(b => b.BatchId).ToList();
        if (missing.Count > 0)
            throw new ArgumentException(
                $"以下批次缺工程参数（在 GUI 按批次填，或在输入 Excel 的「批次信息」sheet 填）："
                + string.Join(", ", missing));

        // 装配 workbook
        var batches = batchRows.Select(b => new AnchorBatchInput(
            b.BatchId, paramsByBatch[b.BatchId], b.Rows.ToArray())).ToArray();
        var workbook = new AnchorWorkbookInput(standard, batches);

        // 算
        var result = AnchorCalculator.Calc(workbook);

        // 写 Excel 输出：每批 1 sheet（数据分析） + 1 隐藏 sheet（批次参数 metadata，供
        // report.run_from_result 重建 AnchorParams + 拿灌浆日期用，避免用户再次输入）。
        // 报告内插表语义已迁到 Word，不再 Excel 出。
        //
        // 持久化灌浆日期：取 batchUserInputs（已并入「批次信息」sheet 回退）里每批的
        // grouting_date 写进 metadata sheet 第 7 列 —— 让结果 xlsx 自带日期，result 路径
        // 不再依赖 GUI/预设。
        var groutingDateByBatch = new Dictionary<string, string>();
        foreach (var (batchId, bui) in batchUserInputs)
        {
            if (bui.TryGetValue("grouting_date", out var date)
                && !string.IsNullOrWhiteSpace(date))
                groutingDateByBatch[batchId] = date;
        }
        XLWorkbook wb = File.Exists(outPath) ? new XLWorkbook(outPath) : new XLWorkbook();
        using (wb)
        {
            foreach (var br in result.BatchResults)
            {
                var analysisName = Calc.SheetNameUtil.Safe($"{br.BatchId}-数据分析");
                if (wb.Worksheets.TryGetWorksheet(analysisName, out var old1)) old1.Delete();
                AnchorAnalysisSheet.Write(wb.Worksheets.Add(analysisName), br);
            }
            AnchorJudgmentBasisSheet.Write(wb); // 演算稿：判定公式 + 规范条款（可见，reader 不回读）
            AnchorResultMetadataSheet.Write(wb, paramsByBatch, groutingDateByBatch);
            SaveWorkbook(wb, outPath);
        }

        // 可选 Word 报告：程序按规范建「逐根 表2.4」插进模板的 {{表格:锚杆}} 占位符 + 填薄壳。
        // 各批 grouting_date 已并入 batchUserInputs（含「批次信息」sheet 回退），表内按批出值。
        var wordOutputs = new List<string>();
        var wordUnknownKeys = new List<string>();
        var wordMissingImages = new List<string>();
        if (!string.IsNullOrWhiteSpace(wordTemplatePath))
        {
            var wordDir = !string.IsNullOrWhiteSpace(wordOutputDir)
                ? wordOutputDir
                : Path.Combine(src.DirectoryName ?? "", $"{Path.GetFileNameWithoutExtension(src.Name)}_Word报告");
            Directory.CreateDirectory(wordDir);

            var wordFileName = !string.IsNullOrWhiteSpace(reportName)
                ? (reportName!.EndsWith(".docx", StringComparison.OrdinalIgnoreCase)
                    ? reportName!
                    : $"{reportName}.docx")
                : "锚杆抗拔报告.docx";
            var wordOut = Path.Combine(wordDir, SafeFileName(wordFileName));

            var genResult = AnchorWordTable.GenerateReport(
                wordTemplatePath, wordOut, result, userInputs, batchUserInputs, curveImageDir, sectionNo);

            wordOutputs.Add(wordOut);
            wordUnknownKeys.AddRange(genResult.UnknownKeys);
            wordMissingImages.AddRange(genResult.MissingImages);
            // stderr 日志一份（方便用户在 BottomPanel 看具体哪些字段/图片缺）
            if (genResult.UnknownKeys.Count > 0)
                Console.Error.WriteLine(
                    $"[anchor.run] Word 报告 unknown keys: {string.Join(", ", genResult.UnknownKeys)}");
            if (genResult.MissingImages.Count > 0)
                Console.Error.WriteLine(
                    $"[anchor.run] Word 报告 missing images: {string.Join(", ", genResult.MissingImages)}");
        }

        var res = new Dictionary<string, object?>
        {
            ["batches"] = result.NBatches,
            ["anchors_total"] = result.NRowsTotal,
            ["anchors_qualified"] = result.NQualifiedTotal,
            ["output"] = outPath,
        };
        if (wordOutputs.Count > 0)
        {
            res["word_outputs"] = wordOutputs;
            res["word_unknown_keys"] = wordUnknownKeys;
            res["word_missing_images"] = wordMissingImages;
        }
        return res;
    }

    private static Dictionary<string, string> ParseUserInputs(JsonElement el)
    {
        var d = new Dictionary<string, string>();
        foreach (var prop in el.EnumerateObject())
        {
            if (prop.Value.ValueKind == JsonValueKind.String)
                d[prop.Name] = prop.Value.GetString() ?? "";
        }
        return d;
    }

    /// <summary>解析 batch_user_inputs: { batchId: { key: value } }。容错：跳过非字符串。</summary>
    private static Dictionary<string, Dictionary<string, string>> ParseBatchUserInputs(JsonElement el)
    {
        var d = new Dictionary<string, Dictionary<string, string>>();
        foreach (var batchProp in el.EnumerateObject())
        {
            if (batchProp.Value.ValueKind != JsonValueKind.Object) continue;
            d[batchProp.Name] = ParseUserInputs(batchProp.Value);
        }
        return d;
    }

    private static string SafeFileName(string s)
    {
        foreach (var c in Path.GetInvalidFileNameChars()) s = s.Replace(c, '_');
        return s;
    }

    private static Dictionary<string, AnchorParams> ParseParamsByBatch(JsonElement el)
    {
        if (el.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("各批次工程参数格式错误");
        var result = new Dictionary<string, AnchorParams>();
        foreach (var prop in el.EnumerateObject())
        {
            var ap = prop.Value;
            if (ap.ValueKind != JsonValueKind.Object)
                throw new ArgumentException($"批次「{prop.Name}」的工程参数格式错误");
            double p = ap.GetProperty("P").GetDouble();
            double lf = ap.GetProperty("Lf").GetDouble();
            double la = ap.GetProperty("La").GetDouble();
            double a = ap.GetProperty("A").GetDouble();
            double e = ap.GetProperty("E").GetDouble();
            result[prop.Name] = AnchorParams.Create(p, lf, la, a, e);
        }
        return result;
    }
}
