// 锚杆「判定依据」sheet —— 演算稿：把判定用的公式 + 规范条款 + 符号含义写成一张可见 sheet，
// 让用户/审核在结果 xlsx 里直接看到「每个合格/不合格凭哪条公式、哪本规范算出来」
// （对齐领域约束：判定结果附公式和中间值，程序不能是黑盒）。
//
// 与「<batchId>-数据分析」分工：数据分析表给每根锚杆的输入 + 中间值 M/Q/R + 判定（值）；
// 本表给「这些值是怎么算的」（公式 + 规范 + 符号）。两张合起来 = 完整演算稿。
//
// 独立 sheet 安全性：AnchorExcelReader 跳过无「锚杆编号」列的 sheet、AnchorResultReader 只读
// 「<batchId>-数据分析」，故本表不被任何 reader 回读，加它不影响 result 往返（report.run_from_result）。

using ClosedXML.Excel;

namespace CivCore.Doc.ReportTables;

public static class AnchorJudgmentBasisSheet
{
    public const string SheetName = "判定依据";

    // 公式与 AnchorMath.ComputeRow 一一对应；改公式时同步此处（演算稿即真相，不能漂移）。
    private static readonly (string Label, string Content)[] Items =
    {
        ("规范", "GB 50086-2015《岩土锚杆与喷射混凝土支护工程技术规范》附录 C（蠕变/抗拔试验）"),
        ("弹性位移量 M", "M = 1.2Nt 持荷 5min 位移 - 卸载至 0.1Nt 位移"),
        ("下限 Q", "Q = 0.9·P·Lf / (E·A)，即自由段弹性变形的 90%"),
        ("上限 R", "R = (Lf + La/3)·P / (E·A)，即自由段 + 1/3 锚固段弹性变形"),
        ("判定", "合格 ⇔ Q < M < R（开区间）"),
        ("符号", "P=轴向设计荷载(N)；Lf=自由段长(mm)；La=锚固段长(mm)；A=钢筋截面积(mm²)；E=弹性模量(N/mm²)"),
    };

    /// <summary>把锚杆判定的公式 + 规范条款 + 符号写成一张可见 sheet（演算稿）。幂等：已存在先删。</summary>
    public static void Write(XLWorkbook wb)
    {
        if (wb.Worksheets.TryGetWorksheet(SheetName, out var old)) old.Delete();
        var ws = wb.Worksheets.Add(SheetName);

        ws.Cell(1, 1).Value = "锚杆抗拔判定依据（演算稿）";
        ws.Cell(1, 1).Style.Font.Bold = true;

        int row = 3;
        foreach (var (label, content) in Items)
        {
            ws.Cell(row, 1).Value = label;
            ws.Cell(row, 1).Style.Font.Bold = true;
            ws.Cell(row, 2).Value = content;
            row++;
        }

        ws.Column(1).Width = 16;
        ws.Column(2).Width = 80;
    }
}
