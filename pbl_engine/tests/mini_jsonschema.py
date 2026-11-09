"""Tiny validator for the JSON Schema subset used in schemas/ (no network needed).
For CI, prefer the `jsonschema` package (Draft 2020-12); this keeps the repo's
tests runnable offline."""
import re


def _resolve(ref, root):
    node = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def _type_ok(v, t):
    if t == "object": return isinstance(v, dict)
    if t == "array": return isinstance(v, list)
    if t == "string": return isinstance(v, str)
    if t == "boolean": return isinstance(v, bool)
    if t == "null": return v is None
    if t == "integer": return isinstance(v, int) and not isinstance(v, bool)
    if t == "number": return isinstance(v, (int, float)) and not isinstance(v, bool)
    return False


def validate(v, schema, root=None):
    """Return a list of error strings (empty list means valid)."""
    root = root or schema
    errs = []
    if "$ref" in schema:
        return validate(v, _resolve(schema["$ref"], root), root)
    if "type" in schema:
        ts = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(v, t) for t in ts):
            return [f"type {ts} expected"]
    if "const" in schema and v != schema["const"]: errs.append("const mismatch")
    if "enum" in schema and v not in schema["enum"]: errs.append("not in enum")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in schema and v < schema["minimum"]: errs.append("below minimum")
        if "maximum" in schema and v > schema["maximum"]: errs.append("above maximum")
        if "exclusiveMinimum" in schema and v <= schema["exclusiveMinimum"]: errs.append("not > exclusiveMinimum")
    if isinstance(v, str):
        if "minLength" in schema and len(v) < schema["minLength"]: errs.append("too short")
        if "maxLength" in schema and len(v) > schema["maxLength"]: errs.append("too long")
        if "pattern" in schema and not re.search(schema["pattern"], v): errs.append("pattern")
    if isinstance(v, list):
        if "maxItems" in schema and len(v) > schema["maxItems"]: errs.append("too many items")
        if "items" in schema:
            for i, x in enumerate(v):
                errs += [f"[{i}] {e}" for e in validate(x, schema["items"], root)]
    if isinstance(v, dict):
        for k in schema.get("required", []):
            if k not in v: errs.append(f"missing {k}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errs += [f"unexpected {k}" for k in v if k not in props]
        elif isinstance(schema.get("additionalProperties"), dict):
            for k in v:
                if k not in props:
                    errs += [f"{k}: {e}" for e in validate(v[k], schema["additionalProperties"], root)]
        if "maxProperties" in schema and len(v) > schema["maxProperties"]: errs.append("too many properties")
        for k, sub in props.items():
            if k in v: errs += [f"{k}: {e}" for e in validate(v[k], sub, root)]
    if "oneOf" in schema:
        ok = [not validate(v, s, root) for s in schema["oneOf"]]
        if sum(ok) != 1: errs.append(f"oneOf matched {sum(ok)} branches")
    return errs
