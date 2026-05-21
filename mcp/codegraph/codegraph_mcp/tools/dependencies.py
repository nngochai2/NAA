from graph_client import run_query
from cypher import queries


def get_class_dependencies(class_name: str) -> str:
    dependents = run_query(queries.CLASS_DEPENDENCIES, {"className": class_name})
    invoke_rows = run_query(queries.CLASS_DEPENDENCY_INVOKE_COUNT, {"className": class_name})

    if not dependents:
        return f"No types found that depend on '{class_name}'. Verify the class name exists in the graph."

    invoke_count = invoke_rows[0]["invokeCount"] if invoke_rows else 0
    lines = [f"Types that directly depend on '{class_name}' ({len(dependents)} found, {invoke_count} inbound method invocations):\n"]
    for row in dependents:
        lines.append(f"  {row['fqn']}")
    return "\n".join(lines)


def get_transitive_impact(class_name: str, max_hops: int = 3) -> str:
    capped_hops = min(max_hops, 5)
    # Neo4j does not accept a parameter for the hop count in variable-length patterns,
    # so we build one of five fixed queries selected by hop count.
    cypher_map = {
        1: "MATCH (t:Type {name: $className})<-[:DEPENDS_ON*1..1]-(a:Type) RETURN DISTINCT a.fqn AS fqn, a.name AS name ORDER BY a.fqn",
        2: "MATCH (t:Type {name: $className})<-[:DEPENDS_ON*1..2]-(a:Type) RETURN DISTINCT a.fqn AS fqn, a.name AS name ORDER BY a.fqn",
        3: "MATCH (t:Type {name: $className})<-[:DEPENDS_ON*1..3]-(a:Type) RETURN DISTINCT a.fqn AS fqn, a.name AS name ORDER BY a.fqn",
        4: "MATCH (t:Type {name: $className})<-[:DEPENDS_ON*1..4]-(a:Type) RETURN DISTINCT a.fqn AS fqn, a.name AS name ORDER BY a.fqn",
        5: "MATCH (t:Type {name: $className})<-[:DEPENDS_ON*1..5]-(a:Type) RETURN DISTINCT a.fqn AS fqn, a.name AS name ORDER BY a.fqn",
    }
    rows = run_query(cypher_map[capped_hops], {"className": class_name})

    if not rows:
        return f"No transitive dependents found for '{class_name}' within {capped_hops} hops. Verify the class name exists in the graph."

    lines = [f"Transitive impact of '{class_name}' (up to {capped_hops} hops via DEPENDS_ON, {len(rows)} types affected):\n"]
    for row in rows:
        lines.append(f"  {row['fqn']}")
    return "\n".join(lines)
