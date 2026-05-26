// JSON-RPC 2.0 服务（stdin/stdout 行协议）。
//
// 与 src/civ_core/api/server.py 同设计：
//   - 一行一条 JSON-RPC 消息（行协议比 Content-Length header 简单）
//   - stdin 收请求，stdout 发响应；Console.Error 走日志，绝不污染协议流
//   - Dispatcher 是纯单元：handler 注册 + 请求路由 + 错误兜底
//   - RunAsync 是 stdin/stdout 行循环入口
//
// Handler 类型为 Func<JsonElement?, object?>：handler 自己解析 params（不像 Python 端
// 用反射自动按位置/按关键字解包）。理由：C# 反射性能差且需要写一堆 PropertyInfo 代码，
// 不如让 handler 主动 GetProperty/Deserialize 来得直接可控。

using System.Text.Json;

namespace CivCore.Doc.Server;

public delegate object? Handler(JsonElement? @params);

public static class ErrorCodes
{
    public const int ParseError = -32700;
    public const int InvalidRequest = -32600;
    public const int MethodNotFound = -32601;
    public const int InvalidParams = -32602;
    public const int Internal = -32603;
}

public class Dispatcher
{
    private readonly Dictionary<string, Handler> _handlers = new();

    public void Register(string method, Handler handler)
    {
        if (_handlers.ContainsKey(method))
            throw new ArgumentException($"重复注册 method: {method}");
        _handlers[method] = handler;
    }

    public int MethodCount => _handlers.Count;
    public IEnumerable<string> Methods => _handlers.Keys.OrderBy(s => s);

    /// <summary>
    /// 处理一行原始 JSON 文本，返回响应 JSON 字符串。
    /// 返回 null 表示 notification（无 id），不发送响应。
    /// </summary>
    public string? HandleRaw(string raw)
    {
        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(raw);
        }
        catch (JsonException e)
        {
            return ErrorResponse(null, ErrorCodes.ParseError, $"JSON 解析失败：{e.Message}");
        }

        using (doc)
        {
            if (doc.RootElement.ValueKind != JsonValueKind.Object)
                return ErrorResponse(null, ErrorCodes.InvalidRequest, "请求必须是 JSON 对象");

            var root = doc.RootElement;
            JsonElement? reqId = root.TryGetProperty("id", out var idEl) ? idEl : null;
            string? method = root.TryGetProperty("method", out var mEl) && mEl.ValueKind == JsonValueKind.String
                ? mEl.GetString()
                : null;
            JsonElement? @params = root.TryGetProperty("params", out var pEl) ? pEl : null;

            if (string.IsNullOrEmpty(method))
                return ErrorResponse(reqId, ErrorCodes.InvalidRequest, "缺 method 字段");

            if (!_handlers.TryGetValue(method, out var handler))
            {
                if (reqId is null) return null; // notification 不回响应
                return ErrorResponse(reqId, ErrorCodes.MethodNotFound, $"未知 method: {method}");
            }

            object? result;
            try
            {
                result = handler(@params);
            }
            catch (ArgumentException e)
            {
                Console.Error.WriteLine($"[civ-doc] handler {method} 参数错误: {e.Message}");
                if (reqId is null) return null;
                return ErrorResponse(reqId, ErrorCodes.InvalidParams, e.Message);
            }
            catch (Exception e)
            {
                Console.Error.WriteLine($"[civ-doc] handler {method} 内部异常: {e}");
                if (reqId is null) return null;
                return ErrorResponse(reqId, ErrorCodes.Internal, e.Message);
            }

            if (reqId is null) return null;
            return SuccessResponse(reqId, result);
        }
    }

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        // 中文 / unicode 字符不转 \uXXXX，前端读起来更直观
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private static string SuccessResponse(JsonElement? reqId, object? result)
    {
        var resp = new Dictionary<string, object?>
        {
            ["jsonrpc"] = "2.0",
            ["id"] = reqId.HasValue ? JsonElementToObject(reqId.Value) : null,
            ["result"] = result,
        };
        return JsonSerializer.Serialize(resp, JsonOpts);
    }

    private static string ErrorResponse(JsonElement? reqId, int code, string message)
    {
        var resp = new Dictionary<string, object?>
        {
            ["jsonrpc"] = "2.0",
            ["id"] = reqId.HasValue ? JsonElementToObject(reqId.Value) : null,
            ["error"] = new Dictionary<string, object?>
            {
                ["code"] = code,
                ["message"] = message,
            },
        };
        return JsonSerializer.Serialize(resp, JsonOpts);
    }

    /// <summary>JsonElement → 序列化器认识的原生 object，主要为了让 id 原样回传（数字保数字、字符串保字符串）。</summary>
    private static object? JsonElementToObject(JsonElement el) => el.ValueKind switch
    {
        JsonValueKind.Number => el.TryGetInt64(out var i) ? i : el.GetDouble(),
        JsonValueKind.String => el.GetString(),
        JsonValueKind.True => true,
        JsonValueKind.False => false,
        JsonValueKind.Null => null,
        _ => el.GetRawText(),
    };
}

public static class JsonRpcServer
{
    /// <summary>
    /// 入口：注册所有 handler，跑 stdin/stdout 行循环。stdin EOF 后退出。
    /// </summary>
    public static async Task RunAsync()
    {
        var dispatcher = new Dispatcher();
        Handlers.DocHandlers.RegisterAll(dispatcher);
        Handlers.XlsxHandlers.RegisterAll(dispatcher);
        Handlers.LeebHandlers.RegisterAll(dispatcher);
        Handlers.AnchorHandlers.RegisterAll(dispatcher);
        Handlers.TemplateHandlers.RegisterAll(dispatcher);
        Handlers.ReportHandlers.RegisterAll(dispatcher);
        Handlers.CatalogHandlers.RegisterAll(dispatcher);

        Console.Error.WriteLine(
            $"[civ-doc] 启动；已注册 {dispatcher.MethodCount} 个方法: {string.Join(", ", dispatcher.Methods)}");

        string? line;
        while ((line = await Console.In.ReadLineAsync()) != null)
        {
            // TrimStart 剥 UTF-8 BOM (﻿)：Tauri 写 stdin 不会带，但手测 echo
            // (PowerShell / 某些工具) 会在首行加 BOM，导致 JsonDocument.Parse 拒收。
            line = line.TrimStart('﻿').Trim();
            if (string.IsNullOrEmpty(line)) continue;

            var resp = dispatcher.HandleRaw(line);
            if (resp != null)
            {
                await Console.Out.WriteLineAsync(resp);
                await Console.Out.FlushAsync();
            }
        }

        Console.Error.WriteLine("[civ-doc] stdin 关闭，退出");
    }
}
