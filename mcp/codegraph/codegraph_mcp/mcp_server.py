import os
import logging
import atexit
from mcp.server.fastmcp import FastMCP
import graph_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
from tools.dependencies import get_class_dependencies, get_transitive_impact
from tools.callers import find_method_callers
from tools.fields import get_field_impact
from tools.interfaces import get_interface_implementations
from tools.layers import get_class_layer_path
from tools.overview import get_class_overview

mcp = FastMCP(
    "codegraph",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8001")),
)

atexit.register(graph_client.close)


@mcp.tool()
def tool_get_class_dependencies(class_name: str) -> str:
    """Return all types that directly depend on a class and the count of inbound method invocations.

    Use this to answer: 'What breaks if I change this class?'
    Pass the simple class name (e.g. 'GenericDelegator'), not the fully-qualified name.
    """
    return get_class_dependencies(class_name)


@mcp.tool()
def tool_get_transitive_impact(class_name: str, max_hops: int = 3) -> str:
    """Return all types reachable within max_hops via DEPENDS_ON from the given class.

    Use this to answer: 'What is the full blast radius of changing this class?'
    max_hops is capped at 5. Pass the simple class name, not the FQN.
    """
    return get_transitive_impact(class_name, max_hops)


@mcp.tool()
def tool_find_method_callers(method_name: str, class_name: str = "") -> str:
    """Return all methods that invoke any method whose name contains method_name.

    Use this to answer: 'Who calls this method?'
    Optionally scope the search to a specific class by passing class_name.
    Pass a partial or full method name (e.g. 'execute' or 'findByPrimaryKey').
    """
    return find_method_callers(method_name, class_name or None)


@mcp.tool()
def tool_get_field_impact(field_name: str, class_name: str) -> str:
    """Return all methods that read or write the named field on the given class.

    Use this to answer: 'If I rename or change this field, which methods need updating?'
    Both field_name and class_name are required.
    """
    return get_field_impact(field_name, class_name)


@mcp.tool()
def tool_get_interface_implementations(interface_name: str) -> str:
    """Return all concrete classes that implement the given interface.

    Use this to answer: 'What are all the implementations of this interface?'
    Pass the simple interface name (e.g. 'GenericValue'), not the FQN.
    """
    return get_interface_implementations(interface_name)


@mcp.tool()
def tool_get_class_layer_path(class_name: str) -> str:
    """Return architectural layer entry points (Delegator, Facade, etc.) that call into this class.

    Use this to answer: 'Which layer does this class belong to, and what calls into it from above?'
    Requires layer labels to have been applied by post_process.cypher.
    Pass the simple class name, not the FQN.
    """
    return get_class_layer_path(class_name)


@mcp.tool()
def tool_get_class_overview(class_name: str) -> str:
    """Return a summary of a class: package, methods, fields, interfaces, and superclass.

    Use this as a quick orientation before editing a class.
    Pass the simple class name (e.g. 'GenericDelegator'), not the FQN.
    """
    return get_class_overview(class_name)


if __name__ == "__main__":
    mcp.run(transport="sse")
