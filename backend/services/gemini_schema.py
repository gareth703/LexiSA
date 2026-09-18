"""Convert Pydantic JSON Schemas into the subset google-generativeai accepts.

The SDK's proto ``Schema`` type rejects standard JSON Schema keywords such as
``title``, ``default`` and ``$ref``/``$defs`` (raising ``ValueError: Unknown
field for Schema``), so refs must be inlined and those keys stripped before a
Pydantic model's schema can be used as ``generation_config['response_schema']``.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

_DROP_KEYS = {"title", "default", "$defs"}


def _resolve(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            ref_name = node["$ref"].rsplit("/", 1)[-1]
            return _resolve(defs[ref_name], defs)
        resolved = {key: _resolve(value, defs) for key, value in node.items() if key not in _DROP_KEYS}
        if resolved.get("additionalProperties") is True:
            resolved.pop("additionalProperties")
        return resolved
    if isinstance(node, list):
        return [_resolve(item, defs) for item in node]
    return node


def to_gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    return _resolve(schema, schema.get("$defs", {}))
