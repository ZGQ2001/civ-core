// doc.* RPC 方法注册与实现。
//
// 当前只有 ping/version 验证链路；下一步加 doc.fill_template（Word 模板填充走 OpenXML SDK）。
//
// 设计约束（和 Python 端 api/handlers/*.py 同）：
//   - handler 是普通 static 方法；参数永远是 JsonElement? @params（自己解包）
//   - 返回 object?，由 JsonRpcServer 序列化成 JSON
//   - 抛异常会被 Dispatcher 包成 -32603 Internal error 返前端

using System.Reflection;
using System.Text.Json;
using CivCore.Doc.Server;

namespace CivCore.Doc.Handlers;

public static class DocHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("doc.ping", Ping);
        d.Register("doc.version", Version);
    }

    /// <summary>桥联自测：返 "pong"。</summary>
    public static object Ping(JsonElement? @params) => "pong";

    /// <summary>返回 sidecar 基本信息，让前端能区分跟哪个进程通讯。</summary>
    public static object Version(JsonElement? @params)
    {
        var asmVer = Assembly.GetExecutingAssembly().GetName().Version?.ToString() ?? "0.0.0";
        return new Dictionary<string, object?>
        {
            ["name"] = "civ-doc",
            ["version"] = asmVer,
            ["framework"] = ".NET 9.0",
            ["sidecar"] = "csharp",
        };
    }
}
