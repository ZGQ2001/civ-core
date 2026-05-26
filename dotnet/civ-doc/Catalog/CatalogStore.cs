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

    private static FieldCatalogDto BuildAnchorCatalog()
    {
        var groupMap = new Dictionary<string, string>();
        foreach (var f in AnchorFieldCatalog.All)
        {
            var group = InferGroup(f);
            groupMap[f.Key] = group;
        }

        return new FieldCatalogDto
        {
            Id = "anchor",
            Label = "锚杆检测",
            Fields = AnchorFieldCatalog.All.Select(f => new CatalogFieldDto
            {
                Key = f.Key,
                Name = f.Name,
                Group = groupMap[f.Key],
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
