// civ-doc sidecar 入口。
//
// 作为 Tauri 主进程的子进程跑，stdin/stdout 走 JSON-RPC 2.0 行协议（与 Python sidecar
// civ_core.api 同协议）。负责 Word/Excel 重资产场景（doc.* / xlsx.* 方法），用 OpenXML SDK
// 原生处理，不依赖 Office 安装。
//
// stdout 是协议流，绝不能被业务日志污染 —— Console.Out 只输出 JSON-RPC 响应；日志走 Console.Error。
// （与 Python 端 api/__main__.py 同设计原则。）

using System.Text;
using CivCore.Doc.Server;

// 强制 stdin/stdout/stderr UTF-8：Windows 默认 GBK，中文会乱码导致前端解析失败。
Console.InputEncoding = Encoding.UTF8;
Console.OutputEncoding = Encoding.UTF8;

await JsonRpcServer.RunAsync();
