"""
Neo4j query helpers for the MCP server.
 
All queries use parameterised Cypher — no string interpolation of user input.
The only exception is the variable-length path hop count, which is clamped
to an integer in the range 1–3 before being embedded in the query string.
"""
 
from neo4j import GraphDatabase
 
 
class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
 
    def close(self) -> None:
        self._driver.close()
 
    def verify(self) -> bool:
        try:
            with self._driver.session() as s:
                s.run("RETURN 1").single()
            return True
        except Exception:
            return False
 
    # ── Tools ────────────────────────────────────────────────────────────────
 
    def search_notes(self, query: str, limit: int = 10) -> list[dict]:
        """Full-text search on note title/subfolder AND BR br_id/title/uc_id."""
        cypher = """
            MATCH (n:Note)
            WHERE toLower(n.title)     CONTAINS toLower($kw)
               OR toLower(n.subfolder) CONTAINS toLower($kw)
            RETURN n.title          AS title,
                   n.type           AS type,
                   n.subfolder      AS subfolder,
                   n.status         AS status,
                   n.backlink_count AS backlinks,
                   n.path           AS path,
                   null             AS br_id,
                   null             AS uc_id,
                   null             AS flow_name,
                   'note'           AS result_type
            UNION ALL
            MATCH (b:BR)
            WHERE toLower(b.br_id)    CONTAINS toLower($kw)
               OR toLower(b.title)    CONTAINS toLower($kw)
               OR toLower(coalesce(b.uc_id,      '')) CONTAINS toLower($kw)
               OR toLower(coalesce(b.flow_name,  '')) CONTAINS toLower($kw)
            RETURN b.title              AS title,
                   'BR'                 AS type,
                   coalesce(b.uc_id, '') AS subfolder,
                   coalesce(b.doc_type, '') AS status,
                   0                    AS backlinks,
                   null                 AS path,
                   b.br_id              AS br_id,
                   b.uc_id              AS uc_id,
                   b.flow_name          AS flow_name,
                   'br'                 AS result_type
            ORDER BY backlinks DESC
            LIMIT $limit
        """
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher, kw=query, limit=limit)]
 
    def get_note(self, title: str) -> dict | None:
        """Full details for one note plus its outgoing links."""
        cypher = """
            MATCH (n:Note {title: $title})
            OPTIONAL MATCH (n)-[r]->(m:Note)
            RETURN n.title          AS title,
                   n.type           AS type,
                   n.subfolder      AS subfolder,
                   n.status         AS status,
                   n.created_at     AS created_at,
                   n.word_count     AS word_count,
                   n.backlink_count AS backlinks,
                   n.path           AS path,
                   n.body           AS body,
                   n.summary        AS summary,
                   collect({
                       target: m.title,
                       rel:    type(r),
                       alias:  r.alias
                   }) AS links
        """
        with self._driver.session() as s:
            result = s.run(cypher, title=title).single()
            return dict(result) if result else None
 
    def get_related_notes(self, title: str, hops: int = 1) -> list[dict]:
        """Traverse relationships outward from a note. hops is clamped 1–3."""
        hops = min(max(int(hops), 1), 3)
        # hops is a safe integer — no user string is embedded.
        cypher = (
            f"MATCH (n:Note {{title: $title}})-[r*1..{hops}]-(m:Note) "
            "WHERE n <> m "
            "RETURN DISTINCT m.title AS title, m.type AS type, "
            "       m.subfolder AS subfolder, type(r[0]) AS relationship "
            "ORDER BY m.type, m.title "
            "LIMIT 50"
        )
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher, title=title)]
 
    def get_notes_by_type(self, note_type: str, limit: int = 20) -> list[dict]:
        """List notes filtered by type, sorted by backlink count."""
        cypher = """
            MATCH (n:Note {type: $type})
            RETURN n.title          AS title,
                   n.subfolder      AS subfolder,
                   n.status         AS status,
                   n.backlink_count AS backlinks
            ORDER BY n.backlink_count DESC
            LIMIT $limit
        """
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher, type=note_type, limit=limit)]
 
    def get_tagged_notes(self, tag: str, note_type: str | None = None, limit: int = 50) -> list[dict]:
        """
        Return notes that are tagged with (or linked to) the given tag/note title.
        Optionally filter by note type.
        """
        if note_type:
            cypher = """
                MATCH (n:Note)-[]->(t:Note {title: $tag})
                WHERE n.type = $type
                RETURN n.title   AS title,
                       n.type    AS type,
                       n.status  AS status,
                       n.subfolder AS subfolder,
                       n.summary AS summary
                ORDER BY n.status, n.title
                LIMIT $limit
            """
            with self._driver.session() as s:
                return [dict(r) for r in s.run(cypher, tag=tag, type=note_type, limit=limit)]
        else:
            cypher = """
                MATCH (n:Note)-[]->(t:Note {title: $tag})
                RETURN n.title   AS title,
                       n.type    AS type,
                       n.status  AS status,
                       n.subfolder AS subfolder,
                       n.summary AS summary
                ORDER BY n.type, n.status, n.title
                LIMIT $limit
            """
            with self._driver.session() as s:
                return [dict(r) for r in s.run(cypher, tag=tag, limit=limit)]
 
    def get_backlinks(self, title: str) -> list[dict]:
        """All notes that have an outgoing edge pointing to the given note."""
        cypher = """
            MATCH (src:Note)-[r]->(n:Note {title: $title})
            RETURN src.title  AS source,
                   type(r)    AS relationship,
                   src.type   AS source_type,
                   r.context  AS context
            ORDER BY src.title
        """
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher, title=title)]
 
    def get_stats(self) -> dict:
        """Aggregate counts for the whole graph."""
        cypher = """
            MATCH (n:Note)
            WITH count(n) AS total_notes
            MATCH ()-[r]->()
            RETURN total_notes, count(r) AS total_relationships
        """
        with self._driver.session() as s:
            result = s.run(cypher).single()
            return dict(result) if result else {}
 
    def get_type_counts(self) -> list[dict]:
        cypher = """
            MATCH (n:Note)
            RETURN n.type AS type, count(n) AS count
            ORDER BY count DESC
        """
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher)]
 
    def find_coverage(self, concepts: list[str]) -> list[dict]:
        """
        For each concept string, find the top-3 most relevant existing notes
        and return a gap classification:
          - 'full'    : no existing note matches
          - 'partial' : matches exist but are shallow (word_count < 80 or no body)
          - 'covered' : a substantial note already covers this concept
        """
        results = []
        cypher = """
            MATCH (n:Note)
            WHERE toLower(n.title)   CONTAINS toLower($kw)
               OR toLower(n.body)    CONTAINS toLower($kw)
               OR toLower(n.summary) CONTAINS toLower($kw)
            RETURN n.title          AS title,
                   n.type           AS type,
                   n.word_count     AS word_count,
                   n.summary        AS summary,
                   n.backlink_count AS backlinks
            ORDER BY n.backlink_count DESC, n.word_count DESC
            LIMIT 3
        """
        with self._driver.session() as s:
            for concept in concepts:
                matches = [dict(r) for r in s.run(cypher, kw=concept)]
                if not matches:
                    gap = "full"
                elif matches[0]["word_count"] and matches[0]["word_count"] >= 80:
                    gap = "covered"
                else:
                    gap = "partial"
                results.append({
                    "concept":  concept,
                    "gap_type": gap,
                    "existing": matches,
                })
        return results
 
    def get_all_note_titles(self) -> list[str]:
        """Return every note title — used by the agent to validate [[WikiLinks]]."""
        cypher = "MATCH (n:Note) RETURN n.title AS title ORDER BY n.title"
        with self._driver.session() as s:
            return [r["title"] for r in s.run(cypher)]
 
    # Valid relationship types — whitelist used before embedding in Cypher
    _VALID_REL_TYPES = frozenset({
        "LINKS_TO", "TAGGED_WITH", "EXTENDS", "USES",
        "IMPLEMENTS", "DEPENDS_ON", "RELATES_TO",
    })
 
    def upsert_note_direct(self, props: dict, wikilinks: list[dict]) -> None:
        """
        Insert or update a Note node and its outgoing relationships directly —
        bypasses the build pipeline. Called by commit_approved_notes().
 
        props keys: node_id, title, type, subfolder, status, created_at,
                    path, word_count, content_hash, body, summary
        wikilinks:  list of {target, alias, context, relationship}
        """
        node_cypher = """
            MERGE (n:Note {title: $title})
            SET n.node_id        = $node_id,
                n.type           = $type,
                n.subfolder      = $subfolder,
                n.status         = $status,
                n.created_at     = $created_at,
                n.path           = $path,
                n.word_count     = $word_count,
                n.content_hash   = $content_hash,
                n.body           = $body,
                n.summary        = $summary,
                n.backlink_count = coalesce(n.backlink_count, 0)
        """
        backlink_cypher = """
            MATCH (src:Note {title: $src})-[]->(tgt:Note)
            WITH tgt
            MATCH (incoming:Note)-[]->(tgt)
            WITH tgt, count(incoming) AS cnt
            SET tgt.backlink_count = cnt
        """
        with self._driver.session() as s:
            s.run(node_cypher, **props)
            for link in wikilinks:
                rel = link.get("relationship", "LINKS_TO")
                if rel not in self._VALID_REL_TYPES:
                    rel = "LINKS_TO"
                # rel is from a whitelist — safe to embed in Cypher
                s.run(
                    f"MATCH (src:Note {{title: $src}}), (tgt:Note {{title: $tgt}}) "
                    f"MERGE (src)-[r:{rel}]->(tgt) "
                    f"SET r.alias = $alias, r.context = $context",
                    src=props["title"],
                    tgt=link["target"],
                    alias=link.get("alias", link["target"]),
                    context=link.get("context", ""),
                )
            s.run(backlink_cypher, src=props["title"])
 
    # ── eInvoice SQL / requirements queries ──────────────────────────────────
 
    def get_sql_view(self, view_name: str) -> dict | None:
        """Fetch a SqlView node by qualified_name or view_name (case-insensitive)."""
        cypher = """
            MATCH (v:SqlView)
            WHERE toLower(v.qualified_name) CONTAINS toLower($name)
               OR toLower(v.view_name)      CONTAINS toLower($name)
            RETURN v.qualified_name AS qualified_name,
                   v.view_name      AS view_name,
                   v.schema         AS schema,
                   v.hash           AS hash,
                   v.tag            AS tag,
                   v.body           AS body
            LIMIT 1
        """
        with self._driver.session() as s:
            r = s.run(cypher, name=view_name).single()
            return dict(r) if r else None
 
    def get_sql_segments(self, qualified_name: str) -> list[dict]:
        """Return all SqlSegment nodes for a view."""
        cypher = """
            MATCH (seg:SqlSegment)-[:PART_OF]->(v:SqlView {qualified_name: $qname})
            RETURN seg.segment_name   AS segment_name,
                   seg.dispatch_codes AS dispatch_codes,
                   seg.tag            AS tag
            ORDER BY seg.segment_name
        """
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher, qname=qualified_name)]
 
    def get_field_mappings(self, qualified_name: str, segment: str | None = None) -> list[dict]:
        """Return FieldMapping nodes for a view, optionally filtered by segment."""
        if segment:
            cypher = """
                MATCH (f:FieldMapping)-[:FIELD_OF]->(seg:SqlSegment {segment_name: $seg})
                      -[:PART_OF]->(v:SqlView {qualified_name: $qname})
                RETURN f.alias          AS alias,
                       f.expression     AS expression,
                       f.br_refs        AS br_refs,
                       f.tfs_refs       AS tfs_refs,
                       f.inline_comment AS inline_comment,
                       seg.segment_name AS segment
                ORDER BY f.alias
            """
            with self._driver.session() as s:
                return [dict(r) for r in s.run(cypher, qname=qualified_name, seg=segment)]
        else:
            cypher = """
                MATCH (f:FieldMapping)-[:FIELD_OF]->(seg:SqlSegment)
                      -[:PART_OF]->(v:SqlView {qualified_name: $qname})
                RETURN f.alias          AS alias,
                       f.expression     AS expression,
                       f.br_refs        AS br_refs,
                       f.tfs_refs       AS tfs_refs,
                       f.inline_comment AS inline_comment,
                       seg.segment_name AS segment
                ORDER BY seg.segment_name, f.alias
            """
            with self._driver.session() as s:
                return [dict(r) for r in s.run(cypher, qname=qualified_name)]
 
    def get_requirements(self, flow_name: str | None = None) -> list[dict]:
        """Return all BR nodes, optionally filtered by flow_name.
        Returns summary fields only; use get_requirement_detail() for full body.
        """
        if flow_name:
            cypher = """
                MATCH (b:BR {flow_name: $flow_name})
                RETURN b.br_id           AS br_id,
                       b.uc_id           AS uc_id,
                       b.doc_type        AS doc_type,
                       b.flow_name       AS flow_name,
                       b.title           AS title,
                       b.affected_views  AS affected_views,
                       b.candidate_categories AS candidate_categories,
                       b.confirmed_categories AS confirmed_categories,
                       b.source_file     AS source_file
                ORDER BY b.uc_id, b.br_id, b.doc_type
            """
            with self._driver.session() as s:
                return [dict(r) for r in s.run(cypher, flow_name=flow_name)]
        else:
            cypher = """
                MATCH (b:BR)
                RETURN b.br_id           AS br_id,
                       b.uc_id           AS uc_id,
                       b.doc_type        AS doc_type,
                       b.flow_name       AS flow_name,
                       b.title           AS title,
                       b.affected_views  AS affected_views,
                       b.candidate_categories AS candidate_categories,
                       b.confirmed_categories AS confirmed_categories,
                       b.source_file     AS source_file
                ORDER BY b.flow_name, b.uc_id, b.br_id, b.doc_type
            """
            with self._driver.session() as s:
                return [dict(r) for r in s.run(cypher)]
 
    def get_requirement_detail(
        self,
        br_id: str,
        uc_id: str,
        doc_type: str,
        flow_name: str,
    ) -> dict | None:
        """Return full detail for one BR node, including the parent Document context."""
        cypher = """
            MATCH (b:BR {br_id: $br_id, uc_id: $uc_id, doc_type: $doc_type, flow_name: $flow_name})
            OPTIONAL MATCH (d:Document)-[:DEFINES]->(b)
            RETURN b.br_id               AS br_id,
                   b.uc_id               AS uc_id,
                   b.doc_type            AS doc_type,
                   b.flow_name           AS flow_name,
                   b.title               AS title,
                   b.body                AS body,
                   b.candidate_categories AS candidate_categories,
                   b.confirmed_categories AS confirmed_categories,
                   b.affected_fields     AS affected_fields,
                   b.affected_views      AS affected_views,
                   b.source_file         AS source_file,
                   b.project_id          AS project_id,
                   coalesce(d.context, '') AS document_context
        """
        with self._driver.session() as s:
            row = s.run(
                cypher,
                br_id=br_id, uc_id=uc_id, doc_type=doc_type, flow_name=flow_name,
            ).single()
            return dict(row) if row else None
 
    def get_use_cases(self, flow_name: str) -> list[dict]:
        """Return all UseCases under a Flow."""
        cypher = """
            MATCH (fl:Flow {name: $flow_name})-[:HAS_UC]->(uc:UseCase)
            RETURN uc.uc_id       AS uc_id,
                   uc.project_id  AS project_id,
                   uc.flow_name   AS flow_name
            ORDER BY uc.uc_id
        """
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher, flow_name=flow_name)]
 
    def get_documents(self, uc_id: str, flow_name: str) -> list[dict]:
        """Return all Documents under a UseCase."""
        cypher = """
            MATCH (uc:UseCase {uc_id: $uc_id, flow_name: $flow_name})-[:HAS_DOCUMENT]->(d:Document)
            RETURN d.doc_type    AS doc_type,
                   d.uc_id       AS uc_id,
                   d.flow_name   AS flow_name,
                   d.source_file AS source_file
            ORDER BY d.doc_type
        """
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher, uc_id=uc_id, flow_name=flow_name)]
 
    def get_unlinked_fields(self, qualified_name: str) -> list[dict]:
        """
        Return FieldMappings for a view that have no IMPLEMENTED_BY relationship.
        These are candidates for LLM-assisted linking.
        """
        cypher = """
            MATCH (f:FieldMapping)-[:FIELD_OF]->(seg:SqlSegment)
                  -[:PART_OF]->(v:SqlView {qualified_name: $qname})
            WHERE NOT (f)<-[:IMPLEMENTED_BY]-(:BR)
              AND NOT (f)-[:REFERENCED_BY]-(:BR)
              AND NOT ()<-[:REFERENCED_BY]-(f)
            RETURN f.alias          AS alias,
                   f.expression     AS expression,
                   f.br_refs        AS br_refs,
                   f.inline_comment AS inline_comment,
                   seg.segment_name AS segment
            ORDER BY seg.segment_name, f.alias
        """
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher, qname=qualified_name)]
 
    def write_implemented_by(self, links: list[dict]) -> int:
        """
        Persist IMPLEMENTED_BY edges from Requirement → FieldMapping.
        Each entry: {"br_id": "BR04", "field_alias": "...", "view_name": "...", "segment": "..."}
        Returns the number of edges created.
        """
        import hashlib
 
        rows = []
        for lnk in links:
            field_id = hashlib.sha1(
                f"{lnk['view_name']}::{lnk['segment']}::{lnk['field_alias']}".encode()
            ).hexdigest()[:16]
            rows.append({
                "br_id":    lnk["br_id"],
                "field_id": field_id,
                "reason":   lnk.get("reason", ""),
            })
 
        if not rows:
            return 0
 
        cypher = """
            UNWIND $rows AS row
            MATCH (b:BR {br_id: row.br_id})
            MATCH (f:FieldMapping {id: row.field_id})
            MERGE (b)-[e:IMPLEMENTED_BY]->(f)
            SET e.reason = row.reason
        """
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher, rows=rows)]
        return len(rows)
 
    def get_package_functions(self, package_name: str) -> list[dict]:
        """
        Return all PackageFunction nodes for a given OraclePackage.
        Matches by qualified_name or package_name (case-insensitive).
        """
        cypher = """
            MATCH (f:PackageFunction)-[:PART_OF]->(p:OraclePackage)
            WHERE toLower(p.qualified_name) CONTAINS toLower($name)
               OR toLower(p.package_name)   CONTAINS toLower($name)
            RETURN f.function_name AS function_name,
                   f.parameters    AS parameters,
                   f.return_type   AS return_type,
                   f.br_refs       AS br_refs,
                   f.tfs_refs      AS tfs_refs,
                   f.body          AS body,
                   p.qualified_name AS package_name
            ORDER BY f.function_name
        """
        with self._driver.session() as s:
            return [dict(r) for r in s.run(cypher, name=package_name)]
 
 