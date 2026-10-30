"""Derive BSON validators from Pydantic contracts; no duplicated field lists."""

from copy import deepcopy

from app.schemas.documents import DOCUMENT_MODELS


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


INDEXES = {
    "product_details": [
        ([("product_id", 1)], {"unique": True}),
        ([("category_id", 1), ("attributes.brand", 1)], {}),
        ([("attributes.$**", 1)], {"name": "idx_product_attributes"}),
        ([("description", "text"), ("tags", "text")], {}),
    ],
    "reviews": [
        ([("review_id", 1)], {"unique": True}),
        ([("product_id", 1), ("created_at", -1)], {}),
        ([("type", 1), ("status", 1)], {"partialFilterExpression": {"type": "report", "status": "pending"}}),
    ],
    "order_snapshots": [
        ([("order_id", 1)], {"unique": True}),
        ([("buyer.id", 1), ("order_date", -1)], {}),
        ([("order_status", 1), ("order_date", -1)], {}),
    ],
    "system_logs": [
        ([("log_id", 1), ("created_at", 1)], {"unique": True}),
        ([("created_at", 1)], {"expireAfterSeconds": 90 * 86400}),
        ([("action", 1), ("actor_id", 1), ("created_at", -1)], {}),
    ],
    "violation_logs": [([("log_id", 1)], {"unique": True}), ([("target_user_id", 1), ("created_at", -1)], {})],
    "contact_messages": [([("feedback_id", 1)], {"unique": True}), ([("status", 1), ("created_at", -1)], {})],
}
