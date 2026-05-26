using System.Text.Json;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Template;

namespace CivCore.Doc.Catalog;

public static class CatalogStore
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private static string CatalogDir()
    {
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var dir = Path.Combine(home, ".civ-core", "catalogs");
        if (!Directory.Exists(dir))
            Directory.CreateDirectory(dir);
        return dir;
    }

    private static string CatalogPath(string id) => Path.Combine(CatalogDir(), $"{id}.json");

    public static List<CatalogSummary> List()
    {
        SeedIfEmpty();
        var dir = CatalogDir();
        var result = new List<CatalogSummary>();
        foreach (var file in Directory.GetFiles(dir, "*.json"))
        {
            try
            {
                var json = File.ReadAllText(file);
                var dto = JsonSerializer.Deserialize<FieldCatalogDto>(json, JsonOpts);
                if (dto == null) continue;
                result.Add(new CatalogSummary
                {
                    Id = dto.Id,
                    Label = dto.Label,
                    FieldCount = dto.Fields.Count,
                });
            }
            catch
            {
                // skip malformed catalogs
            }
        }
        return result.OrderBy(c => c.Id).ToList();
    }

    public static FieldCatalogDto? Get(string id)
    {
        SeedIfEmpty();
        var path = CatalogPath(id);
        if (!File.Exists(path)) return null;
        var json = File.ReadAllText(path);
        return JsonSerializer.Deserialize<FieldCatalogDto>(json, JsonOpts);
    }

    public static void Save(FieldCatalogDto catalog)
    {
        if (string.IsNullOrWhiteSpace(catalog.Id))
            throw new ArgumentException("字段目录 id 不可为空");
        if (string.IsNullOrWhiteSpace(catalog.Label))
            throw new ArgumentException("字段目录名称不可为空");
        var json = JsonSerializer.Serialize(catalog, JsonOpts);
        File.WriteAllText(CatalogPath(catalog.Id), json);
    }

    public static void Delete(string id)
    {
        var path = CatalogPath(id);
        if (File.Exists(path))
            File.Delete(path);
    }

    /// <summary>将 JSON 目录转成引擎用的 FieldDef[]，供 ReportHandlers / PlaceholderRenderer 使用。</summary>
    public static FieldDef[] ToFieldDefs(FieldCatalogDto catalog)
    {
        return catalog.Fields.Select(f =>
        {
            var source = Enum.TryParse<FieldSource>(f.Source, ignoreCase: true, out var s)
                ? s : FieldSource.UserInput;
            return FieldDef.Create(f.Key, f.Name, source, f.ValueType, f.DefaultFormat,
                aliases: f.Aliases.Count > 0 ? f.Aliases : null);
        }).ToArray();
    }

    // ── 种子 ──

    private static bool _seeded;

    private static void SeedIfEmpty()
    {
        if (_seeded) return;
        _seeded = true;
        var dir = CatalogDir();
        if (Directory.GetFiles(dir, "*.json").Length > 0) return;
        Save(BuildAnchorCatalog());
        Console.Error.WriteLine("[civ-doc] 已初始化默认字段目录: anchor");
    }

    // ── 层级常量 ──

    private static readonly HashSet<string> ReportLevelKeys = new()
    {
        "client_name", "project_name", "report_no",
        "supervisor_unit", "designer_unit", "constructor_unit",
    };

    private static readonly HashSet<string> DetectionItemKeys = new()
    {
        "inspection_category", "inspection_item", "inspection_site",
        "inspection_basis", "inspection_time", "inspection_engineer",
        "inspection_conclusion",
        "instrument1_name", "instrument1_no", "instrument1_cert_no",
        "instrument1_valid_until", "instrument1_precision",
        "instrument2_name", "instrument2_no", "instrument2_cert_no",
        "instrument2_valid_until", "instrument2_precision",
    };

    private static readonly HashSet<string> BatchLevelKeys = new()
    {
        "batch_id",
        "axial_design_load", "free_length", "anchor_length",
        "steel_area", "elastic_modulus", "axial_design_load_kn",
        "rock_soil_property", "bar_material_spec",
        "grouting_date", "grout_ratio", "grout_strength",
        "drill_angle", "drill_diameter",
    };

    private static string InferLevel(string key)
    {
        if (ReportLevelKeys.Contains(key)) return "report";
        if (DetectionItemKeys.Contains(key)) return "detection_item";
        if (BatchLevelKeys.Contains(key)) return "batch";
        return "component";
    }

    private static FieldCatalogDto BuildAnchorCatalog()
    {
        return new FieldCatalogDto
        {
            Id = "anchor",
            Label = "锚杆检测",
            Fields = AnchorFieldCatalog.All.Select(f => new CatalogFieldDto
            {
                Key = f.Key,
                Name = f.Name,
                Group = InferGroup(f),
                Level = InferLevel(f.Key),
                Source = f.Source.ToString().ToLowerInvariant(),
                ValueType = f.ValueType,
                DefaultFormat = f.DefaultFormat,
                Aliases = f.Aliases.ToList(),
            }).ToList(),
        };
    }

    private static string InferGroup(FieldDef f)
    {
        if (f.Key == "batch_id") return "批次标识";
        if (f.Key.StartsWith("instrument")) return "检测仪器";
        if (f.Key == "curve_image") return "图片";
        return f.Source switch
        {
            FieldSource.Parameter => "工程参数",
            FieldSource.RawInput => "原始数据",
            FieldSource.Calculated => "计算结果",
            FieldSource.UserInput when f.Key.StartsWith("client") || f.Key.StartsWith("project")
                || f.Key.StartsWith("report") || f.Key.StartsWith("supervisor")
                || f.Key.StartsWith("designer") || f.Key.StartsWith("constructor")
                || f.Key.StartsWith("inspection") => "项目信息",
            FieldSource.UserInput => "工程描述",
            _ => "其他",
        };
    }
}
