// 多检测类型「一键 Word 报告」装配引擎 —— 类型无关。
//
// 一份 docx 薄壳模板里可以写多个数据表占位符（每个检测类型一个）：
//     {{表格:锚杆}}      {{表格:防火涂层}}      …
// 调用方给出若干 section（每个 = 占位符 + 建表委托）：
//   · 提供了数据的类型 → 在其占位符处插入「标题段 + 程序建好的表 + 空段」，删占位符段；
//   · 模板里写了但本次没提供数据的类型 → 占位符段直接清掉（「没勾的清掉」）。
// 最后把薄壳里剩下的 {{委托单位}}/{{检测结论}} 等项目字段按 userInputs 填（含页眉页脚）。
//
// 表的内部格式固定在各 builder（CoatingWordTable / AnchorWordTable，判错=事故，规范统一）；
// 薄壳走 {{}} 占位符（甲方可改、换模板零代码）。这是「换模板零代码 + 报告页一键」的后端闭环。
//
// 建表委托接收 MainDocumentPart：锚杆表内含 {{img:曲线图}}，要在 doc 已打开时才能嵌图。

using System.Text.RegularExpressions;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using CivCore.Doc.Template;

namespace CivCore.Doc.ReportTables;

/// <summary>一个 section 建好的表（标题+表 N 组）+ 填表时收集的未知 key / 缺失图片。</summary>
public record SectionBuild(
    IReadOnlyList<(string Title, Table Table)> Tables,
    IReadOnlyList<string> UnknownKeys,
    IReadOnlyList<string> MissingImages)
{
    public static SectionBuild Plain(IReadOnlyList<(string Title, Table Table)> tables)
        => new(tables, Array.Empty<string>(), Array.Empty<string>());
}

/// <summary>
/// 一个检测类型的 section：占位符串 + 建表委托。委托延迟到 doc 打开后调用，
/// 拿到 MainDocumentPart（锚杆嵌曲线图需要）。
/// </summary>
public record ReportSection(string Placeholder, Func<MainDocumentPart, SectionBuild> Build);

/// <summary>装配结果：插入表总数 + 薄壳替换数 + 未知 key/缺失图片合集（去重）。</summary>
public record AssembleResult(
    int TablesInserted,
    int Replaced,
    IReadOnlyList<string> UnknownKeys,
    IReadOnlyList<string> MissingImages);

public static class DocxReportAssembler
{
    /// <summary>匹配任意数据表占位符 {{表格:xxx}}（用于清理没提供数据的类型）。</summary>
    private static readonly Regex TablePlaceholderPattern =
        new(@"\{\{表格:[^}]+\}\}", RegexOptions.Compiled);

    /// <summary>
    /// 用 templatePath 薄壳模板生成 outputPath docx：每个 section 在其占位符处插表，
    /// 模板里没提供数据的 {{表格:xxx}} 清掉，其余 {{}} 按 userInputs（配 catalog）填。
    /// </summary>
    public static AssembleResult Generate(
        string templatePath,
        string outputPath,
        IReadOnlyList<ReportSection> sections,
        IReadOnlyDictionary<string, string> userInputs,
        IReadOnlyList<FieldDef>? catalog = null)
    {
        if (!File.Exists(templatePath))
            throw new ArgumentException($"Word 模板不存在：{templatePath}");

        var dir = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);
        File.Copy(templatePath, outputPath, overwrite: true);

        int tablesInserted = 0, replaced = 0;
        var unknownKeys = new List<string>();
        var missingImages = new List<string>();

        using (var doc = WordprocessingDocument.Open(outputPath, true))
        {
            var main = doc.MainDocumentPart
                ?? throw new ArgumentException("输出 docx 结构异常（缺 MainDocumentPart）");
            var body = main.Document?.Body
                ?? throw new ArgumentException("输出 docx 结构异常（缺 Body）");

            // 1. 每个提供了数据的 section：找占位符段 → 建表 → 在其后插「标题+表+空段」→ 删占位符段
            foreach (var section in sections)
            {
                var anchor = body.Elements<Paragraph>()
                    .FirstOrDefault(p => p.InnerText.Contains(section.Placeholder))
                    ?? throw new ArgumentException(
                        $"提供了该类型的检测数据，但 Word 模板缺少表格占位符 {section.Placeholder}：" +
                        $"请在要放数据表的位置插入一段、独占内容为 {section.Placeholder}" +
                        "（须在正文顶层，不能在表格单元格内）。");

                var built = section.Build(main);
                unknownKeys.AddRange(built.UnknownKeys);
                missingImages.AddRange(built.MissingImages);

                OpenXmlElement cursor = anchor;
                foreach (var (title, table) in built.Tables)
                {
                    var titlePara = WordTableStyle.TitleParagraph(title);
                    cursor.InsertAfterSelf(titlePara); cursor = titlePara;
                    cursor.InsertAfterSelf(table); cursor = table;
                    var spacer = new Paragraph(); // 表后留空段（Word 要求表后有段；多表之间也隔开）
                    cursor.InsertAfterSelf(spacer); cursor = spacer;
                    tablesInserted++;
                }
                anchor.Remove();
            }

            // 2. 清理「模板写了但本次没提供数据」的占位符段（没勾的类型）
            foreach (var p in body.Elements<Paragraph>()
                .Where(p => TablePlaceholderPattern.IsMatch(p.InnerText)).ToList())
                p.Remove();

            // 3. 填薄壳 {{}}（项目信息）。建好的表里是纯文本/图片、无占位符，不受影响。
            var res = PlaceholderRenderer.RenderInto(body, new DictResolver(userInputs), catalog, main);
            replaced += res.Replaced;
            unknownKeys.AddRange(res.UnknownKeys);
            missingImages.AddRange(res.MissingImages);

            // 4. 页眉/页脚也允许写项目级字段（{{委托单位}} 等）
            ReplaceInHeadersAndFooters(main, new DictResolver(userInputs), catalog,
                ref replaced, unknownKeys, missingImages);

            main.Document.Save();
        }

        return new AssembleResult(
            tablesInserted, replaced,
            unknownKeys.Distinct().ToList(),
            missingImages.Distinct().ToList());
    }

    /// <summary>在所有 HeaderPart / FooterPart 上跑一遍替换（页眉页脚里的项目级字段）。</summary>
    private static void ReplaceInHeadersAndFooters(
        MainDocumentPart main, IFieldResolver resolver, IReadOnlyList<FieldDef>? catalog,
        ref int replaced, List<string> unknownKeys, List<string> missingImages)
    {
        foreach (var hp in main.HeaderParts)
        {
            if (hp.Header == null) continue;
            var r = PlaceholderRenderer.RenderInto(hp.Header, resolver, catalog, mainPart: null);
            replaced += r.Replaced;
            unknownKeys.AddRange(r.UnknownKeys);
            missingImages.AddRange(r.MissingImages);
            hp.Header.Save();
        }
        foreach (var fp in main.FooterParts)
        {
            if (fp.Footer == null) continue;
            var r = PlaceholderRenderer.RenderInto(fp.Footer, resolver, catalog, mainPart: null);
            replaced += r.Replaced;
            unknownKeys.AddRange(r.UnknownKeys);
            missingImages.AddRange(r.MissingImages);
            fp.Footer.Save();
        }
    }

    private sealed class DictResolver : IFieldResolver
    {
        private readonly IReadOnlyDictionary<string, string> _v;
        public DictResolver(IReadOnlyDictionary<string, string> v) => _v = v;
        public object? GetValue(string key) => _v.TryGetValue(key, out var s) ? s : null;
    }
}
