// 里氏硬度「报告插入表」生成器（用 ClosedXML 输出精致格式）。
//
// 目标格式参考 D:\3js\项目\鉴定\20260101 小米\D号生产厂房\01检测批一【】.xlsx 里
// 「里氏硬度（钢梁）」/「里氏硬度（钢柱）」sheet：
//   - 14 列：A 序号 | B 构件位置 | C-K 9 次原始 HL 测量 | L 厚度 | M 构件抗拉特征值 | N 批级抗拉平均
//   - 每构件 3 行（3 个测区，每测区 9 次原始打击）
//   - 合并规则：A/B/L/M 跨 3 行；C1:K1（表头 9 列 HL）；N 列整批 N2:N{lastRow}
//   - 字体：表头仿宋 10.5；序号/厚度 Times New Roman 10.5；构件位置 Times New Roman 10；
//          HL 数据 / 构件抗拉 Times New Roman 11；批级抗拉 宋体 11（特意跟其他不同字体）
//   - 列宽：A=4.78  B=17.11  C-K=4.67  L=8.78
//   - 表头行高 72（双行字 wrap_text）
//   - 全 thin 边框

using ClosedXML.Excel;

namespace CivCore.Doc.ReportTables;

/// <summary>单个构件的报告数据：3 个测区 × 9 次原始打击 + 厚度 + 构件级抗拉。</summary>
public record LeebComponent(
    string Name,
    double ThicknessMm,
    int[][] TestAreasRaw,
    double CompFbMinAvg
);

/// <summary>一个检测批的报告数据：构件数组 + 批级抗拉平均。</summary>
public record LeebReportBatch(
    string SheetName,
    LeebComponent[] Components,
    double BatchFbCharAvg
);

public static class LeebReportTable
{
    private const string FontHeader = "仿宋";
    private const string FontDataLatin = "Times New Roman";
    private const string FontBatchLevel = "宋体";

    // ClosedXML 把列宽存为 customWidth = userWidth + ~0.71 padding；openpyxl 读出来含 padding。
    // 目标列宽（openpyxl 读法）= 期望值；C# 设置时减去 padding 让 openpyxl 读出来匹配。
    private const double WidthPadding = 0.71;

    public static void Write(IXLWorksheet ws, LeebReportBatch batch)
    {
        // ── 列宽（目标值减 padding）──
        ws.Column(1).Width = 4.78 - WidthPadding;     // A 序号
        ws.Column(2).Width = 17.11 - WidthPadding;    // B 构件位置
        for (int c = 3; c <= 11; c++)
            ws.Column(c).Width = 4.67 - WidthPadding; // C-K HL 数据
        ws.Column(12).Width = 8.78 - WidthPadding;    // L 厚度
        // M / N 用默认列宽

        // ── 表头（第 1 行）──
        ws.Row(1).Height = 72;
        ws.Cell(1, 1).Value = "序号";
        ws.Cell(1, 2).Value = "构件位置";
        ws.Cell(1, 3).Value = "里氏硬度值（HLi）";
        ws.Range(1, 3, 1, 11).Merge();   // C1:K1 跨 9 列
        ws.Cell(1, 12).Value = "钢材测区厚度（mm）";
        ws.Cell(1, 13).Value = "钢材抗拉特征值（N/mm²）";
        ws.Cell(1, 14).Value = "钢材抗拉特征值的平均值（N/mm²）";

        var headerRange = ws.Range(1, 1, 1, 14);
        headerRange.Style.Font.FontName = FontHeader;
        headerRange.Style.Font.FontSize = 10.5;
        headerRange.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
        headerRange.Style.Alignment.Vertical = XLAlignmentVerticalValues.Center;
        headerRange.Style.Alignment.WrapText = true;

        // ── 数据行：每构件 3 行（27 原始 HL 值）──
        int row = 2;
        for (int i = 0; i < batch.Components.Length; i++)
        {
            var comp = batch.Components[i];
            int startRow = row;

            // C-K：3 行 × 9 列原始 HL 数据
            for (int areaIdx = 0; areaIdx < comp.TestAreasRaw.Length; areaIdx++)
            {
                var readings = comp.TestAreasRaw[areaIdx];
                for (int k = 0; k < readings.Length && k < 9; k++)
                {
                    var cell = ws.Cell(row + areaIdx, 3 + k);
                    cell.Value = readings[k];
                    cell.Style.Font.FontName = FontDataLatin;
                    cell.Style.Font.FontSize = 11.0;
                    cell.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
                    cell.Style.Alignment.Vertical = XLAlignmentVerticalValues.Center;
                }
            }

            // A 列：序号（跨 3 行合并），Times New Roman 10.5
            var aCell = ws.Cell(startRow, 1);
            aCell.Value = i + 1;
            ApplyCenteredFont(aCell, FontDataLatin, 10.5, wrap: true);
            ws.Range(startRow, 1, startRow + 2, 1).Merge();

            // B 列：构件位置（跨 3 行合并），Times New Roman 10（字号小一档）
            var bCell = ws.Cell(startRow, 2);
            bCell.Value = comp.Name;
            ApplyCenteredFont(bCell, FontDataLatin, 10.0, wrap: true);
            ws.Range(startRow, 2, startRow + 2, 2).Merge();

            // L 列：厚度（跨 3 行合并），Times New Roman 10.5
            var lCell = ws.Cell(startRow, 12);
            lCell.Value = comp.ThicknessMm;
            ApplyCenteredFont(lCell, FontDataLatin, 10.5, wrap: true);
            ws.Range(startRow, 12, startRow + 2, 12).Merge();

            // M 列：构件抗拉特征值（跨 3 行合并），Times New Roman 11
            var mCell = ws.Cell(startRow, 13);
            mCell.Value = Math.Round(comp.CompFbMinAvg, 1);
            ApplyCenteredFont(mCell, FontDataLatin, 11.0, wrap: true);
            ws.Range(startRow, 13, startRow + 2, 13).Merge();

            row += 3;
        }

        int lastRow = row - 1;

        // ── N 列：批级抗拉特征值平均（整批 N2:N{lastRow} 合并），宋体 11 ──
        if (batch.Components.Length > 0)
        {
            var nCell = ws.Cell(2, 14);
            nCell.Value = Math.Round(batch.BatchFbCharAvg, 1);
            ApplyCenteredFont(nCell, FontBatchLevel, 11.0, wrap: false);
            ws.Range(2, 14, lastRow, 14).Merge();
        }

        // ── 全 thin 边框（A1 到 N{lastRow}）──
        var fullRange = ws.Range(1, 1, lastRow, 14);
        fullRange.Style.Border.InsideBorder = XLBorderStyleValues.Thin;
        fullRange.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
    }

    private static void ApplyCenteredFont(IXLCell cell, string fontName, double size, bool wrap)
    {
        cell.Style.Font.FontName = fontName;
        cell.Style.Font.FontSize = size;
        cell.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
        cell.Style.Alignment.Vertical = XLAlignmentVerticalValues.Center;
        cell.Style.Alignment.WrapText = wrap;
    }
}
