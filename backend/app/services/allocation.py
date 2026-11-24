"""The allocation contract shared by writers, seeders, migration and verification."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "database/distributed/contracts/bucket-v2.json"


class AllocationError(ValueError):
    pass


class BucketContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: int = Field(ge=2, le=2)
    revision: str
    bucket_count: int = Field(ge=256, le=256)
    hash_algorithm: str
    hash_prefix: str
    owner_key: str
    primary: str
    derived: tuple[str, ...]
    id_policy: str
    ownership_update: str

    def bucket_for_seller(self, seller_id: int) -> int:
        identifier(seller_id)
        digest = hashlib.sha256(f"{self.hash_prefix}{seller_id}".encode("ascii")).digest()
        return int.from_bytes(digest[:8], "big") % self.bucket_count

    def digest(self) -> str:
        return hashlib.sha256(canonical(self.model_dump()).encode()).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def identifier(value: int) -> int:
    if type(value) is not int or not 0 < value <= 2147483647:
        raise AllocationError("Expected a positive PostgreSQL integer ID")
    return value


def site_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", value):
        raise AllocationError("Invalid site identifier")
    return value


def load_contract(path: Path | None = None) -> BucketContract:
    import os

    if path is None:
        path = Path(os.getenv("DATABASE_SRC", ROOT / "database")) / "distributed/contracts/bucket-v2.json"
    contract = BucketContract.model_validate_json(path.read_text())
    if (
        contract.revision != "bucket-v2"
        or contract.hash_algorithm != "sha256-prefix-u64be"
        or contract.hash_prefix != "oldshop:seller:v1:"
        or contract.owner_key != "seller_id"
        or contract.primary != "product"
        or list(contract.derived) != ["product_image", "stock_reservation"]
        or contract.id_policy != "core-allocated-integer-ranges"
        or contract.ownership_update != "migration-only"
    ):
        raise AllocationError("Unsupported allocation contract")
    return contract


def bucket_for_seller(seller_id: int) -> int:
    return load_contract().bucket_for_seller(seller_id)


@dataclass(frozen=True)
class Route:
    bucket_id: int
    site_id: str
    ownership_epoch: int
    mapping_revision: int


class Allocator:
    """Uses an existing core transaction; DSNs never come from request input."""

    def __init__(self, connection):
        self.connection = connection
        self.contract = load_contract()

    def resolve_bucket(self, bucket_id: int, expected_revision: int | None = None) -> Route:
        if type(bucket_id) is not int or not 0 <= bucket_id < self.contract.bucket_count:
            raise AllocationError("Invalid bucket")
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT a.owner_site_id,a.ownership_epoch,a.mapping_revision,a.state FROM bucket_assignment a "
                "JOIN site_registry s ON s.site_id=a.owner_site_id WHERE a.bucket_id=%s AND s.active",
                (bucket_id,),
            )
            row = cursor.fetchone()
        if not row or row[3] != "active" or (expected_revision is not None and row[2] != expected_revision):
            raise AllocationError("Bucket unavailable or routing revision changed")
        return Route(bucket_id, site_identifier(row[0]), row[1], row[2])

    def resolve_seller(self, seller_id: int) -> Route:
        return self.resolve_bucket(self.contract.bucket_for_seller(seller_id))

    def resolve_product(self, product_id: int) -> Route:
        identifier(product_id)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT bucket_id,lifecycle FROM catalogue_directory WHERE product_id=%s", (product_id,))
            row = cursor.fetchone()
        if row is None or row[1] == "deleted":
            raise KeyError(product_id)
        if row[1] != "active":
            raise AllocationError("Product provisioning is not complete")
        return self.resolve_bucket(row[0])

    def allocate_ids(self, entity: str, count: int = 1) -> list[int]:
        if entity not in {"product", "image", "user", "order", "order_detail", "review", "contact"}:
            raise AllocationError("Unknown ID namespace")
        if type(count) is not int or not 1 <= count <= 100000:
            raise AllocationError("Invalid allocation size")
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE global_id_allocator SET next_id=next_id+%s WHERE entity=%s "
                "AND next_id+%s<=2147483647 RETURNING next_id-%s",
                (count, entity, count, count),
            )
            row = cursor.fetchone()
        if row is None:
            raise AllocationError("ID namespace missing or exhausted")
        return list(range(row[0], row[0] + count))


def validate_target(route: Route, state: dict, contract: BucketContract | None = None) -> None:
    contract = contract or load_contract()
    if (
        state.get("site_id") != route.site_id
        or state.get("contract_digest") != contract.digest()
        or state.get("ownership_epoch") != route.ownership_epoch
        or state.get("state") != "active"
    ):
        raise AllocationError("Site identity/lease differs from routing contract")
