// Apply architectural layer labels by class name suffix.
// Run this once after every jQAssistant scan via cypher-shell or Neo4j Browser.

MATCH (t:Type) WHERE t.name ENDS WITH 'Delegator'
SET t:Delegator;

MATCH (t:Type) WHERE t.name ENDS WITH 'BusinessController'
SET t:BusinessController;

MATCH (t:Type) WHERE t.name ENDS WITH 'Facade'
  AND NOT t.name ENDS WITH 'FacadeBean'
SET t:Facade;

MATCH (t:Type) WHERE t.name ENDS WITH 'FacadeBean'
SET t:FacadeBean;

MATCH (t:Type) WHERE t.name ENDS WITH 'Finder'
SET t:Finder;

MATCH (t:Type) WHERE t.name ENDS WITH 'Searcher'
SET t:Searcher;

// Verify — should return non-zero counts for each layer if the codebase has them:
MATCH (t)
WHERE any(label IN labels(t) WHERE label IN
      ['Delegator','BusinessController','Facade','FacadeBean','Finder','Searcher'])
RETURN labels(t) AS Layer, count(t) AS Count
ORDER BY Count DESC;
