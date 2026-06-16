import os
import logging
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
_USER = os.getenv("NEO4J_USER", "neo4j")
_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        auth = (_USER, _PASSWORD) if _PASSWORD else None
        logger.info("Connecting to Neo4j at %s (auth=%s)", _URI, "credentials" if auth else "none")
        try:
            _driver = GraphDatabase.driver(_URI, auth=auth)
            _driver.verify_connectivity()
            logger.info("Neo4j connection established")
        except Exception as e:
            logger.error("Failed to connect to Neo4j at %s: %s", _URI, e)
            raise
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
