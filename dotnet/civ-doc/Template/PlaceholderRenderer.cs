// 占位符报告渲染器 —— 主路径：用户在 Word 里直接写 {key} 或 {中文名}，
// 引擎扫指定范围所有段落替换成实际值。
//
// 公开两条 API：
//   - Render(sourcePath, outputPath, resolver, catalog): 拷文件 + 全文档替换
//   - RenderInto(scope, resolver, catalog): 在已打开的 OpenXml 子树上替换
//     （给 ReportGenerator 在 cloned Table 上做局部替换用）
//
// 设计取舍：
//   - 段落级合并 Run 文本再替换 —— 解决 Word 把 {弹性位移量} 拆成多 Run 的麻烦。
//     代价：丢失同段落内多 Run 的字体差异（极少见，可接受）。
//   - 缺失 key 留原文 + 加 unknownKeys 报告 —— 不阻断生成，让用户能见到没填上的占位符。

using System.Text.RegularExpressions;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace CivCore.Doc.Template;

public class PlaceholderRenderException : Exception
{
    public PlaceholderRenderException(string msg) : base(msg) { }
}

/// <summary>渲染结果：替换计数 + 找不到的 key 列表（给前端做警告用）。</summary>
public record PlaceholderRenderResult(int Replaced, IReadOnlyList<string> UnknownKeys);

public static class PlaceholderRenderer
{
    /// <summary>匹配 {key} 形态；key 允许字母数字下划线 + 中文（不含 { } 本身）。</summary>
    private static readonly Regex PlaceholderPattern =
        new(@"\{([^{}\r\n]+?)\}", RegexOptions.Compiled);

    /// <summary>拷贝 sourcePath 到 outputPath，全文档替换占位符。</summary>
    public static PlaceholderRenderResult Render(
        string sourcePath,
        string outputPath,
        IFieldResolver resolver,
        IReadOnlyList<FieldDef>? catalog = null)
    {
        if (!File.Exists(sourcePath))
            throw new PlaceholderRenderException($"Word 模板文件不存在：{sourcePath}");

        var dir = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            Directory.CreateDirectory(dir);
        File.Copy(sourcePath, outputPath, overwrite: true);

        using var doc = WordprocessingDocument.Open(outputPath, true);
        var body = doc.MainDocumentPart?.Document?.Body
            ?? throw new PlaceholderRenderException("输出 docx 结构异常");

        var result = RenderInto(body, resolver, catalog);
        doc.MainDocumentPart!.Document.Save();
        return result;
    }

    /// <summary>
    /// 在已打开的 OpenXml 子树上替换占位符 —— 不碰文件 IO，可在 cloned Table 这类
    /// 子树上调用。给 ReportGenerator 做"克隆表 + 局部替换"用。
    /// </summary>
    public static PlaceholderRenderResult RenderInto(
        OpenXmlElement scope,
        IFieldResolver resolver,
        IReadOnlyList<FieldDef>? catalog = null)
    {
        var nameToKey = BuildNameIndex(catalog);
        var unknownKeys = new List<string>();
        int replaced = 0;

        // scope 自身是 Paragraph 时也要处理；Descendants<Paragraph> 不含 scope 自身
        var paragraphs = scope is Paragraph selfPara
            ? new[] { selfPara }.Concat(scope.Descendants<Paragraph>()).Distinct()
            : scope.Descendants<Paragraph>();

        foreach (var para in paragraphs.ToList())
            ProcessParagraph(para, resolver, nameToKey, ref replaced, unknownKeys);

        return new PlaceholderRenderResult(replaced, unknownKeys.Distinct().ToList());
    }

    // ── 段落级替换 ──────────────────────────────────────────

    private static void ProcessParagraph(
        Paragraph para,
        IFieldResolver resolver,
        IReadOnlyDictionary<string, string> nameToKey,
        ref int replaced,
        List<string> unknownKeys)
    {
        var runs = para.Elements<Run>().ToList();
        if (runs.Count == 0) return;

        var combined = string.Concat(runs.SelectMany(r => r.Elements<Text>()).Select(t => t.Text));
        if (!PlaceholderPattern.IsMatch(combined)) return;

        // 局部计数器（lambda 不能捕获 ref/out 参数；段落处理完再加到外层）
        int localReplaced = 0;
        var newText = PlaceholderPattern.Replace(combined, m =>
        {
            var raw = m.Groups[1].Value.Trim();
            var key = ResolveKey(raw, nameToKey);
            var val = resolver.GetValue(key);
            if (val == null && !nameToKey.ContainsKey(NormName(raw)))
            {
                unknownKeys.Add(raw);
                return m.Value;
            }
            localReplaced++;
            return val?.ToString() ?? "";
        });
        replaced += localReplaced;

        if (newText == combined) return;

        // 保留首 Run 的 rPr，重写整段
        var firstRunProps = runs[0].RunProperties?.CloneNode(true) as RunProperties;
        foreach (var r in runs) r.Remove();

        var newRun = new Run();
        if (firstRunProps != null) newRun.AppendChild(firstRunProps);
        newRun.AppendChild(new Text(newText) { Space = SpaceProcessingModeValues.Preserve });
        para.AppendChild(newRun);
    }

    // ── helpers ────────────────────────────────────────────

    private static IReadOnlyDictionary<string, string> BuildNameIndex(
        IReadOnlyList<FieldDef>? catalog)
    {
        if (catalog == null) return new Dictionary<string, string>();
        var d = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var f in catalog) d[NormName(f.Name)] = f.Key;
        return d;
    }

    private static string NormName(string s) => s.Trim();

    private static string ResolveKey(string raw, IReadOnlyDictionary<string, string> nameToKey)
    {
        // char.IsLetterOrDigit 在 .NET 对中文字符也返回 true —— Key 严格限定 ASCII
        if (IsKeyLike(raw)) return raw;
        return nameToKey.TryGetValue(NormName(raw), out var k) ? k : raw;
    }

    private static bool IsKeyLike(string s)
    {
        foreach (var c in s)
        {
            bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
                || (c >= '0' && c <= '9') || c == '_';
            if (!ok) return false;
        }
        return s.Length > 0;
    }
}
