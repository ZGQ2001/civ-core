// 标准项目文件夹骨架生成。
//
// 与 src/civ_core/infra_io/workspace_scaffold.py 同：
//   - 业务约定（4 个顶层子文件夹）+ 应用约定（.civ-core/）的唯一定义点
//   - mkdir(exist_ok=True) 实现幂等：已存在的目录不报错，缺失的补齐
//   - 不在此做"删除多余 / 校验完整"等高阶行为
//
// 约定来源照搬实际项目目录（2026_03_26_门头沟…一号地块）的顶层结构。

namespace CivCore.Doc.Workspace;

public static class StandardScaffold
{
    /// <summary>顶层业务子文件夹（命名照用户实际项目目录搬来）。</summary>
    public static readonly string[] StandardSubfolders =
    {
        "委托方提供资料",
        "数据",
        "报告",
        "模板",
    };

    /// <summary>应用专属隐藏目录（默认在文件树里隐藏）。</summary>
    public const string AppDotfolder = ".civ-core";

    /// <summary>应用专属子目录（styles 项目级样式预设；outputs 应用生成的中间产物）。</summary>
    public static readonly string[] AppSubfolders =
    {
        "styles",
        "outputs",
    };

    /// <summary>
    /// 在 root 下建立标准项目骨架；root 自身缺失也会一并 mkdir。
    /// 幂等：已存在的目录不报错；用户已经放进去的文件原样保留。
    /// root 若已被非目录文件占用，Directory.CreateDirectory 会抛 IOException。
    /// </summary>
    public static string Create(string root)
    {
        Directory.CreateDirectory(root);
        foreach (var name in StandardSubfolders)
            Directory.CreateDirectory(Path.Combine(root, name));
        var appRoot = Path.Combine(root, AppDotfolder);
        Directory.CreateDirectory(appRoot);
        foreach (var sub in AppSubfolders)
            Directory.CreateDirectory(Path.Combine(appRoot, sub));
        return root;
    }
}
