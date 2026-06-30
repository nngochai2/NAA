from graph_client import run_query
from cypher import queries


def resolve_class_name(class_name: str) -> tuple[str | None, str | None]:
    """
    Resolve a possibly-partial class name to an exact name in the graph.

    Returns (exact_name, None) on success.
    Returns (None, message) when the name is ambiguous or not found — the caller
    should surface that message directly to the agent.
    """
    candidates = run_query(queries.CLASS_SEARCH, {"className": class_name})

    exact = [r for r in candidates if r["name"] == class_name]
    if exact:
        return class_name, None

    if not candidates:
        return None, (
            f"Class '{class_name}' not found in the graph. "
            "Verify the class name or use tool_search_types to discover matching names."
        )

    if len(candidates) == 1:
        return candidates[0]["name"], None

    lines = [f"'{class_name}' matches {len(candidates)} types — re-query with the exact name:\n"]
    for r in candidates:
        lines.append(f"  {r['fqn']}")
    return None, "\n".join(lines)
