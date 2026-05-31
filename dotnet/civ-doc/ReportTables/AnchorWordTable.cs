// 锚杆抗拔报告表 → Word 表格（OpenXML 直接建，逐根一张「表2.4 单根结果表」）。
// 供 report.assemble / report.run_from_result / anchor.run 在 docx 模板的「{{表格:锚杆}}」
// 占位符处插入。表的版式（17 列网格 + 合并）固定在代码里——判定数据呈现必须规范统一
// （判错=事故），不随甲方模板乱改；甲方要改的封面/项目主表/结论那层走 {{}} 占位符。
//
// 做法：建表时大部分数据格用 {{key}}/{{img:}} 占位符，建完即用 PlaceholderRenderer.RenderInto
// 配 AnchorRowResolver + AnchorFieldCatalog 填值/嵌曲线图——复用现成填值/格式化/嵌图逻辑，不重写。
// 少数随工程参数变的格（轴向设计值 kN、杆体弹模 GPa、自由/锚固段 m、各级荷载 kN）按列头
// 的正确单位在建表时算成字面量（修正老模板把 N、N/mm²、mm 塞进 kN/GPa/m 列头的口径）。
//
// 标题编号（公司标准）：单根 → 「表{节号}」；多根 → 「表{节号}-1 / -2 …」（全局序号，跨批连续）。

using System.Globalization;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Template;
using static CivCore.Doc.ReportTables.WordTableStyle;

namespace CivCore.Doc.ReportTables;

public static class AnchorWordTable
{
    /// <summary>数据表占位符 —— 用户在模板里要放锚杆逐根结果表的位置写这一段。</summary>
    public const string TablePlaceholder = "{{表格:锚杆}}";

    /// <summary>默认表节号（锚杆抗拔结果表惯例在报告 2.4 节）。</summary>
    public const string DefaultSectionNo = "2.4";

    /// <summary>表2.4 的 17 列网格宽度（twips，照公司母版结构）。</summary>
    private static readonly int[] GridCols =
        { 742, 972, 829, 161, 668, 676, 153, 829, 829, 601, 229, 830, 677, 153, 631, 199, 830 };

    // 试验数据区 10 个荷载列：加载 0.1~1.2Nt + 卸载 1.0~0.1Nt + 锁定荷载。
    private static readonly double[] LoadMul = { 0.1, 0.4, 0.7, 1.0, 1.2, 1.0, 0.7, 0.4, 0.1 };
    private static readonly int[] LoadSpan = { 1, 2, 2, 1, 1, 2, 1, 2, 2, 1 }; // 10 列；∑=15
    private static readonly string[] LoadHdr =
        { "0.1Nt", "0.4Nt", "0.7Nt", "1.0Nt", "1.2Nt", "1.0Nt", "0.7Nt", "0.4Nt", "0.1Nt", "锁定荷载" };
    private static readonly string[] DispPh =
    {
        "{{0.1Nt 时位移 (mm)}}", "{{0.4Nt 时位移 (mm)}}", "{{0.7Nt 时位移 (mm)}}",
        "{{1.0Nt 时位移 (mm)}}", "{{1.2Nt 持荷 5min (mm)}}",
        "{{卸载至 1.0Nt (mm)}}", "{{卸载至 0.7Nt (mm)}}", "{{卸载至 0.4Nt (mm)}}", "{{卸载至 0.1Nt (mm)}}",
    };

    /// <summary>
    /// 单类型便捷出报告（report.run_from_result / anchor.run 共用）：把结果建成逐根 表2.4
    /// 插进模板的 {{表格:锚杆}} 占位符、填薄壳。多检测类型组装走 DocxReportAssembler.Generate。
    /// </summary>
    public static AssembleResult GenerateReport(
        string templatePath,
        string outputPath,
        AnchorWorkbookResult result,
        IReadOnlyDictionary<string, string> userInputs,
        IReadOnlyDictionary<string, Dictionary<string, string>> batchUserInputs,
        string? curveImageDir,
        string sectionNo)
    {
        var detectionLabel = DetectionLabel(userInputs);
        var section = new ReportSection(
            TablePlaceholder,
            mp => BuildSection(result, userInputs, batchUserInputs, curveImageDir, sectionNo, detectionLabel, mp));
        return DocxReportAssembler.Generate(
            templatePath, outputPath, new[] { section }, userInputs, AnchorFieldCatalog.All);
    }

    /// <summary>表标题里的检测项目名：user_inputs 的 inspection_item / 检测项目，缺省锚杆抗拔（验收）。</summary>
    public static string DetectionLabel(IReadOnlyDictionary<string, string> userInputs)
        => userInputs.TryGetValue("inspection_item", out var a) && !string.IsNullOrWhiteSpace(a) ? a
         : userInputs.TryGetValue("检测项目", out var b) && !string.IsNullOrWhiteSpace(b) ? b
         : "锚杆抗拔力（验收）检测";

    /// <summary>
    /// 把整份结果建成「逐根一张表2.4」section：每根一个 AnchorRowResolver 填值嵌图，
    /// 标题按总根数决定单表 / 多表编号。三处共用（report.assemble / run_from_result / anchor.run）。
    /// </summary>
    /// <param name="batchUserInputs">批次级字段（如各批灌浆日期），并入该批每根的 resolver。</param>
    /// <param name="mainPart">已打开 docx 的 MainDocumentPart（嵌曲线图需要）。</param>
    public static SectionBuild BuildSection(
        AnchorWorkbookResult result,
        IReadOnlyDictionary<string, string> userInputs,
        IReadOnlyDictionary<string, Dictionary<string, string>> batchUserInputs,
        string? curveImageDir,
        string sectionNo,
        string detectionLabel,
        MainDocumentPart mainPart)
    {
        int n = result.BatchResults.Sum(b => b.RowsWithResults.Length);
        var tables = new List<(string, Table)>();
        var unknownKeys = new List<string>();
        var missingImages = new List<string>();

        int index = 0;
        foreach (var br in result.BatchResults)
        {
            // 本批字段 = 项目级 ∪ 本批 batch_user_inputs ∪ {batch_id}（保留原合并语义）
            var batchLevel = new Dictionary<string, string>(userInputs);
            if (batchUserInputs.TryGetValue(br.BatchId, out var bui))
                foreach (var kv in bui) batchLevel[kv.Key] = kv.Value;
            batchLevel["batch_id"] = br.BatchId;

            foreach (var (input, res) in br.RowsWithResults)
            {
                index++;
                var resolver = new AnchorRowResolver(
                    input, res, br.Params, batchLevel,
                    anchorIndex: index, curveImageDir: curveImageDir, batchId: br.BatchId);

                var table = BuildLayout(br.Params);
                var rr = PlaceholderRenderer.RenderInto(table, resolver, AnchorFieldCatalog.All, mainPart);
                unknownKeys.AddRange(rr.UnknownKeys);
                missingImages.AddRange(rr.MissingImages);

                var title = n == 1
                    ? $"表{sectionNo}  {detectionLabel}结果表"
                    : $"表{sectionNo}-{index}  {detectionLabel}结果表";
                tables.Add((title, table));
            }
        }

        return new SectionBuild(
            tables, unknownKeys.Distinct().ToList(), missingImages.Distinct().ToList());
    }

    /// <summary>建一张空的表2.4（{{key}}/{{img:}} 待填 + 随工程参数算好的单位正确字面量）。</summary>
    public static Table BuildLayout(AnchorParams p)
    {
        double pKn = p.AxialDesignLoad / 1000.0;     // P：N → kN（列头是 kN）
        var table = NewTable();

        // R0/R1 委托方参数 1：编号 / 材料规格 / 弹模(GPa) / 自由段(m) / 锚固段(m)
        table.AppendChild(Tr(
            Cell("委托方提供的锚杆参数", bold: true, vMerge: MergedCellValues.Restart),
            Cell("锚杆编号", bold: true, gridSpan: 2),
            Cell("杆体材料规格", bold: true, gridSpan: 5),
            Cell("杆体弹模(GPa)", bold: true, gridSpan: 3),
            Cell("自由段长度(m)", bold: true, gridSpan: 2),
            Cell("锚固段长度(m)", bold: true, gridSpan: 4)));
        table.AppendChild(Tr(
            Cell("", vMerge: MergedCellValues.Continue),
            Cell("{{锚杆编号}}", gridSpan: 2),
            Cell("{{杆体材料规格}}", gridSpan: 5),
            Cell(Num(p.ElasticModulus / 1000.0), gridSpan: 3),  // GPa
            Cell(Num(p.FreeLength / 1000.0), gridSpan: 2),      // m
            Cell(Num(p.AnchorLength / 1000.0), gridSpan: 4)));  // m

        // R2/R3 委托方参数 2：轴向拉力(kN) / 锁定荷载(kN) / 钻孔直径 / 钻孔倾角 / 岩土性状
        table.AppendChild(Tr(
            Cell("", vMerge: MergedCellValues.Continue),
            Cell("轴向拉力设计值(kN)", bold: true, gridSpan: 2),
            Cell("锁定荷载(kN)", bold: true, gridSpan: 5),
            Cell("钻孔直径(mm)", bold: true, gridSpan: 3),
            Cell("钻孔倾角", bold: true, gridSpan: 2),
            Cell("岩土性状", bold: true, gridSpan: 4)));
        table.AppendChild(Tr(
            Cell("", vMerge: MergedCellValues.Continue),
            Cell(Num(pKn), gridSpan: 2),
            Cell("/", gridSpan: 5),
            Cell("{{钻孔直径}}", gridSpan: 3),
            Cell("{{钻孔倾角}}", gridSpan: 2),
            Cell("{{岩土性状}}", gridSpan: 4)));

        // R4/R5 委托方参数 3：注浆强度等级 / 配合比 / 注浆方式 / 灌浆压力 / 灌浆日期
        table.AppendChild(Tr(
            Cell("", vMerge: MergedCellValues.Continue),
            Cell("注浆材料强度等级", bold: true, gridSpan: 2),
            Cell("注浆材料配合比", bold: true, gridSpan: 5),
            Cell("注浆方式", bold: true, gridSpan: 3),
            Cell("灌浆压力(MPa)", bold: true, gridSpan: 2),
            Cell("灌浆日期", bold: true, gridSpan: 4)));
        table.AppendChild(Tr(
            Cell("", vMerge: MergedCellValues.Continue),
            Cell("{{注浆材料强度等级}}", gridSpan: 2),
            Cell("{{注浆材料配合比}}", gridSpan: 5),
            Cell("/", gridSpan: 3),
            Cell("/", gridSpan: 2),
            Cell("{{灌浆日期}}", gridSpan: 4)));

        // R6 曲线图（占满右侧 16 列）
        table.AppendChild(Tr(
            Cell("荷载~位移曲线图", bold: true),
            Cell("{{img:曲线图}}", gridSpan: 16)));

        // R7 试验数据表头：试验数据(跨R7-R9) | 荷载(kN)(跨R7-R8) | 10 荷载级
        var r7 = new TableRow();
        r7.AppendChild(Cell("试验数据", bold: true, vMerge: MergedCellValues.Restart));
        r7.AppendChild(Cell("荷载(kN)", bold: true, vMerge: MergedCellValues.Restart));
        for (int i = 0; i < LoadHdr.Length; i++)
            r7.AppendChild(Cell(LoadHdr[i], bold: true, gridSpan: LoadSpan[i]));
        table.AppendChild(r7);

        // R8 各级荷载值（kN，按 P 算）+ 锁定荷载 /
        var r8 = new TableRow();
        r8.AppendChild(Cell("", vMerge: MergedCellValues.Continue));
        r8.AppendChild(Cell("", vMerge: MergedCellValues.Continue));
        for (int i = 0; i < LoadMul.Length; i++)
            r8.AppendChild(Cell(Num(pKn * LoadMul[i]), gridSpan: LoadSpan[i]));
        r8.AppendChild(Cell("/", gridSpan: LoadSpan[9]));
        table.AppendChild(r8);

        // R9 各级位移（{{}} 待填）+ 锁定荷载 /
        var r9 = new TableRow();
        r9.AppendChild(Cell("", vMerge: MergedCellValues.Continue));
        r9.AppendChild(Cell("位移(mm)", bold: true));
        for (int i = 0; i < DispPh.Length; i++)
            r9.AppendChild(Cell(DispPh[i], gridSpan: LoadSpan[i]));
        r9.AppendChild(Cell("/", gridSpan: LoadSpan[9]));
        table.AppendChild(r9);

        // R10 判定表头：试验结果及判定(跨R10-R13) | 测试项目 | 实测值 | 允许值 | 判定
        table.AppendChild(Tr(
            Cell("试验结果及判定", bold: true, vMerge: MergedCellValues.Restart),
            Cell("测试项目", bold: true, gridSpan: 5),
            Cell("实测值", bold: true, gridSpan: 4),
            Cell("允许值", bold: true, gridSpan: 5),
            Cell("判定", bold: true, gridSpan: 2)));

        // R11 弹性位移量：M | 允许范围（Q<M<R，下限 Q / 上限 R）| 判定
        table.AppendChild(Tr(
            Cell("", vMerge: MergedCellValues.Continue),
            Cell("最大试验荷载下弹性位移量", gridSpan: 5),
            Cell("{{弹性位移量 M (mm)}}", gridSpan: 4),
            CellMulti(new[] { "下限：{{判定下限 Q (mm)}}", "上限：{{判定上限 R (mm)}}" }, gridSpan: 5),
            Cell("{{判定结果}}", gridSpan: 2)));

        // R12/R13 锚头蠕变量（照母版固定文字，不参与判定数据）
        table.AppendChild(Tr(
            Cell("", vMerge: MergedCellValues.Continue),
            Cell("最后一级荷载锚头蠕变量", gridSpan: 3, vMerge: MergedCellValues.Restart),
            Cell("1~10min", gridSpan: 2),
            Cell("/", gridSpan: 4),
            Cell("1.0mm", gridSpan: 5),
            Cell("/", gridSpan: 2, vMerge: MergedCellValues.Restart)));
        table.AppendChild(Tr(
            Cell("", vMerge: MergedCellValues.Continue),
            Cell("", gridSpan: 3, vMerge: MergedCellValues.Continue),
            Cell("6~60min", gridSpan: 2),
            Cell("/", gridSpan: 4),
            Cell("2.0mm", gridSpan: 5),
            Cell("", gridSpan: 2, vMerge: MergedCellValues.Continue)));

        return table;
    }

    // ── OpenXML 构件 ──

    private static Table NewTable()
    {
        var props = new TableProperties(
            new TableWidth { Type = TableWidthUnitValues.Dxa, Width = GridCols.Sum().ToString() },
            Borders(),
            new TableLayout { Type = TableLayoutValues.Fixed });
        var grid = new TableGrid();
        foreach (var w in GridCols) grid.AppendChild(new GridColumn { Width = w.ToString() });
        return new Table(props, grid);
    }

    private static TableRow Tr(params TableCell[] cells)
    {
        var row = new TableRow();
        foreach (var c in cells) row.AppendChild(c);
        return row;
    }

    /// <summary>数值格式化：去掉无意义小数（200000/1000 → "200"，500/1000 → "0.5"）。</summary>
    private static string Num(double v) => v.ToString("0.##", CultureInfo.InvariantCulture);
}
