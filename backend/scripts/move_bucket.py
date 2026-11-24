"""Explicit, resumable freeze/copy/verify/cutover. Retains the frozen source for recovery."""

import argparse
import hashlib
import json
import uuid
from pathlib import Path

from psycopg2 import sql
from psycopg2.extras import Json

from app.buckets.catalogue import provision_reference
from app.buckets.db import execute, one, rows, transaction
from app.services.allocation import Allocator, canonical
from seeding.load import put


def copy_row(connection, table, primary_key, row):
    """Copy only into a fenced staging bucket, including reverse migration.

    Replacing a retained shadow is explicit here; ordinary seed import remains
    insert-only. Source values include all changes made after the first cutover.
    """
    encoded = [Json(value) if isinstance(value, (dict, list)) else value for value in row.values()]
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}").format(
        sql.Identifier(table),
        sql.SQL(",").join(map(sql.Identifier, row)),
        sql.SQL(",").join(sql.Placeholder() for _ in row),
        sql.Identifier(primary_key),
        sql.SQL(",").join(
            sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(key), sql.Identifier(key))
            for key in row
            if key != primary_key
        ),
    )
    execute(connection, query, encoded)


def plan(bucket: int, target: str) -> dict:
    with transaction() as core:
        route = Allocator(core).resolve_bucket(bucket)
        if route.site_id == target or not one(
            core, "SELECT site_id FROM site_registry WHERE site_id=%s AND active", (target,)
        ):
            raise ValueError("Target must be a different, registered active site")
    with transaction(target) as destination:
        identity = one(destination, "SELECT * FROM bucket_installation")
        if identity["site_id"] != target:
            raise ValueError("Target identity mismatch")
    return dict(
        operation_id=str(uuid.uuid4()),
        bucket_id=bucket,
        source_site=route.site_id,
        target_site=target,
        old_epoch=route.ownership_epoch,
        mapping_revision=route.mapping_revision,
        target_instance=str(identity["instance_id"]),
    )


def snapshot(site_id, bucket):
    with transaction(site_id) as site:
        products = rows(site, "SELECT * FROM product WHERE bucket_id=%s ORDER BY product_id", (bucket,))
        ids = [p["product_id"] for p in products]
        images = rows(site, "SELECT * FROM product_image WHERE product_id=ANY(%s) ORDER BY image_id", (ids,))
        reservations = rows(
            site, "SELECT * FROM stock_reservation WHERE product_id=ANY(%s) ORDER BY reservation_id", (ids,)
        )
        operations = rows(
            site,
            "SELECT * FROM stock_operation WHERE (result->>'product_id')::integer=ANY(%s) ORDER BY operation_id",
            (ids,),
        )
    return dict(products=products, images=images, reservations=reservations, operations=operations)


def apply(document):
    bucket, source, target = document["bucket_id"], document["source_site"], document["target_site"]
    operation, epoch = document["operation_id"], document["old_epoch"]
    with transaction() as core:
        execute(core, "SELECT pg_advisory_xact_lock(%s,%s)", (736319, bucket))
        prior = one(core, "SELECT * FROM bucket_moves WHERE operation_id=%s FOR UPDATE", (operation,))
        if prior and prior["state"] == "complete":
            return {"state": "complete", "bucket_id": bucket, "target": target}
        assignment = one(core, "SELECT * FROM bucket_assignment WHERE bucket_id=%s FOR UPDATE", (bucket,))
        if assignment["owner_site_id"] == target and assignment["ownership_epoch"] == epoch + 1:
            cutover = True
        else:
            cutover = False
            if assignment["owner_site_id"] != source or assignment["ownership_epoch"] != epoch:
                raise ValueError("Mapping changed since move plan")
            if not prior:
                execute(
                    core,
                    "INSERT INTO bucket_moves(operation_id,bucket_id,source_site,target_site,old_epoch,state,details) "
                    "VALUES(%s,%s,%s,%s,%s,'freezing',%s)",
                    (operation, bucket, source, target, epoch, Json(document)),
                )
            execute(core, "UPDATE bucket_assignment SET state='moving' WHERE bucket_id=%s", (bucket,))
    with transaction(target) as destination:
        if (
            str(one(destination, "SELECT instance_id FROM bucket_installation")["instance_id"])
            != document["target_instance"]
        ):
            raise ValueError("Target database replaced since plan")
    if not cutover:
        # UPDATE lease takes an exclusive row lock, waiting for all FOR SHARE
        # guards held by earlier requests. New transactions see a frozen lease.
        with transaction(source) as origin:
            execute(
                origin,
                "UPDATE bucket_lease SET state='frozen' WHERE bucket_id=%s AND ownership_epoch=%s",
                (bucket, epoch),
            )
        data = snapshot(source, bucket)
        with transaction() as core, transaction(target, maintenance=True) as destination:
            execute(
                destination,
                "INSERT INTO bucket_lease VALUES(%s,%s,'staging') ON CONFLICT(bucket_id) DO UPDATE "
                "SET ownership_epoch=excluded.ownership_epoch,state='staging'",
                (bucket, epoch + 1),
            )
            for product in data["products"]:
                provision_reference(core, destination, product["seller_id"], product["category_id"])
                if product["approved_by"]:
                    provision_reference(core, destination, product["approved_by"], product["category_id"])
                put(destination, "seller_bucket", "seller_id", dict(seller_id=product["seller_id"], bucket_id=bucket))
                existing = one(
                    destination, "SELECT bucket_id FROM product WHERE product_id=%s", (product["product_id"],)
                )
                if existing and existing["bucket_id"] != bucket:
                    raise ValueError("Target ID collision outside the staging bucket")
                copy_row(destination, "product", "product_id", product)
            execute(
                destination,
                "DELETE FROM product_image WHERE product_id=ANY(%s) AND NOT image_id=ANY(%s)",
                (
                    [product["product_id"] for product in data["products"]],
                    [image["image_id"] for image in data["images"]],
                ),
            )
            for image in data["images"]:
                copy_row(destination, "product_image", "image_id", image)
            for reservation in data["reservations"]:
                copy_row(destination, "stock_reservation", "reservation_id", reservation)
            for item in data["operations"]:
                copy_row(destination, "stock_operation", "operation_id", item)
            # Image import triggers touch parents; restore the exact source
            # version/timestamps inside the same maintenance transaction.
            for product in data["products"]:
                values = {k: v for k, v in product.items() if k != "product_id"}
                query = sql.SQL("UPDATE product SET {} WHERE product_id=%s").format(
                    sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(k)) for k in values)
                )
                execute(destination, query, (*values.values(), product["product_id"]))
        copied = snapshot(target, bucket)
        if canonical(data) != canonical(copied):
            raise ValueError("Bucket verification failed; source stays frozen and mapping stays moving")
        digest = hashlib.sha256(canonical(data).encode()).hexdigest()
        with transaction() as core:
            execute(
                core,
                "UPDATE bucket_moves SET state='verified',details=details||%s WHERE operation_id=%s",
                (Json({"checksum": digest}), operation),
            )
            execute(
                core,
                "UPDATE bucket_assignment SET owner_site_id=%s,ownership_epoch=%s,mapping_revision=mapping_revision+1 "
                "WHERE bucket_id=%s AND owner_site_id=%s AND ownership_epoch=%s",
                (target, epoch + 1, bucket, source, epoch),
            )
    # A crash here leaves mapping 'moving': resume opens only the target lease.
    with transaction(target) as destination:
        execute(
            destination,
            "UPDATE bucket_lease SET state='active' WHERE bucket_id=%s AND ownership_epoch=%s",
            (bucket, epoch + 1),
        )
    with transaction() as core:
        execute(
            core,
            "UPDATE bucket_assignment SET state='active' WHERE bucket_id=%s AND owner_site_id=%s "
            "AND ownership_epoch=%s",
            (bucket, target, epoch + 1),
        )
        execute(core, "UPDATE bucket_moves SET state='complete',updated_at=now() WHERE operation_id=%s", (operation,))
    return dict(state="complete", bucket_id=bucket, source=source, target=target, retained_source=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--bucket", type=int, required=True)
    p.add_argument("--to-site", required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("apply")
    p.add_argument("--plan", type=Path, required=True)
    p = sub.add_parser("resume")
    p.add_argument("--operation-id", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        document = plan(args.bucket, args.to_site)
        with args.output.open("x") as stream:
            json.dump(document, stream, indent=2)
        print(json.dumps(document))
    else:
        if args.command == "apply":
            document = json.loads(args.plan.read_text())
        else:
            with transaction() as core:
                document = one(core, "SELECT details FROM bucket_moves WHERE operation_id=%s", (args.operation_id,))[
                    "details"
                ]
        print(json.dumps(apply(document)))


if __name__ == "__main__":
    main()
