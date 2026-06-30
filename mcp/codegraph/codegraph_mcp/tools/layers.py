from graph_client import run_query
from cypher import queries
from tools.resolver import resolve_class_name

_LAYER_LABELS = {"Delegator", "BusinessController", "Facade", "FacadeBean", "Finder", "Searcher"}


def get_class_layer_path(class_name: str) -> str:
    class_name, message = resolve_class_name(class_name)
    if class_name is None:
        return message

    rows = run_query(queries.CLASS_LAYER_PATH, {"className": class_name})

    if not rows:
        return (
            f"No architectural layer entry points found calling into '{class_name}'. "
            "This may mean the class is not reachable from a layer entry point within 6 hops, "
            "or that post_process.cypher has not been run to apply layer labels."
        )

    lines = [f"Architectural layer callers of '{class_name}' ({len(rows)} entry points found):\n"]
    for row in rows:
        layer_labels = [l for l in row["entryLayers"] if l in _LAYER_LABELS]
        layer_str = ", ".join(layer_labels) if layer_labels else "unknown layer"
        lines.append(f"  [{layer_str}] {row['fqn']}")
    return "\n".join(lines)
