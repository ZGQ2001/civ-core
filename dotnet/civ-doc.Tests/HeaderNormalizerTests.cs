// HeaderNormalizer 单测：列名归一化公共核心（锚杆/防火共用）。
// 剥尾部单位括注是 CoatingColumns 专属（不在 Core），故这里「(mm)」保留。

using CivCore.Doc.Calc;
using Xunit;

namespace CivCore.Doc.Tests;

public class HeaderNormalizerTests
{
    [Theory]
    [InlineData(null, "")]
    [InlineData("  锚杆编号  ", "锚杆编号")]      // trim
    [InlineData("设计厚度（mm）", "设计厚度(mm)")] // 全角括号→半角；不剥单位（剥单位是 Coating 专属）
    [InlineData("0.1Nt", "0.1nt")]               // 小写
    [InlineData("卸载 0.1Nt", "卸载0.1nt")]       // 去空格 + 小写
    public void Core_归一化(string? input, string expected)
    {
        Assert.Equal(expected, HeaderNormalizer.Core(input!));
    }
}
