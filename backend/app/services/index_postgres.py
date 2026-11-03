"""Restricted DDL compiler and read-only PostgreSQL catalog reconciliation."""

import re

from app.services.index_config import PGIndex


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


def literal(value):
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("SQL strings cannot contain NUL")
        # Explicit escape strings are independent of standard_conforming_strings.
        return "E'" + value.replace("\\", "\\\\").replace("'", "''") + "'"
    if type(value) is bool:
        return "TRUE" if value else "FALSE"
    if type(value) in (int, float):
        import math

        if not math.isfinite(value):
            raise ValueError("Nonfinite SQL literal")
        return str(value)
    raise ValueError("Unsupported SQL literal")


def predicate_sql(predicate):
    if predicate is None:
        return None
    for group, joiner in ((predicate.all, " AND "), (predicate.any, " OR ")):
        if group is not None:
            return "(" + joiner.join(predicate_sql(p) for p in group) + ")"
    column = identifier(predicate.column)
    if predicate.op == "in":
        return f"({column} IN ({', '.join(literal(v) for v in predicate.value)}))"
    operator = {"eq": "=", "ne": "<>", "lt": "<", "le": "<=", "gt": ">", "ge": ">=", "has_key": "?"}
    return f"({column} {operator[predicate.op]} {literal(predicate.value)})"


def key_sql(key, method):
    result = identifier(key.column)
    if key.expression == "tsvector":
        result = f"to_tsvector({literal(key.config)}, {result})"
    if key.opclass:
        result += " " + identifier(key.opclass)
    if method == "btree":
        order = key.order or "ASC"
        result += f" {order} NULLS {key.nulls or ('FIRST' if order == 'DESC' else 'LAST')}"
    return result


def create_sql(index: PGIndex):
    if index.managed_by != "application":
        raise ValueError("Constraint indexes are inventoried, never compiled as standalone DDL")
    statement = (
        f"CREATE {'UNIQUE ' if index.unique else ''}INDEX {identifier(index.name)} ON "
        f"{identifier(index.schema_name)}.{identifier(index.table)} USING {index.method} "
        f"({', '.join(key_sql(k, index.method) for k in index.keys)})"
    )
    if index.predicate:
        statement += " WHERE " + predicate_sql(index.predicate)
    return statement + ";"


# This parser compares only the expression language this contract emits. Unknown
# syntax fails closed as a conflict; string case, AND/OR grouping remain significant.
TOKEN = re.compile(
    r"\s*(E?'(?:''|\\.|[^'])*'|\"(?:\"\"|[^\"])*\"|::|<>|!=|<=|>=|[(),\[\]=?<>-]|"
    r"[0-9]+(?:\.[0-9]+)?|[a-zA-Z_][a-zA-Z0-9_$]*)"
)


def expression_tree(source):
    if not source:
        return None
    tokens = []
    position = 0
    while position < len(source):
        match = TOKEN.match(source, position)
        if not match:
            if not source[position:].strip():
                break
            raise ValueError("Unsupported catalog expression")
        token = match[1]
        if token.startswith(("'", "E'")):
            escaped = token.startswith("E'")
            value = token[2 if escaped else 1 : -1].replace("''", "'")
            if escaped:
                value = re.sub(r"\\(.)", r"\1", value)
            tokens.append(("string", value))
        elif token.startswith('"'):
            tokens.append(("identifier", token[1:-1].replace('""', '"')))
        else:
            tokens.append(token.lower())
        position = match.end()
    # Casts introduced by pg_get_expr are ignored only for supported literal types.
    cleaned = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "::":
            if i + 1 >= len(tokens) or tokens[i + 1] not in ("text", "integer", "numeric", "boolean", "regconfig"):
                raise ValueError("Unsupported catalog cast")
            i += 2
            if tokens[i : i + 2] == ["[", "]"]:
                i += 2
        else:
            cleaned.append(tokens[i])
            i += 1
    tokens = cleaned
    offset = 0

    def take(expected=None):
        nonlocal offset
        if offset >= len(tokens) or (expected is not None and tokens[offset] != expected):
            raise ValueError("Unsupported catalog expression grammar")
        token = tokens[offset]
        offset += 1
        return token

    def peek():
        return tokens[offset] if offset < len(tokens) else None

    def atom():
        token = take()
        if token == "(":
            value = logical_or()
            take(")")
            return value
        if token == "-":
            return ("number", -float(take()))
        if isinstance(token, tuple):
            return token
        if token in ("true", "false"):
            return ("bool", token == "true")
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", token):
            return ("number", float(token))
        if token == "array":
            take("[")
            values = [atom()]
            while peek() == ",":
                take(",")
                values.append(atom())
            take("]")
            return ("array", tuple(values))
        if token in ("any", "to_tsvector") and peek() == "(":
            take("(")
            values = [logical_or()]
            while peek() == ",":
                take(",")
                values.append(logical_or())
            take(")")
            return (token, tuple(values))
        return ("identifier", token)

    def comparison():
        if peek() == "not":
            take("not")
            return ("=", atom(), ("bool", False))
        left = atom()
        if peek() == "in":
            take("in")
            take("(")
            values = [atom()]
            while peek() == ",":
                take(",")
                values.append(atom())
            take(")")
            return ("in", left, tuple(values))
        if peek() in ("=", "<>", "!=", "<", "<=", ">", ">=", "?"):
            operator = take()
            right = atom()
            if operator == "=" and right[0] == "any":
                return ("in", left, right[1][0][1])
            return ("<>" if operator == "!=" else operator, left, right)
        return left

    def group(joiner, parser):
        values = [parser()]
        while peek() == joiner:
            take(joiner)
            values.append(parser())
        if len(values) == 1:
            return values[0]
        # PostgreSQL flattens associative expressions, preserving order.
        flat = []
        for value in values:
            flat.extend(value[1] if value[0] == joiner else [value])
        return (joiner, tuple(flat))

    def logical_and():
        return group("and", comparison)

    def logical_or():
        return group("or", logical_and)

    tree = logical_or()
    if offset != len(tokens):
        raise ValueError("Trailing catalog expression tokens")
    return tree


def inventory(connection):
    """Return only metadata, including constraint ownership and attached index OIDs."""
    from psycopg2.extras import RealDictCursor

    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
            SELECT ix.oid::bigint AS oid,n.nspname AS schema,ix.relname AS name,t.relname AS table,
              t.oid::bigint AS table_oid,t.relkind='p' AS partitioned,t.relispartition AS table_partition,
              am.amname AS method,i.indisunique AS unique,i.indisvalid AS valid,
              i.indisready AS ready,i.indislive AS live,i.indnullsnotdistinct AS nulls_not_distinct,
              i.indnatts-i.indnkeyatts AS includes,
              EXISTS(SELECT 1 FROM pg_constraint c
                     WHERE c.conindid=ix.oid AND c.contype IN ('p','u','x')) AS constraint_owned,
              (SELECT inhparent::bigint FROM pg_inherits WHERE inhrelid=ix.oid LIMIT 1) AS parent,
              pg_get_expr(i.indpred,i.indrelid) AS predicate,
              ARRAY(SELECT pg_get_indexdef(ix.oid,k,true) FROM generate_series(1,i.indnkeyatts) k) AS expressions,
              ARRAY(SELECT a.attname FROM unnest(i.indkey) WITH ORDINALITY x(attnum,pos)
                    LEFT JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=x.attnum
                    WHERE x.pos<=i.indnkeyatts ORDER BY x.pos) AS columns,
              i.indoption::smallint[] AS flags,
              ARRAY(SELECT CASE WHEN c.opcdefault THEN '' ELSE ns.nspname||'.'||c.opcname END
                    FROM unnest(i.indclass) WITH ORDINALITY x(oid,pos)
                    JOIN pg_opclass c ON c.oid=x.oid JOIN pg_namespace ns ON ns.oid=c.opcnamespace
                    ORDER BY x.pos) AS opclasses,
              NOT EXISTS(SELECT 1 FROM unnest(i.indcollation) WITH ORDINALITY x(oid,pos)
                    LEFT JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=i.indkey[x.pos::int-1]
                    WHERE x.oid<>COALESCE(a.attcollation,0)) AS default_collation,
              ix.reloptions AS storage_options
            FROM pg_index i JOIN pg_class ix ON ix.oid=i.indexrelid
            JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_am am ON am.oid=ix.relam WHERE n.nspname='public' ORDER BY t.relname,ix.relname
        """)
        indexes = [dict(row) for row in cursor.fetchall()]
        cursor.execute("""SELECT n.nspname,t.relname,a.attname,t.oid::bigint
            FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum>0 AND NOT a.attisdropped
            WHERE n.nspname='public' AND t.relkind IN ('r','p')""")
        columns = {}
        for row in cursor.fetchall():
            schema, table, column, oid = row.values()
            columns.setdefault((schema, table), {"oid": oid, "columns": set()})["columns"].add(column)
        cursor.execute("SELECT inhparent::bigint,inhrelid::bigint FROM pg_inherits")
        inheritance = [(r["inhparent"], r["inhrelid"]) for r in cursor.fetchall()]
    return indexes, columns, inheritance


def differences(index, actual):
    reasons = []
    expected = {
        "method": index.method,
        "unique": index.unique,
        "valid": True,
        "ready": True,
        "live": True,
        "nulls_not_distinct": False,
        "includes": 0,
        "constraint_owned": index.managed_by == "constraint",
        "default_collation": True,
    }
    for key, value in expected.items():
        if actual[key] != value:
            reasons.append(key)
    if actual["storage_options"]:
        reasons.append("storage_options")
    expected_columns = [None if k.expression else k.column for k in index.keys]
    expected_flags = [
        (1 if k.order == "DESC" else 0)
        + (2 if (k.nulls or ("FIRST" if k.order == "DESC" else "LAST")) == "FIRST" else 0)
        if index.method == "btree"
        else 0
        for k in index.keys
    ]
    if actual["columns"] != expected_columns:
        reasons.append("keys")
    if actual["flags"] != expected_flags:
        reasons.append("order/nulls")
    if actual["opclasses"] != [("public." + k.opclass) if k.opclass else "" for k in index.keys]:
        reasons.append("opclass")
    try:
        if expression_tree(actual["predicate"]) != expression_tree(predicate_sql(index.predicate)):
            reasons.append("predicate")
        for key, source in zip(index.keys, actual["expressions"], strict=True):
            if key.expression and expression_tree(source) != expression_tree(
                f"to_tsvector({literal(key.config)}, {identifier(key.column)})"
            ):
                reasons.append("expression")
    except ValueError:
        reasons.append("unsupported_expression")
    return reasons


def plan_postgres(connection, catalog):
    indexes, columns, inheritance = inventory(connection)
    by_name = {(i["schema"], i["name"]): i for i in indexes}
    by_parent = {}
    for row in indexes:
        by_parent.setdefault(row["parent"], []).append(row)
    table_children = {}
    for parent, child in inheritance:
        table_children.setdefault(parent, set()).add(child)
    managed_oids = set()
    entries = []
    for spec in catalog.postgresql:
        actual = by_name.get((spec.schema_name, spec.name))
        table = columns.get((spec.schema_name, spec.table))
        reasons = []
        partition_indexes = []

        def predicate_columns(predicate):
            if predicate is None:
                return set()
            if predicate.column:
                return {predicate.column}
            return set().union(*(predicate_columns(p) for p in (predicate.all or predicate.any)))

        required_columns = {k.column for k in spec.keys} | predicate_columns(spec.predicate)
        if not table or not required_columns.issubset(table["columns"]):
            reasons.append("missing_table_or_column")
        if actual:
            managed_oids.add(actual["oid"])
            if actual["table"] != spec.table:
                reasons.append("table")
            reasons += differences(spec, actual)
            pending = [actual]
            while pending:
                parent = pending.pop()
                children = by_parent.get(parent["oid"], [])
                expected_tables = table_children.get(parent["table_oid"], set())
                if {c["table_oid"] for c in children} != expected_tables:
                    reasons.append("partition_attachments")
                for child in children:
                    managed_oids.add(child["oid"])
                    child_reasons = differences(spec, child)
                    reasons += ["partition:" + r for r in child_reasons]
                    partition_indexes.append(
                        {
                            "name": child["name"],
                            "table": child["table"],
                            "valid": child["valid"],
                            "reasons": child_reasons,
                        }
                    )
                    pending.append(child)
        elif spec.managed_by == "constraint":
            reasons.append("missing_constraint_index")
        entries.append(
            {
                "name": spec.name,
                "schema": spec.schema_name,
                "table": spec.table,
                "status": "conflict" if reasons else "matched" if actual else "missing",
                "reasons": sorted(set(reasons)),
                "managed_by": spec.managed_by,
                "actual": {
                    key: actual[key]
                    for key in (
                        "method",
                        "unique",
                        "columns",
                        "expressions",
                        "flags",
                        "opclasses",
                        "predicate",
                        "valid",
                        "ready",
                        "live",
                        "constraint_owned",
                        "includes",
                        "default_collation",
                    )
                }
                if actual
                else None,
                "partition_indexes": partition_indexes,
            }
        )
    unmanaged = [
        {
            "schema": i["schema"],
            "table": i["table"],
            "name": i["name"],
            "constraint_owned": i["constraint_owned"],
            "attached": i["parent"] is not None,
        }
        for i in indexes
        if i["oid"] not in managed_oids
    ]
    return {"indexes": entries, "unmanaged": unmanaged}
