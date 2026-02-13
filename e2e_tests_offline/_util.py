from __future__ import annotations

import json
from typing import Any


def find_function_call_output_item(items: list[object], *, call_id: str) -> dict[str, Any]:
    for x in items:
        if not isinstance(x, dict):
            continue
        if x.get("type") != "function_call_output":
            continue
        if x.get("call_id") != call_id:
            continue
        return x
    raise AssertionError(f"expected a function_call_output item for call_id={call_id!r}")


def parse_function_call_output_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("output")
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        if not payload.strip():
            return {}
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError as e:
            raise AssertionError(f"expected JSON string tool output, got: {payload!r}") from e
        if not isinstance(obj, dict):
            raise AssertionError(f"expected JSON object tool output, got: {type(obj).__name__}")
        return obj
    raise AssertionError(f"expected function_call_output.output to be dict or JSON string, got: {type(payload).__name__}")


def get_function_call_output_payload(items: list[object], *, call_id: str) -> dict[str, Any]:
    item = find_function_call_output_item(items, call_id=call_id)
    return parse_function_call_output_payload(item)

