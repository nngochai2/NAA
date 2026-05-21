import re
import json
from itertools import groupby
 
from neo4j import GraphDatabase
from rich.console import Console
 
from models import Note, SqlView, SqlSegment, FieldMapping, BR, Flow, UseCase, Document, OraclePackage, PackageFunction
from config import BATCH_SIZE
 
console = Console()
 
def _sanitize_rel_type(rel_type: str) -> str:
    """Return a Neo4j-safe relationship type string (uppercase, only A-Z and _)."""
    return re.sub(r"[^A-Z_]", "_", rel_type.upper())
 
 
def _make_rel_cypher(rel_type: str) -> str:
    """Build the parameterised MERGE Cypher for a given relationship type."""
    safe = _sanitize_rel_type(rel_type)
    return (
        f"UNWIND $rows AS row\n"
        f"MATCH (src:Note {{id: row.src_id}})\n"
        f"MATCH (tgt:Note {{id: row.tgt_id}})\n"
        f"MERGE (src)-[r:{safe}]->(tgt)\n"
        f"SET r.alias   = row.alias,\n"
        f"    r.context = row.context"
    )
 
 
class GraphBuilder:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
 
    def close(self):
        self.driver.close()
 
    def verify_connection(self) -> bool:
        try:
            with self.driver.session() as session:
                session.run("RETURN 1").single()
            return True
        except Exception as e:
            console.print(f"[red]Connection failed:[/] {e}")
            return False
 
    def clear_graph(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        console.print("[red]Cleared existing graph.[/]")
 
    def create_constraints(self):
        with self.driver.session() as s:
            s.run("CREATE CONSTRAINT note_id IF NOT EXISTS FOR (n:Note) REQUIRE n.node_id IS UNIQUE")
            s.run("CREATE CONSTRAINT tag_id  IF NOT EXISTS FOR (t:TAG)  REQUIRE t.node_id IS UNIQUE")
            s.run("CREATE INDEX note_type    IF NOT EXISTS FOR (n:Note) ON (n.type)")
        console.print("[green]Created uniqueness constraints.[/]")
 
    def upsert_notes(self, notes: list[Note]):
        rows = [{
            "id":             n.node_id,
            "title":          n.title,
            "type":           n.note_type,
            "subfolder":      n.subfolder,
            "status":         n.status,
            "created_at":     n.created_at,
            "path":           str(n.path),
            "word_count":     n.word_count,
            "hash":           n.content_hash,
            "backlink_count": len(n.backlinks),
            "body":           n.body,
            "summary":        n.summary or n.body[:300],
        } for n in notes]
 
        cypher = """
            UNWIND $rows AS row
            MERGE (n:Note {id: row.id})
            SET n.title          = row.title,
                n.type           = row.type,
                n.subfolder      = row.subfolder,
                n.status         = row.status,
                n.created_at     = row.created_at,
                n.path           = row.path,
                n.word_count     = row.word_count,
                n.hash           = row.hash,
                n.backlink_count = row.backlink_count,
                n.body           = row.body,
                n.summary        = row.summary
        """
        with self.driver.session() as s:
            for i in range(0, len(rows), BATCH_SIZE):
                s.run(cypher, rows=rows[i : i + BATCH_SIZE])
 
        console.print(f"[green]Upserted {len(notes)} notes.[/]")
 
    def upsert_relationships(self, notes: list[Note]):
        title_to_id = {n.title: n.node_id for n in notes}
        rows = []
        for note in notes:
            for link in note.links:
                tgt_id = title_to_id.get(link.target)
                if tgt_id:
                    rows.append({
                        "src_id":  note.node_id,
                        "tgt_id":  tgt_id,
                        "rel":     link.relationship,
                        "alias":   link.alias,
                        "context": link.context[:120],
                    })
        rows_sorted = sorted(rows, key=lambda r: r["rel"])
        with self.driver.session() as s:
            for rel_type, group in groupby(rows_sorted, key=lambda r: r["rel"]):
                batch  = list(group)
                cypher = _make_rel_cypher(rel_type)
                for i in range(0, len(batch), BATCH_SIZE):
                    s.run(cypher, rows=batch[i : i + BATCH_SIZE])
 
        console.print(f"[green]Upserted {len(rows)} relationships.[/]")
 
    def get_stats(self) -> dict:
        with self.driver.session() as s:
            return {
                "nodes": s.run(
                    "MATCH (n:Note) RETURN count(n) AS c"
                ).single()["c"],
                "relationships": s.run(
                    "MATCH ()-[r]->() RETURN count(r) AS c"
                ).single()["c"],
                "type_distribution": s.run(
                    "MATCH (n:Note) RETURN n.type AS type, count(n) AS c ORDER BY c DESC"
                ).data(),
                "relationship_distribution": s.run(
                    "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS c ORDER BY c DESC"
                ).data(),
                "tag_hubs": s.run(
                    """
                    MATCH (t:Note {type: 'TAG'})
                    RETURN t.title AS tag, t.backlink_count AS refs
                    ORDER BY refs DESC LIMIT 15
                    """
                ).data(),
                "isolated_nodes": s.run(
                    "MATCH (n:Note) WHERE NOT (n)--() RETURN count(n) AS c"
                ).single()["c"],
            }
 
    # ── eInvoice SQL / docx ingestion ─────────────────────────────────────────
 
    def create_sql_constraints(self):
        with self.driver.session() as s:
            s.run("CREATE CONSTRAINT sql_view_id     IF NOT EXISTS FOR (v:SqlView)        REQUIRE v.id IS UNIQUE")
            s.run("CREATE CONSTRAINT sql_segment_id  IF NOT EXISTS FOR (s:SqlSegment)     REQUIRE s.id IS UNIQUE")
            s.run("CREATE CONSTRAINT field_map_id    IF NOT EXISTS FOR (f:FieldMapping)   REQUIRE f.id IS UNIQUE")
            s.run("CREATE CONSTRAINT flow_id         IF NOT EXISTS FOR (fl:Flow)          REQUIRE fl.id IS UNIQUE")
            s.run("CREATE CONSTRAINT uc_id           IF NOT EXISTS FOR (uc:UseCase)       REQUIRE uc.id IS UNIQUE")
            s.run("CREATE CONSTRAINT document_id     IF NOT EXISTS FOR (d:Document)       REQUIRE d.id IS UNIQUE")
            s.run("CREATE CONSTRAINT br_id           IF NOT EXISTS FOR (b:BR)             REQUIRE b.id IS UNIQUE")
            s.run("CREATE CONSTRAINT ora_pkg_id      IF NOT EXISTS FOR (p:OraclePackage)  REQUIRE p.id IS UNIQUE")
            s.run("CREATE CONSTRAINT pkg_func_id     IF NOT EXISTS FOR (f:PackageFunction) REQUIRE f.id IS UNIQUE")
        console.print("[green]Created SQL/docx constraints.[/]")
 
    def upsert_sql_view(self, view: SqlView):
        with self.driver.session() as s:
            s.run(
                """
                MERGE (v:SqlView {id: $id})
                SET v.qualified_name = $qualified_name,
                    v.schema         = $schema,
                    v.view_name      = $view_name,
                    v.body           = $body,
                    v.hash           = $hash,
                    v.tag            = $tag
                """,
                id=view.node_id,
                qualified_name=view.qualified_name,
                schema=view.schema,
                view_name=view.view_name,
                body=view.body,
                hash=view.content_hash,
                tag=view.tag,
            )
        console.print(f"[green]Upserted SqlView:[/] {view.qualified_name}")
 
    def upsert_sql_segments(self, segments: list[SqlSegment]):
        rows = [{
            "id":           seg.node_id,
            "view_id":      SqlView(
                                qualified_name=seg.view_qualified_name,
                                schema="", view_name="", body="", tag=""
                            ).node_id,
            "segment_name": seg.segment_name,
            "dispatch":     json.dumps(seg.dispatch_codes),
            "body":         seg.body,
            "tag":          seg.tag,
        } for seg in segments]
 
        # Pre-compute view node_ids properly
        import hashlib
        for i, seg in enumerate(segments):
            rows[i]["view_id"] = hashlib.sha1(seg.view_qualified_name.encode()).hexdigest()[:16]
 
        with self.driver.session() as s:
            for i in range(0, len(rows), BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MERGE (seg:SqlSegment {id: row.id})
                    SET seg.segment_name    = row.segment_name,
                        seg.dispatch_codes  = row.dispatch,
                        seg.body            = row.body,
                        seg.tag             = row.tag
                    WITH seg, row
                    MATCH (v:SqlView {id: row.view_id})
                    MERGE (seg)-[:PART_OF]->(v)
                    """,
                    rows=rows[i : i + BATCH_SIZE],
                )
        console.print(f"[green]Upserted {len(segments)} SqlSegment(s).[/]")
 
    def upsert_field_mappings(self, fields: list[FieldMapping]):
        import hashlib
 
        rows = [{
            "id":             f.node_id,
            "seg_id":         hashlib.sha1(
                                  f"{f.view_qualified_name}::{f.segment_name}".encode()
                              ).hexdigest()[:16],
            "alias":          f.alias,
            "expression":     f.expression,
            "br_refs":        json.dumps(f.br_refs),
            "tfs_refs":       json.dumps(f.tfs_refs),
            "inline_comment": f.inline_comment,
            "tag":            f.tag,
        } for f in fields]
 
        with self.driver.session() as s:
            for i in range(0, len(rows), BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MERGE (f:FieldMapping {id: row.id})
                    SET f.alias          = row.alias,
                        f.expression     = row.expression,
                        f.br_refs        = row.br_refs,
                        f.tfs_refs       = row.tfs_refs,
                        f.inline_comment = row.inline_comment,
                        f.tag            = row.tag
                    WITH f, row
                    MATCH (seg:SqlSegment {id: row.seg_id})
                    MERGE (f)-[:FIELD_OF]->(seg)
                    """,
                    rows=rows[i : i + BATCH_SIZE],
                )
        console.print(f"[green]Upserted {len(fields)} FieldMapping(s).[/]")
 
    # ── Hierarchy upserts: Flow → UseCase → Document → BR ───────────────────
 
    def upsert_flows(self, flow_names: set[str]):
        """MERGE Flow nodes for each distinct flow name."""
        rows = [{"id": Flow(name=n).node_id, "name": n} for n in flow_names if n]
        if not rows:
            return
        with self.driver.session() as s:
            for i in range(0, len(rows), BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MERGE (fl:Flow {id: row.id})
                    SET fl.name = row.name
                    """,
                    rows=rows[i : i + BATCH_SIZE],
                )
        console.print(f"[green]Upserted {len(rows)} Flow(s).[/]")
 
    def upsert_use_cases(self, use_cases: list[UseCase]):
        """MERGE UseCase nodes and HAS_UC edges from parent Flow."""
        rows = [{
            "id":         uc.node_id,
            "uc_id":      uc.uc_id,
            "project_id": uc.project_id,
            "flow_name":  uc.flow_name,
            "flow_id":    Flow(name=uc.flow_name).node_id,
        } for uc in use_cases]
        if not rows:
            return
        with self.driver.session() as s:
            for i in range(0, len(rows), BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MERGE (uc:UseCase {id: row.id})
                    SET uc.name       = row.uc_id,
                        uc.uc_id      = row.uc_id,
                        uc.project_id = row.project_id,
                        uc.flow_name  = row.flow_name
                    WITH uc, row
                    MATCH (fl:Flow {id: row.flow_id})
                    MERGE (fl)-[:HAS_UC]->(uc)
                    """,
                    rows=rows[i : i + BATCH_SIZE],
                )
        console.print(f"[green]Upserted {len(rows)} UseCase(s).[/]")
 
    def upsert_documents(self, documents: list[Document]):
        """MERGE Document nodes and HAS_DOCUMENT edges from parent UseCase."""
        rows = [{
            "id":         d.node_id,
            "uc_id":      d.uc_id,
            "doc_type":   d.doc_type,
            "flow_name":  d.flow_name,
            "source_file": d.source_file,
            "context":    d.context,
            "parent_id":  UseCase(uc_id=d.uc_id, project_id="", flow_name=d.flow_name).node_id,
        } for d in documents]
        if not rows:
            return
        with self.driver.session() as s:
            for i in range(0, len(rows), BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MERGE (d:Document {id: row.id})
                    SET d.name        = row.uc_id + ' ' + row.doc_type,
                        d.uc_id       = row.uc_id,
                        d.doc_type    = row.doc_type,
                        d.flow_name   = row.flow_name,
                        d.source_file = row.source_file,
                        d.context     = CASE WHEN row.context <> '' THEN row.context ELSE d.context END
                    WITH d, row
                    MATCH (uc:UseCase {id: row.parent_id})
                    MERGE (uc)-[:HAS_DOCUMENT]->(d)
                    """,
                    rows=rows[i : i + BATCH_SIZE],
                )
        console.print(f"[green]Upserted {len(rows)} Document(s).[/]")
 
    def upsert_brs(self, brs: list[BR]):
        """Upsert BR nodes with DEFINES edges from parent Document."""
        rows = [{
            "id":                    b.node_id,
            "br_id":                 b.br_id,
            "uc_id":                 b.uc_id,
            "doc_type":              b.doc_type,
            "flow_name":             b.flow_name,
            "title":                 b.title,
            "body":                  b.body,
            "candidate_categories":  json.dumps(b.candidate_categories),
            "confirmed_categories":  json.dumps(b.confirmed_categories),
            "affected_fields":       json.dumps(b.affected_fields),
            "affected_views":        json.dumps(b.affected_views),
            "source_file":           b.source_file,
            "project_id":            b.project_id,
            "doc_id":                Document(
                                         uc_id=b.uc_id,
                                         doc_type=b.doc_type,
                                         flow_name=b.flow_name,
                                     ).node_id,
        } for b in brs]
        if not rows:
            return
        cypher = """
            UNWIND $rows AS row
            MERGE (b:BR {id: row.id})
            ON CREATE SET
                b.name                = row.uc_id + '::' + row.doc_type + '::' + row.br_id,
                b.br_id               = row.br_id,
                b.uc_id               = row.uc_id,
                b.doc_type            = row.doc_type,
                b.flow_name           = row.flow_name,
                b.title               = row.title,
                b.body                = row.body,
                b.candidate_categories = row.candidate_categories,
                b.confirmed_categories = row.confirmed_categories,
                b.affected_fields     = row.affected_fields,
                b.affected_views      = row.affected_views,
                b.source_file         = row.source_file,
                b.project_id          = row.project_id
            ON MATCH SET
                b.name                = row.uc_id + '::' + row.doc_type + '::' + row.br_id,
                b.title               = CASE WHEN row.title <> '' THEN row.title ELSE b.title END,
                b.body                = CASE WHEN row.body  <> '' THEN row.body  ELSE b.body  END,
                b.affected_fields     = CASE WHEN row.affected_fields <> '[]' THEN row.affected_fields ELSE b.affected_fields END,
                b.affected_views      = row.affected_views,
                b.confirmed_categories = CASE WHEN row.confirmed_categories <> '[]' THEN row.confirmed_categories ELSE b.confirmed_categories END
            WITH b, row
            MATCH (d:Document {id: row.doc_id})
            MERGE (d)-[:DEFINES]->(b)
        """
        with self.driver.session() as s:
            for i in range(0, len(rows), BATCH_SIZE):
                s.run(cypher, rows=rows[i : i + BATCH_SIZE])
        console.print(f"[green]Upserted {len(brs)} BR(s).[/]")
 
    def link_same_as_brs(self, flow_name: str):
        """
        Within each UseCase, link BR nodes that share the same br_id across
        different doc_types with a bidirectional SAME_AS edge.
        E.g. UC36::FDD::BR04 <-> UC36::SDD::BR04
        """
        with self.driver.session() as s:
            s.run(
                """
                MATCH (a:BR {flow_name: $flow_name})
                MATCH (b:BR {flow_name: $flow_name})
                WHERE a.uc_id = b.uc_id AND a.br_id = b.br_id AND a.doc_type < b.doc_type
                MERGE (a)-[:SAME_AS]->(b)
                """,
                flow_name=flow_name,
            )
        console.print(f"[green]Linked SAME_AS BR pairs for flow '{flow_name}'.[/]")
 
    def reconcile_br_field_links(self):
        """
        Graph-side reconciliation: create REFERENCED_BY edges from every BR node
        to every FieldMapping whose stored br_refs list contains that BR's br_id.
 
        This works regardless of ingest order — SQL-first, docx-first, or mixed
        across multiple runs — and handles fan-out to FDD + SDD variants of the
        same br_id automatically (one FieldMapping → many BRs across any number
        of documents / flows).
        """
        # Pull all FieldMappings that have at least one BR ref stored
        with self.driver.session() as s:
            rows_raw = s.run(
                "MATCH (f:FieldMapping) "
                "WHERE f.br_refs IS NOT NULL AND f.br_refs <> '[]' "
                "RETURN f.id AS id, f.br_refs AS br_refs"
            ).data()
 
        rows = []
        for f in rows_raw:
            try:
                br_ids = json.loads(f["br_refs"])
            except (ValueError, TypeError):
                continue
            for br_id in br_ids:
                rows.append({"field_id": f["id"], "br_id": br_id})
 
        if not rows:
            console.print("[dim]No BR→FieldMapping refs to reconcile.[/]")
            return
 
        with self.driver.session() as s:
            for i in range(0, len(rows), BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MATCH (f:FieldMapping {id: row.field_id})
                    MATCH (b:BR {br_id: row.br_id})
                    MERGE (b)-[:REFERENCED_BY]->(f)
                    """,
                    rows=rows[i : i + BATCH_SIZE],
                )
        console.print(f"[green]Reconciled {len(rows)} BR→FieldMapping REFERENCED_BY edge(s).[/]")
 
    # Backward-compat alias (used by tests)
    def link_br_comments_to_requirements(self, fields, requirements):
        self.reconcile_br_field_links()
 
    def tag_nodes_with_einvoice(
        self,
        tag: str,
        view_names: list[str],
    ):
        """
        Link SqlView nodes to their parent Flow via TAGGED_WITH.
        Uses the Flow node (MERGE by name) so no separate Tag node is created.
        BRs are already reachable via the Flow → UseCase → Document → BR hierarchy
        and do not need a separate TAGGED_WITH edge.
        """
        if not tag or not view_names:
            return
        with self.driver.session() as s:
            s.run(
                """
                UNWIND $names AS name
                MATCH (v:SqlView {qualified_name: name})
                MERGE (fl:Flow {name: $tag})
                MERGE (v)-[:TAGGED_WITH]->(fl)
                """,
                names=view_names, tag=tag,
            )
        console.print(f"[green]Tagged {len(view_names)} view(s) with flow '{tag}'.[/]")
 
    def upsert_oracle_package(self, pkg: OraclePackage):
        with self.driver.session() as s:
            s.run(
                """
                MERGE (p:OraclePackage {id: $id})
                SET p.qualified_name = $qualified_name,
                    p.schema         = $schema,
                    p.package_name   = $package_name,
                    p.spec_body      = $spec_body,
                    p.hash           = $hash,
                    p.tag            = $tag
                """,
                id=pkg.node_id,
                qualified_name=pkg.qualified_name,
                schema=pkg.schema,
                package_name=pkg.package_name,
                spec_body=pkg.spec_body,
                hash=pkg.content_hash,
                tag=pkg.tag,
            )
        console.print(f"[green]Upserted OraclePackage:[/] {pkg.qualified_name}")
 
    def upsert_package_functions(self, functions: list[PackageFunction]):
        rows = [{
            "id":           f.node_id,
            "pkg_id":       OraclePackage(
                                qualified_name=f.package_qualified_name,
                                schema="", package_name="", spec_body="", tag=""
                            ).node_id,
            "function_name": f.function_name,
            "parameters":    f.parameters,
            "return_type":   f.return_type,
            "body":          f.body,
            "br_refs":       json.dumps(f.br_refs),
            "tfs_refs":      json.dumps(f.tfs_refs),
            "tag":           f.tag,
        } for f in functions]
 
        # Pre-compute pkg node_ids properly
        import hashlib as _hl
        for i, f in enumerate(functions):
            rows[i]["pkg_id"] = _hl.sha1(f.package_qualified_name.encode()).hexdigest()[:16]
 
        with self.driver.session() as s:
            for i in range(0, len(rows), BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MERGE (f:PackageFunction {id: row.id})
                    SET f.function_name = row.function_name,
                        f.parameters    = row.parameters,
                        f.return_type   = row.return_type,
                        f.body          = row.body,
                        f.br_refs       = row.br_refs,
                        f.tfs_refs      = row.tfs_refs,
                        f.tag           = row.tag
                    WITH f, row
                    MATCH (p:OraclePackage {id: row.pkg_id})
                    MERGE (f)-[:PART_OF]->(p)
                    """,
                    rows=rows[i : i + BATCH_SIZE],
                )
        console.print(f"[green]Upserted {len(functions)} PackageFunction(s).[/]")
 
    def link_fields_to_functions(self, fields: list[FieldMapping], functions: list[PackageFunction]):
        """
        Create CALLS edges from FieldMapping → PackageFunction when the field's
        expression contains a call to the function (by name).
        """
        import re as _re
        rows = []
        for f in functions:
            # Match bare function name or package-qualified call
            call_re = _re.compile(
                r'\b(?:\w+\.)*' + _re.escape(f.function_name) + r'\s*\(',
                _re.IGNORECASE,
            )
            for field in fields:
                if call_re.search(field.expression):
                    rows.append({"field_id": field.node_id, "func_id": f.node_id})
 
        if not rows:
            return
 
        with self.driver.session() as s:
            for i in range(0, len(rows), BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MATCH (f:FieldMapping     {id: row.field_id})
                    MATCH (fn:PackageFunction {id: row.func_id})
                    MERGE (f)-[:CALLS]->(fn)
                    """,
                    rows=rows[i : i + BATCH_SIZE],
                )
        console.print(f"[green]Created {len(rows)} CALLS edge(s) from FieldMapping → PackageFunction.[/]")

    # ── Generic requirement upsert (rule-file driven) ─────────────────────────

    def upsert_requirements(
        self,
        requirements: list,
        parent_node_id: str | None = None,
        parent_rel:     str        = "DEFINES",
    ) -> None:
        """
        Upsert ``GenericRequirement`` nodes using dynamic Neo4j labels.

        Because Neo4j labels cannot be Cypher parameters they are sanitized
        and interpolated directly into the query string.  One batch per
        distinct label is executed.

        Parameters
        ----------
        requirements:
            List of ``GenericRequirement`` instances (from ``docx_generic_parser``).
        parent_node_id:
            If supplied, a ``(parent)-[:parent_rel]->(item)`` edge is created.
        parent_rel:
            Relationship type from parent to each item node (default: DEFINES).
        """
        by_label: dict[str, list] = {}
        for r in requirements:
            by_label.setdefault(r.node_label, []).append(r)

        safe_parent_rel = re.sub(r"[^A-Z_]", "_", parent_rel.upper())

        with self.driver.session() as s:
            for label, group in by_label.items():
                safe_label = re.sub(r"[^A-Za-z0-9_]", "_", label)

                rows = [{
                    "id":                    r.node_id,
                    "req_id":                r.req_id,
                    "title":                 r.title,
                    "body":                  r.body,
                    "source_file":           r.source_file,
                    "candidate_categories":  json.dumps(r.candidate_categories),
                    "named_extractions":     json.dumps(r.named_extractions),
                    "metadata":              json.dumps(r.metadata),
                    "parent_id":             parent_node_id or "",
                } for r in group]

                if parent_node_id:
                    cypher = f"""
                        UNWIND $rows AS row
                        MERGE (r:{safe_label} {{id: row.id}})
                        SET r.req_id               = row.req_id,
                            r.title                = row.title,
                            r.body                 = row.body,
                            r.source_file          = row.source_file,
                            r.candidate_categories = row.candidate_categories,
                            r.named_extractions    = row.named_extractions,
                            r.metadata             = row.metadata
                        WITH r, row
                        MATCH (p {{id: row.parent_id}})
                        MERGE (p)-[:{safe_parent_rel}]->(r)
                    """
                else:
                    cypher = f"""
                        UNWIND $rows AS row
                        MERGE (r:{safe_label} {{id: row.id}})
                        SET r.req_id               = row.req_id,
                            r.title                = row.title,
                            r.body                 = row.body,
                            r.source_file          = row.source_file,
                            r.candidate_categories = row.candidate_categories,
                            r.named_extractions    = row.named_extractions,
                            r.metadata             = row.metadata
                    """

                for i in range(0, len(rows), BATCH_SIZE):
                    s.run(cypher, rows=rows[i : i + BATCH_SIZE])

        console.print(f"[green]Upserted {len(requirements)} generic requirement(s).[/]")

 