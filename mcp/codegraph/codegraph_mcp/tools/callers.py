from graph_client import run_query
from cypher import queries
from tools.resolver import resolve_class_name


def find_method_callers(method_name: str, class_name: str | None = None) -> str:
    if class_name:
        class_name, message = resolve_class_name(class_name)
        if class_name is None:
            return message
        rows = run_query(queries.METHOD_CALLERS_SCOPED, {"methodName": method_name, "className": class_name})
        scope_desc = f"on class '{class_name}'"
    else:
        rows = run_query(queries.METHOD_CALLERS, {"methodName": method_name})
        scope_desc = "across all classes"

    if not rows:
        return f"No callers found for method containing '{method_name}' {scope_desc}. Verify the method name exists in the graph."

    lines = [f"Callers of '{method_name}' {scope_desc} ({len(rows)} found):\n"]
    for row in rows:
        lines.append(f"  {row['callerSignature']}")
    return "\n".join(lines)
