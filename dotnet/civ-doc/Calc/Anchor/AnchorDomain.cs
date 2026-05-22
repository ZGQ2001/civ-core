// 锚杆抗拔试验数据契约（GB 50086-2015《岩土锚杆与喷射混凝土支护工程技术规范》）。
//
// 列名按 Nt 倍数表达（0.1Nt = 0.1·轴向拉力设计值 P），不绑死 kN 值；
// 这样同一份代码可以处理任意 P，列名也跟报告内插表格的 «占位符» 语义一致。

namespace CivCore.Doc.Calc.Anchor;

/// <summary>工程参数（同一批次所有锚杆共享）。</summary>
public record AnchorParams(
    double AxialDesignLoad,    // P (N)
    double FreeLength,         // Lf (mm)
    double AnchorLength,       // La (mm)
    double SteelArea,          // A (mm²)
    double ElasticModulus      // E (N/mm²)
)
{
    public static AnchorParams Create(double p, double lf, double la, double a, double e)
    {
        if (p <= 0) throw new ArgumentException($"轴向拉力设计值 P 必须 > 0，得到 {p}");
        if (lf <= 0) throw new ArgumentException($"自由段长度 Lf 必须 > 0，得到 {lf}");
        if (la <= 0) throw new ArgumentException($"锚固段长度 La 必须 > 0，得到 {la}");
        if (a <= 0) throw new ArgumentException($"钢筋面积 A 必须 > 0，得到 {a}");
        if (e <= 0) throw new ArgumentException($"弹性模量 E 必须 > 0，得到 {e}");
        return new AnchorParams(p, lf, la, a, e);
    }
}

/// <summary>11 个位移读数（mm）：4 加载 + 3 持荷 + 4 卸载。</summary>
public record AnchorDisplacements(
    double D01Nt,        // 0.1·P 时位移
    double D04Nt,        // 0.4·P
    double D07Nt,        // 0.7·P
    double D10Nt,        // 1.0·P
    double D12Nt1Min,    // 1.2·P 持荷 1min
    double D12Nt3Min,    // 1.2·P 持荷 3min
    double D12Nt5Min,    // 1.2·P 持荷 5min（最大荷载下总位移）
    double U10Nt,        // 卸载到 1.0·P
    double U07Nt,        // 卸载到 0.7·P
    double U04Nt,        // 卸载到 0.4·P
    double U01Nt         // 卸载到 0.1·P（卸载完残余位移）
);

/// <summary>单根锚杆输入。</summary>
public record AnchorRowInput(
    string AnchorId,
    AnchorDisplacements Displacements
)
{
    public static AnchorRowInput Create(string id, AnchorDisplacements d)
    {
        if (string.IsNullOrWhiteSpace(id))
            throw new ArgumentException("锚杆编号不可为空");
        return new AnchorRowInput(id, d);
    }
}

/// <summary>单根锚杆结果。</summary>
public record AnchorRowResult(
    double ElasticDisplacement,    // M = D12Nt5Min - U01Nt
    double LowerLimit,             // Q = 0.9·P·Lf / (E·A)
    double UpperLimit,             // R = (Lf + La/3)·P / (E·A)
    bool Qualified                 // Q < M < R
);

/// <summary>单批输入（同一组工程参数）。</summary>
public record AnchorBatchInput(
    string BatchId,
    AnchorParams Params,
    AnchorRowInput[] Rows
);

/// <summary>单批结果。</summary>
public record AnchorBatchResult(
    string BatchId,
    AnchorParams Params,
    (AnchorRowInput Input, AnchorRowResult Result)[] RowsWithResults,
    int NQualified,
    int NTotal
);

/// <summary>整文件输入（含规范 + 多批）。</summary>
public record AnchorWorkbookInput(
    string Standard,
    AnchorBatchInput[] Batches
);

/// <summary>整文件结果。</summary>
public record AnchorWorkbookResult(
    string Standard,
    AnchorBatchResult[] BatchResults,
    int NBatches,
    int NRowsTotal,
    int NQualifiedTotal
);
