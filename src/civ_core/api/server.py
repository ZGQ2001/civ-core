"""JSON-RPC 2.0 服务（stdin/stdout 行协议）。

设计：
  - 一行一条 JSON-RPC 消息（行协议比 Content-Length header 简单且足够）
  - stdin 收请求，stdout 发响应；stderr 不参与协议，只走 logger（避免污染协议流）
  - Dispatcher 是纯单元：handler 注册 + 请求路由 + 错误兜底；
    不直接碰 stdin/stdout，便于单测和复用（未来如果换 socket 协议也能复用）
  - serve() 是 stdin/stdout 行循环入口；__main__ 调它

JSON-RPC 2.0 错误码约定：
  -32700 Parse error
  -32600 Invalid request
  -32601 Method not found
  -32602 Invalid params  （我们不强校验 params，交给 handler 自己；调用错就走 -32603）
  -32603 Internal error  （handler 内部异常）
"""

from __future__ import annotations

import inspect
import json
import sys
from collections.abc import Callable
from typing import Any

from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# JSON-RPC 错误码
ERR_PARSE_ERROR = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603

Handler = Callable[..., Any]


class Dispatcher:
    """JSON-RPC 路由器 —— 纯逻辑，不碰 IO。"""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, method: str, handler: Handler) -> None:
        """注册 method → handler；重复注册抛 ValueError（防 handler 模块互覆盖）。"""
        if method in self._handlers:
            raise ValueError(f"重复注册 method: {method!r}")
        self._handlers[method] = handler

    def register_module(self, prefix: str, module: Any) -> None:
        """便捷：把 module 里所有不以 _ 开头的可调用对象按 `prefix.name` 注册。

        例：register_module("workspace", workspace_module) →
            workspace_module.last() 注册成 "workspace.last"
        """
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if callable(obj):
                self.register(f"{prefix}.{name}", obj)

    def handle_raw(self, raw: str) -> str:
        """处理一行原始 JSON 文本，返回响应 JSON 字符串（空串表示无响应/notification）。"""
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as e:
            return self._error_response(None, ERR_PARSE_ERROR, f"JSON 解析失败：{e}")

        if not isinstance(req, dict):
            return self._error_response(None, ERR_INVALID_REQUEST, "请求必须是 JSON 对象")

        req_id = req.get("id")  # None → notification（不返回响应）
        method = req.get("method")
        params = req.get("params", None)

        if not isinstance(method, str) or not method:
            return self._error_response(req_id, ERR_INVALID_REQUEST, "缺 method 字段")

        handler = self._handlers.get(method)
        if handler is None:
            if req_id is None:
                return ""  # notification 不回任何响应
            return self._error_response(
                req_id, ERR_METHOD_NOT_FOUND, f"未知 method: {method!r}"
            )

        try:
            result = self._invoke(handler, params)
        except Exception as e:
            log.exception("handler %s 抛异常", method)
            if req_id is None:
                return ""  # notification 即便出错也不回响应
            return self._error_response(req_id, ERR_INTERNAL, f"{type(e).__name__}: {e}")

        if req_id is None:
            return ""  # notification 不回响应
        return json.dumps(
            {"jsonrpc": "2.0", "id": req_id, "result": result},
            ensure_ascii=False,
        )

    def _invoke(self, handler: Handler, params: Any) -> Any:
        """根据 params 类型选择按位置/按关键字调用。"""
        if params is None:
            return handler()
        if isinstance(params, list):
            return handler(*params)
        if isinstance(params, dict):
            return handler(**params)
        raise TypeError(f"params 必须是 list/dict/None，得到 {type(params).__name__}")

    @staticmethod
    def _error_response(req_id: Any, code: int, message: str) -> str:
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": code, "message": message},
            },
            ensure_ascii=False,
        )

    def methods(self) -> list[str]:
        """已注册的全部方法名（按字母序）。"""
        return sorted(self._handlers.keys())


# ── stdin/stdout 行循环 ──────────────────────────────────────
def serve(dispatcher: Dispatcher) -> int:
    """读 stdin 一行 → dispatch → 写一行 stdout。stdin EOF 后退出。

    Windows 控制台默认 GBK，强制 UTF-8 避免中文路径乱码。
    """
    # 把 stdin/stdout 改成 UTF-8（line-buffered），让 Tauri sidecar 通信稳定
    sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)  # type: ignore[attr-defined]

    log.info("api server 启动；已注册 %d 个方法", len(dispatcher.methods()))
    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if not line:
            continue
        resp = dispatcher.handle_raw(line)
        if resp:
            sys.stdout.write(resp + "\n")
            sys.stdout.flush()
    log.info("stdin 关闭，api server 退出")
    return 0


def _ensure_arity_matches(handler: Handler, name: str) -> None:
    """开发期助手：检查 handler 签名是否能被 dispatcher 调用（不强制，仅警告）。"""
    try:
        inspect.signature(handler)
    except (TypeError, ValueError):
        log.warning("handler %s 无法 introspection 签名，调用时再校验", name)
