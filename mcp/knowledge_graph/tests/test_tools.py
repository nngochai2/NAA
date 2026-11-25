import asyncio

from knowledge_graph_mcp.server import mcp
from knowledge_graph_mcp.tools import notes, requirements

EXPECTED_TOOLS = {
    "search_notes",
    "get_note",
    "get_related_notes",
    "get_backlinks",
    "get_tagged_notes",
    "get_notes_by_type",
    "get_graph_stats",
    "find_knowledge_gaps",
    "get_all_note_titles",
    "stage_note",
    "list_staged_notes",
    "approve_staged_note",
    "reject_staged_note",
    "commit_approved_notes",
    "get_use_cases",
    "get_documents",
    "get_requirements",
    "get_requirement_detail",
    "assign_br_category",
}

WRITE_TOOLS = {
    "stage_note",
    "approve_staged_note",
    "reject_staged_note",
    "commit_approved_notes",
    "assign_br_category",
}


def test_all_tools_registered_with_correct_read_only_hints():
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for t in tools:
        assert t.annotations.readOnlyHint is (t.name not in WRITE_TOOLS), t.name


def test_search_notes_formats_notes_and_brs(db):
    db.search_notes.return_value = [
        {
            "title": "Invoice Numbering",
            "type": "CONVENTION",
            "subfolder": "Billing",
            "backlinks": 3,
        },
        {
            "result_type": "br",
            "br_id": "BR03",
            "uc_id": "UC36",
            "flow_name": "eInvoice",
            "status": "FDD",
            "title": "Validate tax code",
        },
    ]
    out = notes.search_notes("  invoice  ", limit=500)
    db.search_notes.assert_called_once_with("invoice", 50)
    assert "**Invoice Numbering**  [CONVENTION]  Billing  — 3 backlink(s)" in out
    assert "get_requirement_detail(br_id='BR03', uc_id='UC36', doc_type='FDD'" in out


def test_search_notes_no_results(db):
    db.search_notes.return_value = []
    assert notes.search_notes("zzz") == "No notes or requirements found matching 'zzz'."


def test_get_note_not_found(db):
    db.get_note.return_value = None
    assert "not found" in notes.get_note("Missing")


def test_get_tagged_notes_rejects_invalid_type(db):
    out = notes.get_tagged_notes("Billing", "bogus")
    assert out.startswith("Invalid type 'bogus'")
    db.get_tagged_notes.assert_not_called()


def test_get_tagged_notes_normalises_type(db):
    db.get_tagged_notes.return_value = []
    out = notes.get_tagged_notes(" Billing ", " task ")
    db.get_tagged_notes.assert_called_once_with("Billing", "TASK", 50)
    assert out == "No notes of type TASK found linked to ' Billing '."


def test_get_notes_by_type_caps_limit(db):
    db.get_notes_by_type.return_value = []
    notes.get_notes_by_type("architecture", limit=1000)
    db.get_notes_by_type.assert_called_once_with("ARCHITECTURE", 100)


def test_get_graph_stats(db):
    db.get_stats.return_value = {"total_notes": 12, "total_relationships": 30}
    db.get_type_counts.return_value = [{"type": "TASK", "count": 7}]
    out = notes.get_graph_stats()
    assert "Total notes:         12" in out
    assert "TASK" in out and "7" in out


def test_assign_br_category_normalises_and_reports(db):
    db.set_br_categories.return_value = True
    out = requirements.assign_br_category("br04", "uc36", "fdd", " eInvoice ", "Validation, , UI")
    db.set_br_categories.assert_called_once_with(
        "BR04", "UC36", "FDD", "eInvoice", ["Validation", "UI"]
    )
    assert out.startswith("✅ Set confirmed_categories = ['Validation', 'UI'] on br04")


def test_assign_br_category_not_found(db):
    db.set_br_categories.return_value = False
    assert requirements.assign_br_category("BR1", "UC1", "FDD", "f", "x").startswith("No BR found")


def test_get_requirement_detail_prefers_confirmed_categories(db):
    db.get_requirement_detail.return_value = {
        "br_id": "BR03",
        "title": "Validate",
        "confirmed_categories": '["UI"]',
        "candidate_categories": '["DB"]',
        "body": "Body text",
    }
    out = requirements.get_requirement_detail("br03", "uc36", "fdd")
    assert '**Categories (confirmed):** ["UI"]' in out
    assert "candidate" not in out
    assert "### Requirement Body\nBody text" in out
