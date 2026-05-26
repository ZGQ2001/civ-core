// 占位符报告渲染器 —— 主路径：用户在 Word 里直接写 {{key}} 或 {{中文名}}，
// 引擎扫指定范围所有段落替换成实际值。
//
// 公开两条 API：
//   - Render(sourcePath, outputPath, resolver, catalog): 拷文件 + 全文档替换
//   - RenderInto(scope, resolver, catalog, mainPart): 在已打开的 OpenXml 子树上替换
//     （给 ReportGenerator 在 cloned Table 上做局部替换用）
//
// 设计取舍：
//   - 段落级合并 Run 文本再替换 —— 解决 Word 把 {{弹性位移量}} 拆成多 Run 的麻烦。
//     代价：丢失同段落内多 Run 的字体差异（极少见，可接受）。
//   - 缺失 key 留原文 + 加 unknownKeys 报告 —— 不阻断生成，让用户能见到没填上的占位符。
//   - 数值字段按 catalog 的 DefaultFormat 格式化（如 "0.00" → 保留 2 位小数），
//     避免 Word 里出现 1.23456789 这种裸 double。
//   - 图片占位符 {{img:xxx}} —— resolver 返图片路径，引擎自动嵌入 OpenXML Drawing。
//     文件不存在或没传 mainPart 时留原文 + 加 missingImages 报告。
//     段落里图片与文本混排时，按位置切成多个 Run（文本 Run + 图片 Run）。

using System.Globalization;
using System.Text.RegularExpressions;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace CivCore.Doc.Template;

public class PlaceholderRenderException : Exception
{
    public PlaceholderRenderException(string msg) : base(msg) { }
}

/// <summary>渲染结果：替换计数 + 找不到的 key 列表 + 找不到的图片路径列表（给前端做警告用）。</summary>
public record PlaceholderRenderResult(
    int Replaced,
    IReadOnlyList<string> UnknownKeys)
{
    /// <summary>
    /// 图片占位符（{{img:xxx}}）解析失败的 raw 串（含 img: 前缀）。
    /// 失败原因：mainPart=null、resolver 返 null、文件不存在、PNG 头读不动等。
    /// 默认空列表，向后兼容 record positional 构造。
    /// </summary>
    public IReadOnlyList<string> MissingImages { get; init; } = Array.Empty<string>();
}

public static class PlaceholderRenderer
{
    /// <summary>匹配 {{key}} 形态；key 允许字母数字下划线 + 中文（不含 { } 本身）。</summary>
    private static readonly Regex PlaceholderPattern =
        new(@"\{\{([^{}\r\n]+?)\}\}", RegexOptions.Compiled);

    /// <summary>图片占位符前缀 —— 用户写 {{img:曲线图}} 引擎当图嵌入。</summary>
    private const string ImagePrefix = "img:";

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
        var mainPart = doc.MainDocumentPart
            ?? throw new PlaceholderRenderException("输出 docx 结构异常（缺 MainDocumentPart）");
        var body = mainPart.Document?.Body
            ?? throw new PlaceholderRenderException("输出 docx 结构异常（缺 Body）");

        var result = RenderInto(body, resolver, catalog, mainPart);
        mainPart.Document.Save();
        return result;
    }

    /// <summary>
    /// 在已打开的 OpenXml 子树上替换占位符 —— 不碰文件 IO，可在 cloned Table 这类
    /// 子树上调用。给 ReportGenerator 做"克隆表 + 局部替换"用。
    /// </summary>
    /// <param name="mainPart">
    /// 含 ImageParts 的 MainDocumentPart。仅当模板含 {{img:xxx}} 时需要；
    /// 旧调用方不嵌图传 null 即可（遇图片占位符会留原文+加 missingImages 报告）。
    /// </param>
    public static PlaceholderRenderResult RenderInto(
        OpenXmlElement scope,
        IFieldResolver resolver,
        IReadOnlyList<FieldDef>? catalog = null,
        MainDocumentPart? mainPart = null)
    {
        var catalogIndex = BuildCatalogIndex(catalog);
        var unknownKeys = new List<string>();
        var missingImages = new List<string>();
        int replaced = 0;

        // scope 自身是 Paragraph 时也要处理；Descendants<Paragraph> 不含 scope 自身
        var paragraphs = scope is Paragraph selfPara
            ? new[] { selfPara }.Concat(scope.Descendants<Paragraph>()).Distinct()
            : scope.Descendants<Paragraph>();

        foreach (var para in paragraphs.ToList())
            ProcessParagraph(para, resolver, catalogIndex, mainPart,
                ref replaced, unknownKeys, missingImages);

        return new PlaceholderRenderResult(replaced, unknownKeys.Distinct().ToList())
        {
            MissingImages = missingImages.Distinct().ToList(),
        };
    }

    // ── 段落级替换 ──────────────────────────────────────────

    /// <summary>段落切片：文本片段（含未替换原文）or 图片片段（含图片路径）。</summary>
    private abstract record Segment;
    private sealed record TextSegment(string Text) : Segment;
    private sealed record ImageSegment(string ImagePath) : Segment;

    private static void ProcessParagraph(
        Paragraph para,
        IFieldResolver resolver,
        CatalogIndex catalog,
        MainDocumentPart? mainPart,
        ref int replaced,
        List<string> unknownKeys,
        List<string> missingImages)
    {
        var runs = para.Elements<Run>().ToList();
        if (runs.Count == 0) return;

        var combined = string.Concat(runs.SelectMany(r => r.Elements<Text>()).Select(t => t.Text));
        if (!PlaceholderPattern.IsMatch(combined)) return;

        // 解析所有占位符，按位置切段
        var matches = PlaceholderPattern.Matches(combined);
        var segments = new List<Segment>();
        int cursor = 0;
        int localReplaced = 0;
        bool hasImage = false;

        foreach (Match m in matches)
        {
            if (m.Index > cursor)
                segments.Add(new TextSegment(combined.Substring(cursor, m.Index - cursor)));

            var raw = m.Groups[1].Value.Trim();
            if (raw.StartsWith(ImagePrefix, StringComparison.OrdinalIgnoreCase))
            {
                // 图片占位符 {{img:xxx}}
                var imgKey = raw.Substring(ImagePrefix.Length).Trim();
                var (key, _) = catalog.Resolve(imgKey);
                var val = resolver.GetValue(key);
                var imgPath = val?.ToString();
                if (mainPart == null || string.IsNullOrWhiteSpace(imgPath) || !File.Exists(imgPath))
                {
                    missingImages.Add(raw);
                    segments.Add(new TextSegment(m.Value)); // 留原文
                }
                else
                {
                    segments.Add(new ImageSegment(imgPath));
                    localReplaced++;
                    hasImage = true;
                }
            }
            else
            {
                // 文本占位符 {{xxx}}
                var (key, fieldDef) = catalog.Resolve(raw);
                var val = resolver.GetValue(key);
                if (val == null && fieldDef == null)
                {
                    unknownKeys.Add(raw);
                    segments.Add(new TextSegment(m.Value)); // 留原文
                }
                else
                {
                    segments.Add(new TextSegment(FormatValue(val, fieldDef)));
                    localReplaced++;
                }
            }
            cursor = m.Index + m.Length;
        }
        if (cursor < combined.Length)
            segments.Add(new TextSegment(combined.Substring(cursor)));

        replaced += localReplaced;

        // 没图片 + 替换后字符串没变 → 跳过重写（保留原 Run 字体差异等）
        if (!hasImage)
        {
            var newText = string.Concat(segments.OfType<TextSegment>().Select(s => s.Text));
            if (newText == combined) return;
        }

        // 重写整段：保留首 Run 的 rPr 给文本片段；图片片段独立 Run
        var firstRunProps = runs[0].RunProperties?.CloneNode(true) as RunProperties;
        foreach (var r in runs) r.Remove();

        foreach (var seg in segments)
        {
            switch (seg)
            {
                case TextSegment t:
                    if (string.IsNullOrEmpty(t.Text)) continue;
                    var textRun = new Run();
                    if (firstRunProps != null)
                        textRun.AppendChild(firstRunProps.CloneNode(true));
                    textRun.AppendChild(new Text(t.Text)
                    {
                        Space = SpaceProcessingModeValues.Preserve,
                    });
                    para.AppendChild(textRun);
                    break;
                case ImageSegment img:
                    // mainPart != null 在上面分支已保证
                    var imageRun = ImageInjector.CreateImageRun(mainPart!, img.ImagePath);
                    para.AppendChild(imageRun);
                    break;
            }
        }
    }

    // ── helpers ────────────────────────────────────────────

    /// <summary>
    /// 按 catalog 的 DefaultFormat 把 double/int 格式化成字符串，避免 Word 里出现
    /// 1.234567 这类裸 double。catalog 没标 format 或类型不是数字时回退到 ToString。
    /// </summary>
    private static string FormatValue(object? val, FieldDef? fieldDef)
    {
        if (val == null) return "";
        if (fieldDef?.DefaultFormat is { Length: > 0 } fmt)
        {
            return val switch
            {
                double d => d.ToString(fmt, CultureInfo.InvariantCulture),
                float f => f.ToString(fmt, CultureInfo.InvariantCulture),
                decimal m => m.ToString(fmt, CultureInfo.InvariantCulture),
                long l => l.ToString(fmt, CultureInfo.InvariantCulture),
                int i => i.ToString(fmt, CultureInfo.InvariantCulture),
                _ => val.ToString() ?? "",
            };
        }
        return val.ToString() ?? "";
    }

    /// <summary>
    /// catalog 索引：把 raw 占位符内容（key / 中文名 / 别名）解析成「真实 key + FieldDef」。
    /// FieldDef 用于后续格式化（DefaultFormat）。
    /// </summary>
    private sealed class CatalogIndex
    {
        private readonly Dictionary<string, FieldDef> _byKey;
        private readonly Dictionary<string, FieldDef> _byName;

        public CatalogIndex(IReadOnlyList<FieldDef>? catalog)
        {
            _byKey = new Dictionary<string, FieldDef>(StringComparer.Ordinal);
            _byName = new Dictionary<string, FieldDef>(StringComparer.Ordinal);
            if (catalog == null) return;
            foreach (var f in catalog)
            {
                _byKey[f.Key] = f;
                _byName[NormName(f.Name)] = f;
                foreach (var alias in f.Aliases)
                    _byName[NormName(alias)] = f;
            }
        }

        /// <summary>raw 是 ASCII key → 直查；否则当中文名/别名 → 反查。</summary>
        public (string Key, FieldDef? Def) Resolve(string raw)
        {
            var norm = NormName(raw);
            if (IsKeyLike(norm))
                return (norm, _byKey.TryGetValue(norm, out var fk) ? fk : null);
            if (_byName.TryGetValue(norm, out var fn))
                return (fn.Key, fn);
            return (raw, null);
        }
    }

    private static CatalogIndex BuildCatalogIndex(IReadOnlyList<FieldDef>? catalog)
        => new(catalog);

    private static string NormName(string s) => s.Trim();

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
