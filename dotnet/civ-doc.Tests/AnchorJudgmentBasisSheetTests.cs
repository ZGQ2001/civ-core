// AnchorJudgmentBasisSheet 单测：演算稿 sheet 写入（公式 + 规范条款可见、幂等）。

using System.Linq;
using ClosedXML.Excel;
using CivCore.Doc.ReportTables;
using Xunit;

namespace CivCore.Doc.Tests;

public class AnchorJudgmentBasisSheetTests
{
    [Fact]
    public void Write_生成判定依据sheet_含公式与规范条款()
    {
        using var wb = new XLWorkbook();
        AnchorJudgmentBasisSheet.Write(wb);

        Assert.True(wb.Worksheets.TryGetWorksheet(AnchorJudgmentBasisSheet.SheetName, out var ws));
        var text = string.Join("\n", ws.CellsUsed().Select(c => c.GetString()));
        Assert.Contains("GB 50086-2015", text);   // 规范号可追溯
        Assert.Contains("0.9·P·Lf", text);          // 下限 Q 公式
        Assert.Contains("Q < M < R", text);         // 判定区间
    }

    [Fact]
    public void Write_幂等_重复写只一张()
    {
        using var wb = new XLWorkbook();
        AnchorJudgmentBasisSheet.Write(wb);
        AnchorJudgmentBasisSheet.Write(wb);
        Assert.Equal(1, wb.Worksheets.Count(w => w.Name == AnchorJudgmentBasisSheet.SheetName));
    }
}
