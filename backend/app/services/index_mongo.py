"""MongoDB index reconciliation; additive apply, no implicit drop/rebuild/collMod."""

from app.services.index_config import IndexCatalog

STATE_COLLECTION = "_index_catalog_state"


def document_field(schema, field):
    """Check dotted paths against the existing contracts; dynamic dicts stay open."""
    definitions = schema.get("$defs", {})

    def walk(node, parts):
        if "$ref" in node:
            return walk(definitions[node["$ref"].split("/")[-1]], parts)
        if "anyOf" in node:
            for branch in node["anyOf"]:
                found = walk(branch, parts)
                if found is not None:
                    return found
            return None
        if not parts:
            return node
        if node.get("type") == "array":
            return walk(node["items"], parts)
        if parts == ["$**"] and node.get("type") == "object":
            return node
        if parts[0] in node.get("properties", {}):
            return walk(node["properties"][parts[0]], parts[1:])
        if node.get("additionalProperties"):
            return {}  # Mongo-owned semi-structured dictionaries permit dynamic keys.
        return None

    return walk(schema, field.split("."))


def contract_schemas(collections):
    from app.schemas.documents import DOCUMENT_MODELS

    models = dict(DOCUMENT_MODELS)
    if "etl_errors" in collections:
        from app.schemas.etl import ETLError

        models["etl_errors"] = ETLError
    return {name: model.model_json_schema(by_alias=True) for name, model in models.items() if name in collections}


def field_conflicts(spec, schema):
    reasons = []
    for field, _ in spec.keys:
        node = document_field(schema, field)
        if node is None:
            reasons.append("unknown_document_field:" + field)
        elif spec.options.expireAfterSeconds is not None:
            variants = node.get("anyOf", [node])
            if not any(v.get("format") == "date-time" for v in variants):
                reasons.append("ttl_requires_date_contract:" + field)

    def check_partial_fields(condition):
        for field, value in condition.items():
            if field in ("$and", "$or"):
                for item in value:
                    check_partial_fields(item)
            elif document_field(schema, field) is None:
                reasons.append("unknown_partial_field:" + field)

    if spec.options.partialFilterExpression:
        check_partial_fields(spec.options.partialFilterExpression)
    return reasons


def signature(keys, options):
    keys = [tuple(pair) for pair in keys]
    weights = options.get("weights")
    if weights is None and any(direction == "text" for _, direction in keys):
        weights = {field: 1 for field, direction in keys if direction == "text"}
        position = next(i for i, pair in enumerate(keys) if pair[1] == "text")
        keys = [pair for pair in keys if pair[1] != "text"]
        keys[position:position] = [("_fts", "text"), ("_ftsx", 1)]
    result = {
        "keys": keys,
        "unique": options.get("unique", False),
        "sparse": options.get("sparse", False),
        "hidden": options.get("hidden", False),
        "partial": options.get("partialFilterExpression"),
        "ttl": options.get("expireAfterSeconds"),
        "collation": options.get("collation"),
        "wildcardProjection": options.get("wildcardProjection"),
    }
    if weights is not None:
        result.update(
            weights=weights,
            default_language=options.get("default_language", "english"),
            language_override=options.get("language_override", "language"),
            textIndexVersion=options.get("textIndexVersion", 3),
        )
    return result


def plan_mongo(database, catalog):
    existing_collections = set(database.list_collection_names())
    schemas = contract_schemas({s.collection for s in catalog.mongodb})
    cache = {}
    entries = []
    identities = {(s.collection, s.options.name) for s in catalog.mongodb}
    for spec in catalog.mongodb:
        if spec.collection not in cache:
            cache[spec.collection] = (
                database[spec.collection].index_information() if spec.collection in existing_collections else {}
            )
        existing = cache[spec.collection]
        keys, options = spec.driver_spec()
        desired = signature(keys, options)
        actual = existing.get(spec.options.name)
        reasons = field_conflicts(spec, schemas[spec.collection]) if spec.collection in schemas else []
        if spec.collection not in schemas and spec.collection not in existing_collections:
            reasons.append("unknown_collection_without_document_contract")
        if actual:
            observed = signature(actual["key"], actual)
            reasons += [key for key in desired if desired[key] != observed[key]]
        else:
            for name, info in existing.items():
                if signature(info["key"], info) == desired:
                    reasons.append("equivalent_definition_with_other_name:" + name)
        entries.append(
            {
                "collection": spec.collection,
                "name": spec.options.name,
                "status": "conflict" if reasons else "matched" if actual else "missing",
                "reasons": reasons,
                "expected": desired,
                "actual": signature(actual["key"], actual) if actual else None,
            }
        )
    unmanaged = []
    for collection in sorted(existing_collections - {STATE_COLLECTION}):
        info = cache.get(collection)
        if info is None:
            info = database[collection].index_information()
        for name in info:
            if (collection, name) not in identities:
                unmanaged.append(
                    {"collection": collection, "name": name, "managed_by": "database" if name == "_id_" else "external"}
                )
    return {"indexes": entries, "unmanaged": unmanaged}


def apply_mongo(database, catalog, *, record=True):
    before = plan_mongo(database, catalog)
    if any(i["status"] == "conflict" for i in before["indexes"]):
        raise ValueError("Mongo index conflict; review plan before changing or rebuilding an index")
    missing = {(i["collection"], i["name"]) for i in before["indexes"] if i["status"] == "missing"}
    created = []
    for spec in catalog.mongodb:
        if (spec.collection, spec.options.name) in missing:
            keys, options = spec.driver_spec()
            database[spec.collection].create_index(keys, **options)
            created.append({"collection": spec.collection, "name": spec.options.name})
    after = plan_mongo(database, catalog)
    if any(i["status"] != "matched" for i in after["indexes"]):
        raise ValueError("Mongo index verification failed after apply; revision was not recorded")
    if record:
        # This is the Mongo applied snapshot, independent of PostgreSQL success/failure.
        snapshot = IndexCatalog(schema_version=1, revision=catalog.revision, postgresql=[], mongodb=catalog.mongodb)
        database[STATE_COLLECTION].replace_one(
            {"_id": "mongodb"},
            {
                "_id": "mongodb",
                "catalog": snapshot.payload(),
                "sha256": snapshot.digest(),
            },
            upsert=True,
        )
    return {"created": created, **after}


def applied_mongo_catalog(database):
    state = database[STATE_COLLECTION].find_one({"_id": "mongodb"})
    if not state:
        raise ValueError("Mongo applied snapshot missing; run init_mongo or apply_indexes --engine mongodb")
    catalog = IndexCatalog.model_validate(state["catalog"])
    if catalog.digest() != state["sha256"]:
        raise ValueError("Mongo applied snapshot checksum mismatch")
    return catalog
