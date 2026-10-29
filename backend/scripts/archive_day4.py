"""Private logical backups of app Mongo collections and all three MinIO buckets.

Use while API/ETL writes are stopped. Verify restores only into UUID temporary names.
"""

import argparse
import hashlib
import json
import uuid
from pathlib import Path

from bson import decode_all, encode, json_util

from app.core.config import settings
from app.services.mongo import get_database
from app.services.storage import minio_client


def buckets():
    return [settings.MINIO_BUCKET_PRODUCT_IMAGES, settings.MINIO_BUCKET_USER_AVATARS, settings.MINIO_BUCKET_ATTACHMENTS]


def backup(directory: Path) -> dict:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    database = get_database()
    manifest = {"mongo": [], "minio": []}
    for name in sorted(database.list_collection_names()):
        if name.startswith("day4_bench_") or name.startswith("day4_restore_"):
            raise RuntimeError("Wait for temporary benchmark/restore collections before backup")
        collection = database[name]
        filename = f"collection_{len(manifest['mongo'])}.bson"
        count = 0
        with (directory / filename).open("wb") as target:
            for document in collection.find({}):
                target.write(encode(document))
                count += 1
        manifest["mongo"].append(
            {
                "name": name,
                "file": filename,
                "count": count,
                "options": collection.options(),
                "indexes": list(collection.list_indexes()),
            }
        )
    client = minio_client()
    for bucket in buckets():
        for obj in client.list_objects(bucket, recursive=True):
            filename = f"object_{len(manifest['minio'])}.bin"
            info = client.stat_object(bucket, obj.object_name)
            response = client.get_object(bucket, obj.object_name)
            digest = hashlib.sha256()
            try:
                with (directory / filename).open("wb") as target:
                    for block in response.stream(64 * 1024):
                        target.write(block)
                        digest.update(block)
            finally:
                response.close()
                response.release_conn()
            manifest["minio"].append(
                {
                    "bucket": bucket,
                    "key": obj.object_name,
                    "file": filename,
                    "size": info.size,
                    "content_type": info.content_type,
                    "sha256": digest.hexdigest(),
                }
            )
    (directory / "manifest.json").write_text(json_util.dumps(manifest, indent=2) + "\n")
    return {
        "mongo_collections": len(manifest["mongo"]),
        "mongo_documents": sum(item["count"] for item in manifest["mongo"]),
        "minio_objects": len(manifest["minio"]),
    }


def verify_restore(directory: Path) -> dict:
    manifest = json_util.loads((directory / "manifest.json").read_text())
    database = get_database()
    client = minio_client()
    token = uuid.uuid4().hex
    names = []
    objects = []
    try:
        for item in manifest["mongo"]:
            name = "day4_restore_" + token + "_" + str(len(names))
            names.append(name)
            options = {
                key: value
                for key, value in item["options"].items()
                if key in ("validator", "validationLevel", "validationAction", "collation")
            }
            collection = database.create_collection(name, **options)
            documents = decode_all((directory / item["file"]).read_bytes())
            if documents:
                collection.insert_many(documents)
            for index in item["indexes"]:
                if index["name"] != "_id_":
                    options = {key: value for key, value in index.items() if key not in ("key", "v", "ns", "name")}
                    # text indexes contain internal _fts fields: restore canonical Day 3 specs below.
                    if "textIndexVersion" in options:
                        continue
                    collection.create_index(list(index["key"].items()), name=index["name"], **options)
            if any("textIndexVersion" in index for index in item["indexes"]):
                from app.services.mongo_schema import INDEXES

                for keys, options in INDEXES.get(item["name"], []):
                    if any(value == "text" for _, value in keys):
                        collection.create_index(keys, **options)
            restored = {document["_id"]: encode(document) for document in collection.find({})}
            assert restored == {document["_id"]: encode(document) for document in documents}
        for item in manifest["minio"]:
            key = "__day4_restore_" + token + "/" + str(len(objects))
            objects.append((item["bucket"], key))
            with (directory / item["file"]).open("rb") as source:
                client.put_object(item["bucket"], key, source, length=item["size"], content_type=item["content_type"])
            response = client.get_object(item["bucket"], key)
            digest = hashlib.sha256()
            try:
                for block in response.stream(64 * 1024):
                    digest.update(block)
            finally:
                response.close()
                response.release_conn()
            assert digest.hexdigest() == item["sha256"]
        return {"mongo_restored": len(names), "minio_restored": len(objects), "result": "PASS"}
    finally:
        for name in names:
            database.drop_collection(name)
        for bucket, key in objects:
            client.remove_object(bucket, key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "verify"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(backup(args.directory) if args.action == "backup" else verify_restore(args.directory)))


if __name__ == "__main__":
    main()
