from graph_client import run_query
from cypher import queries
from tools.resolver import resolve_class_name


def get_interface_implementations(interface_name: str) -> str:
    interface_name, message = resolve_class_name(interface_name)
    if interface_name is None:
        return message

    rows = run_query(queries.INTERFACE_IMPLEMENTATIONS, {"interfaceName": interface_name})

    if not rows:
        return f"No implementations found for interface '{interface_name}'. Verify the interface name exists in the graph."

    lines = [f"Concrete implementations of '{interface_name}' ({len(rows)} found):\n"]
    for row in rows:
        lines.append(f"  {row['fqn']}")
    return "\n".join(lines)
