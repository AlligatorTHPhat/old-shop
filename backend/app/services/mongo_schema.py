"""Derive BSON validators from Pydantic contracts; no duplicated field lists."""

from copy import deepcopy

from app.schemas.documents import DOCUMENT_MODELS
from app.services.index_config import mongo_indexes


def bson_schema(model) -> dict:
    schema = model.model_json_schema(by_alias=True)
    definitions = schema.get("$defs", {})
    types = {
        "object": "object",
        "array": "array",
        "string": "string",
        "boolean": "bool",
        "integer": ["int", "long"],
        "number": ["double", "int", "long"],
        "null": "null",
    }

    def convert(node):
        if "$ref" in node:
            return convert(definitions[node["$ref"].split("/")[-1]])
        result = {}
        for key, value in node.items():
            if key == "type":
                result["bsonType"] = types[value]
            elif key == "format" and value == "date-time":
                result["bsonType"] = "date"
            elif key == "properties":
                result[key] = {
                    name: ({"bsonType": "object"} if name == "attributes" else convert(prop))
                    for name, prop in value.items()
                }
            elif key in ("anyOf", "oneOf", "allOf"):
                result[key] = [convert(item) for item in value]
            elif key == "items":
                result[key] = convert(value)
            elif key == "const":
                result["enum"] = [value]
            elif key in ("exclusiveMinimum", "exclusiveMaximum"):
                result["minimum" if key == "exclusiveMinimum" else "maximum"] = value
                result[key] = True
            elif key in (
                "required",
                "enum",
                "minimum",
                "maximum",
                "minLength",
                "maxLength",
                "minItems",
                "maxItems",
                "pattern",
                "additionalProperties",
            ):
                result[key] = convert(value) if isinstance(value, dict) else deepcopy(value)
        if node.get("format") == "date-time":
            result["bsonType"] = "date"
        return result

    return convert(schema)


def validators() -> dict:
    result = {name: {"$jsonSchema": bson_schema(model)} for name, model in DOCUMENT_MODELS.items()}
    result["reviews"]["$jsonSchema"]["oneOf"] = [
        {"properties": {"type": {"enum": ["report"]}, "rating": {"enum": [0]}}},
        {"properties": {"type": {"enum": ["review"]}, "rating": {"minimum": 1}}},
    ]
    return result


# Compatibility adapter for benchmark/archive imports; JSON is the definition source.
INDEXES = mongo_indexes()
