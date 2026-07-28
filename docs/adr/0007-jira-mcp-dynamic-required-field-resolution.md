# jira_create_issue resolves project-specific required fields dynamically, and validates before creating

Some Jira Data Center projects add fields to the issue-create screen beyond the API's own bare minimum — Component/s, and per-project custom fields like Product or Planned Start — and mark them required. Previously `jira_create_issue` had no way to supply these, so creation failed with Jira's raw validation error after the round trip.

`jira_create_issue` now accepts `components` and `due_date` as explicit parameters for the two common standard fields, plus a generic `custom_fields: {name: value}` parameter for anything project-specific. Per ADR 0001, custom field names are resolved to their `customfield_XXXXX` id via `createmeta` at call time rather than hardcoded, and the value is coerced into the JSON shape Jira expects (e.g. a select-list field's value gets wrapped as `{"value": ...}`) based on the field's own schema type — so callers pass a plain name and a plain value without knowing Jira's per-type wire format.

Before creating, the tool now always fetches `createmeta` for the target issue type (previously fetched only when resolving a parent link) and diffs the project's required fields against what the call actually supplies. A gap fails fast with the missing fields' human-readable names, rather than surfacing as a Jira 400 after the issue almost got created. `reporter` is excluded from this check since Jira defaults it from the caller's own authenticated identity (ADR 0006), even though create-meta may still flag it as required.

## Considered Options

- **Pass through raw Jira field payloads (`fields: dict`)**: rejected — pushes Jira's `customfield_XXXXX` ids and per-type wire shapes onto every caller, which is exactly the hardcoding ADR 0001 avoids elsewhere in this server.
- **No preflight validation, rely on Jira's existing error surfacing**: rejected — the whole point of adding `custom_fields` is to make creation succeed on projects with extra required fields; silently letting a still-missing field reach Jira just delays the same failure by one round trip instead of naming it up front.
