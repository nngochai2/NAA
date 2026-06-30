CLASS_SEARCH = """
MATCH (t:Type) WHERE t.name CONTAINS $className
RETURN t.name AS name, t.fqn AS fqn
ORDER BY t.name
"""

CLASS_DEPENDENCIES = """
MATCH (t:Type {name: $className})<-[:DEPENDS_ON]-(dependent:Type)
RETURN dependent.fqn AS fqn, dependent.name AS name
ORDER BY dependent.fqn
"""

CLASS_DEPENDENCY_INVOKE_COUNT = """
MATCH (t:Type {name: $className})-[:DECLARES]->(m:Method)<-[:INVOKES]-(caller:Method)
RETURN count(caller) AS invokeCount
"""

TRANSITIVE_IMPACT = """
MATCH (t:Type {name: $className})<-[:DEPENDS_ON*1..$maxHops]-(affected:Type)
RETURN DISTINCT affected.fqn AS fqn, affected.name AS name
ORDER BY affected.fqn
"""

METHOD_CALLERS = """
MATCH (caller:Method)-[:INVOKES]->(m:Method)
WHERE m.name CONTAINS $methodName
RETURN DISTINCT caller.signature AS callerSignature, caller.name AS callerName
ORDER BY caller.signature
"""

METHOD_CALLERS_SCOPED = """
MATCH (t:Type {name: $className})-[:DECLARES]->(m:Method)
WHERE m.name CONTAINS $methodName
WITH m
MATCH (caller:Method)-[:INVOKES]->(m)
RETURN DISTINCT caller.signature AS callerSignature, caller.name AS callerName
ORDER BY caller.signature
"""

FIELD_IMPACT = """
MATCH (t:Type {name: $className})-[:DECLARES]->(f:Field {name: $fieldName})
WITH f
MATCH (m:Method)-[r:READS|WRITES]->(f)
RETURN m.signature AS methodSignature, m.name AS methodName, type(r) AS access
ORDER BY m.signature
"""

INTERFACE_IMPLEMENTATIONS = """
MATCH (impl:Type)-[:IMPLEMENTS]->(iface:Type {name: $interfaceName})
RETURN impl.fqn AS fqn, impl.name AS name
ORDER BY impl.fqn
"""

CLASS_LAYER_PATH = """
MATCH (entry:Type)-[:INVOKES*1..6]->(m:Method)<-[:DECLARES]-(t:Type {name: $className})
WHERE any(label IN labels(entry) WHERE label IN
      ['Delegator','BusinessController','Facade','FacadeBean','Finder','Searcher'])
RETURN DISTINCT labels(entry) AS entryLayers, entry.fqn AS fqn
ORDER BY fqn
"""

CLASS_OVERVIEW_TYPE = """
MATCH (t:Type {name: $className})
RETURN t.fqn AS fqn, t.name AS name, labels(t) AS typeLabels
"""

CLASS_OVERVIEW_METHODS = """
MATCH (t:Type {name: $className})-[:DECLARES]->(m:Method)
RETURN m.name AS name, m.signature AS signature
ORDER BY m.name
"""

CLASS_OVERVIEW_FIELDS = """
MATCH (t:Type {name: $className})-[:DECLARES]->(f:Field)
RETURN f.name AS name
ORDER BY f.name
"""

CLASS_OVERVIEW_IMPLEMENTS = """
MATCH (t:Type {name: $className})-[:IMPLEMENTS]->(iface:Type)
RETURN iface.fqn AS fqn, iface.name AS name
ORDER BY iface.fqn
"""

CLASS_OVERVIEW_EXTENDS = """
MATCH (t:Type {name: $className})-[:EXTENDS]->(parent:Type)
RETURN parent.fqn AS fqn, parent.name AS name
"""
