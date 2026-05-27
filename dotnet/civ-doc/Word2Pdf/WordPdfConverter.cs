// Word/WPS COM 引擎挂载 + Word → PDF 批量转换。
//
// 与 src/civ_core/infra_io/word_to_pdf.py 同：
//   - 优先 Word.Application，回退 KWPS.Application（WPS Office）
//   - DispatchEx 强制起新进程，避免与用户当前打开的 Word 共用进程
//   - 批量场景共用 1 个 Word 实例（启动 Word ~3 秒）；单文件失败不打断批量
//   - FileFormat=17 = wdFormatPDF；ReadOnly=1 防修改源文档

using System.Diagnostics.CodeAnalysis;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace CivCore.Doc.Word2Pdf;

[SupportedOSPlatform("windows")]
public static class WordPdfConverter
{
    private const int WdFormatPdf = 17;
    private const int WdDoNotSaveChanges = 0;

    public record ConvertResult(List<string> Written, List<(string Path, string Error)> Failed);

    /// <summary>
    /// 批量转换 inputs → outputDir 下的 .pdf 文件。共用 1 个 COM 实例。
    /// 单文件失败记入 Failed，不打断批量；inputs 为空抛 ArgumentException。
    /// </summary>
    public static ConvertResult ConvertBatch(IReadOnlyList<string> inputs, string outputDir)
    {
        if (inputs.Count == 0)
            throw new ArgumentException("输入列表为空（请至少添加 1 个 Word 文件再开始转换）");

        Directory.CreateDirectory(outputDir);
        var result = new ConvertResult(new List<string>(), new List<(string, string)>());

        var (app, engineName) = MountEngine();
        try
        {
            Console.Error.WriteLine($"[word2pdf] 引擎：{engineName} | 共 {inputs.Count} 个文件");
            foreach (var raw in inputs)
            {
                var src = raw;
                var stem = Path.GetFileNameWithoutExtension(src);
                var outPath = Path.Combine(outputDir, $"{stem}.pdf");
                try
                {
                    ConvertOneWithApp(app, src, outPath);
                    result.Written.Add(outPath);
                }
                catch (Exception e)
                {
                    Console.Error.WriteLine($"[word2pdf] 转换失败 {Path.GetFileName(src)}: {e.Message}");
                    result.Failed.Add((src, $"{e.GetType().Name}: {e.Message}"));
                }
            }
        }
        finally
        {
            QuitEngine(app);
        }
        return result;
    }

    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "dynamic COM interop")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "dynamic COM interop")]
    private static (dynamic App, string Name) MountEngine()
    {
        var wordType = Type.GetTypeFromProgID("Word.Application");
        if (wordType != null)
        {
            try
            {
                dynamic app = Activator.CreateInstance(wordType)!;
                app.Visible = false;
                app.DisplayAlerts = 0;
                return (app, "Microsoft Word");
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[word2pdf] Word 挂载失败，尝试 WPS：{ex.Message}");
            }
        }

        var wpsType = Type.GetTypeFromProgID("KWPS.Application");
        if (wpsType == null)
            throw new InvalidOperationException(
                "未检测到 Word 或 WPS 环境（Word 转 PDF 需要本机安装 Microsoft Word 或 WPS Office；请确认任一软件已正确安装、能正常启动）");
        dynamic wps = Activator.CreateInstance(wpsType)!;
        wps.Visible = false;
        wps.DisplayAlerts = 0;
        return (wps, "WPS Office");
    }

    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "dynamic COM interop")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "dynamic COM interop")]
    private static void ConvertOneWithApp(dynamic app, string inPath, string outPath)
    {
        if (!File.Exists(inPath))
            throw new FileNotFoundException($"输入文件不存在：{inPath}");
        var outDir = Path.GetDirectoryName(outPath);
        if (!string.IsNullOrEmpty(outDir))
            Directory.CreateDirectory(outDir);

        var absIn = Path.GetFullPath(inPath);
        var absOut = Path.GetFullPath(outPath);

        dynamic? doc = null;
        try
        {
            // ReadOnly=1 防止修改原文档；FileFormat=17 = wdFormatPDF
            doc = app.Documents.Open(absIn, ReadOnly: 1);
            doc.SaveAs(absOut, FileFormat: WdFormatPdf);
        }
        finally
        {
            if (doc != null)
            {
                try { doc.Close(WdDoNotSaveChanges); }
                catch (Exception e)
                {
                    Console.Error.WriteLine($"[word2pdf] 关闭文档失败（已忽略）：{e.Message}");
                }
            }
        }
    }

    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "dynamic COM interop")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "dynamic COM interop")]
    private static void QuitEngine(dynamic? app)
    {
        if (app == null) return;
        try
        {
            app.Quit();
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"[word2pdf] COM 引擎 Quit 失败（已忽略）：{e.Message}");
        }
        finally
        {
            if (Marshal.IsComObject((object)app))
                Marshal.FinalReleaseComObject((object)app);
        }
    }
}
