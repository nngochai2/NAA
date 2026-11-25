import asyncio

import pytest
from conftest import type_row

from codegraph_mcp import server
from codegraph_mcp.cypher import queries
from codegraph_mcp.tools.callers import find_method_callers
from codegraph_mcp.tools.dependencies import get_class_dependencies, get_transitive_impact
from codegraph_mcp.tools.fields import get_field_impact
from codegraph_mcp.tools.interfaces import get_interface_implementations
from codegraph_mcp.tools.layers import get_class_layer_path
from codegraph_mcp.tools.overview import get_class_overview
from codegraph_mcp.tools.resolver import resolve_class_name


def test_all_tools_registered_read_only():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == {
        "tool_search_types",
        "tool_get_class_dependencies",
        "tool_get_transitive_impact",
        "tool_find_method_callers",
        "tool_get_field_impact",
        "tool_get_interface_implementations",
        "tool_get_class_layer_path",
        "tool_get_class_overview",
    }
    assert all(t.annotations.readOnlyHint for t in tools)


# ── resolver ──────────────────────────────────────────────────────────────────


def test_resolver_prefers_exact_match_among_many(graph):
    graph.on(queries.CLASS_SEARCH, [type_row("Invoice"), type_row("InvoiceLine")])
    assert resolve_class_name("Invoice") == ("Invoice", None)


def test_resolver_accepts_single_partial_match(graph):
    graph.on(queries.CLASS_SEARCH, [type_row("InvoiceEngineBizService")])
    assert resolve_class_name("InvoiceEngine") == ("InvoiceEngineBizService", None)


def test_resolver_lists_ambiguous_candidates(graph):
    graph.on(queries.CLASS_SEARCH, [type_row("InvoiceA"), type_row("InvoiceB")])
    name, message = resolve_class_name("Invoice")
    assert name is None
    assert "'Invoice' matches 2 types" in message
    assert "com.acme.InvoiceA" in message and "com.acme.InvoiceB" in message


def test_resolver_not_found(graph):
    name, message = resolve_class_name("Nope")
    assert name is None and "not found in the graph" in message


def test_unresolved_name_short_circuits_every_tool(graph):
    for call in (
        lambda: get_class_dependencies("Nope"),
        lambda: get_transitive_impact("Nope"),
        lambda: find_method_callers("run", "Nope"),
        lambda: get_field_impact("f", "Nope"),
        lambda: get_interface_implementations("Nope"),
        lambda: get_class_layer_path("Nope"),
        lambda: get_class_overview("Nope"),
    ):
        assert "not found in the graph" in call()
    assert {c for c, _ in graph.calls} == {queries.CLASS_SEARCH}


# ── search / dependencies ─────────────────────────────────────────────────────


def test_search_types(graph):
    assert server.tool_search_types("X") == "No types found matching 'X'."
    graph.on(queries.CLASS_SEARCH, [type_row("Foo")])
    assert server.tool_search_types("Fo") == "Types matching 'Fo' (1 found):\n\n  com.acme.Foo"


def test_class_dependencies_reports_invoke_count(graph):
    graph.on(queries.CLASS_SEARCH, [type_row("Svc")])
    graph.on(queries.CLASS_DEPENDENCIES, [{"fqn": "com.acme.A"}, {"fqn": "com.acme.B"}])
    graph.on(queries.CLASS_DEPENDENCY_INVOKE_COUNT, [{"invokeCount": 7}])
    out = get_class_dependencies("Svc")
    assert out.startswith("Types that directly depend on 'Svc' (2 found, 7 inbound")
    assert out.endswith("  com.acme.A\n  com.acme.B")


@pytest.mark.parametrize("requested, used", [(1, 1), (3, 3), (5, 5), (99, 5)])
def test_transitive_impact_caps_hops(graph, requested, used):
    graph.on(queries.CLASS_SEARCH, [type_row("Svc")])
    out = get_transitive_impact("Svc", requested)
    cypher, params = graph.calls[-1]
    assert f"[:DEPENDS_ON*1..{used}]" in cypher
    assert params == {"className": "Svc"}
    assert f"within {used} hops" in out


# ── callers / fields / interfaces ─────────────────────────────────────────────


def test_method_callers_unscoped_and_scoped(graph):
    graph.on(queries.METHOD_CALLERS, [{"callerSignature": "void a()"}])
    assert "across all classes (1 found)" in find_method_callers("exec")

    graph.on(queries.CLASS_SEARCH, [type_row("Dao")])
    graph.on(queries.METHOD_CALLERS_SCOPED, [{"callerSignature": "void b()"}])
    out = find_method_callers("find", "Da")
    assert "on class 'Dao' (1 found)" in out
    assert graph.calls[-1][1] == {"methodName": "find", "className": "Dao"}


def test_server_passes_empty_class_name_as_unscoped(graph):
    server.tool_find_method_callers("exec", "")
    assert graph.calls[-1][0] == queries.METHOD_CALLERS


def test_field_impact_splits_reads_and_writes(graph):
    graph.on(queries.CLASS_SEARCH, [type_row("Invoice")])
    graph.on(
        queries.FIELD_IMPACT,
        [
            {"access": "READS", "methodSignature": "int getTotal()"},
            {"access": "WRITES", "methodSignature": "void setTotal(int)"},
            {"access": "READS", "methodSignature": "String toString()"},
        ],
    )
    out = get_field_impact("total", "Invoice")
    assert "2 reader(s), 1 writer(s)" in out
    assert out.index("READS:") < out.index("int getTotal()") < out.index("WRITES:")


def test_interface_implementations(graph):
    graph.on(queries.CLASS_SEARCH, [type_row("Repo")])
    assert "No implementations found" in get_interface_implementations("Repo")
    graph.on(queries.INTERFACE_IMPLEMENTATIONS, [{"fqn": "com.acme.JdbcRepo"}])
    assert "  com.acme.JdbcRepo" in get_interface_implementations("Repo")


# ── layers / overview ─────────────────────────────────────────────────────────


def test_layer_path_keeps_only_known_layer_labels(graph):
    graph.on(queries.CLASS_SEARCH, [type_row("Dao")])
    graph.on(
        queries.CLASS_LAYER_PATH,
        [
            {"fqn": "com.acme.InvoiceFacade", "entryLayers": ["Type", "Class", "Facade"]},
            {"fqn": "com.acme.Thing", "entryLayers": ["Type"]},
        ],
    )
    out = get_class_layer_path("Dao")
    assert "[Facade] com.acme.InvoiceFacade" in out
    assert "[unknown layer] com.acme.Thing" in out


def test_layer_path_explains_missing_post_processing(graph):
    graph.on(queries.CLASS_SEARCH, [type_row("Dao")])
    assert "post_process.cypher" in get_class_layer_path("Dao")


def test_class_overview(graph):
    graph.on(queries.CLASS_SEARCH, [type_row("Invoice")])
    graph.on(
        queries.CLASS_OVERVIEW_TYPE, [{"fqn": "com.acme.Invoice", "typeLabels": ["Type", "Class"]}]
    )
    graph.on(queries.CLASS_OVERVIEW_EXTENDS, [{"fqn": "com.acme.Base"}])
    graph.on(queries.CLASS_OVERVIEW_IMPLEMENTS, [{"fqn": "java.io.Serializable"}])
    graph.on(queries.CLASS_OVERVIEW_FIELDS, [{"name": "total"}])
    graph.on(queries.CLASS_OVERVIEW_METHODS, [{"signature": "int getTotal()"}])

    out = get_class_overview("Invoice")

    assert out.startswith("Overview of Class: com.acme.Invoice")
    for expected in (
        "Extends: com.acme.Base",
        "Implements (1):",
        "Fields (1):",
        "    total",
        "Methods (1):",
        "    int getTotal()",
    ):
        assert expected in out


def test_class_overview_without_members(graph):
    graph.on(queries.CLASS_SEARCH, [type_row("Marker")])
    graph.on(queries.CLASS_OVERVIEW_TYPE, [{"fqn": "com.acme.Marker", "typeLabels": ["Type"]}])
    out = get_class_overview("Marker")
    assert out.startswith("Overview of Type: com.acme.Marker")
    assert "No declared fields or methods found." in out
