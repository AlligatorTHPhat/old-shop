"""Evaluate M01/M02 on strict temporary collections; no application data is changed."""

import argparse
import hashlib
import json
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.services.mongo import get_database
from app.services.mongo_schema import INDEXES, validators

CASES = {
    "image_missing": (
        {"deleted": False, "images.key": "products/index_missing.jpg"},
        1,
    ),
    "image_unique": ({"deleted": False, "images.key": "products/index_49999.jpg"}, 1),
    "image_shared": ({"deleted": False, "images.key": "products/index_shared.jpg"}, 1),
    "brand_ram": (
        {"deleted": False, "attributes.brand": "brand7", "attributes.ram_gb": 16},
        5001,
    ),
}


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def measure(database, collection, destination, repeats):
    result = {}
    for name, (query, limit) in CASES.items():
        plans = []
        signatures = []
        for _ in range(repeats + 1):
            rows = list(
                collection.find(query, {"_id": 0, "product_id": 1}).limit(limit)
            )
            # Reference lookup is EXISTS; ordering of candidate IDs is not part of the API.
            signature = (
                bool(rows) if limit == 1 else sorted(r["product_id"] for r in rows)
            )
            signatures.append(
                hashlib.sha256(json.dumps(signature).encode()).hexdigest()
            )
            plans.append(
                database.command(
                    "explain",
                    {
                        "find": collection.name,
                        "filter": query,
                        "projection": {"_id": 0, "product_id": 1},
                        "limit": limit,
                    },
                    verbosity="executionStats",
                )
            )
        assert len(set(signatures)) == 1
        plans = plans[1:]
        dump(
            destination / f"{name}.json",
            {"query": query, "plans": plans, "result_sha256": signatures[0]},
        )
        result[name] = {
            key: statistics.median(p["executionStats"][key] for p in plans)
            for key in (
                "nReturned",
                "totalKeysExamined",
                "totalDocsExamined",
                "executionTimeMillis",
            )
        }
        result[name]["result_sha256"] = signatures[0]
    return result


def writes(collection, destination):
    result = {}
    for name, field in (
        ("attribute_update", "attributes.ram_gb"),
        ("image_update", "images.0.key"),
    ):
        samples = []
        for i in range(101):
            value = (
                (8 if i % 2 else 16)
                if name == "attribute_update"
                else f"products/index_write_{i % 2}.jpg"
            )
            start = time.perf_counter()
            collection.update_one({"product_id": 1}, {"$set": {field: value}})
            if i:
                samples.append((time.perf_counter() - start) * 1000)
        ordered = sorted(samples)
        result[name] = {
            "median_ms": statistics.median(samples),
            "p95_ms": ordered[94],
            "samples": samples,
            "measurement": "client wall-clock, same connection/one writer",
        }
    dump(destination / "writes.json", result)
    return {
        k: {a: b for a, b in v.items() if a != "samples"} for k, v in result.items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if not settings.MONGO_DB.startswith("indexing_v2_"):
        raise SystemExit("Refusing benchmark outside an indexing_v2_* database")
    args.output.mkdir(parents=True, exist_ok=False)
    database = get_database()
    name = "indexing_v2_products_" + uuid.uuid4().hex
    collection = database.create_collection(
        name,
        validator=validators()["product_details"],
        validationLevel="strict",
        validationAction="error",
    )
    try:
        docs = []
        for g in range(1, 50001):
            docs.append(
                {
                    "_id": f"index:{g}",
                    "product_id": g,
                    "category_id": 1 + g % 8,
                    "description": "Synthetic benchmark product",
                    "deleted": g % 29 == 0,
                    "attributes": {
                        "brand": "brand" + str(g % 50),
                        "ram_gb": 8 + 8 * (g % 3),
                    },
                    "tags": [],
                    "updated_at": datetime(2026, 11, 1, tzinfo=UTC),
                    "images": [
                        {
                            "bucket": "product-images",
                            "key": "products/index_shared.jpg"
                            if g % 10 == 0
                            else f"products/index_{g}.jpg",
                            "is_primary": True,
                            "display_order": 1,
                        }
                    ],
                }
            )
        collection.insert_many(docs)
        for keys, options in INDEXES["product_details"]:
            if options.get("name") in {
                "idx_live_product_image_key",
                "idx_live_product_brand_ram",
            }:
                continue
            collection.create_index(keys, **options)
        baseline = args.output / "before"
        baseline.mkdir()
        summary = {
            "version": database.command("buildInfo")["version"],
            "count": collection.count_documents({}),
            "collection": name,
            "baseline_indexes": collection.index_information(),
            "before": measure(database, collection, baseline, args.repeats),
            "before_writes": writes(collection, baseline),
            "candidates": {},
        }
        for code, keys, options in (
            (
                "M01",
                [("images.key", 1)],
                {
                    "name": "idx_live_product_image_key",
                    "partialFilterExpression": {"deleted": False},
                },
            ),
            (
                "M02",
                [("attributes.brand", 1), ("attributes.ram_gb", 1), ("product_id", 1)],
                {
                    "name": "idx_live_product_brand_ram",
                    "partialFilterExpression": {"deleted": False},
                },
            ),
        ):
            destination = args.output / code
            destination.mkdir()
            before_bytes = database.command("collStats", name)["totalIndexSize"]
            start = time.perf_counter()
            index = collection.create_index(keys, **options)
            seconds = time.perf_counter() - start
            try:
                result = measure(database, collection, destination, args.repeats)
                for case in CASES:
                    assert (
                        result[case]["result_sha256"]
                        == summary["before"][case]["result_sha256"]
                    ), (code, case)
                summary["candidates"][code] = {
                    "queries": result,
                    "writes": writes(collection, destination),
                    "build_seconds": seconds,
                    "added_index_bytes": database.command("collStats", name)[
                        "totalIndexSize"
                    ]
                    - before_bytes,
                    "definition": {"keys": keys, **options},
                }
                dump(args.output / "summary.json", summary)
                print(json.dumps({"candidate": code, "queries": result}), flush=True)
            finally:
                collection.drop_index(index)
        dump(args.output / "summary.json", summary)
    finally:
        database.drop_collection(name)


if __name__ == "__main__":
    main()
