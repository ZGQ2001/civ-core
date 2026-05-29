// CoatingExcelReader 单测：用 ClosedXML 内存里建长表 sheet 喂给 reader。

using System.IO;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingExcelReaderTests
{
    private static readonly string[] Headers =
    {
        "批次", "构件位置", "构件类型", "设计厚度", "截面号", "测点位置", "实测厚度",
    };

    private static string MakeTempFile(Action<IXLWorksheet> setup)
    {
        string path = Path.Combine(Path.GetTempPath(), $"coating_test_{Guid.NewGuid():N}.xlsx");
        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add("Sheet1");
        for (int c = 0; c < Headers.Length; c++) ws.Cell(1, c + 1).Value = Headers[c];
        setup(ws);
        wb.SaveAs(path);
        return path;
    }

    /// <summary>写一个测点行。</summary>
    private static void Row(IXLWorksheet ws, int r, string batch, string loc, string type,
        double design, int section, string pos, double thickness)
    {
        ws.Cell(r, 1).Value = batch;
        ws.Cell(r, 2).Value = loc;
        ws.Cell(r, 3).Value = type;
        ws.Cell(r, 4).Value = design;
        ws.Cell(r, 5).Value = section;
        ws.Cell(r, 6).Value = pos;
        ws.Cell(r, 7).Value = thickness;
    }

    [Fact]
    public void ReadRows_单批一构件_两截面六测点()
    {
        string path = MakeTempFile(ws =>
        {
            int r = 2;
            Row(ws, r++, "B1", "梁1", "梁", 24, 1, "梁侧面", 25);
            Row(ws, r++, "B1", "梁1", "梁", 24, 1, "梁侧面", 26);
            Row(ws, r++, "B1", "梁1", "梁", 24, 1, "梁底面", 27);
            Row(ws, r++, "B1", "梁1", "梁", 24, 2, "梁侧面", 24);
            Row(ws, r++, "B1", "梁1", "梁", 24, 2, "梁侧面", 25);
            Row(ws, r++, "B1", "梁1", "梁", 24, 2, "梁底面", 28);
        });
        try
        {
            var batches = CoatingExcelReader.ReadRows(path);
            Assert.Single(batches);
            Assert.Equal("B1", batches[0].BatchId);
            Assert.Single(batches[0].Members);
            var m = batches[0].Members[0];
            Assert.Equal("梁1", m.Location);
            Assert.Equal("梁", m.MemberType);
            Assert.Equal(24, m.DesignThickness);
            Assert.Equal(6, m.Points.Length);
            Assert.Equal("梁侧面", m.Points[0].Position);
            Assert.Equal(2, m.Points[5].SectionNo);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_批次列为空_归入默认批()
    {
        string path = MakeTempFile(ws =>
        {
            int r = 2;
            Row(ws, r++, "", "柱1", "柱", 24, 1, "东侧面", 25);
            Row(ws, r++, "", "柱1", "柱", 24, 1, "西侧面", 26);
        });
        try
        {
            var batches = CoatingExcelReader.ReadRows(path);
            Assert.Single(batches);
            Assert.Equal(CoatingExcelReader.DefaultBatchId, batches[0].BatchId);
            Assert.Single(batches[0].Members);
            Assert.Equal(2, batches[0].Members[0].Points.Length);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_多批多构件_保持出现顺序()
    {
        string path = MakeTempFile(ws =>
        {
            int r = 2;
            Row(ws, r++, "B2", "梁A", "梁", 24, 1, "梁底面", 25);
            Row(ws, r++, "B1", "梁B", "梁", 24, 1, "梁底面", 25);
            Row(ws, r++, "B2", "梁C", "梁", 24, 1, "梁底面", 25);
        });
        try
        {
            var batches = CoatingExcelReader.ReadRows(path);
            Assert.Equal(2, batches.Count);
            Assert.Equal("B2", batches[0].BatchId);
            Assert.Equal(2, batches[0].Members.Count);
            Assert.Equal("梁A", batches[0].Members[0].Location);
            Assert.Equal("B1", batches[1].BatchId);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_缺实测厚度列_抛异常_提示列名()
    {
        string path = Path.Combine(Path.GetTempPath(), $"coating_missing_{Guid.NewGuid():N}.xlsx");
        using (var wb = new XLWorkbook())
        {
            var ws = wb.Worksheets.Add("Sheet1");
            // 只写到「测点位置」，故意缺「实测厚度」
            for (int c = 0; c < 6; c++) ws.Cell(1, c + 1).Value = Headers[c];
            ws.Cell(2, 2).Value = "梁1";
            wb.SaveAs(path);
        }
        try
        {
            var ex = Assert.Throws<ArgumentException>(() => CoatingExcelReader.ReadRows(path));
            Assert.Contains("实测厚度", ex.Message);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_同构件设计厚度不一致_抛异常()
    {
        string path = MakeTempFile(ws =>
        {
            int r = 2;
            Row(ws, r++, "B1", "梁1", "梁", 24, 1, "梁底面", 25);
            Row(ws, r++, "B1", "梁1", "梁", 30, 2, "梁底面", 25); // 设计厚度变了
        });
        try
        {
            var ex = Assert.Throws<ArgumentException>(() => CoatingExcelReader.ReadRows(path));
            Assert.Contains("设计厚度不一致", ex.Message);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_设计厚度带单位后缀_容错解析()
    {
        string path = MakeTempFile(ws =>
        {
            ws.Cell(2, 1).Value = "B1";
            ws.Cell(2, 2).Value = "柱1";
            ws.Cell(2, 3).Value = "柱";
            ws.Cell(2, 4).Value = "24mm"; // 文本带单位
            ws.Cell(2, 5).Value = 1;
            ws.Cell(2, 6).Value = "东侧面";
            ws.Cell(2, 7).Value = 25;
        });
        try
        {
            var batches = CoatingExcelReader.ReadRows(path);
            Assert.Equal(24, batches[0].Members[0].DesignThickness);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ListBatchIds_去重并保序()
    {
        string path = MakeTempFile(ws =>
        {
            int r = 2;
            Row(ws, r++, "A", "m1", "梁", 24, 1, "梁底面", 25);
            Row(ws, r++, "B", "m2", "梁", 24, 1, "梁底面", 25);
            Row(ws, r++, "A", "m3", "梁", 24, 1, "梁底面", 25);
            Row(ws, r++, "C", "m4", "梁", 24, 1, "梁底面", 25);
        });
        try
        {
            var ids = CoatingExcelReader.ListBatchIds(path);
            Assert.Equal(new[] { "A", "B", "C" }, ids);
        }
        finally { File.Delete(path); }
    }
}
