"""Entry point for the Jira MCP server."""
import os

import uvicorn
from dotenv import load_dotenv

from .server import create_starlette_app


def main() -> None:
    load_dotenv()
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8005"))
    print("Jira MCP server starting")
    print(f"SSE endpoint: http://{host}:{port}/sse")
    uvicorn.run(create_starlette_app(), host=host, port=port)


if __name__ == "__main__":
    main()
