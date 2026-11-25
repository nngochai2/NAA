"""Specification requirements tools — Flow → UseCase → Document → BR."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from ..app import get_db, mcp


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_use_cases(flow_name: str = "") -> str:
    """
    List all UseCases under a flow.

    Args:
        flow_name: The flow to query.
    """
    ucs = get_db().get_use_cases(flow_name.strip())
    if not ucs:
        return f"No UseCases found for flow '{flow_name}'."
    lines = [f"UseCases for flow '{flow_name}' ({len(ucs)}):\n"]
    for uc in ucs:
        lines.append(f"  {uc['uc_id']}  (project: {uc.get('project_id', '?')})")
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_documents(uc_id: str, flow_name: str = "") -> str:
    """
    List all Documents (FDD, SDD, UC …) under a UseCase.

    Args:
        uc_id:     The UseCase ID, e.g. "UC36".
        flow_name: The flow name.
    """
    docs = get_db().get_documents(uc_id.strip().upper(), flow_name.strip())
    if not docs:
        return f"No Documents found for {uc_id} in flow '{flow_name}'."
    lines = [f"Documents for {uc_id} / flow '{flow_name}':\n"]
    for d in docs:
        lines.append(f"  [{d['doc_type']}]  {d.get('source_file', '?')}")
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_requirements(flow_name: str = "") -> str:
    """
    List all BRs (business requirements) extracted from specification documents.
    Shows BR ID, UC, doc_type, title, and categories.

    Args:
        flow_name: Flow to filter by. Leave empty to return BRs across all flows.
    """
    brs = get_db().get_requirements(flow_name.strip() if flow_name else None)
    if not brs:
        return f"No BRs found for flow '{flow_name}'."
    lines = [f"BRs ({len(brs)}) for flow '{flow_name}':\n"]
    for b in brs:
        cats = b.get("confirmed_categories") or b.get("candidate_categories") or "[]"
        lines.append(
            f"[{b['br_id']}] {b.get('uc_id', '')}/{b.get('doc_type', '')}  {b['title'][:75]}"
        )
        if cats and cats != "[]":
            lines.append(f"    categories: {cats}")
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_requirement_detail(
    br_id: str,
    uc_id: str,
    doc_type: str,
    flow_name: str = "",
) -> str:
    """
    Get the full body of a single BR node, including the parent Document context
    (intro/scope/background), affected fields, categories, and source file.

    Args:
        br_id:     The BR identifier, e.g. "BR03".
        uc_id:     The UseCase ID, e.g. "UC36".
        doc_type:  Document type: "FDD", "SDD", or "UC".
        flow_name: Flow the BR belongs to.
    """
    r = get_db().get_requirement_detail(
        br_id.strip().upper(),
        uc_id.strip().upper(),
        doc_type.strip().upper(),
        flow_name.strip(),
    )
    if not r:
        return f"No BR found for {br_id} / {uc_id} / {doc_type} in flow '{flow_name}'."
    lines = [
        f"**[{r['br_id']}] {r['title']}**",
        f"UC: {r.get('uc_id', '')}  |  doc_type: {r.get('doc_type', '')}  |  "
        f"flow: {r.get('flow_name', '')}  |  source: {r.get('source_file', '')}",
    ]
    confirmed = r.get("confirmed_categories") or ""
    candidate = r.get("candidate_categories") or ""
    if confirmed and confirmed != "[]":
        lines.append(f"**Categories (confirmed):** {confirmed}")
    elif candidate and candidate != "[]":
        lines.append(f"**Categories (candidate):** {candidate}")
    if r.get("document_context"):
        lines += ["", "### Document Context (intro / scope / background)", r["document_context"]]
    if r.get("body"):
        lines += ["", "### Requirement Body", r["body"]]
    fields = r.get("affected_fields", "[]")
    if fields and fields != "[]":
        lines += ["", f"**Affected fields:** {fields}"]
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def assign_br_category(
    br_id: str,
    uc_id: str,
    doc_type: str,
    flow_name: str,
    categories: str,
) -> str:
    """
    Confirm the implementation category/categories for a BR node.
    Updates confirmed_categories, overwriting any previous value.

    Args:
        br_id:      The BR identifier, e.g. "BR04".
        uc_id:      The UseCase ID, e.g. "UC36".
        doc_type:   Document type: "FDD", "SDD", or "UC".
        flow_name:  The flow name.
        categories: Comma-separated category labels to assign.
    """
    cats = [c.strip() for c in categories.split(",") if c.strip()]
    found = get_db().set_br_categories(
        br_id.strip().upper(),
        uc_id.strip().upper(),
        doc_type.strip().upper(),
        flow_name.strip(),
        cats,
    )
    if not found:
        return f"No BR found for {br_id} / {uc_id} / {doc_type} in flow '{flow_name}'."
    return f"✅ Set confirmed_categories = {cats} on {br_id} ({uc_id}/{doc_type}/{flow_name})."
