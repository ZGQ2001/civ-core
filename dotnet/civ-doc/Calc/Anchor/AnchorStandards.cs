// 锚杆抗拔试验支持的规范清单。当前只支持 GB 50086-2015；
// 未来扩展只需追加常量 + Supported 列表，AnchorMath 不需要改动
// （5 个 Nt 等级和判定公式由 GB 50086-2015 锁定）。

namespace CivCore.Doc.Calc.Anchor;

public static class AnchorStandards
{
    public const string GB_50086_2015 = "GB 50086-2015";

    public static readonly string[] Supported = { GB_50086_2015 };

    public static void Validate(string standard)
    {
        if (!Supported.Contains(standard))
            throw new ArgumentException(
                $"不支持的规范：{standard}（当前支持：{string.Join(", ", Supported)}）");
    }
}
