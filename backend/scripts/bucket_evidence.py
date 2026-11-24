"""Read-only evidence and local HTTP timings. This is not a production capacity test."""

import argparse
import importlib.metadata
import json
import statistics
import time
import urllib.request

from app.buckets.db import one, rows, transaction
from app.core.config import settings
from app.services import neo4j
from app.services.allocation import bucket_for_seller, load_contract
from app.services.mongo import get_database
from scripts.verify_seed import verify


def collect(base):
    result = {
        "contract_digest": load_contract().digest(),
        "test_vectors": {str(identifier): bucket_for_seller(identifier) for identifier in (3, 8, 12, 101, 202)},
        "neo4j_driver": importlib.metadata.version("neo4j"),
        "namespace": neo4j.namespace(),
        "verification": verify(include_graph=True),
        "timings": {},
    }
    with transaction() as core:
        result["seed_runs"] = rows(core, "SELECT run_id,dataset_id,dataset_hash,state,phase FROM seed_runs")
        result["seed_manifests"] = rows(
            core, "SELECT manifest->'counts' AS counts,manifest->'sites' AS sites FROM seed_manifest"
        )
        result["moves"] = rows(
            core,
            "SELECT bucket_id,source_site,target_site,old_epoch,state,details->>'checksum' AS checksum "
            "FROM bucket_moves ORDER BY updated_at",
        )
        result["generation"] = one(core, "SELECT * FROM graph_projection_state")
    result["graph_counts"] = [
        dict(record)
        for record in neo4j.driver()
        .execute_query(
            "CYPHER 5 MATCH(n) WHERE n.key STARTS WITH $prefix "
            "RETURN labels(n)[0] AS label,count(*) AS count ORDER BY label",
            prefix=neo4j.namespace() + ":",
            database_=settings.NEO4J_DATABASE,
        )
        .records
    ]
    result["mongo_products"] = get_database().product_details.count_documents({})
    for path in ("/health/ready", "/api/v1/products?limit=20", "/api/v1/images/search?q=alphaonly"):
        elapsed = []
        for _ in range(10):
            start = time.perf_counter()
            with urllib.request.urlopen(base.rstrip("/") + path, timeout=20) as response:
                body = json.load(response)
            elapsed.append(1000 * (time.perf_counter() - start))
        result["timings"][path] = dict(
            samples=10,
            p50_ms=round(statistics.median(elapsed), 2),
            p95_ms=round(statistics.quantiles(elapsed, n=20, method="inclusive")[18], 2),
        )
        if path.endswith("alphaonly"):
            result["image_query"] = dict(
                q="alphaonly", image_ids=[row["image_id"] for row in body["items"]], consistency=body["consistency"]
            )
    result["scope"] = "Local 1000-product demo plus test fixtures; sequential HTTP samples, no production load claim"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://backend:8000")
    print(json.dumps(collect(parser.parse_args().base_url), indent=2, ensure_ascii=False, default=str))
