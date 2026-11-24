"""Rebuildable graph projections. PostgreSQL/Mongo remain authoritative."""

import hashlib
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings


def folded(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold().replace("đ", "d").replace("Đ", "D"))
    return "".join(char for char in value if unicodedata.category(char) != "Mn")


def tokens(value: str) -> list[str]:
    return re.findall(r"\w+", folded(value), flags=re.UNICODE)


def prepared_query(value: str) -> str:
    words = tokens(value)
    if not words or len(words) > 32:
        raise HTTPException(422, "Nhập từ khóa mô tả ảnh.")
    return " AND ".join(f'"{word}"' for word in words)


def key(kind: str, identifier: int) -> str:
    return f"{namespace()}:{kind}:{identifier}"


def namespace() -> str:
    return f"{settings.BUCKET_DATASET}:g{settings.GRAPH_GENERATION}"


def ready() -> bool:
    from app.buckets.db import one, transaction

    with transaction() as core:
        state = one(core, "SELECT * FROM graph_projection_state")
    return bool(state and state["state"] == "active" and state["generation"] == settings.GRAPH_GENERATION)


@lru_cache(maxsize=1)
def driver():
    from neo4j import GraphDatabase

    if not settings.GRAPH_ENABLED or not settings.NEO4J_URI:
        raise HTTPException(503, "Tìm kiếm đồ thị chưa được cấu hình.")
    return GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        connection_timeout=5,
        max_transaction_retry_time=8,
        max_connection_pool_size=8,
    )


def write(function, *args):
    from neo4j import unit_of_work

    with driver().session(database=settings.NEO4J_DATABASE) as session:
        return session.execute_write(unit_of_work(timeout=float(settings.GRAPH_TIMEOUT_SECONDS))(function), *args)


def initialize():
    from app.buckets.db import one, transaction

    with transaction() as core:
        instance = str(one(core, "SELECT instance_id FROM bucket_installation")["instance_id"])
        generation = one(core, "SELECT generation FROM graph_projection_state")["generation"]
        if generation != settings.GRAPH_GENERATION:
            raise ValueError("Graph generation differs; restart this consumer with the active generation")
    root = Path(os.getenv("DATABASE_SRC", Path(__file__).resolve().parents[3] / "database"))
    with driver().session(database=settings.NEO4J_DATABASE) as session:
        session.run(
            "CYPHER 5 CREATE CONSTRAINT graph_schema_migration_key IF NOT EXISTS "
            "FOR(n:GraphSchemaMigration) REQUIRE n.key IS UNIQUE"
        ).consume()
        session.run(
            "CYPHER 5 CREATE CONSTRAINT graph_installation_key IF NOT EXISTS "
            "FOR (n:GraphInstallation) REQUIRE n.key IS UNIQUE"
        ).consume()
        existing = session.run(
            "CYPHER 5 MERGE(i:GraphInstallation {key:$key}) ON CREATE SET i.core_instance=$instance "
            "RETURN i.core_instance AS instance",
            key=settings.BUCKET_DATASET,
            instance=instance,
        ).single()
        if existing["instance"] != instance:
            raise ValueError("Graph namespace belongs to a different core installation")
        for path in sorted((root / "neo4j").glob("[0-9][0-9][0-9]_*.cypher")):
            text = path.read_text()
            digest = hashlib.sha256(text.encode()).hexdigest()
            identity = f"{settings.BUCKET_DATASET}:{path.name}"
            old = session.run(
                "CYPHER 5 MATCH(m:GraphSchemaMigration {key:$key}) RETURN m.digest AS digest", key=identity
            ).single()
            if old:
                if old["digest"] != digest:
                    raise ValueError("Graph migration checksum changed")
                continue
            for statement in text.split(";"):
                if statement.strip():
                    session.run(statement).consume()
            session.run(
                "CYPHER 5 MERGE(m:GraphSchemaMigration {key:$key}) SET m.digest=$digest", key=identity, digest=digest
            ).consume()
        session.run("CALL db.awaitIndexes(120)").consume()


def catalogue(product: dict):
    def apply(tx):
        pid = product["product_id"]
        node = tx.run(
            "CYPHER 5 MERGE(p:Product {key:$key}) SET p._lock=coalesce(p._lock,0)+1 "
            "RETURN coalesce(p.catalogue_revision,0) AS revision",
            key=key("product", pid),
        ).single()
        revision = product["catalogue_revision"]
        if node["revision"] > revision:
            return
        props = {name: product.get(name) for name in ("product_id", "seller_id", "category_id", "bucket_id", "title")}
        props.update(
            catalogue_revision=revision,
            deleted=product["is_deleted"],
            visible=product["visible"],
            namespace=namespace(),
        )
        tx.run(
            "CYPHER 5 MATCH(p:Product {key:$key}) SET p += $props "
            "MERGE(u:User {key:$user_key}) SET u.user_id=$seller "
            "MERGE(c:Category {key:$category_key}) SET c.category_id=$category "
            "MERGE(u)-[:SELLS]->(p) WITH p,c OPTIONAL MATCH(p)-[r:IN_CATEGORY]->() DELETE r "
            "MERGE(p)-[:IN_CATEGORY]->(c)",
            key=key("product", pid),
            props=props,
            user_key=key("user", product["seller_id"]),
            category_key=key("category", product["category_id"]),
            seller=product["seller_id"],
            category=product["category_id"],
        ).consume()
        images = []
        for image in product["product_images"]:
            images.append(
                dict(
                    key=key("image", image["image_id"]),
                    image_id=image["image_id"],
                    product_id=pid,
                    image_url=image["image_url"],
                    namespace=namespace(),
                )
            )
        tx.run(
            "CYPHER 5 MATCH(p:Product {key:$key}) UNWIND $images AS item "
            "MERGE(i:Image {key:item.key}) SET i += item,i.deleted=false,i.catalogue_revision=$revision "
            "MERGE(p)-[:HAS_IMAGE]->(i)",
            key=key("product", pid),
            images=images,
            revision=revision,
        ).consume()
        tx.run(
            "CYPHER 5 MATCH(p:Product {key:$key})-[:HAS_IMAGE]->(i:Image) "
            "WHERE NOT i.image_id IN $ids SET i.deleted=true,i.catalogue_revision=$revision",
            key=key("product", pid),
            ids=[image["image_id"] for image in images],
            revision=revision,
        ).consume()

    write(apply)


def metadata(product: dict, document: dict) -> bool:
    revision = document.get("metadata_revision", 0)
    annotations = {row["image_id"]: row for row in document.get("image_metadata", [])}
    images = []
    for image in product["product_images"]:
        row = annotations.get(image["image_id"], {})
        text = " ".join(filter(None, (row.get("caption"), row.get("description"))))
        images.append(
            dict(
                key=key("image", image["image_id"]),
                caption=row.get("caption"),
                description=row.get("description"),
                search_text=unicodedata.normalize("NFC", text),
                search_text_folded=folded(text),
            )
        )

    def apply(tx):
        node = tx.run(
            "CYPHER 5 MATCH(p:Product {key:$key}) SET p._lock=coalesce(p._lock,0)+1 "
            "RETURN coalesce(p.metadata_revision,-1) AS revision",
            key=key("product", product["product_id"]),
        ).single()
        if not node:
            return False
        if node["revision"] > revision:
            return True
        count = tx.run(
            "CYPHER 5 MATCH(p:Product {key:$key})-[:HAS_IMAGE]->(i:Image) "
            "WHERE i.deleted=false RETURN count(i) AS count",
            key=key("product", product["product_id"]),
        ).single()["count"]
        if count != len(images):
            return False
        tx.run(
            "CYPHER 5 UNWIND $images AS item MATCH(i:Image {key:item.key}) SET i += item,i.metadata_revision=$revision",
            images=images,
            revision=revision,
        ).consume()
        tx.run(
            "CYPHER 5 MATCH(p:Product {key:$key}) SET p.metadata_revision=$revision",
            key=key("product", product["product_id"]),
            revision=revision,
        ).consume()
        return True

    return write(apply)


def order(order: dict, items: list[dict]):
    def apply(tx):
        k = key("order", order["order_id"])
        tx.run(
            "CYPHER 5 MERGE(o:Order {key:$key}) SET o._lock=coalesce(o._lock,0)+1,o.order_id=$id,"
            "o.status=$status MERGE(u:User {key:$user_key}) SET u.user_id=$buyer MERGE(u)-[:PLACED]->(o)",
            key=k,
            id=order["order_id"],
            status=order["order_status"],
            user_key=key("user", order["buyer_id"]),
            buyer=order["buyer_id"],
        ).consume()
        for item in items:
            tx.run(
                "CYPHER 5 MATCH(o:Order {key:$order_key}) MATCH(p:Product {key:$product_key}) "
                "MERGE(l:OrderItem {key:$key}) SET l.quantity=$quantity "
                "MERGE(o)-[:HAS_ITEM]->(l) MERGE(l)-[:OF_PRODUCT]->(p)",
                order_key=k,
                product_key=key("product", item["product_id"]),
                key=key("order_item", item["order_detail_id"]),
                quantity=item["quantity"],
            ).consume()

    write(apply)


def review(row: dict):
    def apply(tx):
        tx.run(
            "CYPHER 5 MERGE(r:Review {key:$key}) SET r.rating=$rating,r.deleted=$deleted "
            "WITH r MATCH(p:Product {key:$product_key}) MERGE(u:User {key:$user_key}) "
            "MERGE(u)-[:WROTE]->(r) MERGE(r)-[:REVIEWS]->(p)",
            key=key("review", row["review_id"]),
            rating=row["rating"],
            deleted=row["is_deleted"],
            product_key=key("product", row["product_id"]),
            user_key=key("user", row["buyer_id"]),
        ).consume()

    write(apply)


def search(query: str, offset=0, limit=100) -> list[dict]:
    from neo4j import Query
    from neo4j.exceptions import Neo4jError, ServiceUnavailable

    if not ready():
        raise HTTPException(503, "Graph projection generation is not active")
    try:
        result = driver().execute_query(
            Query(
                "CYPHER 5 CALL db.index.fulltext.queryNodes('image_metadata_text',$query) YIELD node AS i,score "
                "MATCH(p:Product)-[:HAS_IMAGE]->(i) WHERE i.namespace=$namespace AND "
                "i.deleted=false AND p.deleted=false "
                "RETURN i.image_id AS image_id,p.product_id AS product_id,score "
                "ORDER BY score DESC,i.image_id ASC SKIP $offset LIMIT $limit",
                timeout=settings.GRAPH_TIMEOUT_SECONDS,
            ),
            query=prepared_query(query),
            namespace=namespace(),
            offset=offset,
            limit=limit,
            database_=settings.NEO4J_DATABASE,
            routing_="r",
        )
        return [row.data() for row in result.records]
    except (Neo4jError, ServiceUnavailable) as error:
        raise HTTPException(503, "Tìm kiếm ảnh đang tạm thời không khả dụng.") from error


def related(product_id: int, limit: int = 20) -> list[int]:
    from neo4j import Query

    if not ready():
        raise HTTPException(503, "Graph projection generation is not active")
    result = driver().execute_query(
        Query(
            "CYPHER 5 MATCH(p:Product {key:$key})-[:IN_CATEGORY]->(c)<-[:IN_CATEGORY]-(other:Product) "
            "WHERE other.key<>p.key AND other.visible=true AND other.seller_id<>p.seller_id "
            "OPTIONAL MATCH(o:Order)-[:HAS_ITEM]->(:OrderItem)-[:OF_PRODUCT]->(p),"
            "(o)-[:HAS_ITEM]->(:OrderItem)-[:OF_PRODUCT]->(other) WHERE o.status=3 "
            "RETURN other.product_id AS id,count(DISTINCT o) AS common ORDER BY common DESC,id ASC LIMIT $limit",
            timeout=float(settings.GRAPH_TIMEOUT_SECONDS),
        ),
        key=key("product", product_id),
        limit=limit,
        database_=settings.NEO4J_DATABASE,
        routing_="r",
    )
    return [row["id"] for row in result.records]


def close():
    if driver.cache_info().currsize:
        driver().close()
        driver.cache_clear()


def tombstone(product_id: int):
    def apply(tx):
        tx.run(
            "CYPHER 5 MERGE(p:Product {key:$key}) SET p._lock=coalesce(p._lock,0)+1,"
            "p.deleted=true,p.visible=false,p.product_id=$id,p.namespace=$namespace "
            "WITH p OPTIONAL MATCH(p)-[:HAS_IMAGE]->(i:Image) SET i.deleted=true",
            key=key("product", product_id),
            id=product_id,
            namespace=namespace(),
        ).consume()

    write(apply)
