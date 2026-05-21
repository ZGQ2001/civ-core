// 里氏硬度数据契约（对应 Python src/civ_core/domain/calc_schema.py 的 LeebHardness* 类）。
//
// 设计原则跟 Python 端同（CLAUDE.md 锁定）：
//   - 全 record（C# 的 immutable 数据结构，类似 Python @dataclass(frozen=True)）
//   - 构造时校验非法字段，类似 __post_init__
//   - 不引复杂模型库，纯标准库

namespace CivCore.Doc.Calc.Leeb;

/// <summary>单个测区计算结果（9 次原始 HL + 各种修正与导出值）。</summary>
public record LeebHardnessTestArea(
    int[] RawHlValues,
    int HlM,
    double HlT,
    double HlA,
    double HlCorrected,
    double FbMin,
    double FbMax
)
{
    public static LeebHardnessTestArea Create(
        int[] rawHlValues,
        int hlM,
        double hlT,
        double hlA,
        double hlCorrected,
        double fbMin,
        double fbMax)
    {
        if (rawHlValues.Length != 9)
            throw new ArgumentException(
                $"LeebHardnessTestArea.RawHlValues 必须 9 个值，得到 {rawHlValues.Length}");
        return new LeebHardnessTestArea(rawHlValues, hlM, hlT, hlA, hlCorrected, fbMin, fbMax);
    }
}

/// <summary>单个构件计算结果（N 个测区聚合后）。</summary>
public record LeebHardnessResult(
    LeebHardnessTestArea[] TestAreas,
    double CompFbMinAvg,
    double CompFbMaxAvg,
    double CompFbEst,
    double BatchFbCharAvg
);

/// <summary>单个构件输入（来源 Excel：3 测区 × 9 HL + 厚度 + 角度 + 名字 + 序号）。</summary>
public record LeebHardnessComponentInput(
    int Seq,
    string Name,
    double Thickness,
    double AngleDegrees,
    int[][] TestAreasRaw,
    string BatchName = ""
)
{
    public static LeebHardnessComponentInput Create(
        int seq,
        string name,
        double thickness,
        double angleDegrees,
        int[][] testAreasRaw,
        string batchName = "")
    {
        if (string.IsNullOrWhiteSpace(name))
            throw new ArgumentException("LeebHardnessComponentInput.Name 不可为空");
        if (thickness <= 0)
            throw new ArgumentException(
                $"LeebHardnessComponentInput.Thickness 必须 > 0，得到 {thickness}");
        if (testAreasRaw.Length == 0)
            throw new ArgumentException("LeebHardnessComponentInput.TestAreasRaw 至少 1 个测区");
        for (int i = 0; i < testAreasRaw.Length; i++)
        {
            if (testAreasRaw[i].Length != 9)
                throw new ArgumentException(
                    $"LeebHardnessComponentInput.TestAreasRaw[{i}] 必须 9 个测点，得到 {testAreasRaw[i].Length}");
        }
        return new LeebHardnessComponentInput(seq, name, thickness, angleDegrees, testAreasRaw, batchName);
    }
}

/// <summary>单批输入（一个 Excel sheet 对应一批）。</summary>
public record LeebHardnessBatch(
    string BatchName,
    LeebHardnessComponentInput[] Components
);

/// <summary>单批计算结果。</summary>
public record LeebHardnessBatchResult(
    string BatchName,
    (LeebHardnessComponentInput Input, LeebHardnessResult Result)[] ComponentsWithResults,
    double BatchFbCharAvg,
    int NComponents
);

/// <summary>整文件多批输入（一个 xlsx 文件对应一个 workbook）。</summary>
public record LeebHardnessWorkbook(
    LeebHardnessBatch[] Batches
);

/// <summary>整文件多批计算结果。</summary>
public record LeebHardnessWorkbookResult(
    LeebHardnessBatchResult[] BatchResults,
    int NBatches,
    int NComponentsTotal
);
