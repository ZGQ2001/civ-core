// AnchorResultMetadataSheet 单测：结果 xlsx「_批次参数」隐藏 sheet 的读写往返。
// 这张 sheet 是算完持久化、供 report.run_from_result 复用工程参数 + 灌浆日期的来源。

using System;
using System.Collections.Generic;
using System.IO;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.ReportTables;
using Xunit;

namespace CivCore.Doc.Tests;

public class AnchorResultMetadataSheetTests
{
    [Fact]
    public void WriteThenRead_往返_参数与灌浆日期()
    {
        var paramsByBatch = new Dictionary<string, AnchorParams>
        {
            ["批次1"] = AnchorParams.Create(180000, 500, 7500, 804.25, 200000),
            ["批次2"] = AnchorParams.Create(200000, 600, 8000, 900, 200000),
        };
        var dates = new Dictionary<string, string>
        {
            ["批次1"] = "2026-05-01",
            // 批次2 无日期 —— 留空
        };

        using var wb = new XLWorkbook();
        AnchorResultMetadataSheet.Write(wb, paramsByBatch, dates);

        var readParams = AnchorResultMetadataSheet.Read(wb);
        Assert.Equal(2, readParams.Count);
        Assert.Equal(180000d, readParams["批次1"].AxialDesignLoad);
        Assert.Equal(200000d, readParams["批次2"].AxialDesignLoad);

        var readDates = AnchorResultMetadataSheet.ReadGroutingDates(wb);
        Assert.Single(readDates); // 只收非空日期的批次
        Assert.Equal("2026-05-01", readDates["批次1"]);
        Assert.False(readDates.ContainsKey("批次2"));
    }

    [Fact]
    public void Write_隐藏sheet_置Hidden()
    {
        var paramsByBatch = new Dictionary<string, AnchorParams>
        {
            ["批次1"] = AnchorParams.Create(180000, 500, 7500, 804.25, 200000),
        };
        using var wb = new XLWorkbook();
        AnchorResultMetadataSheet.Write(wb, paramsByBatch);
        var ws = wb.Worksheet(AnchorResultMetadataSheet.SheetName);
        Assert.Equal(XLWorksheetVisibility.Hidden, ws.Visibility);
    }

    [Fact]
    public void ReadGroutingDates_旧结果xlsx无第7列_返回空()
    {
        // 模拟旧版本写的 metadata sheet：只有 6 列工程参数，无灌浆日期列。
        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add(AnchorResultMetadataSheet.SheetName);
        ws.Cell(1, 1).Value = "batch_id";
        ws.Cell(2, 1).Value = "批次1";
        ws.Cell(2, 2).Value = 180000;
        ws.Cell(2, 3).Value = 500;
        ws.Cell(2, 4).Value = 7500;
        ws.Cell(2, 5).Value = 804.25;
        ws.Cell(2, 6).Value = 200000;

        // 参数照常读出（向后兼容）
        Assert.Single(AnchorResultMetadataSheet.Read(wb));
        // 灌浆日期为空 dict（旧文件无第 7 列）
        Assert.Empty(AnchorResultMetadataSheet.ReadGroutingDates(wb));
    }

    [Fact]
    public void ReadGroutingDates_DateTime单元格_归一化为_yyyy_MM_dd()
    {
        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add(AnchorResultMetadataSheet.SheetName);
        ws.Cell(1, 1).Value = "batch_id";
        ws.Cell(2, 1).Value = "批次1";
        ws.Cell(2, 7).Value = new DateTime(2026, 5, 1);

        Assert.Equal("2026-05-01", AnchorResultMetadataSheet.ReadGroutingDates(wb)["批次1"]);
    }
}
