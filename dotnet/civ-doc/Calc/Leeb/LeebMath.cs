// 里氏硬度核心数学函数（对应 Python src/civ_core/core/calc_functions.py 的查表 / 插值 / 截尾平均）。
//
// 三个核心函数：
//   LookupWithInterp        ←→ Python _lookup_with_interp（1D 查表 + 线性插值）
//   Lookup2dFixedKey1InterpKey2 ←→ Python _lookup_2d_fixed_key1_interp_key2（2D 查表）
//   TrimMeanLeeb           ←→ Python _trim_mean_leeb（9 点截尾平均）
//
// 输入 rows 来自 StandardsDb.ReadAll(tableName) —— 已按 key1, key2 升序。
// 这层不接 StandardsDb 对象（解耦 IO 和算法，方便单测）。

using CivCore.Doc.Standards;

namespace CivCore.Doc.Calc.Leeb;

/// <summary>StandardsRow 的哪一列作为查表结果值。</summary>
public enum ValueColumn { Value1, Value2, Value3 }

public static class LeebMath
{
    /// <summary>
    /// 1D 查表 + 线性插值：rows 按 key1 升序，key 必须落在 [min, max] 内（不外推）。
    /// 精确命中 key1 时直接返回；否则在前后两行之间线性插值。
    /// </summary>
    public static double LookupWithInterp(
        IReadOnlyList<StandardsRow> rows,
        double key,
        ValueColumn col = ValueColumn.Value1)
    {
        if (rows.Count == 0)
            throw new ArgumentException("规范查表为空");

        // 精确命中
        foreach (var row in rows)
        {
            if (row.Key1 == key)
            {
                var v = GetValue(row, col);
                if (v is null)
                    throw new ArgumentException($"规范表 key={key} 行 {col} 为空");
                return v.Value;
            }
        }

        // 越界检查
        if (key < rows[0].Key1 || key > rows[^1].Key1)
            throw new ArgumentException(
                $"查表 key={key} 超出范围 [{rows[0].Key1}, {rows[^1].Key1}]");

        // 线性插值：找前后两点
        for (int i = 0; i < rows.Count - 1; i++)
        {
            var lo = rows[i];
            var hi = rows[i + 1];
            if (lo.Key1 < key && key < hi.Key1)
            {
                var vLo = GetValue(lo, col);
                var vHi = GetValue(hi, col);
                if (vLo is null || vHi is null)
                    throw new ArgumentException($"规范表插值区间 {col} 缺值");
                double t = (key - lo.Key1) / (hi.Key1 - lo.Key1);
                return vLo.Value + t * (vHi.Value - vLo.Value);
            }
        }

        throw new ArgumentException($"查表 key={key} 未找到匹配行");
    }

    /// <summary>
    /// 2D 查表：先按 key1 精确过滤（如角度档），再在该 key1 的所有行中按 key2 线性插值。
    /// 用于角度修正表（角度档精确 + HL_m 插值）等"分类 + 数值插值"场景。
    /// </summary>
    public static double Lookup2dFixedKey1InterpKey2(
        IReadOnlyList<StandardsRow> rows,
        double key1,
        double key2,
        ValueColumn col = ValueColumn.Value1,
        string key1Label = "key1")
    {
        var matched = rows.Where(r => r.Key1 == key1).ToList();
        if (matched.Count == 0)
            throw new ArgumentException($"{key1Label}={key1} 在规范表中不存在");

        // 按 key2 升序（已在 SQL ORDER BY，这里防御性再排一次）
        matched.Sort((a, b) => (a.Key2 ?? 0).CompareTo(b.Key2 ?? 0));

        // 精确命中
        foreach (var row in matched)
        {
            if (row.Key2 == key2)
            {
                var v = GetValue(row, col);
                if (v is null)
                    throw new ArgumentException(
                        $"规范表 ({key1Label}={key1}, key2={key2}) {col} 为空");
                return v.Value;
            }
        }

        // 单行特例：常数
        if (matched.Count == 1)
        {
            var v = GetValue(matched[0], col);
            return v ?? 0.0;
        }

        // 越界检查
        double k2Min = matched[0].Key2 ?? 0;
        double k2Max = matched[^1].Key2 ?? 0;
        if (key2 < k2Min || key2 > k2Max)
            throw new ArgumentException(
                $"查表 key2={key2} 超出 ({key1Label}={key1}) 区间 [{k2Min}, {k2Max}]");

        // 插值
        for (int i = 0; i < matched.Count - 1; i++)
        {
            var lo = matched[i];
            var hi = matched[i + 1];
            double k2Lo = lo.Key2 ?? 0;
            double k2Hi = hi.Key2 ?? 0;
            if (k2Lo < key2 && key2 < k2Hi)
            {
                var vLo = GetValue(lo, col);
                var vHi = GetValue(hi, col);
                if (vLo is null || vHi is null)
                    throw new ArgumentException($"规范表插值区间 {col} 缺值");
                double t = (key2 - k2Lo) / (k2Hi - k2Lo);
                return vLo.Value + t * (vHi.Value - vLo.Value);
            }
        }

        throw new ArgumentException(
            $"查表 ({key1Label}={key1}, key2={key2}) 未匹配");
    }

    /// <summary>
    /// 9 点截尾平均（INSP-001 §1.1）：剔除最高 2 个 + 最低 2 个，剩 5 个取平均后四舍五入取整。
    /// 对应 Excel `ROUND(TRIMMEAN(..., 4/9), 0)`。
    ///
    /// 注意：Python `int(mean + 0.5)` 实现的是「向零截断的四舍五入」（.5 向上），
    /// 不同于 Python 内置 `round()` 的「半数向偶」。C# 这里用同样语义保证等价。
    /// </summary>
    public static int TrimMeanLeeb(IReadOnlyList<int> values)
    {
        if (values.Count != 9)
            throw new ArgumentException(
                $"里氏硬度截尾平均需 9 个测点，得到 {values.Count}");

        var sorted = values.OrderBy(v => v).ToArray();
        int sum = 0;
        for (int i = 2; i < 7; i++) sum += sorted[i];
        double mean = sum / 5.0;
        // 「+0.5 后向零截断」语义：mean=4.5 → 5，mean=-4.5 → -5
        return mean >= 0
            ? (int)(mean + 0.5)
            : -(int)(-mean + 0.5);
    }

    private static double? GetValue(StandardsRow row, ValueColumn col) => col switch
    {
        ValueColumn.Value1 => row.Value1,
        ValueColumn.Value2 => row.Value2,
        ValueColumn.Value3 => row.Value3,
        _ => throw new ArgumentOutOfRangeException(nameof(col)),
    };
}
