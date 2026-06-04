// Handler 公共小工具（去重：原 Anchor/Coating handler 各抄一份的解析逻辑收敛到此）。
// 只放「字节级等价」的共性；有行为差异的（如 ParseUserInputs 的解包层）留在各 handler，
// 各自在本核心之上组合，不擅自统一行为（出错代价是工程事故）。

using System.Text.Json;

namespace CivCore.Doc.Handlers;

public static class HandlerUtil
{
    /// <summary>JSON 对象 → string map：只收 string 值、跳过非 string（与原 Anchor/Coating ParseUserInputs 内层循环一致）。</summary>
    public static Dictionary<string, string> ParseStringMap(JsonElement obj)
    {
        var d = new Dictionary<string, string>();
        foreach (var prop in obj.EnumerateObject())
            if (prop.Value.ValueKind == JsonValueKind.String)
                d[prop.Name] = prop.Value.GetString() ?? "";
        return d;
    }
}
