// pdf_tools.* RPC：PDF 合并 / 拆分 / 检视。
//
// 与 src/civ_core/api/handlers/pdf_tools.py 同协议：
//   pdf_tools.merge(inputs, output)                                   -> {output, count}
//   pdf_tools.split_per_page(input, output_dir, name_template?)       -> {written, count}
//   pdf_tools.split_by_ranges(input, output_dir, expr, name_template?) -> {written, count}
//   pdf_tools.inspect(paths)                                          -> {files, total_pages}

using System.Text.Json;
using CivCore.Doc.Pdf;
using CivCore.Doc.Server;

namespace CivCore.Doc.Handlers;

public static class PdfToolsHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("pdf_tools.merge", Merge);
        d.Register("pdf_tools.split_per_page", SplitPerPage);
        d.Register("pdf_tools.split_by_ranges", SplitByRanges);
        d.Register("pdf_tools.inspect", Inspect);
    }

    public static object Merge(JsonElement? @params)
    {
        var inputs = RequireStringArray(@params, "inputs");
        var output = RequireString(@params, "output");
        var saved = PdfMerger.Merge(inputs, output);
        return new Dictionary<string, object?>
        {
            ["output"] = saved,
            ["count"] = inputs.Count,
        };
    }

    public static object SplitPerPage(JsonElement? @params)
    {
        var input = RequireString(@params, "input");
        var outputDir = RequireString(@params, "output_dir");
        var nameTemplate = OptionalString(@params, "name_template", "{stem}_p{n}.pdf");
        var written = PdfMerger.SplitPerPage(input, outputDir, nameTemplate);
        return new Dictionary<string, object?>
        {
            ["written"] = written,
            ["count"] = written.Count,
        };
    }

    public static object SplitByRanges(JsonElement? @params)
    {
        var input = RequireString(@params, "input");
        var outputDir = RequireString(@params, "output_dir");
        var expr = RequireString(@params, "expr");
        var nameTemplate = OptionalString(@params, "name_template", "{stem}_{start}-{end}.pdf");
        var written = PdfMerger.SplitByRanges(input, outputDir, expr, nameTemplate);
        return new Dictionary<string, object?>
        {
            ["written"] = written,
            ["count"] = written.Count,
        };
    }

    public static object Inspect(JsonElement? @params)
    {
        var paths = RequireStringArray(@params, "paths");
        var files = new List<Dictionary<string, object?>>();
        int totalPages = 0;

        foreach (var p in paths)
        {
            var item = new Dictionary<string, object?> { ["path"] = p };
            if (!File.Exists(p))
            {
                item["error"] = $"文件不存在：{p}";
                files.Add(item);
                continue;
            }
            try
            {
                item["size_kb"] = Math.Round(new FileInfo(p).Length / 1024.0, 1);
            }
            catch (IOException e)
            {
                item["size_kb"] = null;
                item["error"] = $"读文件大小失败：{e.Message}";
                files.Add(item);
                continue;
            }
            var (pages, error) = PdfMerger.ReadPageCount(p);
            if (pages.HasValue)
            {
                item["pages"] = pages.Value;
                totalPages += pages.Value;
            }
            else if (error != null)
            {
                item["error"] = error;
            }
            files.Add(item);
        }

        return new Dictionary<string, object?>
        {
            ["files"] = files,
            ["total_pages"] = totalPages,
        };
    }

    private static string RequireString(JsonElement? @params, string key)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException($"缺少参数：{key}");
        if (!@params.Value.TryGetProperty(key, out var el) || el.ValueKind != JsonValueKind.String)
            throw new ArgumentException($"缺少参数：{key}");
        var s = el.GetString();
        if (string.IsNullOrEmpty(s))
            throw new ArgumentException($"参数 {key} 不能为空");
        return s;
    }

    private static string OptionalString(JsonElement? @params, string key, string defaultValue)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object) return defaultValue;
        if (!@params.Value.TryGetProperty(key, out var el)) return defaultValue;
        if (el.ValueKind != JsonValueKind.String) return defaultValue;
        var s = el.GetString();
        return string.IsNullOrEmpty(s) ? defaultValue : s;
    }

    private static List<string> RequireStringArray(JsonElement? @params, string key)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException($"缺少参数：{key}");
        if (!@params.Value.TryGetProperty(key, out var el) || el.ValueKind != JsonValueKind.Array)
            throw new ArgumentException($"参数 {key} 必须是字符串数组");
        var result = new List<string>(el.GetArrayLength());
        foreach (var item in el.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.String)
                throw new ArgumentException($"参数 {key} 必须是字符串数组（含非字符串元素）");
            var s = item.GetString();
            if (!string.IsNullOrEmpty(s)) result.Add(s);
        }
        return result;
    }
}
