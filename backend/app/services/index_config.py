"""Versioned index declarations. Parsing/validation never connects to a database."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictInt, model_validator

DATABASE_DIR = Path(os.getenv("DATABASE_SRC", Path(__file__).resolve().parents[3] / "database"))
CATALOG_PATH = DATABASE_DIR / "indexing/catalog.json"
Identifier = Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Predicate(Contract):
    all: list["Predicate"] | None = None
    any: list["Predicate"] | None = None
    column: Identifier | None = None
    op: Literal["eq", "ne", "lt", "le", "gt", "ge", "in", "has_key"] | None = None
    value: JsonValue = None

    @model_validator(mode="after")
    def check(self) -> Self:
        groups = [group for group in (self.all, self.any) if group is not None]
        if groups:
            if len(groups) != 1 or not groups[0] or self.column or self.op or self.value is not None:
                raise ValueError("Predicate must contain one nonempty all/any group or a column/op/value leaf")
        else:
            if not self.column or not self.op or self.value is None:
                raise ValueError("Predicate leaf requires column, op and non-null value")
            values = self.value if self.op == "in" else [self.value]
            if not isinstance(values, list) or not values:
                raise ValueError("IN requires a nonempty array")
            if any(type(v) not in (str, bool, int, float) for v in values):
                raise ValueError("Predicate values must be scalar literals")
            if self.op == "has_key" and not isinstance(self.value, str):
                raise ValueError("JSONB has_key requires a string")
        return self


class PGKey(Contract):
    column: Identifier
    expression: Literal["tsvector"] | None = None
    config: Literal["english", "simple"] | None = None
    order: Literal["ASC", "DESC"] | None = None
    nulls: Literal["FIRST", "LAST"] | None = None
    opclass: Literal["gin_trgm_ops"] | None = None


class PGIndex(Contract):
    name: Identifier
    schema_name: Literal["public"] = Field(default="public", alias="schema")
    table: Identifier
    method: Literal["btree", "gin"] = "btree"
    unique: StrictBool = False
    keys: list[PGKey] = Field(min_length=1, max_length=32)
    predicate: Predicate | None = None
    managed_by: Literal["application", "constraint"] = "application"

    @model_validator(mode="after")
    def check(self) -> Self:
        if len({k.column for k in self.keys}) != len(self.keys):
            raise ValueError("Duplicate PostgreSQL index key")
        for key in self.keys:
            if self.method == "gin" and (key.order or key.nulls or self.unique):
                raise ValueError("GIN does not accept order, null ordering or unique")
            if self.method == "btree" and (key.opclass or key.expression):
                raise ValueError("This contract supports expressions/opclass only for GIN")
            if (key.expression is None) != (key.config is None):
                raise ValueError("tsvector expression requires config")
            if key.expression and key.opclass:
                raise ValueError("tsvector cannot use gin_trgm_ops")
        if self.managed_by == "constraint" and (not self.unique or self.predicate or self.method != "btree"):
            raise ValueError("Constraint indexes must be unique B-tree without predicate")
        return self


class MongoOptions(Contract):
    name: Annotated[str, Field(min_length=1, max_length=127, pattern=r"^[A-Za-z0-9_.$-]+$")]
    unique: StrictBool = False
    sparse: StrictBool = False
    hidden: StrictBool = False
    partialFilterExpression: dict[str, JsonValue] | None = None
    expireAfterSeconds: Annotated[StrictInt, Field(ge=0, le=2147483647)] | None = None


def check_partial(value):
    """Deliberately small allowlist: no arbitrary server-side JS/query operators."""
    if not isinstance(value, dict) or not value:
        raise ValueError("Partial filter must be a nonempty object")
    for field, condition in value.items():
        if field in ("$and", "$or"):
            if not isinstance(condition, list) or not condition:
                raise ValueError("Logical partial filter requires a nonempty array")
            for item in condition:
                check_partial(item)
        elif not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", field):
            raise ValueError("Invalid partial filter field")
        elif isinstance(condition, dict):
            if not condition:
                raise ValueError("Partial operator condition cannot be empty")
            for op, operand in condition.items():
                if op not in ("$eq", "$gt", "$gte", "$lt", "$lte", "$exists", "$in", "$type"):
                    raise ValueError(f"Unsupported partial operator: {op}")
                if op == "$exists" and operand is not True:
                    raise ValueError("Partial $exists supports true only")
                if op == "$type" and operand not in (
                    "double",
                    "string",
                    "object",
                    "array",
                    "binData",
                    "undefined",
                    "objectId",
                    "bool",
                    "date",
                    "null",
                    "regex",
                    "dbPointer",
                    "javascript",
                    "symbol",
                    "javascriptWithScope",
                    "int",
                    "timestamp",
                    "long",
                    "decimal",
                    "minKey",
                    "maxKey",
                    "number",
                ):
                    raise ValueError("Partial $type requires a supported BSON type alias")
                if op == "$in":
                    if (
                        not isinstance(operand, list)
                        or not operand
                        or any(isinstance(v, (list, dict)) for v in operand)
                    ):
                        raise ValueError("Partial $in requires scalar array")
                elif isinstance(operand, (dict, list)):
                    raise ValueError("Partial operator requires scalar value")
        elif isinstance(condition, list):
            raise ValueError("Partial equality requires scalar value")


class MongoIndex(Contract):
    collection: Identifier
    keys: list[list[str | StrictInt]] = Field(min_length=1, max_length=32)
    options: MongoOptions

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.collection == "_index_catalog_state":
            raise ValueError("The applied-snapshot metadata collection is reserved")
        fields = []
        for pair in self.keys:
            if len(pair) != 2:
                raise ValueError("Mongo key must be [field, direction]")
            field, direction = pair
            if not isinstance(field, str) or not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*(?:\.\$\*\*)?|\$\*\*", field
            ):
                raise ValueError("Invalid Mongo index field")
            if type(direction) is bool or direction not in (1, -1, "text"):
                raise ValueError("Supported Mongo directions: 1, -1, text")
            fields.append(field)
        if len(set(fields)) != len(fields) or self.options.name == "_id_" or "_id" in fields:
            raise ValueError("Duplicate/reserved Mongo key or index name")
        text = any(k[1] == "text" for k in self.keys)
        wildcard = any("$**" in f for f in fields)
        if wildcard and (len(fields) != 1 or self.keys[0][1] != 1 or self.options.unique or self.options.sparse):
            raise ValueError("Wildcard requires one ascending, nonunique key and no explicit sparse")
        if text and (wildcard or self.options.unique or self.options.sparse):
            raise ValueError("Text cannot combine with wildcard, unique or explicit sparse")
        if self.options.partialFilterExpression is not None:
            check_partial(self.options.partialFilterExpression)
            if self.options.sparse:
                raise ValueError("partialFilterExpression and sparse are mutually exclusive")
        if self.options.expireAfterSeconds is not None and (len(fields) != 1 or text or wildcard):
            raise ValueError("TTL requires a single numeric-direction field")
        return self

    def driver_spec(self):
        options = self.options.model_dump(exclude_none=True)
        # Preserve the old driver interface and implicit defaults.
        return [tuple(k) for k in self.keys], {k: v for k, v in options.items() if v is not False}


class IndexCatalog(Contract):
    schema_version: Literal[1]
    revision: Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")]
    postgresql: list[PGIndex]
    mongodb: list[MongoIndex]

    @model_validator(mode="after")
    def check(self) -> Self:
        for identities in (
            [(i.schema_name, i.name) for i in self.postgresql],
            [(i.collection, i.options.name) for i in self.mongodb],
        ):
            if len(set(identities)) != len(identities):
                raise ValueError("Duplicate index identity")
        definitions = [
            (i.collection, json.dumps(i.keys), json.dumps(i.options.model_dump(exclude={"name"}), sort_keys=True))
            for i in self.mongodb
        ]
        if len(set(definitions)) != len(definitions):
            raise ValueError("Duplicate Mongo definitions under different names")
        for collection in {i.collection for i in self.mongodb}:
            if sum(any(k[1] == "text" for k in i.keys) for i in self.mongodb if i.collection == collection) > 1:
                raise ValueError("Only one text index per collection")
        return self

    def payload(self):
        return self.model_dump(by_alias=True, exclude_none=True)

    def digest(self):
        return hashlib.sha256(
            json.dumps(self.payload(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON property: {key}")
        result[key] = value
    return result


def load_catalog(path: Path | str = CATALOG_PATH) -> IndexCatalog:
    payload = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=no_duplicates,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant: {value}")),
    )
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int:
        raise ValueError("schema_version must be integer 1")
    return IndexCatalog.model_validate(payload)


def mongo_indexes(catalog=None):
    result = {}
    for index in (catalog or load_catalog()).mongodb:
        result.setdefault(index.collection, []).append(index.driver_spec())
    return result
