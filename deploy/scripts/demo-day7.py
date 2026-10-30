"""Rehearse/record 6-minute real browser + DB demo in an owned disposable Compose project.

Requires report tooling, Chrome, ffmpeg and Playwright's ffmpeg. No .env.data is read.
The oldshop-data stack and its volumes are never stopped or reconfigured.
"""

import argparse
import functools
import http.server
import json
import os
import re
import secrets
import signal
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/tmp/oldshop-day7-pw")
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs/report"
OUT = REPORT / "generated"
SCREENS = REPORT / "screenshots"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--mongo-image", default="mongo:7.0")
parser.add_argument(
    "--resume-owned-project",
    help="Recover only an interrupted oldshop-day7-demo-* project",
)
parser.add_argument(
    "--resume-env", type=Path, help="Original temporary .env for that owned project"
)
parser.add_argument(
    "--seconds",
    type=int,
    default=365,
    help="Final video target; real operations may extend it",
)
args = parser.parse_args()
if not 300 <= args.seconds <= 410:
    raise SystemExit("Rehearsal must target 5–7 minutes")
if bool(args.resume_owned_project) != bool(args.resume_env):
    raise SystemExit("Both resume arguments are required together")
if args.resume_env and (
    args.resume_env.name != ".env"
    or not args.resume_env.parent.name.startswith("oldshop-day7-")
    or args.resume_env.parent.parent != Path("/tmp")
):
    raise SystemExit("Resume accepts only runner-owned /tmp/oldshop-day7-*/.env")
project = args.resume_owned_project or "oldshop-day7-demo-" + secrets.token_hex(4)
if not re.fullmatch(r"oldshop-day7-demo-[0-9a-f]{8}", project):
    raise SystemExit(
        "Only runner-owned oldshop-day7-demo-<8 hex> projects are accepted"
    )
evidence = {
    "project": project,
    "isolated": True,
    "date": "2026-10-30",
    "stages": [],
    "result": "RUNNING",
    "note": "Video is silent with subtitles; SQL/API console is explicitly labelled, not a pgAdmin/Compass impersonation.",
}


def interrupted(signum, _frame):
    raise RuntimeError(
        f"Recording interrupted by signal {signum}; cleaning owned project"
    )


signal.signal(signal.SIGTERM, interrupted)


def run(cmd, stdin=None):
    completed = subprocess.run(
        cmd,
        check=False,
        cwd=ROOT,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=240,
    )
    if completed.returncode:
        # Commands never contain passwords. Do not dump arbitrary DB rows/config into errors.
        raise RuntimeError(
            f"Command failed (exit {completed.returncode}): " + " ".join(cmd[:4])
        )
    return completed.stdout.strip()


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


OUT.mkdir(parents=True, exist_ok=True)
SCREENS.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="oldshop-day7-") as tmp:
    env = Path(tmp) / ".env"
    values = {}
    template = args.resume_env or ROOT / "deploy/.env.data.example"
    for line in template.read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = (
                secrets.token_hex(384 if key == "MONGO_KEYFILE" else 32)
                if value == "CHANGE_ME"
                else value
            )
    values.update(
        MONGO_IMAGE=args.mongo_image,
        BACKEND_IMAGE="oldshop-data-backend:day6",
        FRONTEND_IMAGE="oldshop-data-frontend:day6",
        STORAGE_BACKEND="minio",
    )
    for key in (
        "PG_PRIMARY_PORT",
        "PG_REPLICA_PORT",
        "BACKEND_PORT",
        "FRONTEND_PORT",
        "MINIO_API_PORT",
        "MINIO_CONSOLE_PORT",
    ):
        values[key] = "0"
    env.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    env.chmod(0o600)
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "--env-file",
        str(env),
        "-f",
        str(ROOT / "deploy/docker-compose.distributed.yml"),
        "--profile",
        "resilience",
    ]

    def dc(*cmd, stdin=None):
        return run(compose + list(cmd), stdin)

    def py(source):
        return dc("exec", "-T", "backend", "python", "-", stdin=source)

    def pg(query):
        code = """import json\nfrom scripts.migrate import connect\nwith connect() as c,c.cursor() as cur:\n cur.execute(__QUERY__)\n print(json.dumps({'columns':[d.name for d in cur.description],'rows':cur.fetchall()},default=str))\n""".replace(
            "__QUERY__", repr(query)
        )
        return json.loads(py(code))

    def mongo_status():
        js = """const u=encodeURIComponent(process.env.MONGO_INITDB_ROOT_USERNAME);const p=encodeURIComponent(process.env.MONGO_INITDB_ROOT_PASSWORD);const a=new Mongo(`mongodb://${u}:${p}@localhost:27017/admin?directConnection=true`).getDB('admin');const r=a.runCommand({replSetGetStatus:1});print(JSON.stringify({set:r.set,members:r.members.map(m=>({host:m.name,state:m.stateStr}))}));"""
        return json.loads(
            dc(
                "exec", "-T", "mongo1", "mongosh", "--nodb", "--quiet", "--eval", js
            ).splitlines()[-1]
        )

    def get(url):
        with urllib.request.urlopen(url, timeout=20) as response:
            return json.load(response)

    def public_product(url):
        p = get(url + "/api/v1/products/1")
        return {
            k: p[k]
            for k in (
                "product_id",
                "price",
                "quantity",
                "attributes",
                "tags",
                "metadata_status",
            )
        }

    def status():
        return json.loads(
            dc("exec", "-T", "etl-worker", "python", "-m", "etl.run", "status")
        )

    def etl(mode):
        output = dc(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "python",
            "backend",
            "-m",
            "etl.run",
            mode,
        )
        result = json.loads(output.splitlines()[-1])
        assert result["status"] == "success", result["status"]
        return result

    server = None
    try:
        print("Preparing disposable project " + project, flush=True)
        if not args.resume_owned_project:
            dc(
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "240",
                "pg-primary",
                "pg-replica",
                "mongo1",
                "mongo2",
                "mongo3",
                "minio",
            )
            for name in ("mongo-init", "mongo-expand", "minio-init"):
                dc("run", "--rm", "--no-deps", name)
        dc("up", "-d", "--wait", "--wait-timeout", "240")
        dc("restart", "frontend")
        dc("up", "-d", "--no-deps", "--wait", "--wait-timeout", "90", "frontend")
        frontend = "http://" + dc("port", "frontend", "8080").splitlines()[0]
        minio_console = "http://" + dc("port", "minio", "9001").splitlines()[0]
        deadline = time.monotonic() + 90
        while True:
            s = status()
            if s.get("last_run", {}).get("status") == "success" and s["pending"] == 0:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Initial ETL not ready")
            time.sleep(1)
        # Only demo metadata; root is unnecessary, application DB role owns this document.
        py(
            "from app.services.mongo import get_database\nget_database().product_details.update_one({'product_id':1},{'$set':{'attributes':{'brand':'OldShop Demo','ram_gb':8,'storage_gb':256},'tags':['demo-isolated','used']}})\n"
        )
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(Quiet, directory=str(REPORT))
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        console = f"http://127.0.0.1:{server.server_port}/demo_console.html"

        def present(title, left_title, left, right_title, right, visual=None):
            data = {
                "title": title,
                "meta": f"{project} · "
                + datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(
                    timespec="seconds"
                ),
                "left_title": left_title,
                "left": left,
                "right_title": right_title,
                "right": right,
                "visual": visual,
            }
            (OUT / "demo_data.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            )

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path="/opt/google/chrome/chrome",
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                record_video_dir=str(OUT / "raw_video"),
                record_video_size={"width": 1280, "height": 720},
            )
            page = context.new_page()
            video = page.video
            start = time.monotonic()

            def until(seconds):
                while time.monotonic() - start < seconds:
                    page.wait_for_timeout(200)

            def shot(name):
                page.screenshot(path=str(SCREENS / (name + ".png")))

            def stage(name, body):
                evidence["stages"].append(
                    {
                        "name": name,
                        "elapsed_seconds": round(time.monotonic() - start, 2),
                        **body,
                    }
                )
                print("STAGE " + name, flush=True)

            services = [
                {
                    "service": r["Service"],
                    "state": r["State"],
                    "health": r.get("Health", ""),
                }
                for r in [
                    json.loads(line)
                    for line in dc("ps", "--format", "json").splitlines()
                ]
            ]
            present(
                "1 / Stack demo đã khởi động",
                "Dịch vụ thực",
                services,
                "Kiến trúc một host",
                "",
                "assets/07_architecture.svg",
            )
            page.goto(console)
            page.wait_for_timeout(1000)
            shot("01_stack")
            stage("stack", {"services": services})
            until(35)
            partitions = pg(
                "SELECT relid::regclass::text,parentrelid::regclass::text,isleaf,level FROM pg_partition_tree('public.\"order\"'::regclass)"
            )
            replication = pg(
                "SELECT application_name,state,sync_state FROM pg_stat_replication"
            )
            present(
                "2 / PostgreSQL: partition và replication",
                "pg_partition_tree(order)",
                partitions,
                "pg_stat_replication",
                replication,
            )
            page.wait_for_timeout(1500)
            shot("02_postgres")
            stage("postgres", {"partitions": partitions, "replication": replication})
            until(75)
            document = json.loads(
                py(
                    "import json\nfrom app.services.mongo import get_database\nd=get_database().product_details.find_one({'product_id':1},{'_id':0,'product_id':1,'attributes':1,'tags':1,'etl':1})\nprint(json.dumps(d,default=str))\n"
                )
            )
            product = public_product(frontend)
            assert (
                product["attributes"]["ram_gb"] == 8
                and product["metadata_status"] == "available"
            )
            present(
                "3 / MongoDB: document + API hợp nhất",
                "Document truy vấn thật",
                document,
                "API vẫn lấy giá/stock PG",
                product,
            )
            page.wait_for_timeout(1500)
            shot("03_mongo")
            stage("mongo", {"product": product, "document": document})
            until(115)
            page.goto(frontend + "/shop/product/1")
            page.get_by_text("Thông số sản phẩm", exact=True).wait_for(timeout=30000)
            page.get_by_text(
                "Thông số sản phẩm", exact=True
            ).scroll_into_view_if_needed()
            page.wait_for_timeout(1500)
            assert page.get_by_text("OldShop Demo", exact=True).is_visible()
            shot("04_product")
            stage("product_ui", {"metadata_visible": True})
            until(150)
            # MinIO console login is on demo credentials only; password input stays masked.
            page.goto(minio_console)
            page.wait_for_timeout(2000)
            page.locator("#accessKey").fill(values["MINIO_ROOT_USER"])
            page.locator("#secretKey").fill(values["MINIO_ROOT_PASSWORD"])
            page.get_by_role(
                "button", name=re.compile("Log In|Sign In|Login", re.IGNORECASE)
            ).click()
            # New browser profiles show MinIO's existing AGPL information panel.
            page.get_by_role("button", name="Acknowledge", exact=True).click(
                timeout=15000
            )
            page.get_by_role("button", name="product-images", exact=True).click()
            page.get_by_text("products", exact=True).dblclick()
            image_object = page.get_by_text(
                re.compile(r".*\.(?:jpg|jpeg|png|webp)$", re.IGNORECASE)
            ).first
            image_object.wait_for(timeout=15000)
            object_name = image_object.inner_text()
            image_object.dblclick()
            page.get_by_role("button", name="Preview", exact=True).click()
            page.wait_for_function(
                "Array.from(document.images).some(i => i.naturalWidth > 100 && i.naturalHeight > 100)"
            )
            page.wait_for_timeout(1000)
            shot("05_minio")
            stage(
                "minio_console",
                {
                    "authenticated": True,
                    "bucket_visible": "product-images",
                    "license_panel_closed": True,
                    "image_object_visible": object_name,
                },
            )
            until(185)
            dc("stop", "etl-worker")
            first = etl("full")
            second = etl("full")
            assert (
                first["details"]["quality"]["collections"]
                == second["details"]["quality"]["collections"]
            )
            preserved = public_product(frontend)["attributes"]["ram_gb"] == 8
            assert preserved
            quality = second["details"]["quality"]
            counts = {k: v["mongo_active"] for k, v in quality["collections"].items()}
            present(
                "5 / Full ETL hai lần: không nhân bản",
                "Kết quả đối soát",
                {
                    "counts": counts,
                    "field_mismatches": quality["mismatches"],
                    "media": quality["media"],
                    "mongo_attributes_preserved": preserved,
                },
                "Sáu pipeline + ACK",
                "",
                "assets/07_etl.svg",
            )
            page.goto(console)
            page.wait_for_timeout(1000)
            shot("06_etl")
            stage(
                "etl_twice",
                {
                    "counts": counts,
                    "media": quality["media"],
                    "metadata_preserved": preserved,
                    "runs": [
                        {
                            "run_id": r["run_id"],
                            "status": r["status"],
                            "rows_in": r["rows_in"],
                            "rows_out": r["rows_out"],
                            "errors": r["errors"],
                        }
                        for r in (first, second)
                    ],
                },
            )
            dc("up", "-d", "--no-deps", "--wait", "--wait-timeout", "90", "etl-worker")
            until(230)
            plan = pg(
                'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT order_id,order_status FROM "order" WHERE order_id=1'
            )
            (ROOT / "docs/evidence/day7_current_pruning.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
            )
            present(
                "6 / EXPLAIN: pruning hiện hành, benchmark có nguồn",
                "Query thực trên seed nhỏ",
                {
                    "query": 'SELECT order_id,order_status FROM "order" WHERE order_id=1',
                    "plan": plan,
                },
                "Benchmark Ngày 4: median 3 lượt, không phải đo lại hôm nay",
                "",
                "assets/07_pg_benchmark.svg",
            )
            page.wait_for_timeout(1500)
            shot("07_explain")
            stage("explain", {"seed_query_plan_recorded": True})
            until(275)
            dc("stop", "mongo2")
            product = public_product(frontend)
            members = mongo_status()
            assert product["metadata_status"] == "available"
            assert any(
                m["host"].startswith("mongo2:")
                and m["state"] not in ("PRIMARY", "SECONDARY")
                for m in members["members"]
            )
            present(
                "7 / mongo2 đã dừng, ứng dụng vẫn trả dữ liệu",
                "Replica set thực",
                members,
                "GET product vẫn thành công",
                product,
            )
            page.wait_for_timeout(1500)
            shot("08_node_down")
            stage("mongo2_down", {"members": members, "product_http_200": True})
            until(320)
            dc("up", "-d", "--no-deps", "--wait", "--wait-timeout", "90", "mongo2")
            deadline = time.monotonic() + 60
            while True:
                members = mongo_status()
                if sum(m["state"] == "SECONDARY" for m in members["members"]) == 2:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Mongo secondary recovery deadline")
                time.sleep(1)
            ready = json.loads(
                py(
                    "import json,urllib.request\nprint(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())\n"
                )
            )
            assert ready["status"] == "ok"
            present(
                "8 / Phục hồi hoàn tất — phạm vi một máy",
                "Replica set đã phục hồi",
                members,
                "Kết quả và giới hạn",
                {
                    "ready": ready,
                    "full_twice": "PASS",
                    "metadata_preserved": True,
                    "node_failure": "PASS",
                    "host_failure": "NOT TESTED",
                    "Mongo8": "NOT TESTED",
                    "remote_CI": "NOT RUN",
                },
            )
            page.wait_for_timeout(1500)
            shot("09_recovered")
            stage("recovered", {"members": members, "ready": ready})
            until(args.seconds)
            context.close()
            raw = Path(video.path())
            browser.close()
        elapsed = time.monotonic() - start
        subtitles = [
            (
                0,
                35,
                "Khởi động stack demo riêng: dữ liệu seed, không thay stack đang dùng.",
            ),
            (35, 75, "PostgreSQL: HASH order, user split và WAL async tới standby."),
            (75, 115, "Mongo giữ metadata động; API vẫn lấy giá và tồn kho từ PG."),
            (
                115,
                150,
                "Giao diện sản phẩm hiển thị thuộc tính Mongo và ảnh qua gateway.",
            ),
            (150, 185, "MinIO console thật: bucket private trong project demo."),
            (
                185,
                230,
                "Full ETL hai lần: count khớp, không mất attributes/tags Mongo.",
            ),
            (230, 275, "EXPLAIN hiện hành và benchmark lịch sử có nhãn nguồn rõ ràng."),
            (
                275,
                320,
                "Dừng mongo2 trong project demo: quorum còn lại tiếp tục phục vụ.",
            ),
            (
                320,
                max(365, int(elapsed) + 1),
                "Khôi phục secondary và readiness; chưa chứng minh chịu mất host.",
            ),
        ]

        def tc(t):
            return (
                f"{int(t) // 3600:02d}:{int(t) % 3600 // 60:02d}:{int(t) % 60:02d},000"
            )

        srt = (
            "\n\n".join(
                f"{i}\n{tc(a)} --> {tc(b)}\n{text}"
                for i, (a, b, text) in enumerate(subtitles, 1)
            )
            + "\n"
        )
        (OUT / "oldshop_demo.srt").write_text(srt)
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(raw),
                "-vf",
                "subtitles=" + str(OUT / "oldshop_demo.srt"),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(OUT / "oldshop_demo.mp4"),
            ]
        )
        probe = json.loads(
            run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(OUT / "oldshop_demo.mp4"),
                ]
            )
        )
        duration = float(probe["format"]["duration"])
        assert 300 <= duration <= 420, duration
        evidence.update(
            result="PASS",
            video_seconds=duration,
            video="docs/report/generated/oldshop_demo.mp4",
            video_width=probe["streams"][0]["width"],
            video_height=probe["streams"][0]["height"],
            cleanup="Owned project and all its disposable volumes removed in finally",
        )
        print("Recorded video; cleaning disposable stack", flush=True)
    finally:
        if server:
            server.shutdown()
        dc("down", "--volumes", "--remove-orphans")
        if args.resume_env:
            args.resume_env.unlink()
            args.resume_env.parent.rmdir()
        if evidence["result"] == "PASS":
            (ROOT / "docs/evidence/day7_rehearsal.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
            )
            print("PASS rehearsal, real browser video and cleanup", flush=True)
