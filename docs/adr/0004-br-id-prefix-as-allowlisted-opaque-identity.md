---
status: accepted
---

# BR ID prefixes are allow-listed and preserved verbatim, never interpreted as categories

Some FDD/SDD documents contain more than one business-rule table, each with its own ID prefix (e.g. `BRU01`, `BRU23` in one table, `BRM01`, `BRM23` in another). These prefixes are meaningful to the document's author — they mark distinct rule groupings — but we deliberately do not decode what a given prefix *means*. `docx_generic_parser.py` validates each prefix against a per-rule-file allow-list (`parsing-rules/*.yml`) so unrecognized/typo'd prefixes surface as warnings instead of vanishing silently, then preserves the matched ID string verbatim (e.g. `BRU01`) as part of the BR's identity (`uc_id::doc_type::br_id`) and `:BR` node label. We considered splitting prefixes into separate Neo4j labels (`:BR_Utility`, `:BR_Main`) or an inferred `group`/`category` property, but rejected both: they'd require someone to interpret and hardcode what each prefix "means," which is guesswork the parser has no business doing, and it would fork the uniform treatment `link_same_as_brs`, `candidate_categories`, and the UI already give every BR node regardless of source table.
