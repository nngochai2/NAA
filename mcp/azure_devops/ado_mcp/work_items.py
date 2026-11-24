"""Work item queries: details, WIQL search, discussion history, relations."""
from __future__ import annotations

import html
import logging
import re
from typing import Any

from .client import AdoClient

logger = logging.getLogger("ado-mcp")


def display_name(field: Any) -> str | None:
    if isinstance(field, dict):
        return field.get("displayName") or field.get("name")
    return field


def strip_html(raw_html: str) -> str:
    """Naïve HTML stripper — good enough for ADO description fields."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_work_item(client: AdoClient, item_id: int) -> dict[str, Any]:
    data = client.get(client.wi_url(f"workitems/{item_id}"), params={"$expand": "all"})
    fields = data.get("fields", {})
    relations = data.get("relations", [])

    # Flatten the most useful fields
    return {
        "id": data.get("id"),
        "url": data.get("_links", {}).get("html", {}).get("href", ""),
        "type": fields.get("System.WorkItemType"),
        "title": fields.get("System.Title"),
        "state": fields.get("System.State"),
        "assigned_to": display_name(fields.get("System.AssignedTo")),
        "created_by": display_name(fields.get("System.CreatedBy")),
        "created_date": fields.get("System.CreatedDate"),
        "changed_date": fields.get("System.ChangedDate"),
        "iteration": fields.get("System.IterationPath"),
        "area": fields.get("System.AreaPath"),
        "priority": fields.get("Microsoft.VSTS.Common.Priority"),
        "description": strip_html(fields.get("System.Description", "")),
        "acceptance_criteria": strip_html(
            fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", "")
        ),
        "tags": fields.get("System.Tags", ""),
        "relations": [
            {
                "rel": r.get("rel"),
                "url": r.get("url"),
                "attributes": r.get("attributes", {}),
            }
            for r in relations
        ],
    }


def search_work_items(client: AdoClient, wiql_where: str, top: int = 20) -> list[dict[str, Any]]:
    """
    Run a WIQL query. Pass a WHERE clause fragment, e.g.:
      "[System.State] = 'Active' AND [System.IterationPath] UNDER 'Sprint 12'"
    """
    query = (
        f"SELECT [System.Id], [System.Title], [System.State], "
        f"[System.WorkItemType], [System.AssignedTo] "
        f"FROM WorkItems "
        f"WHERE [System.TeamProject] = '{client.project}' AND {wiql_where} "
        f"ORDER BY [System.ChangedDate] DESC"
    )
    data = client.post(client.wi_url("wiql"), body={"query": query}, params={"$top": top})
    items = data.get("workItems", [])
    if not items:
        return []

    ids = ",".join(str(i["id"]) for i in items[:top])
    batch = client.get(
        client.wi_url("workitems"),
        params={
            "ids": ids,
            "fields": "System.Id,System.Title,System.State,"
                      "System.WorkItemType,System.AssignedTo,System.IterationPath",
        },
    )
    return [
        {
            "id": w["id"],
            "type": w["fields"].get("System.WorkItemType"),
            "title": w["fields"].get("System.Title"),
            "state": w["fields"].get("System.State"),
            "assigned_to": display_name(w["fields"].get("System.AssignedTo")),
            "iteration": w["fields"].get("System.IterationPath"),
        }
        for w in batch.get("value", [])
    ]


def fetch_comments(client: AdoClient, item_id: int) -> list[dict[str, Any]]:
    """
    Reads discussion history via the work-item revisions endpoint (api-version 5.0),
    which works on all on-prem ADO Server versions.  Each revision that has a
    non-empty System.History field is one comment / history entry.
    """
    data = client.get(client.wi_url(f"workitems/{item_id}/revisions"))
    results = []
    for rev in data.get("value", []):
        fields = rev.get("fields", {})
        history = strip_html(fields.get("System.History", ""))
        if not history:
            continue
        results.append({
            "revision": rev.get("rev"),
            "author": display_name(fields.get("System.ChangedBy")),
            "date": fields.get("System.ChangedDate"),
            "text": history,
        })
    return results


def fetch_related_items(client: AdoClient, item_id: int) -> list[dict[str, Any]]:
    """Return work-item relations with resolved titles where possible."""
    item = fetch_work_item(client, item_id)
    results = []
    for rel in item.get("relations", []):
        rel_type = rel.get("rel", "")
        url = rel.get("url", "")

        # Resolve only work-item links (not attachments, hyperlinks, etc.)
        if "_apis/wit/workitems/" in url:
            try:
                related_id = int(url.rstrip("/").split("/")[-1])
                related = client.get(client.wi_url(f"workitems/{related_id}"))
                f = related.get("fields", {})
                results.append(
                    {
                        "relation_type": rel_type,
                        "id": related_id,
                        "type": f.get("System.WorkItemType"),
                        "title": f.get("System.Title"),
                        "state": f.get("System.State"),
                    }
                )
            except Exception as e:
                logger.warning("Could not resolve related item from %s: %s", url, e)
        else:
            results.append(
                {
                    "relation_type": rel_type,
                    "url": url,
                    "attributes": rel.get("attributes", {}),
                }
            )
    return results
