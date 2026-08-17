"""Small, deterministic JSON Schema subset used by VoyageSkill contracts.

The supported keywords are intentionally limited to those present in the
versioned schemas under ``schemas/``. Unsupported keywords remain annotations;
adding a validation keyword to a contract therefore requires adding its
implementation and tests in the same change.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return type(left) is type(right) and left == right


def _matches_type(instance: Any, expected: str) -> bool:
    return {
        "object": lambda: isinstance(instance, dict),
        "array": lambda: isinstance(instance, list),
        "string": lambda: isinstance(instance, str),
        "integer": lambda: isinstance(instance, int) and not isinstance(instance, bool),
        "number": lambda: isinstance(instance, (int, float)) and not isinstance(instance, bool),
        "boolean": lambda: isinstance(instance, bool),
        "null": lambda: instance is None,
    }.get(expected, lambda: False)()


def _child_path(path: str, key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key, ensure_ascii=False)}]"


def _is_date_time(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate(instance: Any, schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []

    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(isinstance(item, str) and _matches_type(instance, item) for item in expected_types):
            return [f"{path}: type must be {' or '.join(str(item) for item in expected_types)}"]

    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append(f"{path}: const must be {schema['const']!r}")

    enum = schema.get("enum")
    if isinstance(enum, list) and not any(_json_equal(instance, item) for item in enum):
        errors.append(f"{path}: value is not in enum {enum!r}")

    if isinstance(instance, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(instance) < minimum:
            errors.append(f"{path}: minLength is {minimum}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, instance) is None:
            errors.append(f"{path}: value does not match pattern {pattern!r}")
        if schema.get("format") == "date-time" and not _is_date_time(instance):
            errors.append(f"{path}: value is not a valid date-time")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in instance:
                    errors.append(f"{_child_path(path, key)}: required property is missing")

        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, value in instance.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    errors.extend(_validate(value, child_schema, _child_path(path, key)))
                elif schema.get("additionalProperties") is False:
                    errors.append(f"{_child_path(path, key)}: additionalProperties is false")

    if isinstance(instance, list):
        minimum = schema.get("minItems")
        if isinstance(minimum, int) and len(instance) < minimum:
            errors.append(f"{path}: minItems is {minimum}")

        if schema.get("uniqueItems") is True:
            seen: set[str] = set()
            for item in instance:
                encoded = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if encoded in seen:
                    errors.append(f"{path}: uniqueItems contains duplicate {item!r}")
                    break
                seen.add(encoded)

        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                errors.extend(_validate(item, item_schema, f"{path}[{index}]"))

        contains = schema.get("contains")
        if isinstance(contains, dict) and not any(not _validate(item, contains, f"{path}[{index}]") for index, item in enumerate(instance)):
            expected = f" const {contains['const']!r}" if "const" in contains else ""
            errors.append(f"{path}: contains has no matching item{expected}")

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for subschema in all_of:
            if isinstance(subschema, dict):
                errors.extend(_validate(instance, subschema, path))

    return errors


def validate_instance(instance: Any, schema: dict[str, Any]) -> list[str]:
    """Return deterministic JSON-path errors for the supported schema subset."""

    if not isinstance(schema, dict):
        return ["$: schema must be an object"]
    return _validate(instance, schema, "$")
