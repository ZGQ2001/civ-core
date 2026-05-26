// 锚杆 IFieldResolver 实现 —— 把单根锚杆的输入 + 计算结果 + 工程参数 + 用户输入
// 映射到 AnchorFieldCatalog 里的 Key。
//
// 解耦点：实现 Template.IFieldResolver 接口，引擎只调 GetValue(key)，不知道锚杆这事。
// 未来加钻芯就再写一个 DrillingRowResolver，零改动引擎。

using CivCore.Doc.Template;

namespace CivCore.Doc.Calc.Anchor;

/// <summary>
/// 单根锚杆的解析器实例 —— 报告生成时 batch.RowsWithResults 每个元素包一个。
/// </summary>
public class AnchorRowResolver : IFieldResolver
{
    private readonly AnchorRowInput _input;
    private readonly AnchorRowResult _result;
    private readonly AnchorParams _params;
    private readonly IReadOnlyDictionary<string, string> _userInputs;
    private readonly int _anchorIndex;
    private readonly string? _curveImageDir;

    /// <param name="anchorIndex">
    /// 1-based 全局序号 —— 模板里 {{锚杆序号}} 填这个值。0 表示未设置（旧调用方兼容）。
    /// 报告级别全局递增（209 根全在一份报告里，从 1 数到 209）。
    /// </param>
    /// <param name="curveImageDir">
    /// 曲线图目录（来自 plot_curves 输出）。{{img:曲线图}} 占位符会按 anchor_id 智能查找：
    ///   1) 优先 svg > png > jpg > jpeg
    ///   2) 精确匹配 {anchor_id}.{ext}，否则前缀匹配 {anchor_id}_*.{ext}（避免误中 {id}1.svg）
    /// 见 <see cref="FindCurveImage"/>。null 时 curve_image 字段返 null，引擎报 missingImages。
    /// </param>
    public AnchorRowResolver(
        AnchorRowInput input,
        AnchorRowResult result,
        AnchorParams @params,
        IReadOnlyDictionary<string, string>? userInputs = null,
        int anchorIndex = 0,
        string? curveImageDir = null)
    {
        _input = input;
        _result = result;
        _params = @params;
        _userInputs = userInputs ?? new Dictionary<string, string>();
        _anchorIndex = anchorIndex;
        _curveImageDir = curveImageDir;
    }

    public object? GetValue(string fieldKey) => fieldKey switch
    {
        // ── AnchorParams ──
        "axial_design_load" => _params.AxialDesignLoad,
        // 报告版面用 kN（catalog alias "轴向拉力设计值" 默认命中此 key）
        "axial_design_load_kn" => _params.AxialDesignLoad / 1000.0,
        "free_length" => _params.FreeLength,
        "anchor_length" => _params.AnchorLength,
        "steel_area" => _params.SteelArea,
        "elastic_modulus" => _params.ElasticModulus,

        // ── AnchorRowInput ──
        "anchor_id" => _input.AnchorId,
        "disp_01nt" => _input.Displacements.D01Nt,
        "disp_04nt" => _input.Displacements.D04Nt,
        "disp_07nt" => _input.Displacements.D07Nt,
        "disp_10nt" => _input.Displacements.D10Nt,
        "disp_12nt_1min" => _input.Displacements.D12Nt1Min,
        "disp_12nt_3min" => _input.Displacements.D12Nt3Min,
        "disp_12nt_5min" => _input.Displacements.D12Nt5Min,
        "disp_unload_10nt" => _input.Displacements.U10Nt,
        "disp_unload_07nt" => _input.Displacements.U07Nt,
        "disp_unload_04nt" => _input.Displacements.U04Nt,
        "disp_unload_01nt" => _input.Displacements.U01Nt,

        // ── AnchorRowResult ──
        "elastic_displacement" => _result.ElasticDisplacement,
        "lower_limit" => _result.LowerLimit,
        "upper_limit" => _result.UpperLimit,
        "judgement_result" => _result.Qualified ? "合格" : "不合格",

        // ── 引擎注入 ──
        "anchor_index" => _anchorIndex,
        "curve_image" => _curveImageDir is null
            ? null
            : FindCurveImage(_curveImageDir, _input.AnchorId),

        // ── 用户输入兜底 ──
        _ => _userInputs.TryGetValue(fieldKey, out var v) ? v : null,
    };

    /// <summary>支持的曲线图扩展名，按优先级排序（svg 矢量保真度最高）。</summary>
    private static readonly string[] _curveImageExtensions = { ".svg", ".png", ".jpg", ".jpeg" };

    /// <summary>
    /// 在 <paramref name="dir"/> 下按 <paramref name="anchorId"/> 智能查找曲线图。
    /// 匹配顺序：每个扩展名先试精确（{id}.ext），再试前缀（{id}_*.ext）。
    /// 前缀匹配只接 "{id}_" 开头，避免 "1" 误中 "11_xxx.svg"。
    /// </summary>
    private static string? FindCurveImage(string dir, string anchorId)
    {
        if (!Directory.Exists(dir)) return null;

        foreach (var ext in _curveImageExtensions)
        {
            var exact = Path.Combine(dir, anchorId + ext);
            if (File.Exists(exact)) return exact;

            string[] prefixMatches;
            try
            {
                prefixMatches = Directory.GetFiles(dir, $"{anchorId}_*{ext}");
            }
            catch (DirectoryNotFoundException)
            {
                return null;
            }
            if (prefixMatches.Length > 0)
            {
                Array.Sort(prefixMatches, StringComparer.Ordinal);
                return prefixMatches[0];
            }
        }
        return null;
    }
}
