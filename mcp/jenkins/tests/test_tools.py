import json

import httpx

from jenkins_mcp.tools import ALL_TOOLS, handle_tool


def _call(make_client, handler, name, args):
    return handle_tool(name, args, client=make_client(handler))[0].text


def _no_crumb(request):
    return "crumbIssuer" in request.url.path


def test_registry_has_38_uniquely_named_jenkins_tools():
    names = [t.name for t in ALL_TOOLS]
    assert len(names) == len(set(names)) == 38
    assert all(n.startswith("jenkins_") for n in names)


def test_every_required_argument_is_declared_in_properties():
    for t in ALL_TOOLS:
        assert set(t.inputSchema["required"]) <= set(t.inputSchema["properties"]), t.name


def test_get_job_status_hits_folder_path_and_returns_json(make_client):
    def handler(request):
        assert request.url.path == "/jenkins/job/team/job/app/api/json"
        return httpx.Response(200, json={"name": "app", "color": "blue"})

    assert json.loads(_call(make_client, handler, "jenkins_get_job_status", {"job_name": "team/app"})) == {
        "name": "app", "color": "blue",
    }


def test_search_jobs_matches_nested_jobs_case_insensitively(make_client):
    tree = {"jobs": [
        {"fullName": "team", "url": "u1", "color": None, "jobs": [
            {"fullName": "team/Deploy-Prod", "url": "u2", "color": "blue", "jobs": []},
            {"fullName": "team/build", "url": "u3", "color": "red", "jobs": []},
        ]},
    ]}

    result = json.loads(_call(make_client, lambda r: httpx.Response(200, json=tree), "jenkins_search_jobs", {"query": "deploy"}))

    assert [j["fullName"] for j in result] == ["team/Deploy-Prod"]


def test_get_job_parameters_flattens_definitions(make_client):
    body = {"property": [{}, {"parameterDefinitions": [{"name": "ENV", "type": "ChoiceParameterDefinition"}]}]}

    result = json.loads(_call(make_client, lambda r: httpx.Response(200, json=body), "jenkins_get_job_parameters", {"job_name": "x"}))

    assert result == [{"name": "ENV", "type": "ChoiceParameterDefinition"}]


def test_trigger_build_with_parameters_posts_form_and_returns_queue_url(make_client):
    seen = {}

    def handler(request):
        if _no_crumb(request):
            return httpx.Response(404)
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return httpx.Response(201, headers={"Location": "https://ci.example.com/jenkins/queue/item/7/"})

    result = json.loads(_call(make_client, handler, "jenkins_trigger_build", {"job_name": "x", "parameters": {"ENV": "qa"}}))

    assert seen == {"path": "/jenkins/job/x/buildWithParameters", "body": "ENV=qa"}
    assert result["queue_url"].endswith("/queue/item/7/")


def test_trigger_build_without_parameters_uses_plain_build(make_client):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(404) if _no_crumb(request) else httpx.Response(201)

    _call(make_client, handler, "jenkins_trigger_build", {"job_name": "x"})

    assert "/jenkins/job/x/build" in paths


def test_console_log_returns_only_the_tail(make_client):
    log = "\n".join(f"line {i}" for i in range(500))

    result = _call(make_client, lambda r: httpx.Response(200, text=log), "jenkins_get_console_log", {"job_name": "x", "tail_lines": 3})

    assert result.endswith("line 497\nline 498\nline 499")
    assert "497 earlier lines omitted" in result


def test_replay_build_extracts_original_script_from_replay_page(make_client):
    seen = {}

    def handler(request):
        if request.method == "GET" and request.url.path.endswith("/replay/"):
            return httpx.Response(200, text='<textarea name="_.mainScript">echo &quot;hi&quot; &amp;&amp; true</textarea>')
        if _no_crumb(request):
            return httpx.Response(404)
        seen["body"] = request.content.decode()
        return httpx.Response(302)

    _call(make_client, handler, "jenkins_replay_build", {"job_name": "x", "build_number": 3})

    assert 'echo \\"hi\\" && true' in httpx.QueryParams(seen["body"])["json"]


def test_get_artifact_reports_binary_by_size_and_rejects_traversal(make_client):
    handler = lambda r: httpx.Response(200, content=b"\xff\xfe\x00", headers={"content-type": "application/zip"})  # noqa: E731

    binary = json.loads(_call(make_client, handler, "jenkins_get_artifact", {"job_name": "x", "artifact_path": "out/a.zip"}))
    bad = _call(make_client, handler, "jenkins_get_artifact", {"job_name": "x", "artifact_path": "../etc"})

    assert binary["size_bytes"] == 3
    assert bad.startswith("Error:")


def test_toggle_node_offline_is_noop_when_already_in_requested_state(make_client):
    posts = []

    def handler(request):
        if request.method == "POST":
            posts.append(request.url.path)
        return httpx.Response(200, json={"offline": True})

    result = json.loads(_call(make_client, handler, "jenkins_toggle_node_offline", {"node_name": "agent1", "offline": True}))

    assert "already offline" in result["message"]
    assert posts == []


def test_toggle_node_offline_posts_when_state_differs(make_client):
    posts = []

    def handler(request):
        if _no_crumb(request):
            return httpx.Response(404)
        if request.method == "POST":
            posts.append(request.url.path)
            return httpx.Response(302)
        return httpx.Response(200, json={"offline": False})

    _call(make_client, handler, "jenkins_toggle_node_offline", {"node_name": "agent1", "offline": True})

    assert posts == ["/jenkins/computer/agent1/toggleOffline"]


def test_get_version_reads_x_jenkins_header(make_client):
    handler = lambda r: httpx.Response(200, json={}, headers={"X-Jenkins": "2.440.1"})  # noqa: E731

    assert json.loads(_call(make_client, handler, "jenkins_get_version", {})) == {"version": "2.440.1"}


def test_api_error_becomes_error_text_instead_of_raising(make_client):
    result = _call(make_client, lambda r: httpx.Response(404, text="Not Found"), "jenkins_get_job_status", {"job_name": "missing"})

    assert result.startswith("Error: Jenkins API error 404")


def test_missing_required_argument_is_named_in_error(make_client):
    result = _call(make_client, lambda r: httpx.Response(200, json={}), "jenkins_get_job_status", {})

    assert result == "Error: Missing required argument: job_name"


def test_unknown_tool_returns_error(make_client):
    assert _call(make_client, lambda r: httpx.Response(200), "jenkins_nope", {}).startswith("Error: Unknown tool")


def test_unreachable_jenkins_becomes_error_text(make_client):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    result = _call(make_client, handler, "jenkins_get_job_status", {"job_name": "x"})

    assert result.startswith("Error: Could not reach Jenkins")
