"""Benchmark three temporary collections in the app DB; cleanup only our UUID names."""

import argparse
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.services.mongo import get_database
from app.services.mongo_schema import INDEXES, validators


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    database = get_database()
    now = datetime(2026, 10, 29, tzinfo=UTC)
    count = 10000
    cases = {
        "product_details": ({"category_id": 3, "attributes.brand": "brand3"}, None),
        "reviews": ({"product_id": 42}, {"created_at": -1}),
        "order_snapshots": ({"buyer.id": 42}, {"order_date": -1}),
    }
    names = []
    summary = {"generated_per_collection": count, "cases": {}}
    try:
        for name, (query, sort) in cases.items():
            temporary = "day4_bench_" + name + "_" + uuid.uuid4().hex
            names.append(temporary)
            collection = database.create_collection(
                temporary, validator=validators()[name], validationLevel="strict", validationAction="error"
            )
            documents = []
            for i in range(1, count + 1):
                date = now - timedelta(seconds=i)
                base = {"_id": str(i), "schema_version": 1}
                if name == "product_details":
                    doc = dict(
                        product_id=i,
                        category_id=(i % 10) + 1,
                        attributes={"brand": "brand" + str((i % 10) + 1)},
                        updated_at=date,
                    )
                elif name == "reviews":
                    doc = dict(
                        review_id=i, product_id=(i % 1000) + 1, buyer_id=1, type="review", rating=4, created_at=date
                    )
                else:
                    doc = dict(
                        order_id=i,
                        buyer={"id": (i % 1000) + 1},
                        items=[{"product_id": 1, "quantity": 1, "price_at_purchase_vnd": 1, "subtotal_vnd": 1}],
                        total_amount_vnd=1,
                        shipping_fee_vnd=0,
                        discount_amount_vnd=0,
                        final_amount_vnd=1,
                        order_status=0,
                        order_date=date,
                        etl={"synced_at": date},
                    )
                documents.append({**base, **doc})
            collection.insert_many(documents)
            command = {"find": temporary, "filter": query, "limit": 20}
            if sort:
                command["sort"] = sort
            summary["cases"][name] = {}
            for phase in ("before", "after"):
                if phase == "after":
                    for keys, options in INDEXES[name]:
                        collection.create_index(keys, **options)
                result = database.command("explain", command, verbosity="executionStats")
                (args.output / f"{phase}_{name}.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
                stats = result["executionStats"]
                summary["cases"][name][phase] = {
                    key: stats[key]
                    for key in ("nReturned", "totalKeysExamined", "totalDocsExamined", "executionTimeMillis")
                }
        summary["version"] = database.command("buildInfo")["version"]
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary))
    finally:
        for name in names:
            database.drop_collection(name)


if __name__ == "__main__":
    main()
