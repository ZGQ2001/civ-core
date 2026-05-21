// 规范库 SQLite 读取层（对应 Python src/civ_core/infra_io/standards_db.py 的读取部分）。
//
// 表结构（单表 standards_tables 多 table_name 区分用途）：
//   id          INTEGER PK
//   table_name  TEXT NOT NULL  -- 逻辑表名（用 TableNames.* 常量识别）
//   key1        REAL NOT NULL
//   key2        REAL           -- NULL = 1D 表
//   value1      REAL NOT NULL
//   value2      REAL
//   value3      REAL
//
// 当前 Python 端负责 seed（每次 init_standards_db 幂等执行）；C# 端只读。
// 数据库文件位置：~/.civ-core/standards.db（Phase 5 之后考虑迁 seed 数据到 C# 端）。

using Microsoft.Data.Sqlite;

namespace CivCore.Doc.Standards;

/// <summary>逻辑表名常量（跟 Python 端 TABLE_LEEB_* 一致）。</summary>
public static class TableNames
{
    public const string LeebThickness = "leeb_thickness_correction";
    public const string LeebAngle = "leeb_angle_correction";
    public const string LeebStrength = "leeb_strength_conversion";
    public const string CoreDrillingK = "core_drilling_k";
    public const string ReboundStrength = "rebound_strength_curve";
    public const string ReboundAngle = "rebound_angle_correction";
    public const string ReboundSurface = "rebound_surface_correction";
}

/// <summary>一行规范数据；含义按 table_name 区分（1D 表只用 key1+value1；2D 表用 key1+key2+value1）。</summary>
public record StandardsRow(
    string TableName,
    double Key1,
    double Value1,
    double? Key2 = null,
    double? Value2 = null,
    double? Value3 = null
);

/// <summary>规范库连接 + 查表（轻量包装 Microsoft.Data.Sqlite）。</summary>
public class StandardsDb : IDisposable
{
    private readonly SqliteConnection _conn;

    /// <summary>用默认路径（~/.civ-core/standards.db）打开规范库。</summary>
    public static StandardsDb OpenDefault()
    {
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var path = Path.Combine(home, ".civ-core", "standards.db");
        if (!File.Exists(path))
            throw new FileNotFoundException(
                $"规范库不存在：{path}。请先跑一次 Python init_standards_db 初始化（healthcheck.py 会触发）。");
        return Open(path);
    }

    public static StandardsDb Open(string dbPath)
    {
        var conn = new SqliteConnection($"Data Source={dbPath};Mode=ReadOnly");
        conn.Open();
        return new StandardsDb(conn);
    }

    private StandardsDb(SqliteConnection conn) => _conn = conn;

    /// <summary>读出某 table_name 的全部行（按 key1, key2 升序）。</summary>
    public List<StandardsRow> ReadAll(string tableName)
    {
        var rows = new List<StandardsRow>();
        using var cmd = _conn.CreateCommand();
        cmd.CommandText = @"
            SELECT key1, key2, value1, value2, value3
            FROM standards_tables
            WHERE table_name = $name
            ORDER BY key1, key2";
        cmd.Parameters.AddWithValue("$name", tableName);
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            rows.Add(new StandardsRow(
                TableName: tableName,
                Key1: reader.GetDouble(0),
                Key2: reader.IsDBNull(1) ? null : reader.GetDouble(1),
                Value1: reader.GetDouble(2),
                Value2: reader.IsDBNull(3) ? null : reader.GetDouble(3),
                Value3: reader.IsDBNull(4) ? null : reader.GetDouble(4)
            ));
        }
        return rows;
    }

    /// <summary>返回某 table_name 的行数（方便完整性校验）。</summary>
    public int CountRows(string tableName)
    {
        using var cmd = _conn.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM standards_tables WHERE table_name = $name";
        cmd.Parameters.AddWithValue("$name", tableName);
        var result = cmd.ExecuteScalar();
        return Convert.ToInt32(result);
    }

    public void Dispose() => _conn.Dispose();
}
