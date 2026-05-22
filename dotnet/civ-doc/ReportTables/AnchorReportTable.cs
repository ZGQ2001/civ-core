// 锚杆「报告内插表」sheet 写入：每根锚杆一张 15 行 × 17 列的表，垂直堆叠（间隔 2 空行）。
// 模板布局参考 docs/civil_kb/formulas/test_pj/数据/数据.xlsx 第 3 个 sheet「报告内插表格」。
//
// 元数据列（杆体材料规格/钻孔直径/钻孔倾角/岩土性状/注浆参数/灌浆日期）保留 «占位符»，
// 由后续 Word 报告填充阶段或人工补；计算列填实际值。

using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;

namespace CivCore.Doc.ReportTables;

public static class AnchorReportTable
{
    private const int Cols = 17;        // A..Q
    private const int RowsPerAnchor = 15; // 表自身 15 行
    private const int GapRows = 2;       // 表与表之间间隔

    public static void Write(IXLWorksheet ws, AnchorBatchResult batch)
    {
        // 列宽：A,B,C 标签列稍宽；中间均匀
        for (int c = 1; c <= Cols; c++) ws.Column(c).Width = 9;
        ws.Column(1).Width = 11;

        int startRow = 1;
        foreach (var (input, result) in batch.RowsWithResults)
        {
            WriteOneTable(ws, startRow, input, result, batch.Params);
            startRow += RowsPerAnchor + GapRows;
        }
    }

    private static void WriteOneTable(
        IXLWorksheet ws,
        int baseRow,
        AnchorRowInput input,
        AnchorRowResult result,
        AnchorParams p)
    {
        // 持有 P 的 kN 值方便填荷载等级
        double pKn = p.AxialDesignLoad / 1000.0;

        // ── 行 1: 标题 ──
        SetMerged(ws, baseRow, 1, baseRow, Cols,
            $"表2.4-{input.AnchorId}  锚杆抗拔力试验结果表", bold: true, fontSize: 12);

        // ── 行 2-7: 委托方参数表 ──
        SetMerged(ws, baseRow + 1, 1, baseRow + 6, 1, "委托方提供的锚杆参数",
            bold: true, wrap: true);

        // 行 2 表头 / 行 3 数据
        SetMerged(ws, baseRow + 1, 2, baseRow + 1, 3, "锚杆编号", header: true);
        SetMerged(ws, baseRow + 1, 4, baseRow + 1, 8, "杆体材料规格", header: true);
        SetMerged(ws, baseRow + 1, 9, baseRow + 1, 11, "杆体弹模(GPa)", header: true);
        SetMerged(ws, baseRow + 1, 12, baseRow + 1, 13, "自由段长度(m)", header: true);
        SetMerged(ws, baseRow + 1, 14, baseRow + 1, 17, "锚固段长度(m)", header: true);

        SetMerged(ws, baseRow + 2, 2, baseRow + 2, 3, input.AnchorId);
        SetMerged(ws, baseRow + 2, 4, baseRow + 2, 8, "«杆体材料规格»");
        SetMerged(ws, baseRow + 2, 9, baseRow + 2, 11, FormatNum(p.ElasticModulus / 1000.0));
        SetMerged(ws, baseRow + 2, 12, baseRow + 2, 13, FormatNum(p.FreeLength / 1000.0));
        SetMerged(ws, baseRow + 2, 14, baseRow + 2, 17, FormatNum(p.AnchorLength / 1000.0));

        // 行 4 表头 / 行 5 数据
        SetMerged(ws, baseRow + 3, 2, baseRow + 3, 3, "轴向拉力设计值(kN)", header: true);
        SetMerged(ws, baseRow + 3, 4, baseRow + 3, 8, "锁定荷载(kN)", header: true);
        SetMerged(ws, baseRow + 3, 9, baseRow + 3, 11, "钻孔直径(mm)", header: true);
        SetMerged(ws, baseRow + 3, 12, baseRow + 3, 13, "钻孔倾角", header: true);
        SetMerged(ws, baseRow + 3, 14, baseRow + 3, 17, "岩土性状", header: true);

        SetMerged(ws, baseRow + 4, 2, baseRow + 4, 3, FormatNum(pKn));
        SetMerged(ws, baseRow + 4, 4, baseRow + 4, 8, "/");
        SetMerged(ws, baseRow + 4, 9, baseRow + 4, 11, "«钻孔直径»");
        SetMerged(ws, baseRow + 4, 12, baseRow + 4, 13, "«钻孔倾角»");
        SetMerged(ws, baseRow + 4, 14, baseRow + 4, 17, "«岩土性状»");

        // 行 6 表头 / 行 7 数据
        SetMerged(ws, baseRow + 5, 2, baseRow + 5, 3, "注浆材料强度等级", header: true);
        SetMerged(ws, baseRow + 5, 4, baseRow + 5, 8, "注浆材料配合比", header: true);
        SetMerged(ws, baseRow + 5, 9, baseRow + 5, 11, "注浆方式", header: true);
        SetMerged(ws, baseRow + 5, 12, baseRow + 5, 13, "灌浆压力(MPa)", header: true);
        SetMerged(ws, baseRow + 5, 14, baseRow + 5, 17, "灌浆日期", header: true);

        SetMerged(ws, baseRow + 6, 2, baseRow + 6, 3, "«注浆材料强度等级»");
        SetMerged(ws, baseRow + 6, 4, baseRow + 6, 8, "«注浆材料配合比»");
        SetMerged(ws, baseRow + 6, 9, baseRow + 6, 11, "/");
        SetMerged(ws, baseRow + 6, 12, baseRow + 6, 13, "/");
        SetMerged(ws, baseRow + 6, 14, baseRow + 6, 17, "«灌浆日期»");

        // ── 行 8: 曲线图占位 ──
        SetMerged(ws, baseRow + 7, 1, baseRow + 7, 1, "荷载~位移曲线图", bold: true);
        SetMerged(ws, baseRow + 7, 2, baseRow + 7, Cols, "«曲线图占位»",
            italic: true);

        // ── 行 9-11: 试验数据（荷载等级表头 + 荷载值 + 位移读数）──
        SetMerged(ws, baseRow + 8, 1, baseRow + 10, 1, "试验数据", bold: true, wrap: true);
        SetMerged(ws, baseRow + 8, 2, baseRow + 9, 2, "荷载(kN)", header: true);

        // 等级表头（行 9）
        WriteLevelHeader(ws, baseRow + 8);
        // 荷载值（行 10，按 P 算各等级 kN 值）
        WriteLoadValues(ws, baseRow + 9, pKn);
        // 位移读数（行 11）
        SetMerged(ws, baseRow + 10, 2, baseRow + 10, 2, "位移(mm)", header: true);
        WriteDisplacements(ws, baseRow + 10, input.Displacements);

        // ── 行 12-15: 试验结果及判定 ──
        SetMerged(ws, baseRow + 11, 1, baseRow + 14, 1, "试验结果及判定",
            bold: true, wrap: true);
        SetMerged(ws, baseRow + 11, 2, baseRow + 11, 6, "测试项目", header: true);
        SetMerged(ws, baseRow + 11, 7, baseRow + 11, 10, "实测值", header: true);
        SetMerged(ws, baseRow + 11, 11, baseRow + 11, 15, "允许值", header: true);
        SetMerged(ws, baseRow + 11, 16, baseRow + 11, 17, "判定", header: true);

        // 行 13: 弹性位移量
        SetMerged(ws, baseRow + 12, 2, baseRow + 12, 6, "最大试验荷载下弹性位移量");
        SetMerged(ws, baseRow + 12, 7, baseRow + 12, 10,
            FormatNum(Math.Round(result.ElasticDisplacement, 2)));
        SetMerged(ws, baseRow + 12, 11, baseRow + 12, 15,
            $"上限：{FormatNum(Math.Round(result.UpperLimit, 2))}  下限：{FormatNum(Math.Round(result.LowerLimit, 2))}");
        var verdict = SetMerged(ws, baseRow + 12, 16, baseRow + 12, 17,
            result.Qualified ? "合格" : "不合格");
        if (!result.Qualified) verdict.Style.Font.FontColor = XLColor.Red;

        // 行 14-15: 蠕变量（数据不足 5min 内,填 /）
        SetMerged(ws, baseRow + 13, 2, baseRow + 14, 4, "最后一级荷载锚头蠕变量");
        SetMerged(ws, baseRow + 13, 5, baseRow + 13, 6, "1~10min", header: true);
        SetMerged(ws, baseRow + 13, 7, baseRow + 13, 10, "/");
        SetMerged(ws, baseRow + 13, 11, baseRow + 13, 15, "1.0mm");
        SetMerged(ws, baseRow + 13, 16, baseRow + 14, 17, "/");
        SetMerged(ws, baseRow + 14, 5, baseRow + 14, 6, "6~60min", header: true);
        SetMerged(ws, baseRow + 14, 7, baseRow + 14, 10, "/");
        SetMerged(ws, baseRow + 14, 11, baseRow + 14, 15, "2.0mm");

        // 全表边框
        var fullRange = ws.Range(baseRow, 1, baseRow + RowsPerAnchor - 1, Cols);
        fullRange.Style.Border.InsideBorder = XLBorderStyleValues.Thin;
        fullRange.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
    }

    private static void WriteLevelHeader(IXLWorksheet ws, int row)
    {
        SetMerged(ws, row, 3, row, 3, "0.1Nt", header: true);
        SetMerged(ws, row, 4, row, 5, "0.4Nt", header: true);
        SetMerged(ws, row, 6, row, 7, "0.7Nt", header: true);
        SetMerged(ws, row, 8, row, 8, "1.0Nt", header: true);
        SetMerged(ws, row, 9, row, 9, "1.2Nt", header: true);
        SetMerged(ws, row, 10, row, 11, "1.0Nt", header: true);
        SetMerged(ws, row, 12, row, 12, "0.7Nt", header: true);
        SetMerged(ws, row, 13, row, 14, "0.4Nt", header: true);
        SetMerged(ws, row, 15, row, 16, "0.1Nt", header: true);
        SetMerged(ws, row, 17, row, 17, "锁定荷载", header: true);
    }

    private static void WriteLoadValues(IXLWorksheet ws, int row, double pKn)
    {
        SetMerged(ws, row, 3, row, 3, FormatNum(0.1 * pKn));
        SetMerged(ws, row, 4, row, 5, FormatNum(0.4 * pKn));
        SetMerged(ws, row, 6, row, 7, FormatNum(0.7 * pKn));
        SetMerged(ws, row, 8, row, 8, FormatNum(1.0 * pKn));
        SetMerged(ws, row, 9, row, 9, FormatNum(1.2 * pKn));
        SetMerged(ws, row, 10, row, 11, FormatNum(1.0 * pKn));
        SetMerged(ws, row, 12, row, 12, FormatNum(0.7 * pKn));
        SetMerged(ws, row, 13, row, 14, FormatNum(0.4 * pKn));
        SetMerged(ws, row, 15, row, 16, FormatNum(0.1 * pKn));
        SetMerged(ws, row, 17, row, 17, "/");
    }

    private static void WriteDisplacements(IXLWorksheet ws, int row, AnchorDisplacements d)
    {
        SetMerged(ws, row, 3, row, 3, FormatNum(d.D01Nt));
        SetMerged(ws, row, 4, row, 5, FormatNum(d.D04Nt));
        SetMerged(ws, row, 6, row, 7, FormatNum(d.D07Nt));
        SetMerged(ws, row, 8, row, 8, FormatNum(d.D10Nt));
        SetMerged(ws, row, 9, row, 9, FormatNum(d.D12Nt5Min));
        SetMerged(ws, row, 10, row, 11, FormatNum(d.U10Nt));
        SetMerged(ws, row, 12, row, 12, FormatNum(d.U07Nt));
        SetMerged(ws, row, 13, row, 14, FormatNum(d.U04Nt));
        SetMerged(ws, row, 15, row, 16, FormatNum(d.U01Nt));
        SetMerged(ws, row, 17, row, 17, "/");
    }

    private static IXLCell SetMerged(
        IXLWorksheet ws,
        int r1, int c1, int r2, int c2,
        string value,
        bool bold = false,
        bool header = false,
        bool wrap = false,
        bool italic = false,
        double? fontSize = null)
    {
        IXLCell head;
        if (r1 == r2 && c1 == c2)
        {
            head = ws.Cell(r1, c1);
        }
        else
        {
            var range = ws.Range(r1, c1, r2, c2);
            range.Merge();
            head = ws.Cell(r1, c1);
        }
        head.Value = value;
        head.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
        head.Style.Alignment.Vertical = XLAlignmentVerticalValues.Center;
        head.Style.Alignment.WrapText = wrap;
        if (bold) head.Style.Font.Bold = true;
        if (italic) head.Style.Font.Italic = true;
        if (fontSize.HasValue) head.Style.Font.FontSize = fontSize.Value;
        if (header) head.Style.Fill.BackgroundColor = XLColor.LightGray;
        return head;
    }

    private static string FormatNum(double v)
    {
        // 整数显示无小数；其他保留 2 位
        if (v == Math.Truncate(v) && Math.Abs(v) < 1e10) return ((long)v).ToString();
        return v.ToString("0.##");
    }
}
