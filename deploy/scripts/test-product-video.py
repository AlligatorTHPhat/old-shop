"""Build and test video on private PostgreSQL/MinIO containers; never use the live stack."""

import argparse
import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", help="Use an already-built backend image (otherwise builds one)")
    args = parser.parse_args()
    suffix = uuid.uuid4().hex[:10]
    network = f"oldshop-video-test-{suffix}"
    pg = f"{network}-pg"
    minio = f"{network}-minio"
    backend = f"{network}-runner"
    provisioner = f"{network}-init"
    image = args.image or f"oldshop-video-test-backend:{suffix}"
    test_image = f"oldshop-video-test-runner:{suffix}"
    minio_image = "quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"
    created_network = False
    try:
        if not args.image:
            run("docker", "build", "-t", image, "-f", "backend/Dockerfile", ".")
        with tempfile.TemporaryDirectory(prefix="oldshop-video-runner-") as directory:
            dockerfile = Path(directory) / "Dockerfile"
            dockerfile.write_text(
                f"FROM {image}\nUSER root\nCOPY backend/requirements-dev.lock /tmp/dev.lock\n"
                "RUN pip install --no-cache-dir --require-hashes -r /tmp/dev.lock\nUSER app\n"
            )
            run("docker", "build", "-t", test_image, "-f", str(dockerfile), ".")
        run("docker", "network", "create", network)
        created_network = True
        run(
            "docker",
            "run",
            "-d",
            "--name",
            pg,
            "--network",
            network,
            "--network-alias",
            "video-pg",
            "--memory",
            "512m",
            "-e",
            "POSTGRES_PASSWORD=video-test-only",
            "postgres:16-alpine",
        )
        run(
            "docker",
            "run",
            "-d",
            "--name",
            minio,
            "--network",
            network,
            "--network-alias",
            "video-minio",
            "--network-alias",
            "minio",
            "--memory",
            "512m",
            "-e",
            "MINIO_ROOT_USER=video_test",
            "-e",
            "MINIO_ROOT_PASSWORD=video-test-only",
            minio_image,
            "server",
            "/data",
        )
        for _attempt in range(60):
            result = subprocess.run(["docker", "exec", pg, "pg_isready", "-U", "postgres"], capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Private test PostgreSQL did not become ready")
        for _attempt in range(60):
            result = subprocess.run(
                ["docker", "exec", minio, "curl", "-fsS", "http://localhost:9000/minio/health/ready"],
                capture_output=True,
            )
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Private test MinIO did not become ready")
        run(
            "docker",
            "run",
            "--rm",
            "--name",
            provisioner,
            "--network",
            network,
            "-e",
            "MINIO_ROOT_USER=video_test",
            "-e",
            "MINIO_ROOT_PASSWORD=video-test-only",
            "-e",
            "MINIO_APP_ACCESS_KEY=video_app",
            "-e",
            "MINIO_APP_SECRET_KEY=video-app-test-only",
            "-v",
            f"{ROOT / 'deploy/data/minio/init.sh'}:/tmp/init-minio.sh:ro",
            "--entrypoint",
            "sh",
            minio_image,
            "/tmp/init-minio.sh",
        )
        options = ["docker", "run", "--rm", "--name", backend, "--network", network, "--memory", "1g"]
        values = {
            "ENVIRONMENT": "test",
            "SECRET_KEY": "video-test-secret-only",
            "DEBUG": "false",
            "DB_HOST": "video-pg",
            "DB_PORT": "5432",
            "DB_USER": "postgres",
            "DB_PASSWORD": "video-test-only",
            "DB_NAME": "video_test",
            "DATABASE_URL": "",
            "STORAGE_BACKEND": "local",
            "MEDIA_DIR": "/tmp/video-test-media",
            "MONGO_URI": "",
            "MINIO_ENDPOINT": "video-minio:9000",
            "MINIO_ACCESS_KEY": "video_app",
            "MINIO_SECRET_KEY": "video-app-test-only",
            "VIDEO_MINIO_INTEGRATION": "1",
        }
        for key, value in values.items():
            options.extend(["-e", f"{key}={value}"])
        # Read source directly so reruns with --image test the current working tree.
        for source, target in (
            ("backend/app", "/app/app"),
            ("backend/scripts", "/app/scripts"),
            ("backend/etl", "/app/etl"),
            ("backend/tests", "/app/tests"),
            ("database", "/opt/database"),
            ("backend/pytest.ini", "/app/pytest.ini"),
        ):
            options.extend(["-v", f"{ROOT / source}:{target}:ro"])
        options.extend(
            [
                "--entrypoint",
                "sh",
                test_image,
                "-c",
                "mkdir -p /tmp/prometheus; python -m scripts.init_db > /tmp/video-bootstrap.log 2>&1 || "
                "{ cat /tmp/video-bootstrap.log; exit 1; }; "
                "python -m pytest -o addopts='' -p no:cacheprovider "
                "tests/test_product_video.py tests/test_v1_product.py tests/test_day3_data.py tests/test_day5_etl.py",
            ]
        )
        run(*options)
        print(json.dumps({"result": "PASS", "postgres": "private disposable", "minio": "private disposable"}))
    finally:
        for name in (backend, provisioner, minio, pg):
            subprocess.run(["docker", "rm", "-fv", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if created_network:
            subprocess.run(["docker", "network", "rm", network], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "image", "rm", test_image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not args.image:
            subprocess.run(["docker", "image", "rm", image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
