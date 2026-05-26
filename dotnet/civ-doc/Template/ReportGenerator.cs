// 多行报告生成器 —— 一份 Word 模板 → 一份 docx，里面按行克隆 N 次"克隆区"。
//
// 占位符驱动（不再有 JSON 配置 / bindings 数组 / 表格签名校验）：
//   1. 用户在 Word 模板里：
//      - 项目级段落 / 表里写 {{委托单位}}/{{项目名称}} 等共享字段
//      - 用一对 marker 包住要按行重复的内容：
//          [[每根锚杆]]              ← 段落，独占一段
//          表2.4-{{锚杆序号}} ...    ← 标题段
//          (数据表，含 {{锚杆编号}}/{{0.1Nt位移}} 等行字段)
//          [[/每根锚杆]]             ← 段落，独占一段
//   2. 引擎：
//      - 找成对 marker → 收集中间所有元素作为"克隆单元"
//      - 对每个 rowResolver：克隆一份单元 + 用 PlaceholderRenderer.RenderInto 替换
//      - 删除原始单元 + 两段 marker
//      - 全文档剩余部分用 projectResolver 替换（项目级字段）
//
// 跟 PlaceholderRenderer 的分工：
//   - PlaceholderRenderer = 替换原子操作（一段一段刷）
//   - ReportGenerator     = 编排（找锚点 + 克隆 N 次 + 各刷一次）
//
// 错误信息原则：每个失败分支都告诉用户「问题在哪 + 怎么修」，绝不返回模糊的"格式错误"。

using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace CivCore.Doc.Template;

public class ReportGenerateException : Exception
{
    public ReportGenerateException(string msg) : base(msg) { }
}

/// <summary>生成结果：每行的占位符替换统计 + 项目级替换统计 + 未知 key 合集 + 缺图片合集。</summary>
public record ReportGenerateResult(
    int RowsRendered,
    int TotalReplaced,
    IReadOnlyList<string> UnknownKeys)
{
    /// <summary>{{img:xxx}} 图片占位符解析失败的 raw 串汇总（去重后）。前端可警告用户。</summary>
    public IReadOnlyList<string> MissingImages { get; init; } = Array.Empty<string>();
}

/// <summary>一个批次的数据：批次级 resolver + 每行 resolver。</summary>
public record BatchSection(
    IFieldResolver BatchResolver,
    IReadOnlyList<IFieldResolver> RowResolvers);

public static class ReportGenerator
{
    /// <summary>默认行重复起始 marker —— 用户在样表前段落里写这个字符串。</summary>
    public const string DefaultPerRowStartMarker = "[[每根锚杆]]";

    /// <summary>默认行重复结束 marker —— 用户在样表后段落里写这个字符串。</summary>
    public const string DefaultPerRowEndMarker = "[[/每根锚杆]]";

    /// <summary>
    /// 用 templateDocxPath 模板生成 outputPath docx：
    /// 找成对 marker → 中间元素克隆 N 次 + 各填一行数据；
    /// 项目级段落/表用 projectResolver 填一次。
    /// </summary>
    /// <param name="templateDocxPath">用户准备好的 Word 模板，带占位符 + 成对 marker。</param>
    /// <param name="projectResolver">项目级字段（同份报告共享，比如委托方/工程名）。</param>
    /// <param name="perRowResolvers">每行一个 resolver。长度 0 抛异常。</param>
    /// <param name="outputPath">输出 docx 绝对路径。父目录不存在自动建。</param>
    /// <param name="catalog">字段 catalog —— 让 {{中文名}}/别名占位符也能识别。</param>
    /// <param name="perRowStartMarker">起始 marker 字符串，默认 [[每根锚杆]]。</param>
    /// <param name="perRowEndMarker">结束 marker 字符串，默认 [[/每根锚杆]]。</param>
    public static ReportGenerateResult Generate(
        string templateDocxPath,
        IFieldResolver projectResolver,
        IReadOnlyList<IFieldResolver> perRowResolvers,
        string outputPath,
        IReadOnlyList<FieldDef>? catalog = null,
        string perRowStartMarker = DefaultPerRowStartMarker,
        string perRowEndMarker = DefaultPerRowEndMarker)
    {
        if (!File.Exists(templateDocxPath))
            throw new ReportGenerateException($"Word 模板文件不存在：{templateDocxPath}");
        if (perRowResolvers.Count == 0)
            throw new ReportGenerateException("没有可填的数据行（perRowResolvers 长度为 0）");

        var dir = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);
        File.Copy(templateDocxPath, outputPath, overwrite: true);

        int totalReplaced = 0;
        var unknownKeys = new List<string>();
        var missingImages = new List<string>();

        using (var doc = WordprocessingDocument.Open(outputPath, true))
        {
            var mainPart = doc.MainDocumentPart
                ?? throw new ReportGenerateException("输出 docx 结构异常（缺 MainDocumentPart）");
            var body = mainPart.Document?.Body
                ?? throw new ReportGenerateException("输出 docx 结构异常（缺 Body）");

            // 1. 找成对 marker + 收集克隆单元
            var (startPara, endPara, unitElements) =
                FindRowMarkerPair(body, perRowStartMarker, perRowEndMarker);

            // 2. 克隆 N 次插入起始 marker 段之后
            OpenXmlElement insertAfter = startPara;
            foreach (var rowResolver in perRowResolvers)
            {
                foreach (var unit in unitElements)
                {
                    var clone = (OpenXmlElement)unit.CloneNode(true);
                    insertAfter.InsertAfterSelf(clone);
                    insertAfter = clone;

                    var res = PlaceholderRenderer.RenderInto(clone, rowResolver, catalog, mainPart);
                    totalReplaced += res.Replaced;
                    unknownKeys.AddRange(res.UnknownKeys);
                    missingImages.AddRange(res.MissingImages);
                }
            }

            // 3. 删原始单元 + 两段 marker（"印章"，复制完丢弃）
            foreach (var unit in unitElements) unit.Remove();
            startPara.Remove();
            endPara.Remove();

            // 4. 项目级替换（剩余的所有段落/表）
            var projectRes = PlaceholderRenderer.RenderInto(body, projectResolver, catalog, mainPart);
            totalReplaced += projectRes.Replaced;
            unknownKeys.AddRange(projectRes.UnknownKeys);
            missingImages.AddRange(projectRes.MissingImages);

            mainPart.Document.Save();
        }

        return new ReportGenerateResult(
            RowsRendered: perRowResolvers.Count,
            TotalReplaced: totalReplaced,
            UnknownKeys: unknownKeys.Distinct().ToList())
        {
            MissingImages = missingImages.Distinct().ToList(),
        };
    }

    /// <summary>
    /// 三级模板：全局 + 批次区块克隆 + 行表克隆。
    /// 模板中用 [[批次]]...[[/批次]] 包裹批次区块，区块内用一对 perRow marker 包住行重复内容。
    /// </summary>
    public static ReportGenerateResult GenerateMultiBatch(
        string templateDocxPath,
        IFieldResolver globalResolver,
        IReadOnlyList<BatchSection> batches,
        string outputPath,
        IReadOnlyList<FieldDef>? catalog = null,
        string batchStartMarker = "[[批次]]",
        string batchEndMarker = "[[/批次]]",
        string perRowStartMarker = DefaultPerRowStartMarker,
        string perRowEndMarker = DefaultPerRowEndMarker)
    {
        if (!File.Exists(templateDocxPath))
            throw new ReportGenerateException($"Word 模板文件不存在：{templateDocxPath}");
        if (batches.Count == 0)
            throw new ReportGenerateException("没有可填的批次数据（batches 长度为 0）");

        var dir = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);
        File.Copy(templateDocxPath, outputPath, overwrite: true);

        int totalReplaced = 0;
        var unknownKeys = new List<string>();
        var missingImages = new List<string>();
        int totalRows = 0;

        using (var doc = WordprocessingDocument.Open(outputPath, true))
        {
            var mainPart = doc.MainDocumentPart
                ?? throw new ReportGenerateException("输出 docx 结构异常（缺 MainDocumentPart）");
            var body = mainPart.Document?.Body
                ?? throw new ReportGenerateException("输出 docx 结构异常（缺 Body）");

            // 1. 找 [[批次]]...[[/批次]] 范围 + 中间元素
            var (batchStart, batchEnd, batchTemplateElements) =
                FindMarkerPair(body, batchStartMarker, batchEndMarker, "批次");

            // 2. 把模板范围（含两个 marker）从 body 中暂存
            var batchInsertAnchor = batchStart.PreviousSibling();
            batchStart.Remove();
            batchEnd.Remove();
            foreach (var el in batchTemplateElements) el.Remove();

            // 3. 逐批次：克隆模板元素 → 处理行重复 → 填批次字段 → 插入 body
            OpenXmlElement? cursor = batchInsertAnchor;
            foreach (var batch in batches)
            {
                var clones = batchTemplateElements
                    .Select(e => (OpenXmlElement)e.CloneNode(true)).ToList();

                // 行重复：在克隆里找成对 perRow marker → 中间元素克隆 N 次
                int rowStartIdx = clones.FindIndex(e =>
                    e is Paragraph p && p.InnerText.Contains(perRowStartMarker));
                if (rowStartIdx >= 0)
                {
                    int rowEndIdx = clones.FindIndex(rowStartIdx + 1, e =>
                        e is Paragraph p && p.InnerText.Contains(perRowEndMarker));
                    if (rowEndIdx < 0)
                        throw new ReportGenerateException(
                            $"批次模板里有起始锚点 {perRowStartMarker} 但缺配对的 {perRowEndMarker}");

                    var rowUnit = clones.GetRange(rowStartIdx + 1, rowEndIdx - rowStartIdx - 1);
                    // 移除：marker 段 + 中间单元（之后插入填好的克隆）
                    clones.RemoveRange(rowStartIdx, rowEndIdx - rowStartIdx + 1);

                    var rowClones = new List<OpenXmlElement>();
                    foreach (var rowResolver in batch.RowResolvers)
                    {
                        foreach (var unit in rowUnit)
                        {
                            var rowClone = (OpenXmlElement)unit.CloneNode(true);
                            var rowRes = PlaceholderRenderer.RenderInto(rowClone, rowResolver, catalog, mainPart);
                            totalReplaced += rowRes.Replaced;
                            unknownKeys.AddRange(rowRes.UnknownKeys);
                            missingImages.AddRange(rowRes.MissingImages);
                            rowClones.Add(rowClone);
                        }
                        totalRows++;
                    }
                    clones.InsertRange(rowStartIdx, rowClones);
                }

                // 填批次级占位符
                foreach (var el in clones)
                {
                    var batchRes = PlaceholderRenderer.RenderInto(el, batch.BatchResolver, catalog, mainPart);
                    totalReplaced += batchRes.Replaced;
                    unknownKeys.AddRange(batchRes.UnknownKeys);
                    missingImages.AddRange(batchRes.MissingImages);
                }

                // 插入处理后的元素到 body
                foreach (var clone in clones)
                {
                    if (cursor == null)
                        cursor = body.PrependChild(clone);
                    else
                    {
                        cursor.InsertAfterSelf(clone);
                        cursor = clone;
                    }
                }
            }

            // 4. 全局替换
            var globalRes = PlaceholderRenderer.RenderInto(body, globalResolver, catalog, mainPart);
            totalReplaced += globalRes.Replaced;
            unknownKeys.AddRange(globalRes.UnknownKeys);
            missingImages.AddRange(globalRes.MissingImages);

            mainPart.Document.Save();
        }

        return new ReportGenerateResult(
            RowsRendered: totalRows,
            TotalReplaced: totalReplaced,
            UnknownKeys: unknownKeys.Distinct().ToList())
        {
            MissingImages = missingImages.Distinct().ToList(),
        };
    }

    // ── marker 定位 ─────────────────────────────────────────

    /// <summary>
    /// 在 Body 顶层（不进表格）找成对 marker，返回起止段 + 中间元素。
    /// 失败信息明确指出缺哪个 marker、应该放在哪里、应该长什么样。
    /// </summary>
    private static (Paragraph Start, Paragraph End, List<OpenXmlElement> Between)
        FindRowMarkerPair(Body body, string startMarker, string endMarker)
    {
        if (startMarker == endMarker)
            throw new ReportGenerateException(
                $"起止锚点不能用同一字符串（{startMarker}）—— 请指定不同的成对 marker");

        var children = body.ChildElements.ToList();
        int startIdx = children.FindIndex(c =>
            c is Paragraph p && p.InnerText.Contains(startMarker));
        if (startIdx < 0)
            throw new ReportGenerateException(
                $"Word 模板缺少行重复起始锚点 {startMarker}：" +
                $"请在要重复的内容（标题段 + 数据表等）上方插入一段、独占内容为 {startMarker}。" +
                "注意 marker 必须在 Body 顶层段落里，不能放在表格单元格内。");

        int endIdx = children.FindIndex(startIdx + 1, c =>
            c is Paragraph p && p.InnerText.Contains(endMarker));
        if (endIdx < 0)
            throw new ReportGenerateException(
                $"找到起始锚点 {startMarker} 但缺配对的结束锚点 {endMarker}：" +
                $"请在要重复的内容下方插入一段、独占内容为 {endMarker}。");

        int unitCount = endIdx - startIdx - 1;
        if (unitCount == 0)
            throw new ReportGenerateException(
                $"克隆区为空：{startMarker} 和 {endMarker} 之间没有任何内容。" +
                "请在两段 marker 之间放入要按行重复的内容（如标题段 + 数据表）。");

        var between = children.GetRange(startIdx + 1, unitCount);
        return ((Paragraph)children[startIdx], (Paragraph)children[endIdx], between);
    }

    /// <summary>通用成对 marker 查找（给 GenerateMultiBatch 找 [[批次]]/[[/批次]] 用）。</summary>
    private static (Paragraph Start, Paragraph End, List<OpenXmlElement> Between)
        FindMarkerPair(Body body, string startMarker, string endMarker, string label)
    {
        var children = body.ChildElements.ToList();
        int startIdx = children.FindIndex(c =>
            c is Paragraph p && p.InnerText.Contains(startMarker));
        if (startIdx < 0)
            throw new ReportGenerateException(
                $"Word 模板缺少{label}起始锚点：请插入一段，内容含 {startMarker}");

        int endIdx = children.FindIndex(startIdx + 1, c =>
            c is Paragraph p && p.InnerText.Contains(endMarker));
        if (endIdx < 0)
            throw new ReportGenerateException(
                $"找到{label}起始锚点 {startMarker} 但缺配对的 {endMarker}");

        var between = children.GetRange(startIdx + 1, endIdx - startIdx - 1);
        return ((Paragraph)children[startIdx], (Paragraph)children[endIdx], between);
    }
}
