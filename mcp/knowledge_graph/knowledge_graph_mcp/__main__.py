"""Entry point: python -m knowledge_graph_mcp"""
from .config import get_config
from .server import mcp


def main() -> None:
    cfg = get_config()
    print(f"Knowledge Graph MCP server starting — SSE on http://{cfg.host}:{cfg.port}/sse")
    print(f"Neo4j: {cfg.neo4j_uri}")
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
