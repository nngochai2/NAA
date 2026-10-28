"""Jenkins test-result and artifact tools."""
from __future__ import annotations

from urllib.parse import quote

from ..client import build_path
from ._base import BUILD, JOB, err, fmt, text, tool

_DEFAULT_ARTIFACT_BYTES = 100_000
_TEST_TREE = (
    "duration,failCount,passCount,skipCount,"
    "suites[name,duration,cases[className,name,status,duration,errorDetails]]"
)


@tool(
    "jenkins_get_test_results",
    "Get a build's test report: pass/fail/skip counts and, per suite, the individual cases. "
    "Passing cases are dropped to keep the output small.",
    {**JOB, **BUILD},
    ["job_name"],
    read_only=True,
)
def get_test_results(client, args):
    data = client.get_json(f"{build_path(args['job_name'], args.get('build_number'))}/testReport", tree=_TEST_TREE)
    for suite in data.get("suites", []):
        suite["cases"] = [c for c in suite.get("cases", []) if c.get("status") not in ("PASSED", "FIXED")]
    return fmt(data)


@tool(
    "jenkins_list_artifacts",
    "List the artifacts archived by a build.",
    {**JOB, **BUILD},
    ["job_name"],
    read_only=True,
)
def list_artifacts(client, args):
    data = client.get_json(build_path(args["job_name"], args.get("build_number")), tree="artifacts[fileName,relativePath]")
    return fmt(data.get("artifacts", []))


@tool(
    "jenkins_get_artifact",
    "Read a text artifact archived by a build. Binary files are reported by size only.",
    {
        **JOB,
        **BUILD,
        "artifact_path": {"type": "string", "description": "Artifact relativePath from jenkins_list_artifacts."},
        "max_bytes": {"type": "integer", "description": "Maximum bytes of text to return.", "default": _DEFAULT_ARTIFACT_BYTES},
    },
    ["job_name", "artifact_path"],
    read_only=True,
)
def get_artifact(client, args):
    relative = args["artifact_path"].strip("/")
    if any(part in ("", ".", "..") for part in relative.split("/")):
        return err(f"Invalid artifact path: {args['artifact_path']!r}")
    quoted = "/".join(quote(part, safe="") for part in relative.split("/"))
    body, content_type = client.get_bytes(f"{build_path(args['job_name'], args.get('build_number'))}/artifact/{quoted}")

    try:
        content = body.decode("utf-8")
    except UnicodeDecodeError:
        return fmt({"path": relative, "size_bytes": len(body), "content_type": content_type,
                    "message": "Binary artifact; content not returned."})

    limit = int(args.get("max_bytes", _DEFAULT_ARTIFACT_BYTES))
    if len(body) > limit:
        content = content[:limit] + f"\n... (truncated, {len(body)} bytes total)"
    return text(content)
