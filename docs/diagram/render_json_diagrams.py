"""Render current JSON UML/DFD to SVG + PNG; export editable PlantUML sources.

Run from the repository root: python docs/diagram/render_json_diagrams.py
Requires matplotlib. Reads model AST; does not import the app or access databases.
"""

import ast
import math
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
INK = "#172b46"
BLUE = "#e8f1ff"
GREEN = "#e5f5ef"
GOLD = "#fff1d9"
PURPLE = "#f0eaff"


def models(relative):
    result = {}
    for node in ast.parse((ROOT / relative).read_text()).body:
        if not isinstance(node, ast.ClassDef):
            continue
        fields = []
        for field in node.body:
            if not isinstance(field, ast.AnnAssign) or not isinstance(field.target, ast.Name):
                continue
            name = field.target.id
            if name == "model_config":
                continue
            annotation = ast.unparse(field.annotation)
            default = field.value
            value = None
            if isinstance(default, ast.Call) and ast.unparse(default.func) == "Field":
                kw = {k.arg: k.value for k in default.keywords}
                if "alias" in kw:
                    name = ast.literal_eval(kw["alias"])
                if "default_factory" in kw:
                    factory = ast.unparse(kw["default_factory"])
                    value = "{}" if factory == "dict" else "[]" if factory == "list" else factory + "()"
                elif "default" in kw:
                    value = ast.unparse(kw["default"])
                elif default.args:
                    first = default.args[0]
                    if not (isinstance(first, ast.Constant) and first.value is Ellipsis):
                        value = ast.unparse(first)
            elif default is not None:
                value = ast.unparse(default)
            fields.append(f"{name}: {annotation}" + (f" = {value}" if value is not None else " {required}"))
        result[node.name] = fields
    return result


DOC = models("backend/app/schemas/documents.py")
API = models("backend/app/schemas/catalog.py")


class Canvas:
    def __init__(self, width, height, title, subtitle):
        self.width, self.height = width, height
        self.fig, self.ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        self.fig.subplots_adjust(0, 0, 1, 1)
        self.ax.set(xlim=(0, width), ylim=(height, 0))
        self.ax.axis("off")
        self.fig.patch.set_facecolor("#ffffff")
        self.text(45, 43, title, 26, weight="bold")
        self.text(45, 82, subtitle, 14, color="#526580")

    def text(self, x, y, value, size=14, color=INK, weight="normal", ha="left", family="DejaVu Sans"):
        self.ax.text(x, y, value, fontsize=size, color=color, weight=weight, ha=ha,
                     va="top", fontfamily=family, linespacing=1.45, zorder=6)

    def line(self, points, color="#526580", dashed=False):
        xs, ys = zip(*points)
        self.ax.plot(xs, ys, color=color, linewidth=1.6, linestyle="--" if dashed else "-", zorder=2)

    def edge(self, points, label=None, at=None, kind="arrow", dashed=False, color="#526580"):
        self.line(points, color, dashed)
        a, b = points[-2:]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        if kind == "inherit":
            base = (b[0] - ux * 17, b[1] - uy * 17)
            self.ax.add_patch(Polygon([b, (base[0] - uy * 9, base[1] + ux * 9),
                                      (base[0] + uy * 9, base[1] - ux * 9)],
                                     facecolor="white", edgecolor=color, zorder=4))
        else:
            self.ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=16,
                                             color=color, linewidth=1.5, zorder=4))
        if kind == "compose":
            a, b = points[:2]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            ux, uy = dx / length, dy / length
            self.ax.add_patch(Polygon([a, (a[0] + ux * 10 - uy * 6, a[1] + uy * 10 + ux * 6),
                                      (a[0] + ux * 20, a[1] + uy * 20),
                                      (a[0] + ux * 10 + uy * 6, a[1] + uy * 10 - ux * 6)],
                                     color=color, zorder=5))
        if label:
            x, y = at
            t = self.ax.text(x, y, label, fontsize=12, va="center", ha="center", color=color,
                             fontfamily="DejaVu Sans", linespacing=1.35, zorder=7)
            t.set_bbox(dict(facecolor="white", edgecolor="none", pad=3))

    def klass(self, x, y, width, name, fields, stereo="object nhúng", fill=BLUE):
        lines = []
        for field in fields:
            lines.extend(textwrap.wrap(field, width=max(25, int((width - 28) / 8.6)),
                                       subsequent_indent="  ", break_long_words=False))
        height = 75 + len(lines) * 23
        self.ax.add_patch(Rectangle((x, y), width, height, facecolor="white", edgecolor=INK, linewidth=1.4, zorder=3))
        self.ax.add_patch(Rectangle((x, y), width, 62, facecolor=fill, edgecolor=INK, linewidth=1.4, zorder=3))
        self.text(x + width / 2, y + 8, f"«{stereo}»", 11, ha="center", color="#526580")
        self.text(x + width / 2, y + 29, name, 15, weight="bold", ha="center")
        for i, line in enumerate(lines):
            self.text(x + 12, y + 73 + i * 23, line, 11, family="DejaVu Sans Mono")
        return x, y, width, height

    def node(self, x, y, width, height, title, lines, kind="process", fill=BLUE):
        if kind == "process":
            self.ax.add_patch(FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0,rounding_size=18",
                                            facecolor=fill, edgecolor=INK, linewidth=1.5, zorder=3))
        else:
            self.ax.add_patch(Rectangle((x, y), width, height, facecolor=fill, edgecolor=INK, linewidth=1.5, zorder=3))
            if kind == "store":
                self.ax.plot([x + 10, x + 10], [y, y + height], color=INK, linewidth=1.5, zorder=4)
        self.text(x + width / 2, y + 17, title, 16, weight="bold", ha="center")
        for i, line in enumerate(lines):
            self.text(x + width / 2, y + 50 + i * 25, line, 13, ha="center")

    def note(self, x, y, width, lines, fill="#f5f7fb"):
        height = 25 + len(lines) * 25
        self.ax.add_patch(Rectangle((x, y), width, height, facecolor=fill, edgecolor="#cbd5e1", zorder=3))
        for i, line in enumerate(lines):
            self.text(x + 14, y + 13 + i * 25, line, 12)

    def save(self, stem):
        self.fig.savefig(HERE / f"{stem}.svg", metadata={"Date": None})
        self.fig.savefig(HERE / f"{stem}.png", dpi=100)
        plt.close(self.fig)


def puml(stem, title, specs, relations, notes):
    out = ["@startuml", f"title {title}", "skinparam shadowing false", "skinparam classAttributeIconSize 0"]
    for name, fields, stereo in specs:
        out.append(f'class {name} <<{stereo}>> {{')
        out.extend("  " + field for field in fields)
        out.append("}")
    out.extend(relations)
    out.append("note as Legend\n" + "\n".join(notes) + "\nend note")
    out.append("@enduml")
    (HERE / f"{stem}.puml").write_text("\n".join(out) + "\n")


def product_uml():
    stem = "08_json_product_uml_current"
    c = Canvas(2200, 1510, "UML · Cấu trúc JSON sản phẩm hiện tại",
               "OldShop | Document MongoDB và DTO phản hồi API là hai hợp đồng riêng | Đối chiếu mã nguồn 10/11/2026")
    c.klass(55, 140, 500, "Document", DOC["Document"], "lớp cơ sở document", PURPLE)
    product = c.klass(720, 140, 640, "ProductDetails", DOC["ProductDetails"], "collection: product_details", GREEN)
    c.klass(1610, 140, 530, "Dimensions", DOC["Dimensions"])
    c.klass(1610, 420, 530, "Condition", DOC["Condition"])
    reference = c.klass(55, 480, 500, "ObjectReference", DOC["ObjectReference"])
    c.klass(55, 775, 500, "ProductImageReference", DOC["ProductImageReference"])
    c.klass(1610, 760, 530, "ETLMetadata", DOC["ETLMetadata"])
    c.edge([(720, 200), (555, 200)], kind="inherit")
    c.edge([(1360, 270), (1490, 270), (1490, 225), (1610, 225)], "dimensions · 0..1", (1480, 190), "compose")
    c.edge([(1360, 420), (1500, 420), (1500, 500), (1610, 500)], "condition · 0..1", (1490, 465), "compose")
    c.edge([(1360, 500), (1465, 500), (1465, 860), (1610, 860)], "etl · 0..1", (1490, 815), "compose")
    c.edge([(720, 430), (630, 430), (630, 860), (555, 860)], "images · 0..*", (635, 730), "compose")
    c.edge([(305, 775), (305, reference[1] + reference[3])], kind="inherit")
    c.note(55, 1060, 590, ["Ký hiệu: tam giác rỗng = kế thừa; thoi đặc = chứa object.",
                                   "{required}: bắt buộc; = giá trị: mặc định ở model.",
                                   "| None: cho phép null. 0..*: mảng có thể rỗng.",
                                   "Identifier: integer > 0; AwareDatetime: có múi giờ.",
                                   "attributes: dict[str, JsonValue] là map động;",
                                   "brand/ram_gb chưa là field bắt buộc của model.",
                                   "bucket/key là tham chiếu; byte file nằm tại MinIO."])
    response = c.klass(720, 930, 640, "ProductResponse", ["… các field core từ ProductBase/ORM",
            "product_id, seller_id, status, view_count, …", "product_images: list[ProductImageResponse] = []"],
            "API DTO · rút gọn", GOLD)
    c.klass(720, 1190, 640, "ProductDetailResponse", API["ProductDetailResponse"], "API DTO", GOLD)
    c.edge([(1040, 1190), (1040, response[1] + response[3])], kind="inherit")
    c.edge([(1200, product[1] + product[3]), (1200, 820), (1420, 820), (1420, 1300), (1360, 1300)],
           "metadata service chỉ bổ sung\nattributes, tags, trạng thái/thời gian sync", (1515, 1110), dashed=True)
    c.note(1610, 1180, 530, ["Phạm vi: field ProductDetails đầy đủ; DTO core rút gọn.",
                                    "UserResponse/ProductReviewResponse không bung ở đây.",
                                    "Document: extra=forbid, strict; attributes linh hoạt.",
                                    "API image_url khác document bucket/key.",
                                    "Không thêm source_site/revision từ kế hoạch tương lai."])
    c.save(stem)
    specs = [(n, DOC[n], "document" if n == "ProductDetails" else "object") for n in
             ["Document", "ProductDetails", "Dimensions", "Condition", "ObjectReference", "ProductImageReference", "ETLMetadata"]]
    specs += [("ProductResponse", ["… core fields abbreviated", "product_images: list[ProductImageResponse]"], "API DTO"),
              ("ProductDetailResponse", API["ProductDetailResponse"], "API DTO")]
    puml(stem, "OldShop — JSON sản phẩm hiện tại", specs, [
        "Document <|-- ProductDetails", "ObjectReference <|-- ProductImageReference",
        'ProductDetails "1" *--> "0..1" Dimensions : dimensions',
        'ProductDetails "1" *--> "0..1" Condition : condition',
        'ProductDetails "1" *--> "0..*" ProductImageReference : images',
        'ProductDetails "1" *--> "0..1" ETLMetadata : etl',
        "ProductResponse <|-- ProductDetailResponse",
        "ProductDetails ..> ProductDetailResponse : metadata service: attributes/tags/sync"], [
        "Document fields follow documents.py; API core is abbreviated.",
        "Composition describes embedded value objects, not database FK or separate collections.",
        "Required/default/null follow model. Defaults are applied by application model, not Mongo validator.",
        "Document uses BSON dates; JSON transport uses ISO 8601."])


def collections_uml():
    stem = "08_json_collections_uml_current"
    c = Canvas(2280, 1900, "UML · Tổng quan sáu document nghiệp vụ",
               "Mỗi lớp bên dưới kế thừa Document; kiểu object nhúng được ghi ngay trong field | Nguồn: schemas/documents.py")
    c.klass(790, 130, 700, "Document", DOC["Document"], "lớp cơ sở chung", PURPLE)
    groups = [("ProductDetails", "product_details"), ("ReviewDocument", "reviews"), ("OrderSnapshot", "order_snapshots"),
              ("SystemLogDocument", "system_logs"), ("ViolationLogDocument", "violation_logs"), ("ContactMessageDocument", "contact_messages")]
    positions = [(50, 455), (790, 455), (1530, 455), (50, 1200), (790, 1200), (1530, 1200)]
    for (name, collection), (x, y) in zip(groups, positions):
        c.klass(x, y, 700, name, DOC[name], f"collection: {collection}", GREEN)
    # Merge six generalizations onto a shared trunk outside the attribute boxes.
    c.line([(400, 365), (2255, 365), (2255, 1120), (400, 1120)])
    for x in (400, 1140, 1880):
        c.line([(x, 455), (x, 365)])
        c.line([(x, 1200), (x, 1120)])
    c.edge([(1140, 365), (1140, 274)], "6 lớp kế thừa", (1140, 320), kind="inherit")
    c.note(50, 1700, 2180, ["Các field ở mỗi lớp là khai báo trực tiếp; còn có _id/schema_version/deleted kế thừa từ Document.",
                                     "OrderSnapshot: buyer [1], items [1..*], payments [0..*], voucher_current [0..1], etl [1] là các object nhúng.",
                                     "Review: moderation [0..1], evidence [0..*]. Contact: attachments [0..*]. Log: payload [0..1]. Đây không phải FK.",
                                     "ETLError (schemas/etl.py) là document vận hành riêng, không kế thừa Document; schema/config index không thuộc sáu collection này.",
                                     "Đây là hợp đồng trong code; một collection có schema không chứng minh mọi workflow ghi đã hoàn thiện."])
    c.save(stem)
    embedded = ["ObjectReference", "ProductImageReference", "Dimensions", "Condition", "ETLMetadata", "Moderation",
                "BuyerReference", "OrderSnapshotItem", "PaymentSnapshot", "VoucherSnapshot", "LogPayload"]
    specs = [("Document", DOC["Document"], "base")]
    specs += [(n, DOC[n], col) for n, col in groups]
    specs += [(n, DOC[n], "embedded") for n in embedded]
    relations = ["Document <|-- " + n for n, _ in groups] + ["ObjectReference <|-- ProductImageReference"]
    for owner, field, target, count in [
        ("ProductDetails", "dimensions", "Dimensions", "0..1"), ("ProductDetails", "condition", "Condition", "0..1"),
        ("ProductDetails", "images", "ProductImageReference", "0..*"), ("ReviewDocument", "moderation", "Moderation", "0..1"),
        ("ReviewDocument", "evidence", "ObjectReference", "0..*"), ("OrderSnapshot", "buyer", "BuyerReference", "1"),
        ("OrderSnapshot", "items", "OrderSnapshotItem", "1..*"), ("OrderSnapshot", "payments", "PaymentSnapshot", "0..*"),
        ("OrderSnapshot", "voucher_current", "VoucherSnapshot", "0..1"), ("SystemLogDocument", "payload", "LogPayload", "0..1"),
        ("ViolationLogDocument", "payload", "LogPayload", "0..1"), ("ContactMessageDocument", "attachments", "ObjectReference", "0..*")]:
        relations.append(f'{owner} "1" *--> "{count}" {target} : {field}')
    relations += [f'{n} "1" *--> "{"1" if n == "OrderSnapshot" else "0..1"}" ETLMetadata : etl' for n, _ in groups]
    puml(stem, "OldShop — sáu document và object nhúng hiện tại", specs, relations, [
        "Identifier = integer in (0, 2^63-1]; VND = integer in [0, 2^63-1].",
        "Review invariant: rating=0 iff type=report; rating 1..5 iff type=review.",
        "ETLError is an operational schema in schemas/etl.py, separate from these six documents.",
        "The PNG/SVG overview lists all direct fields; this source also expands embedded object classes."])


def dfd():
    stem = "08_json_dfd_current"
    c = Canvas(2200, 1590, "DFD mức 1 · Luồng sử dụng JSON hiện tại",
               "Phạm vi: danh mục sản phẩm, media và ETL đa document | Không mô tả hệ hai site tương lai hoặc public metadata-write API")
    # Draw the labeled data flows before nodes, so lines remain behind boxes.
    flows = [
        ("E1", "P1", [(310, 400), (360, 400), (360, 180), (460, 180)], "JSON cập nhật / trạng thái;\nFormData tạo tin + file", (375, 285)),
        ("P1", "E1", [(460, 235), (410, 235), (410, 465), (310, 465)], "JSON / lỗi", (390, 440)),
        ("P1", "D1", [(840, 170), (1080, 170)], "Product / ProductImage\n(SQL/ORM)", (960, 145)),
        ("D1", "P1", [(1080, 220), (840, 220)], "Bản ghi / kết quả ghi", (960, 245)),
        ("E1", "P2", [(310, 545), (460, 545)], "ID / bộ lọc\nattributes JSON", (380, 515)),
        ("P2", "E1", [(460, 620), (310, 620)], "JSON kết quả", (380, 650)),
        ("P2", "D1", [(840, 530), (950, 530), (950, 280), (1080, 280)], "Điều kiện lọc / ID (SQL)", (950, 360)),
        ("D1", "P2", [(1080, 310), (1005, 310), (1005, 580), (840, 580)], "Core, giá, stock, ảnh", (1005, 465)),
        ("P2", "D3", [(840, 665), (1080, 665)], "ID / lọc attributes", (960, 640)),
        ("D3", "P2", [(1080, 715), (840, 715)], "Attributes / tags\nSync / IDs phù hợp", (960, 760)),
        ("P1", "P3", [(650, 290), (650, 360), (65, 360), (65, 1150), (460, 1150)], "File upload / đường dẫn thao tác", (225, 1010)),
        ("P3", "P1", [(460, 1205), (25, 1205), (25, 320), (700, 320), (700, 290)], "URL media đã lưu", (215, 330)),
        ("E1", "P3", [(190, 690), (190, 1090), (460, 1090)], "Yêu cầu GET/HEAD /media", (260, 870)),
        ("P3", "E1", [(460, 1260), (320, 1260), (320, 690)], "Byte ảnh/video; HTTP headers", (330, 970)),
        ("P3", "D4", [(840, 1140), (1080, 1140)], "Byte upload / object key", (960, 1115)),
        ("D4", "P3", [(1080, 1205), (840, 1205)], "Byte file / metadata", (960, 1235)),
        ("P1", "D2", [(840, 270), (900, 270), (900, 420), (1080, 420)], "Event cùng\ntransaction", (960, 405)),
        ("D1", "P4", [(1540, 210), (2130, 210), (2130, 600), (2090, 600)], "Bản ghi nguồn + origin (SQL)", (1900, 185)),
        ("D2", "P4", [(1540, 445), (1700, 445), (1700, 550)], "Event / key JSONB", (1660, 490)),
        ("P4", "D2", [(1940, 550), (1940, 395), (1540, 395)], "ACK / attempts / retry state", (1890, 375)),
        ("P4", "D3", [(1660, 625), (1540, 625)], "BSON upsert", (1600, 600)),
        ("D3", "P4", [(1540, 700), (1660, 700)], "Kết quả ghi", (1600, 730)),
        ("P4", "D4", [(1850, 760), (1850, 1160), (1540, 1160)], "Object key / byte còn thiếu", (1850, 940)),
        ("D4", "P4", [(1540, 1220), (2010, 1220), (2010, 760)], "Metadata / xác nhận object", (2010, 1060)),
    ]
    for _, _, points, label, at in flows:
        c.edge(points, label, at, color="#526580")
    c.node(100, 390, 210, 300, "E1 · Frontend", ["Angular / trình duyệt", "Người xem / seller", "Moderator", "JSON + FormData"], "external", GOLD)
    c.node(460, 120, 380, 170, "1.0 · Ghi sản phẩm", ["FastAPI · validate / quyền", "CRUD + transaction PG", "Không ghi attributes trực tiếp"])
    c.node(460, 500, 380, 230, "2.0 · Đọc & tổng hợp", ["FastAPI + metadata service", "PG core + Mongo attributes", "Lọc / sort / pagination", "ProductDetailResponse"])
    c.node(460, 1060, 380, 220, "3.0 · Xử lý media", ["Storage service + /media", "Upload / stream ảnh, MP4", "URL / bucket / key", "Không nhúng byte vào JSON"])
    c.node(1660, 550, 430, 210, "4.0 · ETL worker", ["Extract → transform → validate", "Partial upsert; retry / ACK", "Giữ attributes/tags đang có", "Kiểm/copy media còn thiếu"], fill=GREEN)
    c.node(1080, 120, 460, 200, "D1 · PostgreSQL nghiệp vụ", ["product, product_image", "order, review, logs, feedback, …", "Dữ liệu nguồn / quan hệ / origin"], "store", PURPLE)
    c.node(1080, 370, 460, 100, "D2 · PostgreSQL outbox", ["etl_outbox; event/entity keys JSONB"], "store", PURPLE)
    c.node(1080, 570, 460, 210, "D3 · MongoDB", ["product_details + 5 document khác", "Attributes/tags và projection", "ETL errors: collection vận hành"], "store", GREEN)
    c.node(1080, 1080, 460, 190, "D4 · MinIO", ["Object bytes + metadata", "product-images / product-videos / …", "Áp dụng khi STORAGE_BACKEND=minio"], "store", GOLD)
    c.note(460, 835, 1080, ["D1 và D2 là hai nhóm dữ liệu trong cùng PostgreSQL, không phải hai database độc lập.",
                                    "Trigger tạo outbox cùng transaction ghi nguồn. Không vẽ luồng trực tiếp kho → kho.",
                                    "Chi tiết: Mongo lỗi → core PG vẫn trả, metadata_status=unavailable.",
                                    "Lọc attributes: Mongo lỗi → 503; không tự bỏ bộ lọc. Giá/stock luôn lấy PG."])
    c.note(55, 1360, 2090, ["Ký hiệu: hình chữ nhật = tác nhân; bo góc = tiến trình; ô hai vạch trái = kho dữ liệu. Mũi tên ghi nội dung dữ liệu, không phải thứ tự chạy.",
                                    "JSON ở HTTP/chuỗi filter; JSONB trong outbox; BSON trong Mongo; SQL/ORM với PostgreSQL; byte file với MinIO.",
                                    "Schema: Pydantic document → BSON validator qua mongo_schema.py → init_mongo cài strict/error; đây là cấu hình, không phải luồng nghiệp vụ riêng.",
                                    "DFD rút gọn không bung auth, mọi CRUD ngoài sản phẩm, report aggregate, media cleanup hay catalogue gateway hai site riêng.",
                                    "Nguồn: api/v1/products.py; services/product_metadata.py; etl/{run,load}.py; etl/pipelines/documents.py; services/storage.py."])
    c.save(stem)
    out = ["@startuml", "title OldShop — DFD mức 1: luồng JSON hiện tại", "skinparam shadowing false",
           'rectangle "E1 · Angular / trình duyệt" as E1',
           'usecase "1.0 Ghi sản phẩm\\nValidate + quyền + CRUD" as P1',
           'usecase "2.0 Đọc và tổng hợp\\nCore PG + metadata Mongo" as P2',
           'usecase "3.0 Xử lý media\\nStorage service /media" as P3',
           'usecase "4.0 ETL\\nExtract / validate / partial upsert / ACK" as P4',
           'database "D1 PG nghiệp vụ\\nproduct / ảnh / nguồn khác" as D1',
           'database "D2 PG outbox\\ncùng database với D1" as D2',
           'database "D3 MongoDB\\n6 document + etl_errors" as D3',
           'storage "D4 MinIO\\nObject bytes" as D4']
    for source, target, _, label, _ in flows:
        out.append(f"{source} --> {target} : " + label.replace("\n", "\\n"))
    out += ['note bottom of D2 : Trigger nguồn ghi D2 cùng transaction; không có luồng trực tiếp kho-kho.',
            'note bottom of D4 : File bytes đi qua tiến trình; JSON chỉ giữ URL/bucket/key.',
            'note bottom of P2 : Chi tiết fallback metadata; attributes filter lỗi trả 503.',
            'note bottom of P4 : Hiện tại single-source PG; không vẽ source_site hoặc write API chưa triển khai.', "@enduml"]
    (HERE / f"{stem}.puml").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    product_uml()
    collections_uml()
    dfd()
    print("Rendered 3 diagrams: PNG, SVG and PlantUML sources in docs/diagram/.")
