"""Check infrastructure without printing credentials; Day 6 HTTP detail probes increment view counts."""

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--resilience", action="store_true")
parser.add_argument("--day6", action="store_true", help="Require integrated Day 6 schema and API")
parser.add_argument("--day5", action="store_true", help="Require migration 005 and an ETL worker")
parser.add_argument("--output", type=Path)
args = parser.parse_args()
compose = ["docker", "compose", "--env-file", str(ROOT / "deploy/.env.data"),
           "-f", str(ROOT / "deploy/docker-compose.distributed.yml")]
if args.resilience:
    compose += ["--profile", "resilience"]


def run(*command):
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60)
    if result.returncode:
        # Commands are fixed and never contain credentials.
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Command failed")
    return result.stdout.strip()


def pg(service, query):
    return run(*compose, "exec", "-T", service, "sh", "-c",
               'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 "$@"',
               "psql", "-c", query)


mongo_connect = """
const user = encodeURIComponent(process.env.MONGO_INITDB_ROOT_USERNAME);
const password = encodeURIComponent(process.env.MONGO_INITDB_ROOT_PASSWORD);
const admin = new Mongo(`mongodb://${user}:${password}@mongo1:27017/admin?directConnection=true`).getDB('admin');
"""


def mongo(code):
    output = run(*compose, "exec", "-T", "mongo1", "mongosh", "--nodb", "--quiet", "--eval", mongo_connect + code)
    return json.loads(output.splitlines()[-1])


result = {"checked_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
          "profile": "resilience" if args.resilience else "base", "checks": {}}
checks = result["checks"]
checks["docker"] = run("docker", "info", "--format", "CPUs={{.NCPU}} MemoryBytes={{.MemTotal}} Version={{.ServerVersion}}")
ps = run(*compose, "ps", "--all", "--format", "json")
services = json.loads(ps) if ps.startswith("[") else [json.loads(line) for line in ps.splitlines() if line]
expected = {"pg-primary", "mongo1", "minio", "backend", "frontend"}
if args.resilience:
    expected |= {"pg-replica", "mongo2", "mongo3"}
for service in expected:
    row = next((row for row in services if row["Service"] == service), None)
    assert row and row["State"] == "running" and row["Health"] == "healthy", f"Unhealthy/missing service: {service}"
for service in ({"mongo-init", "mongo-expand"} if args.resilience else {"mongo-init"}):
    row = next((row for row in services if row["Service"] == service), None)
    assert row and row["State"] == "exited" and row["ExitCode"] == 0, f"Init job failed: {service}"
checks["healthy_services"] = sorted(expected)
checks["postgres_version"] = pg("pg-primary", "SHOW server_version")
assert pg("pg-primary", "SELECT pg_is_in_recovery()") == "f"
checks["baseline"] = pg("pg-primary", "SELECT count(*) FROM pg_tables WHERE schemaname='public'")
if pg("pg-primary", "SELECT to_regclass('public.schema_migrations') IS NOT NULL") == "t":
    checks["migrations"] = pg("pg-primary", "SELECT string_agg(version,',' ORDER BY version) FROM schema_migrations")
    assert checks["migrations"] in ("001,002,003,004", "001,002,003,004,005", "001,002,003,004,005,006")
    assert pg("pg-primary", "SELECT count(*) FROM pg_inherits WHERE inhparent='public.\"order\"'::regclass") == "4"
    assert pg("pg-primary", "SELECT count(*) FROM information_schema.columns WHERE table_name='users_full' AND table_schema='public'") == "20"
else:
    assert checks["baseline"] == "18", "Unrecognized baseline schema"
checks["orders"] = pg("pg-primary", 'SELECT count(*) FROM "order"')
checks["mongo"] = mongo("""
const s = admin.runCommand({replSetGetStatus: 1});
if (s.ok !== 1) throw new Error('Replica set is not ready');
print(JSON.stringify({set:s.set, version:admin.version(), members:s.members.map(m=>({host:m.name,state:m.stateStr}))}));
""")
states = [member["state"] for member in checks["mongo"]["members"]]
assert checks["mongo"]["set"] == "oldshop-rs" and states.count("PRIMARY") == 1
if args.resilience:
    assert len(states) == 3 and states.count("SECONDARY") == 2
checks["mongo_app_auth"] = mongo("""
const appUser = encodeURIComponent(process.env.MONGO_APP_USER);
const appPassword = encodeURIComponent(process.env.MONGO_APP_PASSWORD);
const name = encodeURIComponent(process.env.MONGO_DB);
const appDb = new Mongo(`mongodb://${appUser}:${appPassword}@mongo1:27017/${name}?directConnection=true&authSource=${name}`).getDB(process.env.MONGO_DB);
const auth = appDb.runCommand({connectionStatus:1});
if (auth.authInfo.authenticatedUsers.length !== 1) throw new Error('App authentication failed');
const probe = appDb.runCommand({find:'_day2_nonexistent_probe',filter:{},limit:1});
if (probe.ok !== 1) throw new Error('App read permission failed');
print(JSON.stringify({authenticated:true, database:process.env.MONGO_DB}));
""")
checks["http"] = json.loads(run(*compose, "exec", "-T", "backend", "python", "-c", """
import json, urllib.request
urls = ['http://127.0.0.1:8000/health/ready', 'http://127.0.0.1:8000/api/v1/categories',
        'http://minio:9000/minio/health/ready', 'http://frontend:8080/healthz',
        'http://frontend:8080/api/v1/categories']
result = {}
for url in urls:
    with urllib.request.urlopen(url, timeout=10) as response:
        assert response.status == 200
        result[url] = response.status
print(json.dumps(result))
"""))
has_etl = checks.get("migrations") in ("001,002,003,004,005", "001,002,003,004,005,006")
if args.day6:
    assert checks.get("migrations") == "001,002,003,004,005,006", "Day 6 migration 006 is required"
    checks["day6_api"] = json.loads(run(*compose, "exec", "-T", "backend", "python", "-m", "scripts.verify_day6"))
if args.day5:
    assert has_etl, "Day 5 has not been deployed; migration 005 is required"
if has_etl:
    row = next((row for row in services if row["Service"] == "etl-worker"), None)
    assert row and row["State"] == "running" and row["Health"] == "healthy", "Unhealthy/missing ETL worker"
    checks["healthy_services"].append("etl-worker")
    deadline = time.monotonic() + (120 if args.day6 else 0)
    while True:
        checks["etl"] = json.loads(run(*compose, "exec", "-T", "etl-worker", "python", "-m", "etl.run", "status"))
        current = checks["etl"]
        if (current["pending"] == 0 and current["dead"] == 0 and current.get("last_run")
                and current["last_run"]["status"] == "success") or time.monotonic() >= deadline:
            break
        time.sleep(2)
    assert checks["etl"]["pending"] == 0 and checks["etl"]["dead"] == 0
    assert checks["etl"]["last_run"] and checks["etl"]["last_run"]["status"] == "success"
else:
    checks["etl"] = {"deployed": False, "note": "Stack remains on its previous schema"}
checks["minio_version"] = run(*compose, "exec", "-T", "minio", "minio", "--version").splitlines()[0]
if args.resilience:
    target = pg("pg-primary", "SELECT pg_current_wal_lsn()")
    for _ in range(30):
        if pg("pg-replica", f"SELECT pg_is_in_recovery() AND pg_last_wal_replay_lsn() >= '{target}'::pg_lsn") == "t":
            break
        time.sleep(1)
    else:
        raise RuntimeError("Replica did not replay the primary LSN within 30 seconds")
    checks["pg_stat_replication"] = pg("pg-primary", "SELECT application_name||':'||state||':'||sync_state FROM pg_stat_replication")
    assert "oldshop-data-replica:streaming:async" in checks["pg_stat_replication"]
    checks["replica_orders"] = pg("pg-replica", 'SELECT count(*) FROM "order"')
    assert checks["replica_orders"] == checks["orders"]
ids = run(*compose, "ps", "--quiet").splitlines()
checks["resources"] = run("docker", "stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}} {{.CPUPerc}}", *ids)
result["result"] = "PASS"
encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
print(encoded)
