// 防火涂层膨胀型 Word 表 builder 测试 —— 用 报告表格.xlsx 里的真实膨胀型数据，
// 验证表头 / 各处均值 / 单位换算(mm→μm) / 构件均值 / 判定 都正确。
// 真实数据：国标膨胀型表，构件设计值 220μm，各处实测均值 ~230μm，报告判定「合格」。

using CivCore.Doc.Calc.Coating;
using CivCore.Doc.ReportTables;
using DocumentFormat.OpenXml.Wordprocessing;
using Xunit;

namespace CivCore.Doc.Tests;

public class CoatingWordTableTests
{
    /// <summary>造一个膨胀型构件：5 处，每处 3 个测点（均取该处给定均值 μm），设计值 μm。</summary>
    private static CoatingMemberInput Member(string loc, int designUm, int[] locAvgUm)
    {
        var pts = new List<CoatingPoint>();
        for (int s = 1; s <= locAvgUm.Length; s++)
            for (int k = 1; k <= 3; k++)
                pts.Add(CoatingPoint.Create(s, $"测点{k}", locAvgUm[s - 1] / 1000.0));
        return CoatingMemberInput.Create(loc, "柱", designUm / 1000.0, pts.ToArray());
    }

    [Fact]
    public void BuildExpansion_膨胀型真实数据_表头数值单位判定均正确()
    {
        var wb = new CoatingWorkbookInput(CoatingStandards.GB_50205_2020, new[]
        {
            new CoatingBatchInput("全部", new[]
            {
                Member("地上一层A×1轴", 220, new[] { 232, 230, 230, 231, 230 }),
                Member("地上一层A×2轴", 220, new[] { 231, 231, 230, 232, 230 }),
            }),
        });
        var batch = CoatingCalculator.Calc(wb).BatchResults[0];

        var table = CoatingWordTable.BuildExpansion(batch);
        var rows = table.Elements<TableRow>().ToList();

        Assert.Equal(3, rows.Count); // 表头 + 2 构件

        string Cell(int r, int c) => rows[r].Elements<TableCell>().ElementAt(c).InnerText;

        // 表头（10 列）
        Assert.Equal("序号", Cell(0, 0));
        Assert.Equal("构件编号", Cell(0, 1));
        Assert.Equal("(第1处)平均值(μm)", Cell(0, 2));
        Assert.Equal("(第5处)平均值(μm)", Cell(0, 6));
        Assert.Equal("平均值(μm)", Cell(0, 7));
        Assert.Equal("设计值(μm)", Cell(0, 8));
        Assert.Equal("检测结果", Cell(0, 9));

        // 构件 1：各处 μm + 构件均值(230.6→231) + 设计 220 + 合格
        Assert.Equal("1", Cell(1, 0));
        Assert.Equal("地上一层A×1轴", Cell(1, 1));
        Assert.Equal("232", Cell(1, 2));
        Assert.Equal("231", Cell(1, 5)); // 第4处=231
        Assert.Equal("230", Cell(1, 6)); // 第5处=230
        Assert.Equal("231", Cell(1, 7)); // 构件均值
        Assert.Equal("220", Cell(1, 8));
        Assert.Equal("合格", Cell(1, 9));

        // 构件 2
        Assert.Equal("2", Cell(2, 0));
        Assert.Equal("地上一层A×2轴", Cell(2, 1));
        Assert.Equal("合格", Cell(2, 9));
    }

    /// <summary>造厚型构件：sections[截面][面] 实测值（mm），设计值 mm（≥7→厚型），faces 面名。</summary>
    private static CoatingMemberInput ThickMember(
        string loc, double designMm, string[] faces, double[][] sections)
    {
        var pts = new List<CoatingPoint>();
        for (int s = 0; s < sections.Length; s++)
            for (int f = 0; f < faces.Length; f++)
                pts.Add(CoatingPoint.Create(s + 1, faces[f], sections[s][f]));
        return CoatingMemberInput.Create(loc, "柱", designMm, pts.ToArray());
    }

    [Fact]
    public void BuildThick_厚型钢柱真实数据_表头面名数值均值正确()
    {
        var faces = new[] { "东侧面", "西侧面", "南侧面", "北侧面" };
        var wb = new CoatingWorkbookInput(CoatingStandards.GB_50205_2020, new[]
        {
            new CoatingBatchInput("全部", new[]
            {
                ThickMember("地上一层1/4×4/A轴钢柱", 25, faces, new[]
                {
                    new double[] { 21, 25, 30, 24 },
                    new double[] { 26, 31, 28, 27 },
                    new double[] { 28, 24, 25, 26 },
                }), // 均值 26.25
                ThickMember("地上一层1/28×G轴钢柱", 25, faces, new[]
                {
                    new double[] { 28, 27, 21, 31 },
                    new double[] { 34, 25, 26, 26 },
                }), // 均值 27.25
            }),
        });
        var batch = CoatingCalculator.Calc(wb).BatchResults[0];

        var table = CoatingWordTable.BuildThick(batch.MembersWithResults);
        var rows = table.Elements<TableRow>().ToList();

        // 2 行表头 + (3 + 2) 数据行
        Assert.Equal(7, rows.Count);

        string Cell(int r, int c) => rows[r].Elements<TableCell>().ElementAt(c).InnerText;

        // 表头行 1：序号|构件位置|测点|实测涂层厚度(mm)[跨4列]|平均值(mm)
        Assert.Equal("序号", Cell(0, 0));
        Assert.Equal("测点", Cell(0, 2));
        Assert.Equal("实测涂层厚度(mm)", Cell(0, 3));
        Assert.Equal("平均值(mm)", Cell(0, 4));
        // 表头行 2：面名（前 3 列 + 平均值列是 vMerge 续）
        Assert.Equal("东侧面", Cell(1, 3));
        Assert.Equal("北侧面", Cell(1, 6));

        // 构件 1 截面 1 行：序号/位置/截面/4 面值/均值
        Assert.Equal("1", Cell(2, 0));
        Assert.Equal("地上一层1/4×4/A轴钢柱", Cell(2, 1));
        Assert.Equal("截面1", Cell(2, 2));
        Assert.Equal("21", Cell(2, 3));
        Assert.Equal("24", Cell(2, 6));
        Assert.Equal("26.25", Cell(2, 7)); // 构件均值（vMerge 起始格）

        // 构件 1 截面 2/3：截面递增，合并列为空
        Assert.Equal("截面2", Cell(3, 2));
        Assert.Equal("", Cell(3, 0));      // 序号续（空）
        Assert.Equal("截面3", Cell(4, 2));

        // 构件 2
        Assert.Equal("2", Cell(5, 0));
        Assert.Equal("截面1", Cell(5, 2));
        Assert.Equal("27.25", Cell(5, 7));
    }
}
