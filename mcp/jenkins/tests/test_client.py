import httpx
import pytest

from jenkins_mcp.client import JenkinsApiError, build_path, job_path


def test_job_path_expands_folders_and_quotes_segments():
    assert job_path("team/app/main") == "/job/team/job/app/job/main"
    assert job_path("my job") == "/job/my%20job"
    assert job_path("") == ""


def test_job_path_rejects_traversal():
    with pytest.raises(ValueError):
        job_path("team/../secret")


def test_build_path_defaults_to_last_build():
    assert build_path("a/b") == "/job/a/job/b/lastBuild"
    assert build_path("a", 42) == "/job/a/42"


def test_post_sends_crumb_when_issuer_available(make_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/crumbIssuer/api/json"):
            return httpx.Response(200, json={"crumbRequestField": "Jenkins-Crumb", "crumb": "abc"})
        seen["crumb"] = request.headers.get("jenkins-crumb")
        seen["path"] = request.url.path
        return httpx.Response(302)

    make_client(handler).post("/job/x/disable")

    assert seen == {"crumb": "abc", "path": "/jenkins/job/x/disable"}


def test_post_works_when_crumbs_are_disabled(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if "crumbIssuer" in request.url.path:
            return httpx.Response(404)
        assert "jenkins-crumb" not in request.headers
        return httpx.Response(200)

    make_client(handler).post("/job/x/disable")


def test_http_error_html_is_reduced_to_plain_message(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="<html><body><h1>Forbidden</h1><p>No Overall/Read</p></body></html>")

    with pytest.raises(JenkinsApiError) as exc:
        make_client(handler).get_json("/job/x")

    assert exc.value.status_code == 403
    assert "Forbidden" in exc.value.message and "<" not in exc.value.message
