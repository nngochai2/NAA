"""
Spec-doc ingest test suite.

Cycles 1-5  test DocxRuleParser in isolation (no network).
Cycles 6-9  test the graph write path against a real Neo4j instance.
"""
import pytest
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════════════
# PARSER TESTS (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

class TestDocxRuleParser:

    # ── Cycle 1 — tracer bullet ───────────────────────────────────────────────

    def test_br_rows_extracted_with_normalised_ids(self, rule_path, sample_docx):
        """BR04, BR 23 → BR04, BR23; BR07 stays BR07."""
        from src.docx_generic_parser import DocxRuleParser
        items, _ = DocxRuleParser(rule_path).parse(sample_docx)
        ids = {i.req_id for i in items}
        assert ids == {"BR04", "BR23", "BR07"}

    # ── Cycle 2 ───────────────────────────────────────────────────────────────

    def test_title_taken_from_first_body_line(self, rule_path, sample_docx):
        from src.docx_generic_parser import DocxRuleParser
        items, _ = DocxRuleParser(rule_path).parse(sample_docx)
        br04 = next(i for i in items if i.req_id == "BR04")
        assert br04.title == "First line of BR04"

    # ── Cycle 3 ───────────────────────────────────────────────────────────────

    def test_category_signals_matched_per_body(self, rule_path, sample_docx):
        from src.docx_generic_parser import DocxRuleParser
        items, _ = DocxRuleParser(rule_path).parse(sample_docx)
        by_id = {i.req_id: i for i in items}

        assert "SQLView"   in by_id["BR04"].candidate_categories
        assert "OracleEBS" in by_id["BR23"].candidate_categories
        assert "BatchJob"  in by_id["BR07"].candidate_categories
        assert "Java"      in by_id["BR07"].candidate_categories

    # ── Cycle 4 ───────────────────────────────────────────────────────────────

    def test_named_extractions_deduped_and_sorted(self, rule_path, sample_docx):
        from src.docx_generic_parser import DocxRuleParser
        items, _ = DocxRuleParser(rule_path).parse(sample_docx)
        br04 = next(i for i in items if i.req_id == "BR04")

        assert br04.named_extractions["views"]  == ["VW_INVOICE_HDR"]
        assert br04.named_extractions["fields"] == ["INVOICE_DATE"]

    # ── Cycle 5 ───────────────────────────────────────────────────────────────

    def test_context_collects_non_br_content_only(self, rule_path, sample_docx):
        from src.docx_generic_parser import DocxRuleParser
        _, context = DocxRuleParser(rule_path).parse(sample_docx)

        assert "introduction paragraph" in context
        assert "eInvoice"               in context   # from info table
        # BR table rows must NOT appear in context
        assert "BR04"  not in context
        assert "BR 23" not in context


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH TESTS  (require Neo4j at bolt://localhost:7687)
# ══════════════════════════════════════════════════════════════════════════════

class TestDocumentHierarchy:

    # ── Cycle 6 — tracer bullet ───────────────────────────────────────────────

    def test_document_node_created_with_context(self, graph_db, rule_path, sample_docx):
        """upsert_document_hierarchy merges a Document node and stores context."""
        from src.docx_generic_parser import DocxRuleParser
        _, context = DocxRuleParser(rule_path).parse(sample_docx, source_label="UC99")

        doc_id = graph_db.upsert_document_hierarchy(
            flow_name="TestFlow",
            uc_id="UC99",
            doc_type="FDD",
            source_file="test_fixture.docx",
            context=context,
        )

        with graph_db.driver.session() as s:
            row = s.run(
                "MATCH (d:Document {id: $id}) RETURN d", id=doc_id
            ).single()

        assert row is not None
        d = row["d"]
        assert d["doc_type"]    == "FDD"
        assert d["uc_id"]       == "UC99"
        assert d["source_file"] == "test_fixture.docx"
        assert "introduction"   in d["context"]

    # ── Cycle 7 ───────────────────────────────────────────────────────────────

    def test_br_nodes_linked_to_document_via_defines(self, graph_db, rule_path, sample_docx):
        from src.docx_generic_parser import DocxRuleParser
        items, context = DocxRuleParser(rule_path).parse(sample_docx, source_label="UC99")

        doc_id = graph_db.upsert_document_hierarchy(
            flow_name="TestFlow",
            uc_id="UC99",
            doc_type="FDD",
            source_file="test_fixture.docx",
            context=context,
        )
        graph_db.upsert_requirements(items, parent_node_id=doc_id)

        with graph_db.driver.session() as s:
            row = s.run(
                "MATCH (d:Document {id: $id})-[:DEFINES]->(r:BR) RETURN count(r) AS cnt",
                id=doc_id,
            ).single()

        assert row["cnt"] == 3

    # ── Cycle 8 ───────────────────────────────────────────────────────────────

    def test_usecase_node_linked_to_document(self, graph_db, rule_path, sample_docx):
        from src.docx_generic_parser import DocxRuleParser
        _, context = DocxRuleParser(rule_path).parse(sample_docx, source_label="UC99")

        doc_id = graph_db.upsert_document_hierarchy(
            flow_name="TestFlow",
            uc_id="UC99",
            doc_type="FDD",
            source_file="test_fixture.docx",
            context=context,
        )

        with graph_db.driver.session() as s:
            row = s.run(
                """
                MATCH (uc:UseCase {uc_id: 'UC99'})-[:HAS_DOCUMENT]->(d:Document {id: $id})
                RETURN uc
                """,
                id=doc_id,
            ).single()

        assert row is not None
        assert row["uc"]["flow_name"] == "TestFlow"

    # ── Cycle 9 ───────────────────────────────────────────────────────────────

    def test_flow_node_linked_to_usecase(self, graph_db, rule_path, sample_docx):
        from src.docx_generic_parser import DocxRuleParser
        _, context = DocxRuleParser(rule_path).parse(sample_docx, source_label="UC99")

        graph_db.upsert_document_hierarchy(
            flow_name="TestFlow",
            uc_id="UC99",
            doc_type="FDD",
            source_file="test_fixture.docx",
            context=context,
        )

        with graph_db.driver.session() as s:
            row = s.run(
                """
                MATCH (f:Flow {name: 'TestFlow'})-[:HAS_USE_CASE]->(uc:UseCase {uc_id: 'UC99'})
                RETURN f
                """
            ).single()

        assert row is not None
