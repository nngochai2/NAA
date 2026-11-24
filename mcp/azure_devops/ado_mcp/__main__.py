"""Entry point: python -m ado_mcp"""
import logging

import uvicorn

from .config import get_config
from .server import create_starlette_app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = get_config()  # fail fast on missing credentials
    uvicorn.run(create_starlette_app(), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
