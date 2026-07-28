"""Pure decision logic for Jira's per-instance configuration (ADR 0001, ADR 0003, ADR 0007).

No I/O here — these functions take already-fetched Jira metadata (link types,
transitions, create-meta) and decide what to do with it.
"""
from __future__ import annotations


def resolve_link_type_id(name: str, link_types: list[dict]) -> str:
    for link_type in link_types:
        if link_type["name"].lower() == name.lower():
            return link_type["id"]
    raise ValueError(f"Unknown Jira link type: {name!r}")


def resolve_transition_id(target_status: str, transitions: list[dict]) -> str:
    for transition in transitions:
        if transition["to"]["name"].lower() == target_status.lower():
            return transition["id"]
    raise ValueError(f"No transition to status {target_status!r} from the issue's current state")


def resolve_parent_strategy(
    parent_key: str,
    child_issue_type: str,
    parent_issue_type: str,
    epic_link_field_id: str | None = None,
) -> dict:
    if child_issue_type.lower() == "sub-task":
        return {"extra_fields": {"parent": {"key": parent_key}}, "post_create_link": False}
    if parent_issue_type.lower() == "epic":
        if not epic_link_field_id:
            raise ValueError(
                "Parent is an Epic but no 'Epic Link' custom field was found in this "
                "project's create-meta — cannot link via the Epic Link field."
            )
        return {"extra_fields": {epic_link_field_id: parent_key}, "post_create_link": False}
    return {"extra_fields": {}, "post_create_link": True}


def find_epic_link_field_id(fields_meta: dict) -> str | None:
    for field_id, field in fields_meta.items():
        if field.get("name") == "Epic Link":
            return field_id
    return None


# Jira create-meta schema.type values (and schema.items for "array" fields) that the
# REST API expects wrapped as a reference object rather than passed as a raw scalar.
_NAME_WRAPPED_TYPES = {"user", "group", "version", "component", "project", "issuetype"}
_VALUE_WRAPPED_TYPES = {"option"}


def coerce_custom_field_value(schema: dict, value: object) -> object:
    """Shapes a plain value into the JSON structure Jira's create API expects for a
    field, based on that field's own create-meta schema (ADR 0007)."""
    field_type = schema.get("type")
    if field_type == "array":
        values = value if isinstance(value, list) else [value]
        return [coerce_custom_field_value({"type": schema.get("items")}, v) for v in values]
    if field_type in _NAME_WRAPPED_TYPES:
        return {"name": value}
    if field_type in _VALUE_WRAPPED_TYPES:
        return {"value": value}
    return value


def resolve_custom_fields(custom_fields: dict[str, object], fields_meta: dict) -> dict[str, object]:
    """Maps caller-supplied {field name: value} to {field id: coerced value} using the
    project's own create-meta, so callers never need to know a customfield_XXXXX id
    (ADR 0001, ADR 0007)."""
    field_ids_by_name = {field.get("name"): field_id for field_id, field in fields_meta.items()}
    resolved: dict[str, object] = {}
    for name, value in custom_fields.items():
        field_id = field_ids_by_name.get(name)
        if field_id is None:
            raise ValueError(
                f"Unknown Jira field {name!r} — check the exact field name on this "
                "project's issue-create screen."
            )
        resolved[field_id] = coerce_custom_field_value(fields_meta[field_id].get("schema", {}), value)
    return resolved


def find_missing_required_fields(fields_meta: dict, provided_field_ids: set[str]) -> list[str]:
    """Diffs a project's create-screen requirements against what a create call actually
    supplies, so a missing field fails with its human-readable name up front instead of
    a raw Jira 400 after the round trip (ADR 0007)."""
    always_satisfied = {"reporter"}  # Jira defaults this from the caller's own auth (ADR 0006)
    return [
        field.get("name", field_id)
        for field_id, field in fields_meta.items()
        if field.get("required") and field_id not in provided_field_ids and field_id not in always_satisfied
    ]
