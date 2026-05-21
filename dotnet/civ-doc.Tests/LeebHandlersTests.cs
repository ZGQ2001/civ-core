// LeebHandlers 集成测试 —— 走完整的 RPC handler 路径（JsonElement params → 内部读+算 → JSON 返回）。
// 跟 Python 端 src/civ_core/api/handlers/leeb.py 的 leeb.run 行为对齐。

using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.Handlers;
using Xunit;

namespace CivCore.Doc.Tests;

public class LeebHandlersTests : IDisposable
{
    private readonly string _tmpDir;

    public LeebHandlersTests()
    {
        _tmpDir = Path.Combine(Path.GetTempPath(), $"civ-doc-leeb-{Guid.NewGuid()}");
        Directory.CreateDirectory(_tmpDir);
    }

    public void Dispose() => Directory.Delete(_tmpDir, recursive: true);

    private string MakeInputXlsx()
    {
        var path = Path.Combine(_tmpDir, "input.xlsx");
        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add("检测批1");
        ws.Cell(1, 1).Value = "序号";
        ws.Cell(1, 2).Value = "构件位置";
        for (int c = 0; c < 9; c++)
            ws.Cell(1, 3 + c).Value = $"HL{c + 1}";
        ws.Cell(1, 12).Value = "厚度";

        ws.Cell(2, 1).Value = 1;
        ws.Cell(2, 2).Value = "钢柱A-1";
        int[] r1 = { 467, 465, 471, 468, 467, 468, 473, 472, 463 };
        int[] r2 = { 471, 478, 471, 470, 480, 477, 472, 475, 465 };
        int[] r3 = { 477, 481, 468, 469, 478, 470, 469, 476, 462 };
        for (int c = 0; c < 9; c++)
        {
            ws.Cell(2, 3 + c).Value = r1[c];
            ws.Cell(3, 3 + c).Value = r2[c];
            ws.Cell(4, 3 + c).Value = r3[c];
        }
        ws.Cell(2, 12).Value = 12;

        wb.SaveAs(path);
        return path;
    }

    [Fact]
    public void LeebRun_完整链路_批数_构件数_输出路径_应正确()
    {
        var inputPath = MakeInputXlsx();
        var paramsJson = JsonSerializer.SerializeToElement(new
        {
            input_xlsx = inputPath,
            angle_degrees = 0.0,
        });

        var result = LeebHandlers.Run(paramsJson) as Dictionary<string, object?>;
        Assert.NotNull(result);
        Assert.Equal(1, result!["batches"]);
        Assert.Equal(1, result["components"]);

        // 默认输出路径带 "_里氏_结果.xlsx" 后缀
        var output = result["output"] as string;
        Assert.NotNull(output);
        Assert.EndsWith("input_里氏_结果.xlsx", output);
    }

    [Fact]
    public void LeebRun_report_table_data_结构_应跟Python一致()
    {
        var inputPath = MakeInputXlsx();
        var paramsJson = JsonSerializer.SerializeToElement(new
        {
            input_xlsx = inputPath,
            angle_degrees = 0.0,
        });

        var result = LeebHandlers.Run(paramsJson) as Dictionary<string, object?>;
        var reportData = result!["report_table_data"] as List<Dictionary<string, object?>>;
        Assert.NotNull(reportData);
        Assert.Single(reportData!);

        var batch = reportData![0];
        Assert.Equal("检测批1", batch["sheet_name"]);  // sheet 名作为批名（不带后缀）

        // batch_fb_char_avg 应等于 Python 黄金值 512.0（合成数据 = 单构件）
        var batchAvg = Convert.ToDouble(batch["batch_fb_char_avg"]);
        Assert.Equal(512.0, batchAvg, precision: 6);

        var components = batch["components"] as List<Dictionary<string, object?>>;
        Assert.NotNull(components);
        Assert.Single(components!);

        var comp = components![0];
        Assert.Equal("钢柱A-1", comp["name"]);
        Assert.Equal(12.0, Convert.ToDouble(comp["thickness_mm"]));
        Assert.Equal(512.0, Convert.ToDouble(comp["comp_fb_min_avg"]), precision: 6);
    }

    [Fact]
    public void LeebRun_自定义output_xlsx_应回显在结果()
    {
        var inputPath = MakeInputXlsx();
        var customOut = Path.Combine(_tmpDir, "myresult.xlsx");
        var paramsJson = JsonSerializer.SerializeToElement(new
        {
            input_xlsx = inputPath,
            output_xlsx = customOut,
            angle_degrees = 0.0,
        });

        var result = LeebHandlers.Run(paramsJson) as Dictionary<string, object?>;
        Assert.Equal(customOut, result!["output"]);
    }
}
