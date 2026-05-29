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
using DocumentFormat.OpenXml.Packaging;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.ReportTables;
using CivCore.Doc.Server;
using CivCore.Doc.Template;
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
        // report.run_from_result 重建 AnchorParams 用，避免用户再次输入工程参数）。
        // 报告内插表语义已迁到 Word，不再 Excel 出。
        XLWorkbook wb = File.Exists(outPath) ? new XLWorkbook(outPath) : new XLWorkbook();
        using (wb)
        {
            foreach (var br in result.BatchResults)
            {
                var analysisName = SafeSheetName($"{br.BatchId}-数据分析");
                if (wb.Worksheets.TryGetWorksheet(analysisName, out var old1)) old1.Delete();
                AnchorAnalysisSheet.Write(wb.Worksheets.Add(analysisName), br);
            }
            AnchorResultMetadataSheet.Write(wb, paramsByBatch);
            SaveWorkbook(wb, outPath);
        }

        // 可选 Word 报告：根据模板有没有 [[批次]]...[[/批次]] 段决定走单批 / 多批路径。
        //
        //   旧模板（只有 [[每根锚杆]]）        → ReportGenerator.Generate
        //   新模板（带 [[批次]]...[[/批次]]）  → ReportGenerator.GenerateMultiBatch
        //
        // 单批路径的兼容性补丁：用户旧模板里的 {{灌浆日期}} 仍能出值——
        // 取 batch_user_inputs 里第一个有值的 grouting_date 注入项目级 user_inputs。
        // 多批路径里每批 BatchResolver 用本批 grouting_date，跨批日期独立。
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
            // 模板探测：三层 [[检测项目]]>[[批次]]>[[每根锚杆]] / 两层 [[批次]]>[[每根锚杆]] / 单层
            var useMultiDetectionItem = TemplateHasMarker(wordTemplatePath, "[[检测项目]]");
            var useMultiBatch = TemplateHasBatchMarker(wordTemplatePath);

            ReportGenerateResult genResult;
            if (useMultiDetectionItem)
            {
                // 三层：当前装配线只 anchor 一种 calc，把所有批次包成单个 detection item
                // 项目级字段注入 detection_type 给 {{检测项目}} 占位符用。
                var itemLevel = new Dictionary<string, string>(userInputs);
                itemLevel["detection_type"] = "锚杆抗拔";
                itemLevel.TryAdd("inspection_item", "锚杆抗拔力（验收）检测");

                var sections = new List<BatchSection>();
                int anchorIndex = 0;
                foreach (var br in result.BatchResults)
                {
                    var batchLevel = new Dictionary<string, string>(itemLevel);
                    if (batchUserInputs.TryGetValue(br.BatchId, out var bui))
                    {
                        foreach (var kv in bui) batchLevel[kv.Key] = kv.Value;
                    }
                    batchLevel["batch_id"] = br.BatchId;

                    var batchRowResolvers = new List<IFieldResolver>();
                    foreach (var rw in br.RowsWithResults)
                    {
                        anchorIndex++;
                        batchRowResolvers.Add(new AnchorRowResolver(
                            rw.Input, rw.Result, br.Params, batchLevel,
                            anchorIndex: anchorIndex,
                            curveImageDir: curveImageDir,
                            batchId: br.BatchId));
                    }
                    sections.Add(new BatchSection(
                        new DictionaryResolver(batchLevel),
                        batchRowResolvers));
                }
                var items = new List<DetectionItemSection>
                {
                    new(new DictionaryResolver(itemLevel), sections),
                };
                var globalResolver = new DictionaryResolver(userInputs);
                genResult = ReportGenerator.GenerateMultiDetectionItem(
                    wordTemplatePath, globalResolver, items, wordOut,
                    catalog: AnchorFieldCatalog.All);
            }
            else if (useMultiBatch)
            {
                // 多批：每批一个 BatchSection（BatchResolver 注入项目级 + 本批批次级字段）
                var sections = new List<BatchSection>();
                int anchorIndex = 0;
                foreach (var br in result.BatchResults)
                {
                    // 本批 batch 级字段 = 项目级 ∪ 本批 batch_user_inputs ∪ {batch_id}
                    var batchLevel = new Dictionary<string, string>(userInputs);
                    if (batchUserInputs.TryGetValue(br.BatchId, out var bui))
                    {
                        foreach (var kv in bui) batchLevel[kv.Key] = kv.Value;
                    }
                    batchLevel["batch_id"] = br.BatchId;

                    var batchRowResolvers = new List<IFieldResolver>();
                    foreach (var rw in br.RowsWithResults)
                    {
                        anchorIndex++;
                        batchRowResolvers.Add(new AnchorRowResolver(
                            rw.Input, rw.Result, br.Params, batchLevel,
                            anchorIndex: anchorIndex,
                            curveImageDir: curveImageDir,
                            batchId: br.BatchId));
                    }

                    sections.Add(new BatchSection(
                        new DictionaryResolver(batchLevel),
                        batchRowResolvers));
                }
                var globalResolver = new DictionaryResolver(userInputs);
                genResult = ReportGenerator.GenerateMultiBatch(
                    wordTemplatePath, globalResolver, sections, wordOut,
                    catalog: AnchorFieldCatalog.All);
            }
            else
            {
                // 单批兼容：把 batch_user_inputs 里第一个有值的 grouting_date 灌入项目级
                var mergedInputs = new Dictionary<string, string>(userInputs);
                foreach (var bui in batchUserInputs.Values)
                {
                    if (bui.TryGetValue("grouting_date", out var v)
                        && !string.IsNullOrWhiteSpace(v)
                        && !mergedInputs.ContainsKey("grouting_date"))
                    {
                        mergedInputs["grouting_date"] = v;
                        break;
                    }
                }
                var projectResolver = new DictionaryResolver(mergedInputs);
                var rowResolvers = new List<IFieldResolver>();
                int anchorIndex = 0;
                foreach (var br in result.BatchResults)
                {
                    foreach (var rw in br.RowsWithResults)
                    {
                        anchorIndex++;
                        rowResolvers.Add(new AnchorRowResolver(
                            rw.Input, rw.Result, br.Params, mergedInputs,
                            anchorIndex: anchorIndex,
                            curveImageDir: curveImageDir,
                            batchId: br.BatchId));
                    }
                }
                genResult = ReportGenerator.Generate(
                    wordTemplatePath, projectResolver, rowResolvers, wordOut,
                    catalog: AnchorFieldCatalog.All);
            }

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

    /// <summary>
    /// 检测模板里有没有指定 marker 字符串（用来决定走哪条 ReportGenerator 路径）。
    /// 解析失败时 fallback 到 false——真要坏，ReportGenerator 会给出明确错误。
    /// </summary>
    private static bool TemplateHasMarker(string templatePath, string marker)
    {
        try
        {
            using var doc = WordprocessingDocument.Open(templatePath, false);
            var body = doc.MainDocumentPart?.Document?.Body;
            return body?.InnerText.Contains(marker) ?? false;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(
                $"[anchor.run] 探测 marker {marker} 失败，按未命中处理：{ex.Message}");
            return false;
        }
    }

    private static bool TemplateHasBatchMarker(string templatePath)
        => TemplateHasMarker(templatePath, "[[批次]]");

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

    private class DictionaryResolver : IFieldResolver
    {
        private readonly IReadOnlyDictionary<string, string> _v;
        public DictionaryResolver(IReadOnlyDictionary<string, string> v) => _v = v;
        public object? GetValue(string key) => _v.TryGetValue(key, out var s) ? s : null;
    }

    private static string SafeSheetName(string name)
    {
        var sb = new System.Text.StringBuilder();
        foreach (var c in name)
            sb.Append("/\\?*[]:".Contains(c) ? '_' : c);
        var safe = sb.ToString();
        return safe.Length > 31 ? safe.Substring(0, 31) : safe;
    }
}
