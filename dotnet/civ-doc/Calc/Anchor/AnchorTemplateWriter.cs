// 生成「锚杆抗拔试验」输入 Excel 空白模板。
// 用户点「生成模板」→ 下载 xlsx → 填数据 → 上传回来跑计算。
//
// 模板结构（按 AnchorColumns 契约）：
//   表头行：批次 | 锚杆编号 | 0.1Nt | 0.4Nt | ... | 卸载0.1Nt
//   示例行 3 行：批次1 / 1, 2, 3，全 0 占位让用户改
//   sheet 名「锚杆抗拔数据」

using ClosedXML.Excel;
using CivCore.Doc.Server;

namespace CivCore.Doc.Calc.Anchor;

public static class AnchorTemplateWriter
{
    public const string TemplateSheetName = "锚杆抗拔数据";
    private const int SampleRows = 3;

    /// <summary>写空白模板到 path（覆盖已存在文件）。</summary>
    public static void Write(string path, string standard = AnchorStandards.GB_50086_2015)
    {
        AnchorStandards.Validate(standard);

        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add(TemplateSheetName);

        var headers = new List<string> { AnchorColumns.DefaultBatchIdColumn, AnchorColumns.AnchorId };
        headers.AddRange(AnchorColumns.DisplacementColumns);

        // 表头
        for (int c = 0; c < headers.Count; c++)
        {
            var cell = ws.Cell(1, c + 1);
            cell.Value = headers[c];
            cell.Style.Font.Bold = true;
            cell.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
            cell.Style.Fill.BackgroundColor = XLColor.LightGray;
        }

        // 示例数据（3 行，第一根锚杆填一组真实样例方便用户照抄；后两根全 0）
        var sample = new double[]
        {
            0, 0.56, 1.25, 1.96, 2.6, 2.61, 2.63, 2.35, 1.83, 1.21, 0.58,
        };
        for (int i = 0; i < SampleRows; i++)
        {
            int row = i + 2;
            ws.Cell(row, 1).Value = "批次1";
            ws.Cell(row, 2).Value = (i + 1).ToString();
            for (int j = 0; j < AnchorColumns.DisplacementColumns.Length; j++)
            {
                ws.Cell(row, 3 + j).Value = i == 0 ? sample[j] : 0;
            }
        }

        // 列宽
        ws.Column(1).Width = 10;
        ws.Column(2).Width = 10;
        for (int c = 3; c <= headers.Count; c++) ws.Column(c).Width = 12;

        // 边框
        var range = ws.Range(1, 1, 1 + SampleRows, headers.Count);
        range.Style.Border.InsideBorder = XLBorderStyleValues.Thin;
        range.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;

        // 「批次信息」sheet：按批次的工程参数 + 灌浆日期 —— 这些批次级元数据的唯一来源。
        // 预填一行样例批次（与数据 sheet 的「批次1」对应）+ 默认参数，用户照填即可，
        // 之后前端 / agent 直接读它（anchor.read_batch_info），生成报告不必再在 GUI 重输。
        AnchorBatchInfoSheet.Write(wb, new[]
        {
            new AnchorBatchInfo("批次1",
                AnchorParams.Create(180000, 500, 7500, 804.25, 200000),
                GroutingDate: ""),
        });

        // 第二个 sheet 写说明
        var help = wb.Worksheets.Add("说明");
        help.Cell(1, 1).Value = $"锚杆抗拔试验数据模板（{standard}）";
        help.Cell(1, 1).Style.Font.Bold = true;
        help.Cell(1, 1).Style.Font.FontSize = 14;
        help.Cell(3, 1).Value = "1. 「批次」列：同批次的锚杆共享一组工程参数（P/Lf/La/A/E）。在「批次信息」sheet 按批次填参数 + 灌浆日期，前端会自动读取预填（也可在前端覆盖）。";
        help.Cell(4, 1).Value = "2. 位移读数单位：毫米（mm）；Nt = 轴向拉力设计值 P。";
        help.Cell(5, 1).Value = "3. 0.1Nt 表示 0.1·P 时的位移读数，0.4Nt 表示 0.4·P，依此类推。";
        help.Cell(6, 1).Value = "4. 1.2Nt-1min/3min/5min 是持荷阶段三次读数；1.2Nt-5min 是总位移。";
        help.Cell(7, 1).Value = "5. 卸载0.1Nt 是卸载完最终残余读数；弹性位移量 = 1.2Nt-5min − 卸载0.1Nt。";
        help.Cell(9, 1).Value = $"判定：Q < 弹性位移量 < R 为合格（Q=0.9·P·Lf/(E·A)，R=(Lf+La/3)·P/(E·A)）";
        help.Column(1).Width = 90;

        AtomicFile.SaveWorkbook(wb, path);
    }
}
