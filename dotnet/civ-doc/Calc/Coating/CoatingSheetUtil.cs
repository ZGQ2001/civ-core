// 防火涂层各 sheet 读取的共用 helper（reader / expander 复用）。

using ClosedXML.Excel;

namespace CivCore.Doc.Calc.Coating;

internal static class CoatingSheetUtil
{
    /// <summary>表头行（第 1 行）列名 → 列号，归一化抹平括号/空格/大小写。</summary>
    public static Dictionary<string, int> ReadHeaderMap(IXLWorksheet ws)
    {
        var map = new Dictionary<string, int>();
        var lastCol = ws.Row(1).LastCellUsed()?.Address.ColumnNumber ?? 0;
        for (int c = 1; c <= lastCol; c++)
        {
            var cell = ws.Cell(1, c);
            if (cell.IsEmpty()) continue;
            var key = CoatingColumns.NormalizeHeader(cell.GetString());
            if (!map.ContainsKey(key)) map[key] = c;
        }
        return map;
    }

    public static int? TryColumn(Dictionary<string, int> map, string name)
    {
        var key = CoatingColumns.NormalizeHeader(name);
        return map.TryGetValue(key, out int c) ? c : null;
    }

    public static int RequireColumn(Dictionary<string, int> map, string name, string description)
    {
        var key = CoatingColumns.NormalizeHeader(name);
        if (!map.TryGetValue(key, out int c))
            throw new ArgumentException($"缺少{description}（列名应为「{name}」）");
        return c;
    }

    /// <summary>读数字单元格，容错去单位后缀（如 "24mm" → 24）；空返回 null。</summary>
    public static double? ReadOptDouble(IXLCell cell, string what)
    {
        if (cell.IsEmpty()) return null;
        if (cell.TryGetValue<double>(out double d)) return d;
        var s = cell.GetString().Trim();
        var num = new string(s.TakeWhile(c => char.IsDigit(c) || c == '.' || c == '-').ToArray());
        if (double.TryParse(num, out double v)) return v;
        throw new ArgumentException($"{what}非数字：{s}");
    }

    /// <summary>读整数单元格（容错小数四舍五入）；空返回 null。</summary>
    public static int? ReadOptInt(IXLCell cell, string what)
    {
        var d = ReadOptDouble(cell, what);
        return d.HasValue ? (int)Math.Round(d.Value) : null;
    }

    public static string ReadString(IXLCell cell) => cell.IsEmpty() ? "" : cell.GetString().Trim();
}
