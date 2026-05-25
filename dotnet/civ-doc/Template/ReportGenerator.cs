// 模板报告生成器 —— 引擎层，不知道具体计算类型。
//
// 流程：
//   1. TemplateStorage.Load → 拿到 source.docx + config.json
//   2. ReComputeSignature(source.docx) vs config.TableSignature → 不匹配阻断
//   3. 每个 rowResolver 克隆一份模板表 → 按 bindings 填值（Run 级保样式）
//   4. 移除原模板表 → 保存到 outputPath（原子写 docx）
//
// 解耦点：rowResolvers 由调用方提供（IFieldResolver），引擎不写 anchor/drilling 逻辑。

using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace CivCore.Doc.Template;

public class ReportGenerateException : Exception
{
    public ReportGenerateException(string msg) : base(msg) { }
}

public static class ReportGenerator
{
    /// <summary>
    /// 用 templateName 对应的模板 + rowResolvers 生成报告，写到 outputPath。
    /// </summary>
    /// <param name="templateName">已通过 TemplateStorage.Save 保存的模板名。</param>
    /// <param name="rowResolvers">每个 row 一个 resolver（一根锚杆 → 一张克隆表）。</param>
    /// <param name="outputPath">输出 docx 绝对路径。父目录不存在自动建。</param>
    /// <param name="fieldCatalog">字段 Key→FieldDef 字典，用于查 DefaultFormat；null 则不应用默认格式。</param>
    /// <param name="rootOverride">测试用：模板根目录覆盖。</param>
    public static void Generate(
        string templateName,
        IReadOnlyList<IFieldResolver> rowResolvers,
        string outputPath,
        IReadOnlyDictionary<string, FieldDef>? fieldCatalog = null,
        string? rootOverride = null)
    {
        if (rowResolvers.Count == 0)
            throw new ReportGenerateException("没有可填的数据行");

        var (config, sourceDocx) = TemplateStorage.Load(templateName, rootOverride);

        if (config.Repeat != RepeatStrategy.PerRow)
            throw new ReportGenerateException(
                $"暂只支持 per_row 重复策略，当前模板配置为 {config.Repeat}（第一期未实现）");

        var currentSig = TemplateParser.ComputeSignature(sourceDocx);
        if (currentSig != config.TableSignature)
            throw new ReportGenerateException(
                $"模板已被修改！当前签名 {currentSig} ≠ 保存时签名 {config.TableSignature}，请重新打开模板编辑器绑定字段。");

        // 拷贝 source.docx 到输出路径再操作（不动原模板）
        var dir = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);
        File.Copy(sourceDocx, outputPath, overwrite: true);

        using var doc = WordprocessingDocument.Open(outputPath, true);
        var body = doc.MainDocumentPart?.Document?.Body
            ?? throw new ReportGenerateException("生成失败：输出 docx 结构异常");

        var anchorPara = body.Elements<Paragraph>()
            .FirstOrDefault(p => p.InnerText.Contains(TemplateParser.AnchorMarker))
            ?? throw new ReportGenerateException("生成失败：拷贝出来的 docx 找不到锚点段落");
        var templateTable = anchorPara.ElementsAfter().OfType<Table>().FirstOrDefault()
            ?? throw new ReportGenerateException("生成失败：拷贝出来的 docx 锚点后无表");

        // 每个 resolver 克隆一份模板表，插在最后一次插入的位置之后
        OpenXmlElement insertAfter = templateTable;
        foreach (var resolver in rowResolvers)
        {
            var cloned = (Table)templateTable.CloneNode(deep: true);
            insertAfter.InsertAfterSelf(cloned);
            insertAfter = cloned;

            FillTable(cloned, config.Bindings, resolver, fieldCatalog);
        }

        // 原模板表是"印章"，复制完移除
        templateTable.Remove();

        doc.MainDocumentPart!.Document.Save();
    }

    // ── 单表填充 ────────────────────────────────────────────

    private static void FillTable(
        Table table,
        IReadOnlyList<CellBinding> bindings,
        IFieldResolver resolver,
        IReadOnlyDictionary<string, FieldDef>? catalog)
    {
        foreach (var binding in bindings)
        {
            var cell = TableGridWalker.FindMasterAt(table, binding.Row, binding.Col);
            if (cell == null) continue; // 模板被绑定后改了行列，跳过坏绑定（签名应该已挡住）

            var raw = resolver.GetValue(binding.FieldKey);
            var format = binding.Format ?? (catalog?.GetValueOrDefault(binding.FieldKey)?.DefaultFormat);
            var display = FormatValue(raw, format);
            ReplaceCellTextAtRunLevel(cell, display);
        }
    }

    /// <summary>把值按 .NET 数字格式串渲染成字符串。null → "«未知字段»"。</summary>
    private static string FormatValue(object? raw, string? format)
    {
        if (raw == null) return "«未知字段»";
        if (!string.IsNullOrEmpty(format) && raw is IFormattable f)
            return f.ToString(format, System.Globalization.CultureInfo.InvariantCulture);
        return raw.ToString() ?? "";
    }

    /// <summary>
    /// Run 级替换：定位 cell 第一个 Run，保留 rPr 只换 Text；
    /// 其余 Run（来自模板原占位符的多 Run 拆分）一并删除，防残留旧字。
    /// </summary>
    private static void ReplaceCellTextAtRunLevel(TableCell cell, string display)
    {
        var paragraphs = cell.Elements<Paragraph>().ToList();
        if (paragraphs.Count == 0)
        {
            cell.AppendChild(new Paragraph(new Run(new Text(display))));
            return;
        }

        var firstRun = paragraphs.SelectMany(p => p.Elements<Run>()).FirstOrDefault();
        if (firstRun == null)
        {
            // 段落里没 Run，直接塞一个
            paragraphs[0].AppendChild(new Run(new Text(display)));
        }
        else
        {
            // 第一个 Run：保留 rPr，把所有 Text 合成一个 Text
            var rPr = firstRun.RunProperties;
            firstRun.RemoveAllChildren();
            if (rPr != null) firstRun.AppendChild(rPr);
            firstRun.AppendChild(new Text(display) { Space = DocumentFormat.OpenXml.SpaceProcessingModeValues.Preserve });
        }

        // 删第一个 Run 之外的全部 Run（防止残留旧字符）
        bool seenFirst = false;
        foreach (var para in paragraphs)
        {
            foreach (var run in para.Elements<Run>().ToList())
            {
                if (!seenFirst) { seenFirst = true; continue; }
                run.Remove();
            }
        }
    }
}
