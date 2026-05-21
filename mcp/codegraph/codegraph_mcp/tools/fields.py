from graph_client import run_query
from cypher import queries


def get_field_impact(field_name: str, class_name: str) -> str:
    rows = run_query(queries.FIELD_IMPACT, {"fieldName": field_name, "className": class_name})

    if not rows:
        return (
            f"No methods found that read or write field '{field_name}' on '{class_name}'. "
            "Verify both the field and class name exist in the graph."
        )

    reads = [r for r in rows if r["access"] == "READS"]
    writes = [r for r in rows if r["access"] == "WRITES"]

    lines = [f"Field '{field_name}' on '{class_name}' — {len(reads)} reader(s), {len(writes)} writer(s):\n"]

    if reads:
        lines.append("  READS:")
        for r in reads:
            lines.append(f"    {r['methodSignature']}")

    if writes:
        lines.append("  WRITES:")
        for r in writes:
            lines.append(f"    {r['methodSignature']}")

    return "\n".join(lines)
