# Obsidian Vault Note Format

New notes use YAML frontmatter. The parser (`pipeline/src/parser.py`) also accepts the legacy custom header for existing notes.

---

## Minimal (always include)

```yaml
---
created: YYYY-MM-DD
status: draft
tags:
  - component/pipeline
---
```

## Full (include fields that apply)

```yaml
---
created: YYYY-MM-DD
status: verified
tags:
  - component/oracle-sql
  - domain/compliance
domain: compliance
source: EU Directive 2006/112/EC, Art. 151
confidence: high
last_verified: YYYY-MM-DD
expires: YYYY-MM-DD
---

## Related

See also [[Note A]] and [[Note B]].
```

---

## Field Reference

| Field | Maps to | Notes |
|---|---|---|
| `created` | `Note.created_at` | ISO date `YYYY-MM-DD` |
| `status` | `Note.status` | `draft` → `in-review` → `verified` → `deprecated` |
| `tags` | `TAGGED_WITH` relationships | Use namespaced strings — see tag conventions below |
| `domain` | `Note.metadata` | Used by overnight agent for domain rotation |
| `source` | `Note.metadata` | External document or regulation reference |
| `confidence` | `Note.metadata` | `high` / `medium` / `low` — agent-generated notes set this |
| `last_verified` | `Note.metadata` | ISO date — for compliance notes |
| `expires` | `Note.metadata` | ISO date — for time-sensitive compliance notes |

---

## Tag Namespace Conventions

| Prefix | Meaning | Example |
|---|---|---|
| `component/` | System part | `component/mcp`, `component/pipeline` |
| `domain/` | Business domain | `domain/compliance`, `domain/invoicing` |
| `tech/` | Technology | `tech/neo4j`, `tech/python` |

---

## Rules

- **No wikilinks in YAML.** Obsidian does not render `[[...]]` inside frontmatter — they generate no backlinks and no graph edges. Put cross-note links in the note body instead.
- **No `title:` field.** The filename is authoritative for link resolution; a YAML title is ignored by the parser.
- **No `related:` field.** Use body wikilinks (`See also [[...]]`) — the parser extracts them automatically as `LINKS_TO` relationships.
