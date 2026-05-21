from graph_client import run_query
from cypher import queries


def get_class_overview(class_name: str) -> str:
    type_rows = run_query(queries.CLASS_OVERVIEW_TYPE, {"className": class_name})

    if not type_rows:
        return f"Class '{class_name}' not found in the graph. Verify the class name (use simple name, not FQN)."

    t = type_rows[0]
    kind_labels = [l for l in t["typeLabels"] if l not in ("Type",)]
    kind = ", ".join(kind_labels) if kind_labels else "Type"

    methods = run_query(queries.CLASS_OVERVIEW_METHODS, {"className": class_name})
    fields = run_query(queries.CLASS_OVERVIEW_FIELDS, {"className": class_name})
    implements = run_query(queries.CLASS_OVERVIEW_IMPLEMENTS, {"className": class_name})
    extends = run_query(queries.CLASS_OVERVIEW_EXTENDS, {"className": class_name})

    lines = [
        f"Overview of {kind}: {t['fqn']}\n",
    ]

    if extends:
        lines.append(f"  Extends: {extends[0]['fqn']}")

    if implements:
        lines.append(f"  Implements ({len(implements)}):")
        for row in implements:
            lines.append(f"    {row['fqn']}")

    if fields:
        lines.append(f"\n  Fields ({len(fields)}):")
        for row in fields:
            lines.append(f"    {row['name']}")

    if methods:
        lines.append(f"\n  Methods ({len(methods)}):")
        for row in methods:
            lines.append(f"    {row['signature']}")

    if not fields and not methods:
        lines.append("  No declared fields or methods found.")

    return "\n".join(lines)
