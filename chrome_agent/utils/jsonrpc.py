"""JSON-RPC protocol implementation for Chrome Agent."""

import json
from typing import Any, Optional


class JsonRpcError(Exception):
    """JSON-RPC error."""

    def __init__(self, code: int, message: str, data: Optional[dict] = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"JSON-RPC Error {code}: {message}")


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SERVER_ERROR = -32000

# Custom business error codes
AMBIGUOUS_TARGET = -32021
STALE_ELEMENT_REFERENCE = -32022
VISION_SUGGESTED = -32023
PERMISSION_REQUIRED = -32024
RESTRICTED_PAGE = -32025


def create_request(method: str, params: dict, request_id: str) -> dict:
    """Create a JSON-RPC request."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }


def create_response(result: Any, request_id: str) -> dict:
    """Create a JSON-RPC response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def create_error_response(code: int, message: str, request_id: Optional[str] = None, data: Optional[dict] = None) -> dict:
    """Create a JSON-RPC error response."""
    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if data is not None:
        response["error"]["data"] = data
    return response


def parse_message(data: bytes) -> dict:
    """Parse a JSON-RPC message from bytes."""
    try:
        message = json.loads(data.decode("utf-8"))
        if not isinstance(message, dict):
            raise JsonRpcError(INVALID_REQUEST, "Request must be an object")
        return message
    except json.JSONDecodeError as e:
        raise JsonRpcError(PARSE_ERROR, f"Parse error: {e}")
