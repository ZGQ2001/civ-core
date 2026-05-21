// LeebExcelReader 测试 —— 用 ClosedXML 造合成 xlsx，验证 C# 读取行为
// 跟 Python read_leeb_workbook / read_leeb_components 等价。
//
// 测试数据参考 Python tests/test_leeb_excel.py 里的 _write_new_format_workbook 风格。

using ClosedXML.Excel;
using CivCore.Doc.Calc.Leeb;
using Xunit;

namespace CivCore.Doc.Tests;

public class LeebExcelReaderTests : IDisposable
{
    private readonly string _tmpDir;

    public LeebExcelReaderTests()
    {
        _tmpDir = Path.Combine(Path.GetTempPath(), $"civ-doc-test-{Guid.NewGuid()}");
        Directory.CreateDirectory(_tmpDir);
    }

    public void Dispose() => Directory.Delete(_tmpDir, recursive: true);

    /// <summary>造一个合成 leeb 输入 xlsx：2 批 + 第一批 2 构件 + 第二批 1 构件。</summary>
    private string MakeSyntheticWorkbook()
    {
        var path = Path.Combine(_tmpDir, "synthetic_leeb.xlsx");
        using var wb = new XLWorkbook();

        // 检测批1：2 个构件
        var ws1 = wb.Worksheets.Add("检测批1");
        ws1.Cell(1, 1).Value = "序号";
        ws1.Cell(1, 2).Value = "构件位置";
        for (int c = 0; c < 9; c++)
            ws1.Cell(1, 3 + c).Value = $"HL{c + 1}";
        ws1.Cell(1, 12).Value = "厚度";

        // 构件 1：序号 1，钢柱A-1，厚度 12mm，3 测区 9 HL 值
        ws1.Cell(2, 1).Value = 1;
        ws1.Cell(2, 2).Value = "钢柱A-1";
        int[] r1c1 = { 467, 465, 471, 468, 467, 468, 473, 472, 463 };
        int[] r1c2 = { 471, 478, 471, 470, 480, 477, 472, 475, 465 };
        int[] r1c3 = { 477, 481, 468, 469, 478, 470, 469, 476, 462 };
        for (int c = 0; c < 9; c++)
        {
            ws1.Cell(2, 3 + c).Value = r1c1[c];
            ws1.Cell(3, 3 + c).Value = r1c2[c];
            ws1.Cell(4, 3 + c).Value = r1c3[c];
        }
        ws1.Cell(2, 12).Value = 12;

        // 构件 2：序号 2，钢柱A-2，厚度 12mm
        ws1.Cell(5, 1).Value = 2;
        ws1.Cell(5, 2).Value = "钢柱A-2";
        int[] r2c1 = { 470, 472, 471, 469, 473, 475, 470, 472, 471 };
        int[] r2c2 = { 469, 470, 472, 473, 471, 470, 472, 471, 470 };
        int[] r2c3 = { 471, 472, 470, 471, 470, 473, 469, 471, 472 };
        for (int c = 0; c < 9; c++)
        {
            ws1.Cell(5, 3 + c).Value = r2c1[c];
            ws1.Cell(6, 3 + c).Value = r2c2[c];
            ws1.Cell(7, 3 + c).Value = r2c3[c];
        }
        ws1.Cell(5, 12).Value = 12;

        // 检测批2：1 个构件
        var ws2 = wb.Worksheets.Add("检测批2");
        ws2.Cell(1, 1).Value = "序号";
        ws2.Cell(1, 2).Value = "构件位置";
        for (int c = 0; c < 9; c++)
            ws2.Cell(1, 3 + c).Value = $"HL{c + 1}";
        ws2.Cell(1, 12).Value = "厚度";

        ws2.Cell(2, 1).Value = 1;
        ws2.Cell(2, 2).Value = "钢梁B-1";
        int[] b1c1 = { 460, 462, 461, 459, 463, 465, 460, 462, 461 };
        int[] b1c2 = { 459, 460, 462, 463, 461, 460, 462, 461, 460 };
        int[] b1c3 = { 461, 462, 460, 461, 460, 463, 459, 461, 462 };
        for (int c = 0; c < 9; c++)
        {
            ws2.Cell(2, 3 + c).Value = b1c1[c];
            ws2.Cell(3, 3 + c).Value = b1c2[c];
            ws2.Cell(4, 3 + c).Value = b1c3[c];
        }
        ws2.Cell(2, 12).Value = 10;

        wb.SaveAs(path);
        return path;
    }

    [Fact]
    public void ReadWorkbook_合成数据_两批应该都被读到()
    {
        var path = MakeSyntheticWorkbook();
        var workbook = LeebExcelReader.ReadWorkbook(path, defaultAngleDegrees: 0);

        Assert.Equal(2, workbook.Batches.Length);
        Assert.Equal("检测批1", workbook.Batches[0].BatchName);
        Assert.Equal("检测批2", workbook.Batches[1].BatchName);
    }

    [Fact]
    public void ReadWorkbook_检测批1_应包含_2_个构件_第一构件_3测区_9HL值()
    {
        var path = MakeSyntheticWorkbook();
        var workbook = LeebExcelReader.ReadWorkbook(path);

        var batch1 = workbook.Batches[0];
        Assert.Equal(2, batch1.Components.Length);

        var comp1 = batch1.Components[0];
        Assert.Equal(1, comp1.Seq);
        Assert.Equal("钢柱A-1", comp1.Name);
        Assert.Equal(12.0, comp1.Thickness);
        Assert.Equal("检测批1", comp1.BatchName);
        Assert.Equal(3, comp1.TestAreasRaw.Length);
        Assert.Equal(9, comp1.TestAreasRaw[0].Length);
        // 第 1 测区第 1 个 HL 值
        Assert.Equal(467, comp1.TestAreasRaw[0][0]);
        // 第 3 测区最后一个 HL 值
        Assert.Equal(462, comp1.TestAreasRaw[2][8]);
    }

    [Fact]
    public void ReadWorkbook_默认角度_应被注入到每个构件()
    {
        var path = MakeSyntheticWorkbook();
        var workbook = LeebExcelReader.ReadWorkbook(path, defaultAngleDegrees: -90.0);
        Assert.Equal(-90.0, workbook.Batches[0].Components[0].AngleDegrees);
    }

    [Fact]
    public void ReadWorkbook_sheet名_应自动作为_BatchName_注入构件()
    {
        var path = MakeSyntheticWorkbook();
        var workbook = LeebExcelReader.ReadWorkbook(path);
        foreach (var batch in workbook.Batches)
            foreach (var comp in batch.Components)
                Assert.Equal(batch.BatchName, comp.BatchName);
    }

    [Fact]
    public void ReadWorkbook_文件不存在_应抛_FileNotFoundException()
    {
        Assert.Throws<FileNotFoundException>(() =>
            LeebExcelReader.ReadWorkbook(Path.Combine(_tmpDir, "nope.xlsx")));
    }

    [Fact]
    public void ReadComponents_厚度缺失_应抛_ArgumentException()
    {
        var path = Path.Combine(_tmpDir, "no_thickness.xlsx");
        using (var wb = new XLWorkbook())
        {
            var ws = wb.Worksheets.Add("检测批1");
            ws.Cell(1, 1).Value = "序号";
            for (int c = 0; c < 9; c++)
                ws.Cell(1, 3 + c).Value = $"HL{c + 1}";
            ws.Cell(2, 1).Value = 1;
            ws.Cell(2, 2).Value = "钢柱X";
            for (int c = 0; c < 9; c++)
            {
                ws.Cell(2, 3 + c).Value = 460;
                ws.Cell(3, 3 + c).Value = 460;
                ws.Cell(4, 3 + c).Value = 460;
            }
            // 故意不设置 L 列厚度
            wb.SaveAs(path);
        }

        Assert.Throws<ArgumentException>(() =>
            LeebExcelReader.ReadWorkbook(path));
    }

    // ── 集成测试：用用户提供的真实 D 号站房 Excel ─────────────────
    // 默认 Skip；本地手动跑时去掉 Skip 验证真实数据兼容性。
    [Fact(Skip = "Integration test; 仅本地有用户真实数据时手动去掉 Skip 验证")]
    public void ReadWorkbook_真实数据_D号站房_应该读到里氏硬度批()
    {
        const string realPath = @"D:\3js\项目\鉴定\20260101 小米\D号生产厂房\01检测批一【】.xlsx";
        if (!File.Exists(realPath))
            return;  // 跳过（其他人机器上没这文件）

        var workbook = LeebExcelReader.ReadWorkbook(
            realPath,
            defaultAngleDegrees: -90.0,
            sheetNameFilter: "里氏硬度");

        // 期望：2 个里氏 sheet（钢梁、钢柱），其中钢梁含 ~50 构件、钢柱含 ~8 构件
        Assert.Equal(2, workbook.Batches.Length);
        Assert.Contains(workbook.Batches, b => b.BatchName.Contains("钢梁"));
        Assert.Contains(workbook.Batches, b => b.BatchName.Contains("钢柱"));

        // 钢梁 sheet 151 行 → 50 构件（(151-1)/3 = 50）
        var beam = Array.Find(workbook.Batches, b => b.BatchName.Contains("钢梁"));
        Assert.NotNull(beam);
        Assert.True(beam!.Components.Length > 30, $"钢梁应≥30 构件，实际 {beam.Components.Length}");
        Assert.Equal(3, beam.Components[0].TestAreasRaw.Length);
        Assert.Equal(9, beam.Components[0].TestAreasRaw[0].Length);

        // 钢柱 sheet 25 行 → ~8 构件
        var column = Array.Find(workbook.Batches, b => b.BatchName.Contains("钢柱"));
        Assert.NotNull(column);
        Assert.True(column!.Components.Length > 4, $"钢柱应≥4 构件，实际 {column.Components.Length}");
    }

    [Fact]
    public void ReadComponents_HL值缺失_应抛_ArgumentException()
    {
        var path = Path.Combine(_tmpDir, "no_hl.xlsx");
        using (var wb = new XLWorkbook())
        {
            var ws = wb.Worksheets.Add("检测批1");
            ws.Cell(1, 1).Value = "序号";
            ws.Cell(2, 1).Value = 1;
            ws.Cell(2, 2).Value = "钢柱X";
            ws.Cell(2, 12).Value = 12;
            // 只写前 8 个 HL，第 9 个故意缺失
            for (int c = 0; c < 8; c++)
            {
                ws.Cell(2, 3 + c).Value = 460;
                ws.Cell(3, 3 + c).Value = 460;
                ws.Cell(4, 3 + c).Value = 460;
            }
            wb.SaveAs(path);
        }

        Assert.Throws<ArgumentException>(() =>
            LeebExcelReader.ReadWorkbook(path));
    }
}
