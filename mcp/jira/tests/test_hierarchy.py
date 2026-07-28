import pytest

from jira_mcp.hierarchy import (
    coerce_custom_field_value,
    find_epic_link_field_id,
    find_missing_required_fields,
    resolve_custom_fields,
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


def test_coerce_custom_field_value_passes_through_plain_scalar_types():
    assert coerce_custom_field_value({"type": "string"}, "hello") == "hello"
    assert coerce_custom_field_value({"type": "date"}, "2026-08-01") == "2026-08-01"


def test_coerce_custom_field_value_wraps_option_type_in_value_object():
    result = coerce_custom_field_value({"type": "option"}, "Mobile App")

    assert result == {"value": "Mobile App"}


def test_coerce_custom_field_value_wraps_user_type_in_name_object():
    result = coerce_custom_field_value({"type": "user"}, "jdoe")

    assert result == {"name": "jdoe"}


def test_coerce_custom_field_value_wraps_each_item_of_an_array_field():
    schema = {"type": "array", "items": "option"}

    result = coerce_custom_field_value(schema, ["Mobile App", "Web App"])

    assert result == [{"value": "Mobile App"}, {"value": "Web App"}]


def test_coerce_custom_field_value_wraps_single_value_as_array_when_schema_expects_array():
    schema = {"type": "array", "items": "string"}

    result = coerce_custom_field_value(schema, "solo")

    assert result == ["solo"]


def test_resolve_custom_fields_maps_field_names_to_ids_and_coerces_values():
    fields_meta = {
        "customfield_10050": {"name": "Product", "schema": {"type": "option"}},
        "customfield_10051": {"name": "Planned Start", "schema": {"type": "date"}},
    }

    result = resolve_custom_fields(
        {"Product": "Mobile App", "Planned Start": "2026-08-01"}, fields_meta
    )

    assert result == {
        "customfield_10050": {"value": "Mobile App"},
        "customfield_10051": "2026-08-01",
    }


def test_resolve_custom_fields_raises_clear_error_for_unknown_field_name():
    fields_meta = {"customfield_10050": {"name": "Product", "schema": {"type": "option"}}}

    with pytest.raises(ValueError, match="Nonexistent Field"):
        resolve_custom_fields({"Nonexistent Field": "x"}, fields_meta)


def test_find_missing_required_fields_lists_required_fields_not_yet_provided():
    fields_meta = {
        "summary": {"name": "Summary", "required": True},
        "components": {"name": "Component/s", "required": True},
        "customfield_10050": {"name": "Product", "required": True},
        "priority": {"name": "Priority", "required": False},
    }

    result = find_missing_required_fields(fields_meta, provided_field_ids={"summary"})

    assert result == ["Component/s", "Product"]


def test_find_missing_required_fields_treats_reporter_as_always_satisfied():
    fields_meta = {"reporter": {"name": "Reporter", "required": True}}

    result = find_missing_required_fields(fields_meta, provided_field_ids=set())

    assert result == []


def test_find_missing_required_fields_returns_empty_when_nothing_missing():
    fields_meta = {"summary": {"name": "Summary", "required": True}}

    result = find_missing_required_fields(fields_meta, provided_field_ids={"summary"})

    assert result == []
