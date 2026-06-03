// 检测类型的显式登记表（Pipeline 抽象 Phase 2 框架接缝，见
// docs/plans/2026-06-02-detection-pipeline-abstraction.md §4）。
//
// 把锚杆/防火/里氏三检测类型的 RPC 注册收进「一处显式清单」——加检测类型只动 All 加一行，
// JsonRpcServer 遍历本清单注册、零改动。保持显式可 grep、无反射（CLAUDE.md：不用反射、可追溯）。
//
// 现阶段描述符只含「类型名 + 注册委托」（最小接缝，行为与原 3 行手写 RegisterAll 字节级一致）。
// 后续阶段再往描述符加 Standards / IDetectionPipeline，把 run() 共性收进通用脚手架（§4 Phase 2）。

using CivCore.Doc.Handlers;
using CivCore.Doc.Server;

namespace CivCore.Doc.Detection;

/// <summary>一个检测类型的登记项。Register 把该类型的 RPC 方法注册进 dispatcher。</summary>
public sealed record DetectionModule(string Type, Action<Dispatcher> Register);

public static class DetectionCatalog
{
    /// <summary>全部检测类型 —— 加检测类型在此加一行（顺序沿用原 JsonRpcServer 注册顺序：leeb→anchor→coating）。</summary>
    public static readonly DetectionModule[] All =
    {
        new("leeb", LeebHandlers.RegisterAll),
        new("anchor", AnchorHandlers.RegisterAll),
        new("coating", CoatingHandlers.RegisterAll),
    };
}
