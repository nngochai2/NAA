import json
import re

import pytest
from conftest import VALID_NOTE

from knowledge_graph_mcp.config import get_config
from knowledge_graph_mcp.staging import extract_body, load_staging, note_props, parse_wikilinks
from knowledge_graph_mcp.tools import authoring

NOTE_PATH = "Knowledge/Conventions/Invoice Numbering.md"


def _stage(content=VALID_NOTE, path=NOTE_PATH, note_type="convention"):
    out = authoring.stage_note("Invoice Numbering", path, note_type, content)
    m = re.search(r"Staged note ID: (\w{8})", out)
    return (m.group(1) if m else None), out


# ── parsing helpers ───────────────────────────────────────────────────────────


def test_parse_wikilinks_classifies_tags_and_aliases():
    links = parse_wikilinks(VALID_NOTE + "\n![[embedded.png]]")
    by_target = {lnk["target"]: lnk for lnk in links}
    assert set(by_target) == {"Billing", "Tenant", "Tax Rules"}
    assert by_target["Billing"]["relationship"] == "TAGGED_WITH"
    assert by_target["Tenant"]["relationship"] == "LINKS_TO"
    assert by_target["Tax Rules"]["alias"] == "tax"


def test_extract_body_starts_at_first_h1_and_caps_length():
    assert extract_body(VALID_NOTE).startswith("# Invoice Numbering")
    assert len(extract_body("# T\n" + "x" * 10_000)) == 5000


def test_note_props_normalises_path_and_derives_stable_id():
    def props(path):
        return note_props(
            {
                "vault_relative_path": path,
                "title": "N",
                "note_type": "CONVENTION",
                "content": VALID_NOTE,
            }
        )

    windows, posix = props("a\\Conventions\\N.md"), props("a/Conventions/N.md")
    assert windows["path"] == "a/Conventions/N.md"
    assert windows["subfolder"] == "Conventions"
    assert windows["node_id"] == posix["node_id"]
    assert len(windows["node_id"]) == 16


# ── stage_note validation ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"note_type": "bogus"}, "Invalid note_type"),
        ({"path": "../escape.md"}, "'..' is not allowed"),
        ({"path": "Knowledge/note.txt"}, "must end with .md"),
        ({"content": "# No header"}, "must start with a date header"),
    ],
)
def test_stage_note_rejects_invalid_input(kwargs, expected):
    note_id, out = _stage(**kwargs)
    assert note_id is None
    assert expected in out
    assert load_staging() == {"notes": {}}


@pytest.mark.xfail(
    reason="pre-existing bug: extract_body() truncates to 5000 chars, so the "
    "'body > 5000' guard in stage_note can never trigger",
    strict=True,
)
def test_stage_note_rejects_overlong_body():
    note_id, out = _stage(content="01-01-2026 09:00\n\n# T\n" + "x" * 6000)
    assert note_id is None
    assert "split into smaller notes" in out


# ── full review lifecycle ─────────────────────────────────────────────────────


def test_stage_writes_staging_entry_and_preview(vault):
    note_id, out = _stage()
    assert note_id
    entry = json.loads(get_config().staging_file.read_text(encoding="utf-8"))["notes"][note_id]
    assert entry["status"] == "pending" and entry["note_type"] == "CONVENTION"
    assert (vault / "_staging" / f"{note_id}_Invoice Numbering.md").exists()
    assert "Links:    3 wikilink(s) found" in out


def test_reject_removes_preview_and_commit_purges(vault, db):
    note_id, _ = _stage()
    assert authoring.reject_staged_note(note_id, "dup").startswith("❌ Rejected")
    assert not list((vault / "_staging").glob(f"{note_id}_*.md"))
    assert authoring.commit_approved_notes() == "No approved notes to commit."
    assert load_staging() == {"notes": {}}
    db.upsert_note_direct.assert_not_called()


def test_approve_then_commit_moves_preview_into_vault_and_upserts(vault, db):
    note_id, _ = _stage()
    assert authoring.approve_staged_note(note_id).startswith("✅ Approved")
    assert "already approved" in authoring.approve_staged_note(note_id)

    out = authoring.commit_approved_notes()

    assert out.startswith("✅ Committed (1):")
    assert (vault / NOTE_PATH).read_text(encoding="utf-8") == VALID_NOTE
    assert not list((vault / "_staging").glob("*.md"))
    props, links = db.upsert_note_direct.call_args.args
    assert props["title"] == "Invoice Numbering" and props["subfolder"] == "Conventions"
    assert len(links) == 3
    assert load_staging() == {"notes": {}}


def test_commit_skips_existing_file_and_keeps_pending(vault, db):
    (vault / NOTE_PATH).parent.mkdir(parents=True)
    (vault / NOTE_PATH).write_text("existing", encoding="utf-8")
    approved_id, _ = _stage()
    authoring.approve_staged_note(approved_id)
    _stage(path="Knowledge/Other.md")

    out = authoring.commit_approved_notes()

    assert "Skipped — already existed (1)" in out
    assert "1 note(s) still pending review" in out
    assert (vault / NOTE_PATH).read_text(encoding="utf-8") == "existing"
    db.upsert_note_direct.assert_not_called()


def test_commit_requires_vault_root(monkeypatch):
    monkeypatch.setenv("VAULT_ROOT", "")
    get_config.cache_clear()
    assert "VAULT_ROOT is not configured" in authoring.commit_approved_notes()


def test_unknown_note_id():
    assert "No staged note with ID 'nope'" in authoring.approve_staged_note("nope")
    assert "No staged note with ID 'nope'" in authoring.reject_staged_note("nope")


def test_list_staged_notes():
    assert "No staged notes" in authoring.list_staged_notes()
    note_id, _ = _stage()
    out = authoring.list_staged_notes(show_content=True)
    assert f"⏳ [{note_id}] Invoice Numbering" in out
    assert "      # Invoice Numbering" in out
