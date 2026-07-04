"""Pure decision logic for Jira's per-instance configuration (ADR 0001, ADR 0003).

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
