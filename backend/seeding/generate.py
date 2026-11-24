import hashlib
import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

from app.services.allocation import canonical

DATABASE = Path(os.getenv("DATABASE_SRC", Path(__file__).resolve().parents[2] / "database"))


def generate(profile: str, scale: int = 1) -> dict:
    if profile not in {"demo-v2", "contract-small", "benchmark-v2"} or type(scale) is not int or not 1 <= scale <= 100:
        raise ValueError("Unknown dataset or invalid scale")
    config = json.loads((DATABASE / f"seeding/datasets/{profile}.json").read_text())
    now = datetime.fromisoformat(config["reference_time"])
    rng = random.Random(config["random_seed"])
    data = {
        name: []
        for name in ("users", "categories", "products", "images", "metadata", "orders", "order_details", "reviews")
    }
    for i in range(1, config["users"] + 1):
        data["users"].append(
            dict(
                user_id=i,
                username=f"bucket_user_{i}",
                email=f"bucket{i}@example.com",
                full_name=f"Người dùng mẫu {i}",
                role_id=1 if i == 1 else 2 if i == 2 else 3,
            )
        )
    for i, name in enumerate(
        ("Điện tử", "Máy tính", "Sách", "Gia dụng", "Thời trang", "Đồ chơi", "Nội thất", "Sưu tầm"), 1
    ):
        data["categories"].append(dict(category_id=i, name=name, parent_id=1 if i == 2 else None))
    assets = sorted((DATABASE / "03_seeds/media/products").glob("*.jpg"))
    if not assets:
        raise ValueError("Seed image assets missing")
    for index in range(config["products"] * scale):
        pid = index + 1
        seller = 3 + index % config["sellers"]
        state = {0: 0, 1: 2, 2: 3}.get(index % 40, 1)
        data["products"].append(
            dict(
                product_id=pid,
                seller_id=seller,
                category_id=1 + index % 8,
                title=f"Vật phẩm mẫu {pid}",
                description="Sản phẩm minh họa cho nghiệp vụ phân tán.",
                price=str(100000 + 10000 * (index % 20)),
                quantity=0 if state == 3 else 100,
                initial_quantity=0 if state == 3 else 100,
                status=state,
                is_deleted=index % 40 == 3,
                condition_rating=5 + index % 6,
                created_at=(now - timedelta(days=index % 180)).isoformat(),
                reject_reason="Dữ liệu minh họa từ chối" if state == 2 else None,
            )
        )
        for angle in range(2):
            image_id = 2 * index + angle + 1
            asset = assets[(2 * index + angle) % len(assets)]
            data["images"].append(
                dict(
                    image_id=image_id,
                    product_id=pid,
                    image_url=f"/media/products/bucket-seed/{asset.name}",
                    display_order=angle,
                    is_primary=angle == 0,
                    content_type="image/jpeg",
                    size_bytes=asset.stat().st_size,
                    asset=asset.name,
                    sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),
                )
            )
            if image_id % 11:
                data["metadata"].append(
                    dict(
                        image_id=image_id,
                        product_id=pid,
                        caption=f"Ảnh tư liệu số {image_id}",
                        description="Nhãn tra cứu: alphaonly." if image_id == 9 else "Ảnh minh họa từ bộ dữ liệu mẫu.",
                    )
                )
    eligible = [product for product in data["products"] if product["status"] == 1 and not product["is_deleted"]]
    for index in range(config["orders"] * scale):
        buyer = 3 + index % (config["users"] - 2)
        candidates = [product for product in eligible if product["seller_id"] != buyer]
        chosen = [candidates[index % len(candidates)], candidates[(index + 7) % len(candidates)]]
        status = 4 if index % 7 == 0 else 0 if index % 7 == 1 else 3
        oid = index + 1
        subtotal = sum(int(product["price"]) for product in chosen)
        data["orders"].append(
            dict(
                order_id=oid,
                buyer_id=buyer,
                contact_id=buyer,
                payment_method_id=1,
                total_amount=str(subtotal),
                shipping_fee="30000",
                discount_amount="0",
                final_amount=str(subtotal + 30000),
                order_status=status,
                shipping_address=f"Địa chỉ mẫu của user {buyer}",
                order_date=(now - timedelta(days=rng.randrange(120))).isoformat(),
            )
        )
        for product in chosen:
            lid = len(data["order_details"]) + 1
            data["order_details"].append(
                dict(
                    order_detail_id=lid,
                    order_id=oid,
                    product_id=product["product_id"],
                    quantity=1,
                    price_at_purchase=product["price"],
                    subtotal=product["price"],
                )
            )
            if status != 4:
                product["quantity"] -= 1
            if status == 3 and lid % 3 == 0:
                data["reviews"].append(
                    dict(
                        review_id=len(data["reviews"]) + 1,
                        product_id=product["product_id"],
                        buyer_id=buyer,
                        rating=4 + lid % 2,
                        content="Đánh giá mẫu từ đơn đã giao.",
                        is_verified_purchase=True,
                    )
                )
    data["config"] = config
    data["scale"] = scale
    data["digest"] = hashlib.sha256(canonical(data).encode()).hexdigest()
    from seeding.validate import validate

    return validate(data)
