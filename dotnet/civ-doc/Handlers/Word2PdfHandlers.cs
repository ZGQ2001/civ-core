// word2pdf.* RPC：Word → PDF 批量转换 + docx 体量检视。
//
// 与 src/civ_core/api/handlers/word2pdf.py 同协议：
//   word2pdf.convert(inputs, output_dir) -> {written: [str], failed: [{path, error}], total}
//   word2pdf.inspect(paths)              -> {files: [{path, size_kb, paragraphs, pages?, error?}]}
//
// 渲染策略（多套以保排版精度，按平台取）：
//   - Windows：Word/WPS COM 走 dynamic（与原 Python pywin32 同语义；精度 100%）
//   - macOS：未实现，抛 PlatformNotSupportedException + 提示（真有 Mac 用户后补
//     Microsoft Word for Mac via AppleScript）
//   - Linux：同上，未实现
// 跨平台「降级」渲染（LibreOffice / Pages）会牺牲 ~5% 排版精度，不在当前选项里
// —— 检测报告对甲方模板还原度要求高，宁可平台少也不能让精度打折。

using System.Text.Json;
using CivCore.Doc.Server;
using CivCore.Doc.Word2Pdf;

namespace CivCore.Doc.Handlers;

public static class Word2PdfHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("word2pdf.convert", Convert);
        d.Register("word2pdf.inspect", Inspect);
    }

    public static object Convert(JsonElement? @params)
    {
        var inputs = RequireStringArray(@params, "inputs");
        var outputDir = RequireString(@params, "output_dir");

        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException(
                "word2pdf.convert 当前只支持 Windows（走 Word/WPS COM）。" +
                "macOS / Linux 渲染方案尚未实现 —— 见 dotnet/civ-doc/Handlers/Word2PdfHandlers.cs 顶部注释。");

        var result = WordPdfConverter.ConvertBatch(inputs, outputDir);
        return new Dictionary<string, object?>
        {
            ["written"] = result.Written,
            ["failed"] = result.Failed.Select(f => new Dictionary<string, object?>
            {
                ["path"] = f.Path,
                ["error"] = f.Error,
            }).ToList(),
            ["total"] = inputs.Count,
        };
    }

    public static object Inspect(JsonElement? @params)
    {
        var paths = RequireStringArray(@params, "paths");
        var files = new List<Dictionary<string, object?>>();
        foreach (var p in paths)
        {
            var item = DocxInspector.Inspect(p);
            var dict = new Dictionary<string, object?> { ["path"] = item.Path };
            if (item.SizeKb.HasValue) dict["size_kb"] = item.SizeKb.Value;
            if (item.Paragraphs.HasValue) dict["paragraphs"] = item.Paragraphs.Value;
            if (item.Pages.HasValue) dict["pages"] = item.Pages.Value;
            if (item.Error != null) dict["error"] = item.Error;
            files.Add(dict);
        }
        return new Dictionary<string, object?> { ["files"] = files };
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
