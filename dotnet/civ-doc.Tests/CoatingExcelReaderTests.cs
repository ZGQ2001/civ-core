// CoatingExcelReader 单测：读「测点数据-<类型>」宽表（expand 生成、用户填数字的那张）。

using System.IO;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingExcelReaderTests
{
    // 写一张「测点数据-梁」sheet：批次|构件位置|构件类型|涂层类型|设计厚度|截面号|梁侧面|梁侧面|梁底面
    private static void WriteBeamSheet(XLWorkbook wb, string name = "测点数据-梁")
    {
        var ws = wb.Worksheets.Add(name);
        var headers = new[] { "批次", "构件位置", "构件类型", "涂层类型", "设计厚度", "截面号", "梁侧面", "梁侧面", "梁底面" };
        for (int c = 0; c < headers.Length; c++) ws.Cell(1, c + 1).Value = headers[c];
        // 梁1：2 截面 × 3 面（设计 20 → 厚型）
        var rows = new[]
        {
            new object[] { "B1", "梁1", "梁", "厚型", 20, 1, 21, 22, 27 },
            new object[] { "B1", "梁1", "梁", "厚型", 20, 2, 24, 25, 28 },
        };
        int r = 2;
        foreach (var row in rows)
        {
            for (int c = 0; c < row.Length; c++) ws.Cell(r, c + 1).Value = XLCellValue.FromObject(row[c]);
            r++;
        }
    }

    private static string Save(Action<XLWorkbook> setup)
    {
        string path = Path.Combine(Path.GetTempPath(), $"coating_rd_{Guid.NewGuid():N}.xlsx");
        using var wb = new XLWorkbook();
        setup(wb);
        wb.SaveAs(path);
        return path;
    }

    [Fact]
    public void ReadRows_单sheet_一构件_两截面六测点()
    {
        string path = Save(wb => WriteBeamSheet(wb));
        try
        {
            var batches = CoatingExcelReader.ReadRows(path);
            Assert.Single(batches);
            Assert.Equal("B1", batches[0].BatchId);
            var m = Assert.Single(batches[0].Members);
            Assert.Equal("梁1", m.Location);
            Assert.Equal("梁", m.MemberType);
            Assert.Equal(20, m.DesignThickness);
            Assert.Equal(6, m.Points.Length);
            Assert.Equal("梁侧面", m.Points[0].Position);
            Assert.Equal("梁底面", m.Points[2].Position);
            Assert.Equal(2, m.Points[5].SectionNo);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_多类型sheet_合并所有构件()
    {
        string path = Save(wb =>
        {
            WriteBeamSheet(wb);
            var ws = wb.Worksheets.Add("测点数据-柱");
            var headers = new[] { "批次", "构件位置", "构件类型", "涂层类型", "设计厚度", "截面号", "东侧面", "西侧面", "南侧面", "北侧面" };
            for (int c = 0; c < headers.Length; c++) ws.Cell(1, c + 1).Value = headers[c];
            ws.Cell(2, 1).Value = "B1"; ws.Cell(2, 2).Value = "柱1"; ws.Cell(2, 3).Value = "柱";
            ws.Cell(2, 4).Value = "厚型"; ws.Cell(2, 5).Value = 24; ws.Cell(2, 6).Value = 1;
            ws.Cell(2, 7).Value = 25; ws.Cell(2, 8).Value = 26; ws.Cell(2, 9).Value = 24; ws.Cell(2, 10).Value = 27;
        });
        try
        {
            var batches = CoatingExcelReader.ReadRows(path);
            Assert.Single(batches);
            Assert.Equal(2, batches[0].Members.Count); // 梁1 + 柱1
            var col = batches[0].Members.First(x => x.Location == "柱1");
            Assert.Equal(4, col.Points.Length);
            Assert.Equal("北侧面", col.Points[3].Position);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_构件位置留空行_向上继承()
    {
        string path = Save(wb =>
        {
            var ws = wb.Worksheets.Add("测点数据-梁");
            var headers = new[] { "批次", "构件位置", "构件类型", "涂层类型", "设计厚度", "截面号", "梁侧面", "梁侧面", "梁底面" };
            for (int c = 0; c < headers.Length; c++) ws.Cell(1, c + 1).Value = headers[c];
            // 第一行填全，第二行构件位置/设计留空（模拟合并/手工）
            ws.Cell(2, 1).Value = "B1"; ws.Cell(2, 2).Value = "梁1"; ws.Cell(2, 5).Value = 20; ws.Cell(2, 6).Value = 1;
            ws.Cell(2, 7).Value = 21; ws.Cell(2, 8).Value = 22; ws.Cell(2, 9).Value = 23;
            ws.Cell(3, 6).Value = 2; // 仅截面号 + 测点
            ws.Cell(3, 7).Value = 24; ws.Cell(3, 8).Value = 25; ws.Cell(3, 9).Value = 26;
        });
        try
        {
            var batches = CoatingExcelReader.ReadRows(path);
            var m = Assert.Single(batches[0].Members);
            Assert.Equal("梁1", m.Location);
            Assert.Equal(6, m.Points.Length); // 两行都归到梁1
            Assert.Equal(20, m.DesignThickness);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_5处3点膨胀型sheet_15点入一构件()
    {
        // 国标膨胀型 sheet「测点数据-柱-膨胀型」：5 处 × 3 点（点1/点2/点3）= 15 测点
        string path = Save(wb =>
        {
            var ws = wb.Worksheets.Add("测点数据-柱-膨胀型");
            var headers = new[] { "批次", "构件位置", "构件类型", "涂层类型", "设计厚度", "截面号", "点1", "点2", "点3" };
            for (int c = 0; c < headers.Length; c++) ws.Cell(1, c + 1).Value = headers[c];
            int r = 2;
            for (int chu = 1; chu <= 5; chu++)
            {
                ws.Cell(r, 1).Value = "B1"; ws.Cell(r, 2).Value = "超薄柱1"; ws.Cell(r, 3).Value = "柱";
                ws.Cell(r, 4).Value = "超薄型"; ws.Cell(r, 5).Value = 2.0; ws.Cell(r, 6).Value = chu;
                ws.Cell(r, 7).Value = 1.95; ws.Cell(r, 8).Value = 1.90; ws.Cell(r, 9).Value = 1.92;
                r++;
            }
        });
        try
        {
            var batches = CoatingExcelReader.ReadRows(path);
            var m = Assert.Single(batches[0].Members);
            Assert.Equal("超薄柱1", m.Location);
            Assert.Equal(2.0, m.DesignThickness);
            Assert.Equal(15, m.Points.Length);     // 5 处 × 3 点
            Assert.Equal("点1", m.Points[0].Position);
            Assert.Equal(5, m.Points[14].SectionNo); // 末点在第 5 处
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_无测点数据sheet_抛异常_提示先展开()
    {
        string path = Save(wb => wb.Worksheets.Add("构件清单").Cell(1, 1).Value = "批次");
        try
        {
            var ex = Assert.Throws<ArgumentException>(() => CoatingExcelReader.ReadRows(path));
            Assert.Contains("expand_template", ex.Message);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ListBatchIds_去重保序()
    {
        string path = Save(wb =>
        {
            var ws = wb.Worksheets.Add("测点数据-梁");
            var headers = new[] { "批次", "构件位置", "构件类型", "涂层类型", "设计厚度", "截面号", "梁侧面" };
            for (int c = 0; c < headers.Length; c++) ws.Cell(1, c + 1).Value = headers[c];
            ws.Cell(2, 1).Value = "A"; ws.Cell(2, 2).Value = "m1"; ws.Cell(2, 5).Value = 20; ws.Cell(2, 6).Value = 1; ws.Cell(2, 7).Value = 21;
            ws.Cell(3, 1).Value = "B"; ws.Cell(3, 2).Value = "m2"; ws.Cell(3, 5).Value = 20; ws.Cell(3, 6).Value = 1; ws.Cell(3, 7).Value = 21;
            ws.Cell(4, 1).Value = "A"; ws.Cell(4, 2).Value = "m3"; ws.Cell(4, 5).Value = 20; ws.Cell(4, 6).Value = 1; ws.Cell(4, 7).Value = 21;
        });
        try
        {
            Assert.Equal(new[] { "A", "B" }, CoatingExcelReader.ListBatchIds(path));
        }
        finally { File.Delete(path); }
    }
}
