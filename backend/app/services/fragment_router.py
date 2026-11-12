"""Validated fragmentation metadata; relation names never originate in request input."""

import hashlib
import json
import os
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.services.index_config import no_duplicates

CONTRACT_PATH = Path(os.getenv("DATABASE_SRC", Path(__file__).resolve().parents[3] / "database")) / (
    "distributed/fragmentation.json"
)
Site = Literal["A", "B"]


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Allocation(Metadata):
    site_id: Site
    id_remainder: Literal[0, 1]


class Primary(Metadata):
    relation: Literal["product"]
    owner_relation: Literal["seller_site"]
    owner_key: Literal["seller_id"]
    site_key: Literal["site_id"]
    reconstruction_key: Literal["product_id"]
    id_modulus: Literal[2]


class Derived(Metadata):
    relation: Literal["product_image"]
    parent: Literal["product"]
    parent_key: Literal["product_id"]
    reconstruction_key: Literal["image_id"]


class Vertical(Metadata):
    relations: list[str]
    reconstruction_key: Literal["user_id"]


class References(Metadata):
    authority: Literal["A"]
    relations: list[str]
    updates: Literal["maintenance_only"]


class FragmentContract(Metadata):
    schema_version: Literal[1]
    revision: Literal["fragmentation-v1"]
    sites: list[Allocation]
    primary: Primary
    derived: Derived
    vertical: Vertical
    ownership_update: Literal["reject"]
    references: References

    @model_validator(mode="after")
    def complete(self) -> Self:
        if len(self.sites) != 2 or {s.site_id: s.id_remainder for s in self.sites} != {"A": 1, "B": 0}:
            raise ValueError("Exactly A/odd and B/even are supported")
        if self.vertical.relations != ["user_core", "user_profile", "user_secret", "user_wallet"]:
            raise ValueError("Incomplete vertical reconstruction")
        if self.references.relations != ["category", "seller_site"]:
            raise ValueError("Incomplete reference contract")
        return self

    def digest(self):
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def product_site(self, product_id: int) -> Site:
        if type(product_id) is not int or not 0 < product_id <= 2147483647:
            raise ValueError("product_id must be a positive PostgreSQL integer")
        return next(s.site_id for s in self.sites if product_id % self.primary.id_modulus == s.id_remainder)

    def validate_state(self, state, site: Site):
        remainder = next(s.id_remainder for s in self.sites if s.site_id == site)
        if (
            state.get("site_id") != site
            or state.get("id_remainder") != remainder
            or state.get("contract_sha256") != self.digest()
            or state.get("revision") != self.revision
            or state.get("rules_valid") is not True
            or not state.get("reference_sha256")
        ):
            raise ValueError("Fragment identity, contract or database rules differ")


def load_contract(path=CONTRACT_PATH):
    payload = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)
    # Literal integers also accept bool in Pydantic; reject that ambiguity here.
    if type(payload.get("schema_version")) is not int or type(payload.get("primary", {}).get("id_modulus")) is not int:
        raise ValueError("Contract versions and modulus must be integers")
    if any(type(s.get("id_remainder")) is not int for s in payload.get("sites", [])):
        raise ValueError("Remainders must be integers")
    return FragmentContract.model_validate(payload)


def relations(scope):
    return {
        "local": ("v_local_product", "v_local_category", "v_local_product_image"),
        "remote": ("v_remote_product", "v_remote_category", "v_remote_product_image"),
        "global": ("v_product", "v_category", "v_product_image"),
    }[scope]
