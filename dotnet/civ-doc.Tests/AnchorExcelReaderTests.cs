// AnchorExcelReader 单测：用 ClosedXML 内存里建 sheet 喂给 reader。

using System.IO;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;
using Xunit;

namespace CivCore.Doc.Tests;

public class AnchorExcelReaderTests
{
    private static string MakeTempFile(Action<IXLWorksheet> setup, string sheetName = "Sheet1")
    {
        string path = Path.Combine(Path.GetTempPath(),
            $"anchor_test_{Guid.NewGuid():N}.xlsx");
        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add(sheetName);
        setup(ws);
        wb.SaveAs(path);
        return path;
    }

    private static void WriteHeaders(IXLWorksheet ws)
    {
        var headers = new[]
        {
            "批次", "锚杆编号",
            "0.1Nt", "0.4Nt", "0.7Nt", "1.0Nt",
            "1.2Nt-1min", "1.2Nt-3min", "1.2Nt-5min",
            "卸载1.0Nt", "卸载0.7Nt", "卸载0.4Nt", "卸载0.1Nt",
        };
        for (int c = 0; c < headers.Length; c++) ws.Cell(1, c + 1).Value = headers[c];
    }

    [Fact]
    public void ReadRows_单批次_两根锚杆()
    {
        string path = MakeTempFile(ws =>
        {
            WriteHeaders(ws);
            int[] vals1 = { 0, 1, 1, 2, 3, 3, 3, 2, 2, 1, 1 };  // 占位（数字会被读成 double）
            ws.Cell(2, 1).Value = "B1"; ws.Cell(2, 2).Value = "1";
            for (int i = 0; i < 11; i++) ws.Cell(2, 3 + i).Value = vals1[i];
            ws.Cell(3, 1).Value = "B1"; ws.Cell(3, 2).Value = "2";
            for (int i = 0; i < 11; i++) ws.Cell(3, 3 + i).Value = vals1[i];
        });
        try
        {
            var batches = AnchorExcelReader.ReadRows(path);
            Assert.Single(batches);
            Assert.Equal("B1", batches[0].BatchId);
            Assert.Equal(2, batches[0].Rows.Count);
            Assert.Equal("1", batches[0].Rows[0].AnchorId);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_多批次_保持出现顺序()
    {
        string path = MakeTempFile(ws =>
        {
            WriteHeaders(ws);
            ws.Cell(2, 1).Value = "B2"; ws.Cell(2, 2).Value = "1";
            ws.Cell(3, 1).Value = "B1"; ws.Cell(3, 2).Value = "1";
            ws.Cell(4, 1).Value = "B2"; ws.Cell(4, 2).Value = "2";
            for (int r = 2; r <= 4; r++)
                for (int c = 3; c <= 13; c++) ws.Cell(r, c).Value = 1.0;
        });
        try
        {
            var batches = AnchorExcelReader.ReadRows(path);
            Assert.Equal(2, batches.Count);
            Assert.Equal("B2", batches[0].BatchId);
            Assert.Equal(2, batches[0].Rows.Count);
            Assert.Equal("B1", batches[1].BatchId);
            Assert.Single(batches[1].Rows);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_列名带全角括号_应能识别()
    {
        string path = MakeTempFile(ws =>
        {
            // 列名带全角空格和括号 —— NormalizeHeader 应抹平
            var headers = new[]
            {
                "批次", "锚杆编号",
                "0.1Nt", "0.4Nt", "0.7Nt", "1.0Nt",
                "1.2Nt-1min", "1.2Nt-3min", "1.2Nt-5min",
                "卸载1.0Nt", "卸载0.7Nt", " 卸载0.4Nt ", "卸载0.1Nt",
            };
            for (int c = 0; c < headers.Length; c++) ws.Cell(1, c + 1).Value = headers[c];
            ws.Cell(2, 1).Value = "B1"; ws.Cell(2, 2).Value = "1";
            for (int c = 3; c <= 13; c++) ws.Cell(2, c).Value = 1.0;
        });
        try
        {
            var batches = AnchorExcelReader.ReadRows(path);
            Assert.Single(batches);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ReadRows_缺位移列_抛异常_提示缺失列名()
    {
        string path = MakeTempFile(ws =>
        {
            ws.Cell(1, 1).Value = "批次";
            ws.Cell(1, 2).Value = "锚杆编号";
            // 故意只写 4 列位移读数（缺 7 个）
            ws.Cell(1, 3).Value = "0.1Nt";
            ws.Cell(2, 1).Value = "B1"; ws.Cell(2, 2).Value = "1"; ws.Cell(2, 3).Value = 0;
        });
        try
        {
            var ex = Assert.Throws<ArgumentException>(() => AnchorExcelReader.ReadRows(path));
            Assert.Contains("0.4Nt", ex.Message);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void ListBatchIds_去重并保序()
    {
        string path = MakeTempFile(ws =>
        {
            WriteHeaders(ws);
            ws.Cell(2, 1).Value = "A"; ws.Cell(2, 2).Value = "1";
            ws.Cell(3, 1).Value = "B"; ws.Cell(3, 2).Value = "1";
            ws.Cell(4, 1).Value = "A"; ws.Cell(4, 2).Value = "2";
            ws.Cell(5, 1).Value = "C"; ws.Cell(5, 2).Value = "1";
        });
        try
        {
            var ids = AnchorExcelReader.ListBatchIds(path);
            Assert.Equal(new[] { "A", "B", "C" }, ids);
        }
        finally { File.Delete(path); }
    }
}
