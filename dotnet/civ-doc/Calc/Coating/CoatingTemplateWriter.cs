// 生成「防火涂层厚度」输入 Excel 空白模板（构件清单驱动）。
//
// 模板含 3 张 sheet：
//   「类型预设」 预填 梁/柱（构件类型 → 测点面布置 + 默认设计厚度），可改/可加。
//   「构件清单」 用户主填：一构件一行（批次/构件位置/构件类型/长度(m)/截面数/设计厚度）。
//   「说明」     用法。
// 用户填完构件清单 → coating.expand_template 展开成「测点数据-<类型>」网格 → 只填数字 → coating.run。

using ClosedXML.Excel;
using CivCore.Doc.Server;

namespace CivCore.Doc.Calc.Coating;

public static class CoatingTemplateWriter
{
    public static void Write(string path, string standard = CoatingStandards.GB_50205_2020)
    {
        CoatingStandards.Validate(standard);
        using var wb = new XLWorkbook();

        // ① 类型预设（预填梁/柱）
        var preset = wb.Worksheets.Add(CoatingColumns.TypePresetSheet);
        WriteHeader(preset, new[]
        {
            CoatingColumns.MemberType, CoatingColumns.PointPositions, CoatingColumns.DefaultDesignThickness,
        });
        preset.Cell(2, 1).Value = "梁";
        preset.Cell(2, 2).Value = "梁侧面,梁侧面,梁底面";
        preset.Cell(2, 3).Value = 3.3;
        preset.Cell(3, 1).Value = "柱";
        preset.Cell(3, 2).Value = "东侧面,西侧面,南侧面,北侧面";
        preset.Cell(3, 3).Value = 24;
        Frame(preset, 3, 3);
        preset.Column(2).Width = 30;

        // ② 构件清单（空 + 2 行样例）
        var list = wb.Worksheets.Add(CoatingColumns.MemberListSheet);
        WriteHeader(list, new[]
        {
            CoatingColumns.Batch, CoatingColumns.MemberLocation, CoatingColumns.MemberType,
            CoatingColumns.LengthM, CoatingColumns.SectionCount, CoatingColumns.DesignThickness,
        });
        // 样例：梁填长度(自动算截面数)、柱直接填截面数；设计厚度留空走类型预设默认
        list.Cell(2, 1).Value = "批次1";
        list.Cell(2, 2).Value = "地上一层1/A轴钢梁";
        list.Cell(2, 4).Value = 8; // 长度 8m
        list.Cell(3, 1).Value = "批次1";
        list.Cell(3, 2).Value = "地上一层1/4×4/A轴钢柱";
        list.Cell(3, 5).Value = 3; // 截面数 3
        Frame(list, 3, 6);
        list.Column(2).Width = 26;

        // ③ 说明
        var help = wb.Worksheets.Add("说明");
        help.Cell(1, 1).Value = $"防火涂层厚度检测模板（{standard}）";
        help.Cell(1, 1).Style.Font.Bold = true;
        help.Cell(1, 1).Style.Font.FontSize = 14;
        help.Cell(3, 1).Value = "1. 在「构件清单」一构件一行：构件位置必填；构件类型可留空（自动从名字含「梁/柱」识别）。";
        help.Cell(4, 1).Value = "2. 截面数：填「长度(m)」自动算（国标每3m、北京地标每1m 一截面，向上取整），或直接填「截面数」覆盖。";
        help.Cell(5, 1).Value = "3. 设计厚度：留空用「类型预设」默认；个别构件不同（如有的3.3、有的2.0）在本行填覆盖。";
        help.Cell(6, 1).Value = "4. 涂层类型按设计厚度自动分级：≥7mm 厚型、3~7mm 薄型、≤3mm 超薄型（决定判定、布点与精度）。";
        help.Cell(7, 1).Value = "5. 填完构件清单 → 运行「展开测点网格」生成「测点数据-梁/柱」表 → 只在网格里填实测数字 → 计算。";
        help.Cell(8, 1).Value = "6. 国标薄型/超薄型按 5 处布点、每处 3 个测点（生成「测点数据-<类型>-膨胀型」表，索引列「处号」1~5，列头 测点1/测点2/测点3）；地标仍按截面布点。";
        help.Cell(9, 1).Value = "7. 单位统一 mm；厚型显示2位（游标卡尺）、薄型/超薄型3位（涂层测厚仪）。";
        help.Cell(10, 1).Value = "8. 判定：厚型 ≥80%测点达标且最薄≥设计×0.85；膨胀型(薄/超薄) 构件均值 ≥ 设计×0.95（偏差−5%）。";
        help.Column(1).Width = 115;

        AtomicFile.SaveWorkbook(wb, path);
    }

    private static void WriteHeader(IXLWorksheet ws, string[] headers)
    {
        for (int c = 0; c < headers.Length; c++)
        {
            var cell = ws.Cell(1, c + 1);
            cell.Value = headers[c];
            cell.Style.Font.Bold = true;
            cell.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
            cell.Style.Fill.BackgroundColor = XLColor.LightGray;
        }
    }

    private static void Frame(IXLWorksheet ws, int lastRow, int lastCol)
    {
        var range = ws.Range(1, 1, lastRow, lastCol);
        range.Style.Border.InsideBorder = XLBorderStyleValues.Thin;
        range.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
    }
}
