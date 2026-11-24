"""Lazily-connected Neo4j driver shared by all tools."""
from __future__ import annotations

import logging

from neo4j import GraphDatabase

from .config import get_config

logger = logging.getLogger(__name__)

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        cfg = get_config()
        auth = (cfg.neo4j_user, cfg.neo4j_password) if cfg.neo4j_password else None
        logger.info(
            "Connecting to Neo4j at %s (auth=%s)", cfg.neo4j_uri, "credentials" if auth else "none"
        )
        driver = GraphDatabase.driver(cfg.neo4j_uri, auth=auth)
        try:
            driver.verify_connectivity()
        except Exception as e:
            logger.error("Failed to connect to Neo4j at %s: %s", cfg.neo4j_uri, e)
            driver.close()
            raise
        logger.info("Neo4j connection established")
        # Only cache a verified driver, so the next call retries after a failure.
        _driver = driver
    return _driver


def run_query(cypher: str, params: dict | None = None) -> list[dict]:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(cypher, params or {})
        return [record.data() for record in result]


def close():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
