// 锚杆批级 IFieldResolver —— 给 ReportGenerator 填项目级占位符用。
//
// 单根锚杆的字段（anchor_id / disp_* / 计算结果）见 AnchorRowResolver；
// 这里只提供 batch 内共享的字段（工程参数 + 用户输入）。
// 项目级段落的 {axial_design_load} {client_name} 等都从这里查。

using CivCore.Doc.Template;

namespace CivCore.Doc.Calc.Anchor;

public class AnchorBatchResolver : IFieldResolver
{
    private readonly AnchorParams _params;
    private readonly IReadOnlyDictionary<string, string> _userInputs;

    public AnchorBatchResolver(AnchorParams @params, IReadOnlyDictionary<string, string>? userInputs = null)
    {
        _params = @params;
        _userInputs = userInputs ?? new Dictionary<string, string>();
    }

    public object? GetValue(string fieldKey) => fieldKey switch
    {
        "axial_design_load" => _params.AxialDesignLoad,
        "free_length" => _params.FreeLength,
        "anchor_length" => _params.AnchorLength,
        "steel_area" => _params.SteelArea,
        "elastic_modulus" => _params.ElasticModulus,
        _ => _userInputs.TryGetValue(fieldKey, out var v) ? v : null,
    };
}
