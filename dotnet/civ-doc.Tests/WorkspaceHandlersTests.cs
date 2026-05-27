// WorkspaceHandlers 集成测试 —— 完整 RPC 路径行为对齐 Python handlers/workspace.py。
//
// 注意：WorkspaceStore 写的是用户家目录下的 ~/.civ-core/workspace.json，
// 测试通过临时重定向 HOME / USERPROFILE 环境变量到 tmpDir 避开真实用户数据。

using System.Text.Json;
using CivCore.Doc.Handlers;
using CivCore.Doc.Workspace;
using Xunit;

namespace CivCore.Doc.Tests;

public class WorkspaceHandlersTests : IDisposable
{
    private readonly string _tmpDir;
    private readonly string? _originalUserProfile;
    private readonly string? _originalHome;

    public WorkspaceHandlersTests()
    {
        _tmpDir = Path.Combine(Path.GetTempPath(), $"civ-doc-ws-{Guid.NewGuid()}");
        Directory.CreateDirectory(_tmpDir);
        _originalUserProfile = Environment.GetEnvironmentVariable("USERPROFILE");
        _originalHome = Environment.GetEnvironmentVariable("HOME");
        Environment.SetEnvironmentVariable("USERPROFILE", _tmpDir);
        Environment.SetEnvironmentVariable("HOME", _tmpDir);
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("USERPROFILE", _originalUserProfile);
        Environment.SetEnvironmentVariable("HOME", _originalHome);
        if (Directory.Exists(_tmpDir))
            Directory.Delete(_tmpDir, recursive: true);
    }

    private static JsonElement P(object obj) =>
        JsonDocument.Parse(JsonSerializer.Serialize(obj)).RootElement;

    [Fact]
    public void Last_NoStore_ReturnsNull()
    {
        var res = (Dictionary<string, object?>)WorkspaceHandlers.Last(null)!;
        Assert.Null(res["path"]);
    }

    [Fact]
    public void Set_ThenLast_RoundTrip()
    {
        var ws = Path.Combine(_tmpDir, "myProject");
        Directory.CreateDirectory(ws);

        var setRes = (Dictionary<string, object?>)WorkspaceHandlers.Set(P(new { path = ws }))!;
        Assert.Equal(true, setRes["ok"]);
        Assert.Equal(ws, setRes["path"]);

        var lastRes = (Dictionary<string, object?>)WorkspaceHandlers.Last(null)!;
        Assert.Equal(ws, lastRes["path"]);
    }

    [Fact]
    public void Set_NonExistentDir_Throws()
    {
        var fake = Path.Combine(_tmpDir, "does-not-exist");
        Assert.Throws<ArgumentException>(() =>
            WorkspaceHandlers.Set(P(new { path = fake })));
    }

    [Fact]
    public void Last_PathDeletedAfterSet_ReturnsNull()
    {
        var ws = Path.Combine(_tmpDir, "vanish");
        Directory.CreateDirectory(ws);
        WorkspaceHandlers.Set(P(new { path = ws }));
        Directory.Delete(ws);

        var res = (Dictionary<string, object?>)WorkspaceHandlers.Last(null)!;
        Assert.Null(res["path"]);
    }

    [Fact]
    public void Clear_RemovesLastWorkspace()
    {
        var ws = Path.Combine(_tmpDir, "p1");
        Directory.CreateDirectory(ws);
        WorkspaceHandlers.Set(P(new { path = ws }));

        var clearRes = (Dictionary<string, object?>)WorkspaceHandlers.Clear(null)!;
        Assert.Equal(true, clearRes["ok"]);

        var lastRes = (Dictionary<string, object?>)WorkspaceHandlers.Last(null)!;
        Assert.Null(lastRes["path"]);
    }

    [Fact]
    public void CreateStandard_BuildsFullSkeleton()
    {
        var res = (Dictionary<string, object?>)WorkspaceHandlers.CreateStandard(
            P(new { parent_dir = _tmpDir, name = "门头沟一号地块" }))!;
        Assert.Equal(true, res["ok"]);
        var root = (string)res["path"]!;
        Assert.Equal(Path.Combine(_tmpDir, "门头沟一号地块"), root);

        foreach (var sub in StandardScaffold.StandardSubfolders)
            Assert.True(Directory.Exists(Path.Combine(root, sub)), $"缺业务子目录：{sub}");
        var app = Path.Combine(root, StandardScaffold.AppDotfolder);
        Assert.True(Directory.Exists(app));
        foreach (var sub in StandardScaffold.AppSubfolders)
            Assert.True(Directory.Exists(Path.Combine(app, sub)), $"缺应用子目录：{sub}");
    }

    [Fact]
    public void CreateStandard_Idempotent()
    {
        WorkspaceHandlers.CreateStandard(P(new { parent_dir = _tmpDir, name = "repeat" }));
        // 第二次调用不应报错（mkdir exist_ok）
        var res = (Dictionary<string, object?>)WorkspaceHandlers.CreateStandard(
            P(new { parent_dir = _tmpDir, name = "repeat" }))!;
        Assert.Equal(true, res["ok"]);

        // 用户在中间放了文件，二次调用要保留
        var root = (string)res["path"]!;
        var userFile = Path.Combine(root, "数据", "user_data.xlsx");
        File.WriteAllText(userFile, "user data");
        WorkspaceHandlers.CreateStandard(P(new { parent_dir = _tmpDir, name = "repeat" }));
        Assert.True(File.Exists(userFile));
    }

    [Fact]
    public void CreateStandard_NonExistentParent_Throws()
    {
        Assert.Throws<ArgumentException>(() =>
            WorkspaceHandlers.CreateStandard(
                P(new { parent_dir = Path.Combine(_tmpDir, "ghost"), name = "x" })));
    }

    [Theory]
    [InlineData("")]
    [InlineData("a/b")]
    [InlineData("a\\b")]
    [InlineData("   ")]
    public void CreateStandard_InvalidName_Throws(string name)
    {
        Assert.Throws<ArgumentException>(() =>
            WorkspaceHandlers.CreateStandard(P(new { parent_dir = _tmpDir, name })));
    }
}
