"""Expand init.sql includes into plain SQL for the pgAdmin Query Tool.

Run from any directory:
    python3 database/build_pgadmin_init.py --output /tmp/oldshop-init-pgadmin.sql

The generated script bootstraps an EMPTY database in one transaction. It is not
a migration. Keep database/init.sql and its included files as the source of truth.
"""

import argparse
from pathlib import Path

DATABASE_DIR = Path(__file__).resolve().parent


def expand(path: Path, stack: tuple[Path, ...] = ()) -> str:
    path = path.resolve()
    if not path.is_relative_to(DATABASE_DIR) or path in stack:
        raise ValueError(f"Invalid or recursive include: {path}")
    parts = [f"-- BEGIN SOURCE: {path.relative_to(DATABASE_DIR)}\n"]
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        if line.startswith("\\i "):
            # init.sql resolves includes relative to the database/ working directory.
            included = DATABASE_DIR / line[3:].strip()
            parts.append(expand(included, (*stack, path)))
        elif line.lstrip().startswith("\\"):
            raise ValueError(f"Unsupported psql command in {path.name}: {line.strip()}")
        else:
            parts.append(line)
    parts.append(f"\n-- END SOURCE: {path.relative_to(DATABASE_DIR)}\n")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(DATABASE_DIR):
        raise ValueError("Write generated SQL outside database/ to preserve the SQL sources")
    script = (
        "-- Generated from database/init.sql; use only on an EMPTY database.\n"
        "BEGIN;\n" + expand(DATABASE_DIR / "init.sql") + "\nCOMMIT;\n"
    )
    # Refuse to overwrite an existing file; choose a fresh output path for each build.
    with output.open("x", encoding="utf-8") as target:
        target.write(script)
    print(f"Created {output} ({len(script.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    main()
