import os
from neo4j import GraphDatabase

_URI = os.getenv("NEO4J_URI", "bolt://localhost:7688")
_USER = os.getenv("NEO4J_USER", "neo4j")
_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(_URI, auth=(_USER, _PASSWORD))
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
