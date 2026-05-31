// 防火涂层「一键 Word 报告」引擎：把计算结果渲染进用户的 docx 薄壳模板。
//
//   薄壳（封面/项目信息主表/结论/页眉）：用户在模板里写 {{委托单位}}/{{检测结论}} 等占位符
//     → 由 PlaceholderRenderer 按 user_inputs 填（换模板/换甲方零代码）。
//   数据表：用户在要放表处写一段「{{表格:防火涂层}}」占位符
//     → 本引擎在该处插入按规范格式建好的 Word 表（CoatingWordTable.BuildAll，膨胀型/厚型分表）。
//
// 表的内部格式固定在代码（判错=事故，规范统一）；薄壳走占位符（甲方可改）。这就是
// 「换模板零代码」+「报告页一键」的后端闭环。

using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using CivCore.Doc.Calc.Coating;
using CivCore.Doc.Template;

namespace CivCore.Doc.ReportTables;

public static class CoatingDocxReport
{
    /// <summary>数据表占位符 —— 用户在模板里要放表的位置写这一段。</summary>
    public const string TablePlaceholder = "{{表格:防火涂层}}";

    private const string CjkFont = "SimSun";
    private const string LatinFont = "Times New Roman";

    public record Result(int TablesInserted, int Replaced, IReadOnlyList<string> UnknownKeys);

    /// <summary>
    /// 用 templatePath 薄壳模板生成 outputPath docx：在 {{表格:防火涂层}} 处插入数据表，
    /// 其余 {{}} 占位符按 userInputs 填。members 为单批构件计算结果。
    /// </summary>
    public static Result Generate(
        string templatePath,
        string outputPath,
        IReadOnlyList<(CoatingMemberInput Input, CoatingMemberResult Result)> members,
        string standard,
        IReadOnlyDictionary<string, string> userInputs)
    {
        if (!File.Exists(templatePath))
            throw new ArgumentException($"Word 模板不存在：{templatePath}");
        if (members.Count == 0)
            throw new ArgumentException("没有构件计算结果可填入报告");

        var dir = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);
        File.Copy(templatePath, outputPath, overwrite: true);

        var tables = CoatingWordTable.BuildAll(members, standard);

        using var doc = WordprocessingDocument.Open(outputPath, true);
        var main = doc.MainDocumentPart
            ?? throw new ArgumentException("输出 docx 结构异常（缺 MainDocumentPart）");
        var body = main.Document?.Body
            ?? throw new ArgumentException("输出 docx 结构异常（缺 Body）");

        // 1. 找表格占位符段落（Body 顶层），在其后依次插入「标题段 + 表 + 空段」
        var anchor = body.Elements<Paragraph>()
            .FirstOrDefault(p => p.InnerText.Contains(TablePlaceholder))
            ?? throw new ArgumentException(
                $"Word 模板缺少表格占位符 {TablePlaceholder}：" +
                $"请在要放检测数据表的位置插入一段、独占内容为 {TablePlaceholder}（须在正文顶层，不能在表格单元格内）。");

        OpenXmlElement cursor = anchor;
        foreach (var (title, table) in tables)
        {
            var titlePara = TitleParagraph(title);
            cursor.InsertAfterSelf(titlePara); cursor = titlePara;
            cursor.InsertAfterSelf(table); cursor = table;
            var spacer = new Paragraph(); // 表后留空段（Word 要求表后有段；多表之间也需隔开）
            cursor.InsertAfterSelf(spacer); cursor = spacer;
        }
        anchor.Remove();

        // 2. 填薄壳 {{}}（项目信息）。建好的表里是纯文本无占位符，不受影响。
        var res = PlaceholderRenderer.RenderInto(body, new DictResolver(userInputs), catalog: null, main);

        main.Document.Save();
        return new Result(tables.Count, res.Replaced, res.UnknownKeys);
    }

    /// <summary>表标题段：居中、宋体+Times、小四加粗。</summary>
    private static Paragraph TitleParagraph(string text) => new(
        new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
        new Run(
            new RunProperties(
                new RunFonts { Ascii = LatinFont, HighAnsi = LatinFont, EastAsia = CjkFont },
                new Bold(),
                new FontSize { Val = "24" }),       // 小四 = 12pt
            new Text(text) { Space = SpaceProcessingModeValues.Preserve }));

    private sealed class DictResolver : IFieldResolver
    {
        private readonly IReadOnlyDictionary<string, string> _v;
        public DictResolver(IReadOnlyDictionary<string, string> v) => _v = v;
        public object? GetValue(string key) => _v.TryGetValue(key, out var s) ? s : null;
    }
}
