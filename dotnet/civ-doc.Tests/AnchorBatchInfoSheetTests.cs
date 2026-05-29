// AnchorBatchInfoSheet 单测：输入 xlsx「批次信息」sheet 的读写往返 + 边界。
// 这张 sheet 是按批次工程参数 + 灌浆日期的唯一来源（前端预填 / anchor.run 回退都读它）。

using System;
using System.IO;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;
using Xunit;

namespace CivCore.Doc.Tests;

public class AnchorBatchInfoSheetTests
{
    [Fact]
    public void WriteThenRead_往返_参数与灌浆日期()
    {
        string path = TempXlsx();
        try
        {
            var infos = new[]
            {
                new AnchorBatchInfo("批次1",
                    AnchorParams.Create(180000, 500, 7500, 804.25, 200000), "2026-05-01"),
                new AnchorBatchInfo("批次2",
                    AnchorParams.Create(200000, 600, 8000, 900, 200000), ""),
            };
            using (var wb = new XLWorkbook())
            {
                AnchorBatchInfoSheet.Write(wb, infos);
                wb.SaveAs(path);
            }

            var read = AnchorBatchInfoSheet.Read(path);
            Assert.Equal(2, read.Count);

            Assert.Equal("批次1", read[0].BatchId);
            Assert.NotNull(read[0].Params);
            Assert.Equal(180000d, read[0].Params!.AxialDesignLoad);
            Assert.Equal(804.25d, read[0].Params!.SteelArea);
            Assert.Equal("2026-05-01", read[0].GroutingDate);

            Assert.Equal("批次2", read[1].BatchId);
            Assert.Equal(200000d, read[1].Params!.AxialDesignLoad);
            Assert.Equal("", read[1].GroutingDate);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Read_无批次信息sheet_返回空列表()
    {
        string path = TempXlsx();
        try
        {
            using (var wb = new XLWorkbook())
            {
                wb.Worksheets.Add("其它");
                wb.SaveAs(path);
            }
            Assert.Empty(AnchorBatchInfoSheet.Read(path));
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Read_参数列空_保留批次号与日期_参数为null()
    {
        string path = TempXlsx();
        try
        {
            using (var wb = new XLWorkbook())
            {
                var ws = wb.Worksheets.Add(AnchorBatchInfoSheet.SheetName);
                ws.Cell(1, 1).Value = "批次";
                ws.Cell(2, 1).Value = "批次X";
                ws.Cell(2, 7).Value = "2026-07-07"; // 只有批次号 + 日期，参数列留空
                wb.SaveAs(path);
            }
            var read = AnchorBatchInfoSheet.Read(path);
            Assert.Single(read);
            Assert.Equal("批次X", read[0].BatchId);
            Assert.Null(read[0].Params); // 参数缺失 → null（前端回退默认 / run 报缺参数）
            Assert.Equal("2026-07-07", read[0].GroutingDate);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Read_日期为DateTime单元格_归一化为_yyyy_MM_dd()
    {
        string path = TempXlsx();
        try
        {
            using (var wb = new XLWorkbook())
            {
                var ws = wb.Worksheets.Add(AnchorBatchInfoSheet.SheetName);
                ws.Cell(1, 1).Value = "批次";
                ws.Cell(2, 1).Value = "批次1";
                ws.Cell(2, 7).Value = new DateTime(2026, 5, 1);
                wb.SaveAs(path);
            }
            Assert.Equal("2026-05-01", AnchorBatchInfoSheet.Read(path)[0].GroutingDate);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Read_参数值非法_参数为null_不抛()
    {
        string path = TempXlsx();
        try
        {
            using (var wb = new XLWorkbook())
            {
                var ws = wb.Worksheets.Add(AnchorBatchInfoSheet.SheetName);
                ws.Cell(1, 1).Value = "批次";
                ws.Cell(2, 1).Value = "批次1";
                ws.Cell(2, 2).Value = 0; // P=0 非法（Create 抛）→ 应被吞，Params=null
                ws.Cell(2, 3).Value = 500;
                ws.Cell(2, 4).Value = 7500;
                ws.Cell(2, 5).Value = 804.25;
                ws.Cell(2, 6).Value = 200000;
                wb.SaveAs(path);
            }
            var read = AnchorBatchInfoSheet.Read(path);
            Assert.Single(read);
            Assert.Null(read[0].Params);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Template_含批次信息sheet_批次1默认参数()
    {
        string path = TempXlsx();
        try
        {
            AnchorTemplateWriter.Write(path);
            var read = AnchorBatchInfoSheet.Read(path);
            Assert.Single(read);
            Assert.Equal("批次1", read[0].BatchId);
            Assert.NotNull(read[0].Params);
            Assert.Equal(180000d, read[0].Params!.AxialDesignLoad);
        }
        finally { File.Delete(path); }
    }

    private static string TempXlsx() =>
        Path.Combine(Path.GetTempPath(), $"anchor_bi_{Guid.NewGuid():N}.xlsx");
}
