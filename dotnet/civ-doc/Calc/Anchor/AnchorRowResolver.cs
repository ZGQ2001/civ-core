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
    private readonly string? _batchId;

    /// <param name="anchorIndex">
    /// 1-based 全局序号 —— 模板里 {{锚杆序号}} 填这个值。0 表示未设置（旧调用方兼容）。
    /// 报告级别全局递增（209 根全在一份报告里，从 1 数到 209）。
    /// </param>
    /// <param name="curveImageDir">
    /// 曲线图目录（来自 plot_curves 输出）。{{img:曲线图}} 占位符会智能查找：
    ///   1) 优先 svg > png > jpg > jpeg
    ///   2) 多批次出图按「&lt;批次&gt;_&lt;编号&gt;」命名（plot_curves filename_prefix），故先按
    ///      batchId 前缀找；再回退裸 anchor_id（单批 / 旧图）
    ///   3) 每种 stem 都先精确匹配 {stem}.{ext}，否则前缀匹配 {stem}_*.{ext}
    /// 见 <see cref="FindCurveImage"/>。null 时 curve_image 字段返 null，引擎报 missingImages。
    /// </param>
    /// <param name="batchId">
    /// 本行所属批次 ID —— 用于多批次曲线图按「&lt;批次&gt;_&lt;编号&gt;」查找。null = 不加批次前缀。
    /// </param>
    public AnchorRowResolver(
        AnchorRowInput input,
        AnchorRowResult result,
        AnchorParams @params,
        IReadOnlyDictionary<string, string>? userInputs = null,
        int anchorIndex = 0,
        string? curveImageDir = null,
        string? batchId = null)
    {
        _input = input;
        _result = result;
        _params = @params;
        _userInputs = userInputs ?? new Dictionary<string, string>();
        _anchorIndex = anchorIndex;
        _curveImageDir = curveImageDir;
        _batchId = batchId;
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
            : FindCurveImage(_curveImageDir, _batchId, _input.AnchorId),

        // ── 用户输入兜底 ──
        _ => _userInputs.TryGetValue(fieldKey, out var v) ? v : null,
    };

    /// <summary>支持的曲线图扩展名，按优先级排序（svg 矢量保真度最高）。</summary>
    private static readonly string[] _curveImageExtensions = { ".svg", ".png", ".jpg", ".jpeg" };

    /// <summary>
    /// 在 <paramref name="dir"/> 下查找某根锚杆的曲线图。
    /// 查找顺序（命中即返回）：
    ///   1) 若有 batchId：按 stem「{batchId}_{anchorId}」找（多批次出图前缀命名）
    ///   2) 回退：按 stem「{anchorId}」找（单批 / 未加前缀的旧图）
    /// 每个 stem 内：每个扩展名先精确（{stem}.ext）再前缀（{stem}_*.ext）。
    /// </summary>
    private static string? FindCurveImage(string dir, string? batchId, string anchorId)
    {
        if (!Directory.Exists(dir)) return null;

        if (!string.IsNullOrWhiteSpace(batchId))
        {
            var byBatch = FindByStem(dir, $"{batchId}_{anchorId}");
            if (byBatch != null) return byBatch;
        }
        return FindByStem(dir, anchorId);
    }

    /// <summary>
    /// 在 <paramref name="dir"/> 下按文件名主干 <paramref name="stem"/> 查找。
    /// 每个扩展名先试精确（{stem}.ext），再试前缀（{stem}_*.ext）。
    /// 前缀匹配只接 "{stem}_" 开头，避免 "1" 误中 "11_xxx.svg"。
    /// </summary>
    private static string? FindByStem(string dir, string stem)
    {
        foreach (var ext in _curveImageExtensions)
        {
            var exact = Path.Combine(dir, stem + ext);
            if (File.Exists(exact)) return exact;

            string[] prefixMatches;
            try
            {
                prefixMatches = Directory.GetFiles(dir, $"{stem}_*{ext}");
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
