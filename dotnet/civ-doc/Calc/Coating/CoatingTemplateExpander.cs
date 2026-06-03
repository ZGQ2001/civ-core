// 「构件清单」→「测点数据-<类型>」一键展开（像用户的 WPS JSA 工具，但内置）。
//
// 读「类型预设」(构件类型→测点面+默认设计厚度) + 「构件清单」(一构件一行)，解析：
//   类型：清单填了用清单；否则从构件位置名识别（含预设里的类型关键词，如「梁/柱」）。
//   截面数：清单填了用清单；否则 ⌈长度/间距⌉（国标3m/北京地标1m）。
//   设计厚度：清单填了用清单；否则类型预设默认。
//
// 布局按 标准 × 涂层类型 分两种：
//   国标 + 膨胀型(薄/超薄) → 5 处×3 点（涂层测厚仪，索引列「处号」1~5，列头 测点1/测点2/测点3，
//                            参照 GB/T 50621 §12 防腐涂层口径），sheet 名「测点数据-<类型>-膨胀型」。
//   其余（国标厚型 / 地标任意）→ 截面×面（索引列「截面号」，测点列=面名），sheet 名「测点数据-<类型>」。
// 同类型混涂层类型时拆两张 sheet（列头不同）。测点格留空待用户填数字，整块按构件分色。

using ClosedXML.Excel;
using CivCore.Doc.Server;

namespace CivCore.Doc.Calc.Coating;

public static class CoatingTemplateExpander
{
    public record ExpandResult(int Members, int TotalSections, string[] Sheets);

    private record Resolved(CoatingMemberSpec Spec, string Type, CoatingTypePreset Preset, int Sections, double Design);

    /// <summary>国标膨胀型固定 5 处布点（GB 50205-2020 §13.4.3 + GB/T 50621 §12 防腐：薄/超薄涂层测厚仪 5 处）。</summary>
    private const int FiveLocationCount = 5;
    /// <summary>每处空间布 3 个测点（测点1/测点2/测点3，非重复读数）。</summary>
    private static readonly string[] LocationPointHeaders = { "测点1", "测点2", "测点3" };
    /// <summary>5 处×3 点 sheet 名后缀：测点数据-{类型}-膨胀型。</summary>
    private const string ExpansionSuffix = "膨胀型";

    public static ExpandResult Expand(
        string inputPath, string outputPath, string standard = CoatingStandards.GB_50205_2020)
    {
        CoatingStandards.Validate(standard);
        if (!File.Exists(inputPath))
            throw new FileNotFoundException($"文件不存在：{inputPath}");

        double spacing = CoatingStandards.Spacing(standard);
        bool isNational = standard == CoatingStandards.GB_50205_2020;

        using var wb = new XLWorkbook(inputPath);
        var presets = ReadTypePresets(wb);
        var specs = ReadMemberList(wb);
        if (specs.Count == 0)
            throw new ArgumentException("「构件清单」表没有数据行（请先填构件位置等）");

        // 分组键 = (构件类型, 是否5处×3点)。同类型混涂层类型时拆两张 sheet（列头不同）。
        var byGroup = new Dictionary<(string Type, bool FiveLocation), List<Resolved>>();
        var groupOrder = new List<(string Type, bool FiveLocation)>();
        int totalSections = 0;

        foreach (var spec in specs)
        {
            string type = ResolveType(spec, presets);
            if (!presets.TryGetValue(type, out var preset))
                throw new ArgumentException(
                    $"构件「{spec.Location}」类型「{type}」在「类型预设」表里没定义——请在类型预设表加一行（含测点位置）");
            double design = ResolveDesign(spec, preset);
            // 国标 + 膨胀型（薄/超薄）→ 5 处×3 点；否则截面×面（地标膨胀型也走截面×面，截面数同厚型）。
            bool fiveLocation = isNational && CoatingStandards.IsExpansion(CoatingStandards.Classify(design));
            int sections = fiveLocation ? FiveLocationCount : ResolveSections(spec, spacing);
            totalSections += sections;

            var key = (type, fiveLocation);
            if (!byGroup.TryGetValue(key, out var list))
            {
                list = new List<Resolved>();
                byGroup[key] = list;
                groupOrder.Add(key);
            }
            list.Add(new Resolved(spec, type, preset, sections, design));
        }

        // 删旧「测点数据*」sheet（幂等重展开）
        foreach (var ws in wb.Worksheets.Where(w => w.Name.StartsWith(CoatingColumns.PointDataSheet)).ToList())
            ws.Delete();

        var written = new List<string>();
        foreach (var key in groupOrder)
        {
            string baseName = key.FiveLocation
                ? $"{CoatingColumns.PointDataSheet}-{key.Type}-{ExpansionSuffix}"
                : $"{CoatingColumns.PointDataSheet}-{key.Type}";
            string sheetName = SheetNameUtil.Safe(baseName);
            var ws = wb.Worksheets.Add(sheetName);
            string[] pointHeaders = key.FiveLocation ? LocationPointHeaders : byGroup[key][0].Preset.PointPositions;
            WriteGrid(ws, byGroup[key], pointHeaders, key.FiveLocation);
            written.Add(sheetName);
        }

        AtomicFile.SaveWorkbook(wb, outputPath);
        return new ExpandResult(specs.Count, totalSections, written.ToArray());
    }

    // ── 解析规则 ──

    private static string ResolveType(CoatingMemberSpec spec, Dictionary<string, CoatingTypePreset> presets)
    {
        if (!string.IsNullOrWhiteSpace(spec.MemberType)) return spec.MemberType!.Trim();
        // 从构件位置名识别：含某个预设类型关键词（如「梁」「柱」）即归该类型
        var hit = presets.Keys.FirstOrDefault(k => spec.Location.Contains(k));
        if (hit != null) return hit;
        throw new ArgumentException(
            $"构件「{spec.Location}」无法从名字识别构件类型——请在「构件清单」填「构件类型」列");
    }

    // 仅 截面×面 路径调用（五处3点走 FiveLocationCount，不经此）——故「最少 2 截面」规则收在这里，
    // 膨胀型 5 处×3 点天然豁免（除五处3点的情况）。
    private static int ResolveSections(CoatingMemberSpec spec, double spacing)
    {
        if (spec.SectionCount is int sc)
        {
            if (sc <= 0) throw new ArgumentException($"构件「{spec.Location}」截面数必须 > 0");
            if (sc < CoatingStandards.MinSections)
                throw new ArgumentException($"构件「{spec.Location}」截面数 {sc} < 规范要求的最少 {CoatingStandards.MinSections} 个截面（薄/超薄膨胀型走 5 处×3 点不受此限）");
            return sc;
        }
        if (spec.LengthM is double len && len > 0)
            return Math.Max(CoatingStandards.MinSections, (int)Math.Ceiling(len / spacing)); // ⌈长度/间距⌉，不少于规范最少截面数
        throw new ArgumentException($"构件「{spec.Location}」需填「长度(m)」或「截面数」");
    }

    private static double ResolveDesign(CoatingMemberSpec spec, CoatingTypePreset preset)
    {
        if (spec.DesignThickness is double d)
        {
            if (d <= 0) throw new ArgumentException($"构件「{spec.Location}」设计厚度必须 > 0");
            return d;
        }
        if (preset.DefaultDesignThickness is double def && def > 0) return def;
        throw new ArgumentException(
            $"构件「{spec.Location}」缺设计厚度——在「构件清单」本行填，或在「类型预设」给类型「{preset.MemberType}」设默认值");
    }

    // ── 读输入 sheet ──

    private static Dictionary<string, CoatingTypePreset> ReadTypePresets(XLWorkbook wb)
    {
        if (!wb.Worksheets.TryGetWorksheet(CoatingColumns.TypePresetSheet, out var ws))
            throw new ArgumentException($"缺少「{CoatingColumns.TypePresetSheet}」表");
        var map = CoatingSheetUtil.ReadHeaderMap(ws);
        int typeCol = CoatingSheetUtil.RequireColumn(map, CoatingColumns.MemberType, "类型预设的构件类型列");
        int posCol = CoatingSheetUtil.RequireColumn(map, CoatingColumns.PointPositions, "类型预设的测点位置列");
        int? defCol = CoatingSheetUtil.TryColumn(map, CoatingColumns.DefaultDesignThickness);

        var result = new Dictionary<string, CoatingTypePreset>();
        int lastRow = ws.LastRowUsed()?.RowNumber() ?? 0;
        for (int r = 2; r <= lastRow; r++)
        {
            var type = CoatingSheetUtil.ReadString(ws.Cell(r, typeCol));
            if (type.Length == 0) continue;
            var posRaw = CoatingSheetUtil.ReadString(ws.Cell(r, posCol));
            var positions = posRaw
                .Split(new[] { ',', '，' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            if (positions.Length == 0)
                throw new ArgumentException($"类型「{type}」的测点位置为空（用逗号分隔各面名，如「东侧面,西侧面,南侧面,北侧面」）");
            double? def = defCol is int dc ? CoatingSheetUtil.ReadOptDouble(ws.Cell(r, dc), $"类型「{type}」默认设计厚度") : null;
            result[type] = new CoatingTypePreset(type, positions, def);
        }
        if (result.Count == 0)
            throw new ArgumentException("「类型预设」表没有有效行");
        return result;
    }

    private static List<CoatingMemberSpec> ReadMemberList(XLWorkbook wb)
    {
        if (!wb.Worksheets.TryGetWorksheet(CoatingColumns.MemberListSheet, out var ws))
            throw new ArgumentException($"缺少「{CoatingColumns.MemberListSheet}」表");
        var map = CoatingSheetUtil.ReadHeaderMap(ws);
        int locCol = CoatingSheetUtil.RequireColumn(map, CoatingColumns.MemberLocation, "构件清单的构件位置列");
        int? batchCol = CoatingSheetUtil.TryColumn(map, CoatingColumns.Batch);
        int? typeCol = CoatingSheetUtil.TryColumn(map, CoatingColumns.MemberType);
        int? lenCol = CoatingSheetUtil.TryColumn(map, CoatingColumns.LengthM);
        int? secCol = CoatingSheetUtil.TryColumn(map, CoatingColumns.SectionCount);
        int? designCol = CoatingSheetUtil.TryColumn(map, CoatingColumns.DesignThickness);

        var specs = new List<CoatingMemberSpec>();
        int lastRow = ws.LastRowUsed()?.RowNumber() ?? 0;
        for (int r = 2; r <= lastRow; r++)
        {
            var loc = CoatingSheetUtil.ReadString(ws.Cell(r, locCol));
            if (loc.Length == 0) continue;
            string batch = batchCol is int bc ? CoatingSheetUtil.ReadString(ws.Cell(r, bc)) : "";
            if (batch.Length == 0) batch = CoatingColumns.DefaultBatchId;
            string? type = typeCol is int tc ? NullIfEmpty(CoatingSheetUtil.ReadString(ws.Cell(r, tc))) : null;
            double? len = lenCol is int lc ? CoatingSheetUtil.ReadOptDouble(ws.Cell(r, lc), $"构件「{loc}」长度") : null;
            int? sec = secCol is int scc ? CoatingSheetUtil.ReadOptInt(ws.Cell(r, scc), $"构件「{loc}」截面数") : null;
            double? design = designCol is int dgc ? CoatingSheetUtil.ReadOptDouble(ws.Cell(r, dgc), $"构件「{loc}」设计厚度") : null;
            specs.Add(new CoatingMemberSpec(batch, loc, type, len, sec, design));
        }
        return specs;
    }

    private static string? NullIfEmpty(string s) => string.IsNullOrWhiteSpace(s) ? null : s;

    // ── 写测点数据网格 ──

    /// <summary>相邻构件交替的两种行底色（浅蓝 / 白），让一构件 N 行成块、邻构件易区分。</summary>
    private static readonly XLColor BandColor = XLColor.FromHtml("#DDEBF7");

    private static void WriteGrid(IXLWorksheet ws, List<Resolved> members, string[] pointHeaders, bool fiveLocation)
    {
        // 膨胀型索引列叫「处号」（5 处），其余叫「截面号」。
        string indexHeader = fiveLocation ? CoatingColumns.LocationNo : CoatingColumns.SectionNo;
        var headers = new List<string>
        {
            CoatingColumns.Batch, CoatingColumns.MemberLocation, CoatingColumns.MemberType,
            CoatingColumns.CoatingCategory, CoatingColumns.DesignThickness, indexHeader,
        };
        headers.AddRange(pointHeaders);
        for (int c = 0; c < headers.Count; c++)
        {
            var cell = ws.Cell(1, c + 1);
            cell.Value = headers[c];
            cell.Style.Font.Bold = true;
            cell.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
            cell.Style.Fill.BackgroundColor = XLColor.LightGray;
        }

        int row = 2;
        int memberIdx = 0;
        foreach (var m in members)
        {
            var category = CoatingStandards.Classify(m.Design).ToString();
            int memberStart = row;
            for (int s = 1; s <= m.Sections; s++)
            {
                ws.Cell(row, 1).Value = m.Spec.BatchId;
                ws.Cell(row, 2).Value = m.Spec.Location;
                ws.Cell(row, 3).Value = m.Type;
                ws.Cell(row, 4).Value = category;
                ws.Cell(row, 5).Value = m.Design;
                ws.Cell(row, 6).Value = s;
                // 7..(6+faces) 测点格留空待填
                row++;
            }
            // 按构件分色：偶数构件整块上浅蓝，奇数构件留白 → 相邻构件一眼分清。
            if (memberIdx % 2 == 0 && row > memberStart)
                ws.Range(memberStart, 1, row - 1, headers.Count).Style.Fill.BackgroundColor = BandColor;
            memberIdx++;
        }

        var range = ws.Range(1, 1, row - 1, headers.Count);
        range.Style.Border.InsideBorder = XLBorderStyleValues.Thin;
        range.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
        range.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
        ws.Column(2).Width = 26;
    }
}
