import json

from conftest import BASE, wi_path

from ado_mcp import work_items


def _work_item(item_id=42, relations=None):
    return {
        "id": item_id,
        "_links": {"html": {"href": f"{BASE}/Proj/_workitems/edit/{item_id}"}},
        "fields": {
            "System.WorkItemType": "Bug",
            "System.Title": "Totals wrong",
            "System.State": "Active",
            "System.AssignedTo": {"displayName": "Dev One", "uniqueName": "DOM\\dev1"},
            "System.CreatedBy": {"name": "Creator"},
            "System.Description": "<div>Line&nbsp;one<br/>  line   two</div>",
            "Microsoft.VSTS.Common.Priority": 2,
        },
        "relations": relations or [],
    }


def test_strip_html_and_display_name():
    assert work_items.strip_html("<p>a &amp; b</p>\n\n<b>c</b>") == "a & b c"
    assert work_items.strip_html("") == ""
    assert work_items.display_name({"name": "N"}) == "N"
    assert work_items.display_name("plain") == "plain"


def test_fetch_work_item_flattens_fields(client, ado):
    ado.add("GET", wi_path("workitems/42"), _work_item())
    item = work_items.fetch_work_item(client, 42)
    assert item["title"] == "Totals wrong"
    assert item["assigned_to"] == "Dev One"
    assert item["created_by"] == "Creator"
    assert item["description"] == "Line one line two"  # &nbsp; collapses like whitespace
    assert item["acceptance_criteria"] == ""
    assert item["url"].endswith("/_workitems/edit/42")
    assert ado.requests[-1].url.params["$expand"] == "all"


def test_search_scopes_to_project_and_batches_ids(client, ado):
    ado.add("POST", wi_path("wiql"), {"workItems": [{"id": 1}, {"id": 2}, {"id": 3}]})
    ado.add("GET", wi_path("workitems"), {"value": [
        {"id": 1, "fields": {"System.Title": "A", "System.AssignedTo": {"displayName": "X"}}},
        {"id": 2, "fields": {"System.Title": "B"}},
    ]})

    results = work_items.search_work_items(client, "[System.State] = 'Active'", top=2)

    wiql = json.loads(ado.requests[0].content)["query"]
    assert "WHERE [System.TeamProject] = 'Proj' AND [System.State] = 'Active'" in wiql
    assert ado.requests[0].url.params["$top"] == "2"
    assert ado.requests[1].url.params["ids"] == "1,2"
    assert results[0] == {"id": 1, "type": None, "title": "A", "state": None,
                          "assigned_to": "X", "iteration": None}


def test_search_with_no_hits_skips_batch_call(client, ado):
    ado.add("POST", wi_path("wiql"), {"workItems": []})
    assert work_items.search_work_items(client, "1=1") == []
    assert len(ado.requests) == 1


def test_fetch_comments_skips_revisions_without_history(client, ado):
    ado.add("GET", wi_path("workitems/7/revisions"), {"value": [
        {"rev": 1, "fields": {"System.History": ""}},
        {"rev": 2, "fields": {"System.History": "<p>Decided to defer</p>",
                              "System.ChangedBy": {"displayName": "PM"},
                              "System.ChangedDate": "2026-01-01"}},
    ]})
    assert work_items.fetch_comments(client, 7) == [
        {"revision": 2, "author": "PM", "date": "2026-01-01", "text": "Decided to defer"},
    ]


def test_fetch_related_items_resolves_work_item_links(client, ado):
    relations = [
        {"rel": "System.LinkTypes.Hierarchy-Reverse",
         "url": f"{BASE}/_apis/wit/workItems/10"},          # not resolvable (case)
        {"rel": "System.LinkTypes.Related", "url": f"{BASE}/_apis/wit/workitems/11"},
        {"rel": "System.LinkTypes.Related", "url": f"{BASE}/_apis/wit/workitems/12"},
        {"rel": "Hyperlink", "url": "https://wiki/page", "attributes": {"comment": "spec"}},
    ]
    ado.add("GET", wi_path("workitems/42"), _work_item(relations=relations))
    ado.add("GET", wi_path("workitems/11"),
            {"fields": {"System.Title": "Parent", "System.State": "Done"}})
    # workitems/12 has no route → 404 → logged and skipped

    related = work_items.fetch_related_items(client, 42)

    assert {"relation_type": "System.LinkTypes.Related", "id": 11, "type": None,
            "title": "Parent", "state": "Done"} in related
    assert {"relation_type": "Hyperlink", "url": "https://wiki/page",
            "attributes": {"comment": "spec"}} in related
    assert not any(r.get("id") == 12 for r in related)
    assert len(related) == 3
