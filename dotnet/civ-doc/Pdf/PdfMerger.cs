// PDF 合并 / 拆分。
//
// 与 src/civ_core/infra_io/pdf_io.py 同：
//   • 顺序合并 inputs → 1 个 PDF；落盘走 atomic 写（先写 .tmp 再 rename）
//   • 单文件拆分：每页一个 PDF / 按范围分段
//   • 单输入文件读失败抛 ArgumentException（hint 让 UI 三段式提示能直接消费）

using PdfSharp.Pdf;
using PdfSharp.Pdf.IO;

namespace CivCore.Doc.Pdf;

public static class PdfMerger
{
    public static string Merge(IReadOnlyList<string> inputs, string outputPath)
    {
        if (inputs.Count == 0)
            throw new ArgumentException("合并列表为空（请至少加入 1 个 PDF）");

        EnsureParentDir(outputPath);

        using var output = new PdfDocument();
        foreach (var raw in inputs)
        {
            if (!File.Exists(raw))
                throw new ArgumentException($"输入文件不存在：{raw}");
            try
            {
                using var input = PdfReader.Open(raw, PdfDocumentOpenMode.Import);
                for (int i = 0; i < input.PageCount; i++)
                    output.AddPage(input.Pages[i]);
            }
            catch (PdfReaderException e)
            {
                throw new ArgumentException(
                    $"无法读取 {Path.GetFileName(raw)}：{e.Message}（该 PDF 可能损坏或被加密）", e);
            }
        }

        AtomicSave(output, outputPath);
        return outputPath;
    }

    public static List<string> SplitPerPage(string inputPath, string outputDir, string nameTemplate)
    {
        if (!File.Exists(inputPath))
            throw new ArgumentException($"输入 PDF 不存在：{inputPath}");
        Directory.CreateDirectory(outputDir);

        PdfDocument input;
        try
        {
            input = PdfReader.Open(inputPath, PdfDocumentOpenMode.Import);
        }
        catch (PdfReaderException e)
        {
            throw new ArgumentException(
                $"无法打开 {Path.GetFileName(inputPath)}：{e.Message}（该 PDF 可能损坏或加密）", e);
        }
        try
        {
            int total = input.PageCount;
            if (total == 0)
                throw new ArgumentException($"{Path.GetFileName(inputPath)} 没有任何页（无法拆分）");

            int width = Math.Max(2, total.ToString().Length);
            var stem = Path.GetFileNameWithoutExtension(inputPath);
            var written = new List<string>(total);

            for (int i = 0; i < total; i++)
            {
                using var doc = new PdfDocument();
                doc.AddPage(input.Pages[i]);

                var n = (i + 1).ToString().PadLeft(width, '0');
                var outName = FormatTemplate(nameTemplate,
                    ("stem", stem), ("n", n));
                var outPath = Path.Combine(outputDir, outName);
                AtomicSave(doc, outPath);
                written.Add(outPath);
            }
            return written;
        }
        finally
        {
            input.Dispose();
        }
    }

    public static List<string> SplitByRanges(
        string inputPath, string outputDir, string expr, string nameTemplate)
    {
        if (!File.Exists(inputPath))
            throw new ArgumentException($"输入 PDF 不存在：{inputPath}");
        Directory.CreateDirectory(outputDir);

        PdfDocument input;
        try
        {
            input = PdfReader.Open(inputPath, PdfDocumentOpenMode.Import);
        }
        catch (PdfReaderException e)
        {
            throw new ArgumentException(
                $"无法打开 {Path.GetFileName(inputPath)}：{e.Message}（该 PDF 可能损坏或加密）", e);
        }
        try
        {
            int total = input.PageCount;
            var ranges = PageRangeParser.Parse(expr, total);
            var stem = Path.GetFileNameWithoutExtension(inputPath);
            var written = new List<string>(ranges.Count);

            foreach (var r in ranges)
            {
                using var doc = new PdfDocument();
                for (int i = r.StartIndex; i < r.EndIndex; i++)
                    doc.AddPage(input.Pages[i]);

                var outName = FormatTemplate(nameTemplate,
                    ("stem", stem),
                    ("start", r.Start1.ToString()),
                    ("end", r.End1.ToString()));
                var outPath = Path.Combine(outputDir, outName);
                AtomicSave(doc, outPath);
                written.Add(outPath);
            }
            return written;
        }
        finally
        {
            input.Dispose();
        }
    }

    /// <summary>
    /// 读 PDF 页数（用于 inspect）。损坏/加密返 null + error 字符串，让批量 inspect 单文件失败不影响整体。
    /// </summary>
    public static (int? Pages, string? Error) ReadPageCount(string path)
    {
        if (!File.Exists(path))
            return (null, $"文件不存在：{path}");
        try
        {
            using var doc = PdfReader.Open(path, PdfDocumentOpenMode.Import);
            return (doc.PageCount, null);
        }
        catch (PdfReaderException e)
        {
            return (null, $"解析失败：{e.GetType().Name}: {e.Message}");
        }
        catch (IOException e)
        {
            return (null, $"读文件失败：{e.GetType().Name}: {e.Message}");
        }
    }

    // ── 内部 helpers ──

    private static void EnsureParentDir(string path)
    {
        var dir = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(dir))
            Directory.CreateDirectory(dir);
    }

    /// <summary>原子保存：先写 .tmp，再 File.Move 覆盖。失败不留半截文件。</summary>
    private static void AtomicSave(PdfDocument doc, string targetPath)
    {
        EnsureParentDir(targetPath);
        var tmp = targetPath + ".tmp." + Guid.NewGuid().ToString("N")[..8];
        try
        {
            doc.Save(tmp);
            if (File.Exists(targetPath)) File.Delete(targetPath);
            File.Move(tmp, targetPath);
        }
        catch
        {
            try { if (File.Exists(tmp)) File.Delete(tmp); }
            catch { /* 忽略清理失败 */ }
            throw;
        }
    }

    /// <summary>
    /// 简化版字符串模板：把 "{key}" 替换为对应值。不支持嵌套 / format spec，与 Python str.format
    /// 在单层占位场景下行为一致。模板里有未提供的 key 保留原样不报错。
    /// </summary>
    private static string FormatTemplate(string template, params (string Key, string Value)[] subs)
    {
        var result = template;
        foreach (var (k, v) in subs)
            result = result.Replace("{" + k + "}", v);
        return result;
    }
}
