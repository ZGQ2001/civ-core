# C# sidecar 域规则

> **角色**：仅在 AI 操作 `dotnet/civ-doc/` 目录时加载。放 C# 专属编码规范。
> **主宪法**：`../CLAUDE.md`（架构/路由/不可变规则）

---

## 项目结构

```
dotnet/civ-doc/
├── Program.cs                 入口：UTF-8 stdin/stdout
├── civ-doc.csproj             net9.0, ClosedXML 0.105, Microsoft.Data.Sqlite 10.0
├── NuGet.config               华为云镜像 + nuget.org fallback
├── Server/JsonRpcServer.cs    Dispatcher + 行循环
├── Handlers/                  每个 handler 类有 RegisterAll(Dispatcher) 方法
├── Calc/                      计算逻辑（按检测类型分子目录）
├── StandardsDb/               SQLite 只读
└── ReportTables/              ClosedXML 报告表
```

## JSON-RPC Handler 注册模式

```csharp
// 1. 在 Handlers/ 下新建 XxxHandlers.cs
public static class XxxHandlers
{
    public static void RegisterAll(Dispatcher dispatcher)
    {
        dispatcher.Register("xxx.method1", HandleMethod1);
    }
    
    private static object? HandleMethod1(JsonElement? @params)
    {
        // 入参从 @params 手动解（不用反射）
        var input = @params?.GetProperty("input").GetString()
            ?? throw new ArgumentException("缺少参数: input");
        // 计算...
        return new { result = ... };
    }
}

// 2. 在 JsonRpcServer.RunAsync() 中加一行：
XxxHandlers.RegisterAll(dispatcher);
```

**不需要写 `__all__`**（Python 侧的约束）。C# 侧 handler 是显式注册，不会泄漏。

## 数据契约

用 `record`（不可变，值相等），构造函数校验类似 Python `__post_init__`：

```csharp
public record LeebHardnessResult
{
    public double CompFbMinAvg { get; }
    
    public LeebHardnessResult(double compFbMinAvg)
    {
        if (compFbMinAvg <= 0)
            throw new ArgumentException("comp_fb_min_avg 必须 > 0");
        CompFbMinAvg = compFbMinAvg;
    }
}
```

## 关键约定

- **stdout = 协议流**：只用 `Console.Error.WriteLine()` 打日志。绝不用 `Console.WriteLine()`。
- **UTF-8 强制**：`Program.cs` 已设 `Console.InputEncoding/OutputEncoding = UTF8`。中文不乱码。
- **BOM 容错**：`JsonRpcServer` trim 时剥 `﻿`。
- **错误码**：JSON-RPC 2.0 标准码：-32700 解析失败 / -32600 无效请求 / -32601 方法不存在 / -32603 内部错误。
- **浮点**：`(int)(mean + 0.5)` 四舍五入，不用 `Math.Round()`（默认「半数向偶」，与 Python `int(mean + 0.5)` 语义不同）。
- **SQLite**：`StandardsDb` 只读模式（`Mode=ReadOnly`）。Python sidecar 启动时 seed。

## 测试

```bash
cd dotnet/civ-doc
dotnet build                     # 编译
dotnet test                      # 运行 40 个 xUnit 测试
dotnet test --filter "FullyQualifiedName~LeebCalculator"  # 只跑某类
```

xUnit 项目在 `dotnet/civ-doc.Tests/`，引用 `civ-doc.csproj`。
测试文件命名：`<被测类>Tests.cs`，一个测试类对应一个被测类。

## 已知问题

- `read_line` 无超时（Rust 端 `sidecar.rs` 的问题，C# 端不受影响）
- `doc.compose_report` 未实现（T5.5 Step 3 预留）
