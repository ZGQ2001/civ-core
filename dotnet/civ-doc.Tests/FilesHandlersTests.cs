// FilesHandlers 集成测试 —— 对齐 tests/test_api_handlers.py 中迁移过来的 files.* 用例。
//
// delete/undo_delete 实际会发到 Windows 回收站；测试用唯一 GUID 文件名避免和真实回收站项混淆。

using System.Runtime.Versioning;
using System.Text.Json;
using CivCore.Doc.Files;
using CivCore.Doc.Handlers;
using Xunit;

namespace CivCore.Doc.Tests;

[SupportedOSPlatform("windows")]
public class FilesHandlersTests : IDisposable
{
    private readonly string _tmpDir;

    public FilesHandlersTests()
    {
        _tmpDir = Path.Combine(Path.GetTempPath(), $"civ-doc-files-{Guid.NewGuid()}");
        Directory.CreateDirectory(_tmpDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tmpDir))
            Directory.Delete(_tmpDir, recursive: true);
        RecycleBin.ResetUndoStack();
    }

    private static JsonElement P(object obj) =>
        JsonDocument.Parse(JsonSerializer.Serialize(obj)).RootElement;

    // ── list_dir ────────────────────────────────────────────

    [Fact]
    public void ListDir_DirectoriesBeforeFiles_NaturalSort()
    {
        Directory.CreateDirectory(Path.Combine(_tmpDir, "a"));
        File.WriteAllText(Path.Combine(_tmpDir, "b.txt"), "hi");

        var res = (Dictionary<string, object?>)FilesHandlers.ListDir(P(new { path = _tmpDir }))!;
        var entries = (List<Dictionary<string, object?>>)res["entries"]!;
        Assert.Equal(2, entries.Count);
        Assert.Equal("a", entries[0]["name"]);
        Assert.Equal(true, entries[0]["is_dir"]);
        Assert.Equal("b.txt", entries[1]["name"]);
        Assert.Equal(false, entries[1]["is_dir"]);
        Assert.Equal(2L, entries[1]["size"]);
    }

    [Fact]
    public void ListDir_NaturalSort_File2_Before_File10()
    {
        File.WriteAllText(Path.Combine(_tmpDir, "file2.txt"), "");
        File.WriteAllText(Path.Combine(_tmpDir, "file10.txt"), "");
        File.WriteAllText(Path.Combine(_tmpDir, "file100.txt"), "");

        var res = (Dictionary<string, object?>)FilesHandlers.ListDir(P(new { path = _tmpDir }))!;
        var names = ((List<Dictionary<string, object?>>)res["entries"]!).Select(e => (string)e["name"]!).ToList();
        Assert.Equal(new[] { "file2.txt", "file10.txt", "file100.txt" }, names);
    }

    [Fact]
    public void ListDir_HidesCivCore_EvenWithShowHidden()
    {
        Directory.CreateDirectory(Path.Combine(_tmpDir, ".civ-core"));
        Directory.CreateDirectory(Path.Combine(_tmpDir, "visible"));
        var res = (Dictionary<string, object?>)FilesHandlers.ListDir(P(new { path = _tmpDir, show_hidden = true }))!;
        var names = ((List<Dictionary<string, object?>>)res["entries"]!).Select(e => (string)e["name"]!).ToList();
        Assert.Contains("visible", names);
        Assert.DoesNotContain(".civ-core", names);
    }

    [Fact]
    public void ListDir_HidesDotfiles_ByDefault()
    {
        File.WriteAllText(Path.Combine(_tmpDir, ".gitignore"), "x");
        File.WriteAllText(Path.Combine(_tmpDir, "README.md"), "y");

        var defaultRes = (Dictionary<string, object?>)FilesHandlers.ListDir(P(new { path = _tmpDir }))!;
        var defaultNames = ((List<Dictionary<string, object?>>)defaultRes["entries"]!).Select(e => (string)e["name"]!).ToList();
        Assert.DoesNotContain(".gitignore", defaultNames);

        var shownRes = (Dictionary<string, object?>)FilesHandlers.ListDir(P(new { path = _tmpDir, show_hidden = true }))!;
        var shownNames = ((List<Dictionary<string, object?>>)shownRes["entries"]!).Select(e => (string)e["name"]!).ToList();
        Assert.Contains(".gitignore", shownNames);
    }

    [Fact]
    public void ListDir_NotADirectory_Throws()
    {
        var f = Path.Combine(_tmpDir, "f.txt");
        File.WriteAllText(f, "x");
        Assert.Throws<ArgumentException>(() =>
            FilesHandlers.ListDir(P(new { path = f })));
    }

    // ── exists ────────────────────────────────────────────

    [Fact]
    public void Exists_File_Dir_Missing()
    {
        var f = Path.Combine(_tmpDir, "f.txt");
        File.WriteAllText(f, "x");
        var fileRes = (Dictionary<string, object?>)FilesHandlers.Exists(P(new { path = f }))!;
        Assert.Equal(true, fileRes["exists"]);
        Assert.Equal(false, fileRes["is_dir"]);
        Assert.Equal(true, fileRes["is_file"]);

        var dirRes = (Dictionary<string, object?>)FilesHandlers.Exists(P(new { path = _tmpDir }))!;
        Assert.Equal(true, dirRes["exists"]);
        Assert.Equal(true, dirRes["is_dir"]);
        Assert.Equal(false, dirRes["is_file"]);

        var ghostRes = (Dictionary<string, object?>)FilesHandlers.Exists(
            P(new { path = Path.Combine(_tmpDir, "ghost") }))!;
        Assert.Equal(false, ghostRes["exists"]);
    }

    // ── create / rename ──────────────────────────────────

    [Fact]
    public void CreateFile_Then_Rename_Then_Delete()
    {
        var c = (Dictionary<string, object?>)FilesHandlers.CreateFile(
            P(new { parent = _tmpDir, name = "a.txt" }))!;
        var aPath = (string)c["path"]!;
        Assert.True(File.Exists(aPath));

        var r = (Dictionary<string, object?>)FilesHandlers.Rename(
            P(new { path = aPath, new_name = "b.txt" }))!;
        Assert.False(File.Exists(aPath));
        Assert.True(File.Exists((string)r["path"]!));
        Assert.EndsWith("b.txt", (string)r["path"]!);
    }

    [Fact]
    public void CreateFile_NameAlreadyExists_Throws()
    {
        FilesHandlers.CreateFile(P(new { parent = _tmpDir, name = "x.txt" }));
        Assert.Throws<IOException>(() =>
            FilesHandlers.CreateFile(P(new { parent = _tmpDir, name = "x.txt" })));
    }

    [Fact]
    public void CreateFolder_NonExistentParent_Throws()
    {
        Assert.Throws<ArgumentException>(() =>
            FilesHandlers.CreateFolder(P(new { parent = Path.Combine(_tmpDir, "ghost"), name = "x" })));
    }

    [Theory]
    [InlineData("")]
    [InlineData(" leading-space")]
    [InlineData("trailing-space ")]
    [InlineData("a<b.txt")]
    [InlineData("a*b.txt")]
    [InlineData("CON")]
    [InlineData("CON.txt")]
    public void CreateFile_InvalidName_Throws(string name)
    {
        Assert.Throws<ArgumentException>(() =>
            FilesHandlers.CreateFile(P(new { parent = _tmpDir, name })));
    }

    [Fact]
    public void Rename_NoOpToSameName_ReturnsSamePath()
    {
        var c = (Dictionary<string, object?>)FilesHandlers.CreateFile(
            P(new { parent = _tmpDir, name = "same.txt" }))!;
        var aPath = (string)c["path"]!;
        var r = (Dictionary<string, object?>)FilesHandlers.Rename(
            P(new { path = aPath, new_name = "same.txt" }))!;
        Assert.Equal(aPath, r["path"]);
    }

    // ── copy / move（含唯一命名 + 递归目录复制）──────────

    [Fact]
    public void Copy_File_UniqueRenameOnConflict()
    {
        var src = Path.Combine(_tmpDir, "data.xlsx");
        File.WriteAllBytes(src, new byte[] { 1, 2, 3 });

        var dst = Path.Combine(_tmpDir, "sub");
        Directory.CreateDirectory(dst);
        File.WriteAllText(Path.Combine(dst, "data.xlsx"), "existing");

        var r = (Dictionary<string, object?>)FilesHandlers.Copy(
            P(new { src, dst_parent = dst }))!;
        var target = (string)r["path"]!;
        Assert.Equal(Path.Combine(dst, "data (2).xlsx"), target);
        Assert.Equal(3, new FileInfo(target).Length);
    }

    [Fact]
    public void Copy_Directory_Recursive()
    {
        var src = Path.Combine(_tmpDir, "tree");
        Directory.CreateDirectory(Path.Combine(src, "nested"));
        File.WriteAllText(Path.Combine(src, "a.txt"), "A");
        File.WriteAllText(Path.Combine(src, "nested", "b.txt"), "B");

        var dst = Path.Combine(_tmpDir, "dst");
        Directory.CreateDirectory(dst);

        var r = (Dictionary<string, object?>)FilesHandlers.Copy(
            P(new { src, dst_parent = dst }))!;
        var copied = (string)r["path"]!;
        Assert.True(File.Exists(Path.Combine(copied, "a.txt")));
        Assert.True(File.Exists(Path.Combine(copied, "nested", "b.txt")));
        // 源不动
        Assert.True(File.Exists(Path.Combine(src, "a.txt")));
    }

    [Fact]
    public void Move_SameParentDir_NoOp()
    {
        var src = Path.Combine(_tmpDir, "m.txt");
        File.WriteAllText(src, "x");
        var r = (Dictionary<string, object?>)FilesHandlers.Move(
            P(new { src, dst_parent = _tmpDir }))!;
        Assert.Equal(src, r["path"]);
        Assert.True(File.Exists(src));
    }

    [Fact]
    public void Move_File_ToOtherDir()
    {
        var src = Path.Combine(_tmpDir, "m.txt");
        File.WriteAllText(src, "X");
        var dst = Path.Combine(_tmpDir, "sub");
        Directory.CreateDirectory(dst);

        var r = (Dictionary<string, object?>)FilesHandlers.Move(
            P(new { src, dst_parent = dst }))!;
        var target = (string)r["path"]!;
        Assert.Equal(Path.Combine(dst, "m.txt"), target);
        Assert.False(File.Exists(src));
        Assert.True(File.Exists(target));
    }

    [Fact]
    public void Copy_SourceMissing_Throws()
    {
        var ghost = Path.Combine(_tmpDir, "ghost.txt");
        Assert.Throws<FileNotFoundException>(() =>
            FilesHandlers.Copy(P(new { src = ghost, dst_parent = _tmpDir })));
    }

    // ── delete + undo（实测发回收站；要求 Windows）────────

    [Fact]
    public void Delete_SendsToRecycleBin_ThenUndoRestores()
    {
        if (!OperatingSystem.IsWindows())
            return; // 仅 Windows
        var unique = Guid.NewGuid().ToString("N")[..12];
        var src = Path.Combine(_tmpDir, $"todelete-{unique}.txt");
        File.WriteAllText(src, "doomed");

        FilesHandlers.Delete(P(new { path = src }));
        Assert.False(File.Exists(src));

        var r = (Dictionary<string, object?>)FilesHandlers.UndoDelete(null)!;
        Assert.Equal(src, r["restored_path"]);
        Assert.True(File.Exists(src), "undo 应当把文件还原到原始路径");
    }

    [Fact]
    public void UndoDelete_EmptyStack_Throws()
    {
        RecycleBin.ResetUndoStack();
        Assert.Throws<ArgumentException>(() => FilesHandlers.UndoDelete(null));
    }

    [Fact]
    public void Delete_NonExistent_Throws()
    {
        Assert.Throws<FileNotFoundException>(() =>
            FilesHandlers.Delete(P(new { path = Path.Combine(_tmpDir, "ghost") })));
    }

    // ── reveal（仅 Windows）────────────────────────────

    [Fact]
    public void Reveal_NonExistent_Throws()
    {
        Assert.Throws<FileNotFoundException>(() =>
            FilesHandlers.Reveal(P(new { path = Path.Combine(_tmpDir, "ghost") })));
    }
}
