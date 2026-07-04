import pytest

from jira_mcp.hierarchy import (
    find_epic_link_field_id,
    resolve_link_type_id,
    resolve_parent_strategy,
    resolve_transition_id,
)


def test_resolve_link_type_id_matches_case_insensitively():
    link_types = [
        {"id": "10000", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
        {"id": "10001", "name": "Relates", "inward": "relates to", "outward": "relates to"},
    ]

    result = resolve_link_type_id("blocks", link_types)

    assert result == "10000"


def test_resolve_link_type_id_raises_clear_error_when_no_match():
    link_types = [
        {"id": "10001", "name": "Relates", "inward": "relates to", "outward": "relates to"},
    ]

    with pytest.raises(ValueError, match="Duplicate"):
        resolve_link_type_id("Duplicate", link_types)


def test_resolve_transition_id_matches_target_status_case_insensitively():
    transitions = [
        {"id": "11", "name": "Start Progress", "to": {"id": "3", "name": "In Progress"}},
        {"id": "21", "name": "Close Issue", "to": {"id": "5", "name": "Done"}},
    ]

    result = resolve_transition_id("in progress", transitions)

    assert result == "11"


def test_resolve_transition_id_raises_clear_error_when_no_match():
    transitions = [
        {"id": "11", "name": "Start Progress", "to": {"id": "3", "name": "In Progress"}},
    ]

    with pytest.raises(ValueError, match="Done"):
        resolve_transition_id("Done", transitions)


def test_resolve_parent_strategy_uses_native_parent_field_for_subtask_child():
    strategy = resolve_parent_strategy(
        parent_key="PROJ-1", child_issue_type="Sub-task", parent_issue_type="Story"
    )

    assert strategy == {"extra_fields": {"parent": {"key": "PROJ-1"}}, "post_create_link": False}


def test_resolve_parent_strategy_uses_epic_link_field_for_epic_parent():
    strategy = resolve_parent_strategy(
        parent_key="PROJ-1",
        child_issue_type="Task",
        parent_issue_type="Epic",
        epic_link_field_id="customfield_10008",
    )

    assert strategy == {"extra_fields": {"customfield_10008": "PROJ-1"}, "post_create_link": False}


def test_resolve_parent_strategy_raises_when_epic_parent_but_no_field_id_resolved():
    with pytest.raises(ValueError, match="Epic Link"):
        resolve_parent_strategy(
            parent_key="PROJ-1",
            child_issue_type="Task",
            parent_issue_type="Epic",
            epic_link_field_id=None,
        )


def test_resolve_parent_strategy_falls_back_to_relates_link_for_other_combos():
    strategy = resolve_parent_strategy(
        parent_key="PROJ-1", child_issue_type="Task", parent_issue_type="Story"
    )

    assert strategy == {"extra_fields": {}, "post_create_link": True}


def test_find_epic_link_field_id_finds_field_named_epic_link():
    fields_meta = {
        "customfield_10008": {"name": "Epic Link", "schema": {"custom": "com.pyxis.greenhopper.jira:gh-epic-link"}},
        "summary": {"name": "Summary"},
    }

    result = find_epic_link_field_id(fields_meta)

    assert result == "customfield_10008"


def test_find_epic_link_field_id_returns_none_when_absent():
    fields_meta = {"summary": {"name": "Summary"}}

    result = find_epic_link_field_id(fields_meta)

    assert result is None
