"""Entry point: python -m codegraph_mcp"""

import atexit
import logging

from . import graph_client
from .server import mcp


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    atexit.register(graph_client.close)
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
