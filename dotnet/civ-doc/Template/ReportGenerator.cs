// 多行报告生成器 —— 一份 Word 模板 → 一份 docx，里面按行克隆 N 张表。
//
// 占位符驱动（不再有 JSON 配置 / bindings 数组 / 表格签名校验）：
//   1. 用户在 Word 模板里：
//      - 项目级段落 / 表里写 {client_name}/{project_name} 等共享字段
//      - 找一个段落写 [[每根锚杆]]（DefaultPerRowMarker），后接一张样表
//      - 样表里写每行字段：{anchor_id}/{elastic_displacement} 等
//   2. 引擎：
//      - 找 marker 段 → 后接的 Table = 待克隆样表
//      - 对每个 rowResolver: 克隆样表 + 用 PlaceholderRenderer.RenderInto 替换占位符
//      - 删除原模板表 + marker 段
//      - 全文档剩余部分用 projectResolver 替换（项目级字段）
//
// 跟 PlaceholderRenderer 的分工：
//   - PlaceholderRenderer = 替换原子操作（一段一段刷）
//   - ReportGenerator     = 编排（找锚点 + 克隆 N 次 + 各刷一次）

using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace CivCore.Doc.Template;

public class ReportGenerateException : Exception
{
    public ReportGenerateException(string msg) : base(msg) { }
}

/// <summary>生成结果：每行的占位符替换统计 + 项目级替换统计 + 未知 key 合集。</summary>
public record ReportGenerateResult(
    int RowsRendered,
    int TotalReplaced,
    IReadOnlyList<string> UnknownKeys);

public static class ReportGenerator
{
    /// <summary>默认 marker —— 用户在样表前段落里写这个字符串。</summary>
    public const string DefaultPerRowMarker = "[[每根锚杆]]";

    /// <summary>
    /// 用 templateDocxPath 模板生成 outputPath docx：找 marker → 后接表克隆 N 次 +
    /// 各填一行数据；项目级段落/表用 projectResolver 填一次。
    /// </summary>
    /// <param name="templateDocxPath">用户准备好的 Word 模板，带占位符 + marker。</param>
    /// <param name="projectResolver">项目级字段（同批次共享，比如委托方/工程名）。</param>
    /// <param name="perRowResolvers">每行一个 resolver。长度 0 抛异常。</param>
    /// <param name="outputPath">输出 docx 绝对路径。父目录不存在自动建。</param>
    /// <param name="catalog">字段 catalog —— 让 {中文名} 占位符也能识别。</param>
    /// <param name="perRowMarker">marker 字符串，默认 [[每根锚杆]]。</param>
    public static ReportGenerateResult Generate(
        string templateDocxPath,
        IFieldResolver projectResolver,
        IReadOnlyList<IFieldResolver> perRowResolvers,
        string outputPath,
        IReadOnlyList<FieldDef>? catalog = null,
        string perRowMarker = DefaultPerRowMarker)
    {
        if (!File.Exists(templateDocxPath))
            throw new ReportGenerateException($"Word 模板文件不存在：{templateDocxPath}");
        if (perRowResolvers.Count == 0)
            throw new ReportGenerateException("没有可填的数据行");

        var dir = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);
        File.Copy(templateDocxPath, outputPath, overwrite: true);

        int totalReplaced = 0;
        var unknownKeys = new List<string>();

        using (var doc = WordprocessingDocument.Open(outputPath, true))
        {
            var body = doc.MainDocumentPart?.Document?.Body
                ?? throw new ReportGenerateException("输出 docx 结构异常");

            // 1. 找 marker 段落 + 后接的样表
            var (markerPara, templateTable) = FindMarkerAndTable(body, perRowMarker);

            // 2. 克隆 N 次，每个克隆做局部替换
            OpenXmlElement insertAfter = templateTable;
            foreach (var rowResolver in perRowResolvers)
            {
                var clonedTable = (Table)templateTable.CloneNode(deep: true);
                insertAfter.InsertAfterSelf(clonedTable);
                insertAfter = clonedTable;

                var clonedRes = PlaceholderRenderer.RenderInto(clonedTable, rowResolver, catalog);
                totalReplaced += clonedRes.Replaced;
                unknownKeys.AddRange(clonedRes.UnknownKeys);
            }

            // 3. 删原模板表 + marker 段（它们是"印章"，复制完丢弃）
            templateTable.Remove();
            markerPara.Remove();

            // 4. 项目级替换（剩余的所有段落/表）
            var projectRes = PlaceholderRenderer.RenderInto(body, projectResolver, catalog);
            totalReplaced += projectRes.Replaced;
            unknownKeys.AddRange(projectRes.UnknownKeys);

            doc.MainDocumentPart!.Document.Save();
        }

        return new ReportGenerateResult(
            RowsRendered: perRowResolvers.Count,
            TotalReplaced: totalReplaced,
            UnknownKeys: unknownKeys.Distinct().ToList());
    }

    /// <summary>找含 marker 的段落 + 后接的第一张表。两者都缺时抛带提示的异常。</summary>
    private static (Paragraph Marker, Table Table) FindMarkerAndTable(Body body, string marker)
    {
        var markerPara = body.Elements<Paragraph>()
            .FirstOrDefault(p => p.InnerText.Contains(marker))
            ?? throw new ReportGenerateException(
                $"Word 模板缺少行重复锚点：请在样表前插入一段，内容含 {marker}");

        var table = markerPara.ElementsAfter().OfType<Table>().FirstOrDefault()
            ?? throw new ReportGenerateException(
                $"锚点 {marker} 之后未找到表格 —— 请把样表紧跟在该段落后");

        return (markerPara, table);
    }
}
