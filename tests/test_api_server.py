"""api.server：JSON-RPC 2.0 dispatch + 错误码 + handler 注册。"""

from __future__ import annotations

import json

import pytest

from civ_core.api.server import (
    ERR_INVALID_REQUEST,
    ERR_METHOD_NOT_FOUND,
    ERR_PARSE_ERROR,
    Dispatcher,
)


def _make_dispatcher() -> Dispatcher:
    d = Dispatcher()
    d.register("ping", lambda: "pong")
    d.register("echo", lambda message: {"echo": message})
    d.register("add", lambda a, b: a + b)

    def _boom() -> None:
        raise RuntimeError("kaboom")

    d.register("boom", _boom)
    return d


def test_ping_roundtrip() -> None:
    d = _make_dispatcher()
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    resp = json.loads(d.handle_raw(req))
    assert resp == {"jsonrpc": "2.0", "id": 1, "result": "pong"}


def test_named_params() -> None:
    d = _make_dispatcher()
    req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "echo", "params": {"message": "hi"}})
    resp = json.loads(d.handle_raw(req))
    assert resp["result"] == {"echo": "hi"}


def test_positional_params() -> None:
    d = _make_dispatcher()
    req = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "add", "params": [2, 3]})
    resp = json.loads(d.handle_raw(req))
    assert resp["result"] == 5


def test_method_not_found() -> None:
    d = _make_dispatcher()
    req = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "nope"})
    resp = json.loads(d.handle_raw(req))
    assert resp["error"]["code"] == ERR_METHOD_NOT_FOUND
    assert "nope" in resp["error"]["message"]


def test_parse_error() -> None:
    d = _make_dispatcher()
    resp = json.loads(d.handle_raw("{not json"))
    assert resp["error"]["code"] == ERR_PARSE_ERROR
    assert resp["id"] is None


def test_invalid_request_no_method() -> None:
    d = _make_dispatcher()
    req = json.dumps({"jsonrpc": "2.0", "id": 5})
    resp = json.loads(d.handle_raw(req))
    assert resp["error"]["code"] == ERR_INVALID_REQUEST


def test_handler_exception_becomes_error_response() -> None:
    """handler 内部抛异常应被捕获，封装成 JSON-RPC error；不向上抛。"""
    d = _make_dispatcher()
    req = json.dumps({"jsonrpc": "2.0", "id": 6, "method": "boom"})
    resp = json.loads(d.handle_raw(req))
    assert "error" in resp
    assert "kaboom" in resp["error"]["message"]


def test_register_duplicate_raises() -> None:
    """同名方法注册两次应报错（防止 handler 模块互覆盖）。"""
    d = Dispatcher()
    d.register("dup", lambda: 1)
    with pytest.raises(ValueError):
        d.register("dup", lambda: 2)


def test_notification_no_response() -> None:
    """JSON-RPC notification（无 id）→ handle 仍执行但 handle_raw 返回空串。"""
    d = _make_dispatcher()
    req = json.dumps({"jsonrpc": "2.0", "method": "ping"})
    resp = d.handle_raw(req)
    assert resp == ""
