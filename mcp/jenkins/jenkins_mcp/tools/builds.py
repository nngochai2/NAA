"""Jenkins build tools."""
from __future__ import annotations

import html
import json
import re

from ..client import build_path, job_path
from ._base import BUILD, JOB, err, fmt, text, tool

_BUILD_TREE = (
    "number,url,displayName,result,building,timestamp,duration,estimatedDuration,"
    "description,builtOn,actions[causes[shortDescription],parameters[name,value]]"
)
_DEFAULT_LOG_TAIL_LINES = 200
_MAX_LOG_CHARS = 100_000


@tool(
    "jenkins_get_build_status",
    "Get the status of one build: result, duration, who/what started it and its parameters.",
    {**JOB, **BUILD},
    ["job_name"],
    read_only=True,
)
def get_build_status(client, args):
    path = build_path(args["job_name"], args.get("build_number"))
    return fmt(client.get_json(path, tree=_BUILD_TREE))


@tool(
    "jenkins_get_recent_builds",
    "List a job's most recent builds, newest first.",
    {**JOB, "limit": {"type": "integer", "description": "Maximum builds to return.", "default": 10}},
    ["job_name"],
    read_only=True,
)
def get_recent_builds(client, args):
    limit = max(1, int(args.get("limit", 10)))
    tree = f"builds[number,url,result,building,timestamp,duration]{{0,{limit}}}"
    return fmt(client.get_json(job_path(args["job_name"]), tree=tree).get("builds", []))


@tool(
    "jenkins_trigger_build",
    "Trigger a build, optionally with parameters. Returns the queue item URL.",
    {
        **JOB,
        "parameters": {
            "type": "object",
            "description": "Build parameters as name -> value. Omit for a parameterless job.",
            "additionalProperties": {"type": ["string", "number", "boolean"]},
        },
    },
    ["job_name"],
)
def trigger_build(client, args):
    path = job_path(args["job_name"])
    parameters = args.get("parameters")
    if parameters:
        resp = client.post(f"{path}/buildWithParameters", data={k: str(v) for k, v in parameters.items()})
    else:
        resp = client.post(f"{path}/build")
    return fmt({
        "message": f"Build of '{args['job_name']}' queued.",
        "queue_url": resp.headers.get("Location"),
    })


@tool("jenkins_stop_build", "Abort a running build.", {**JOB, **BUILD}, ["job_name"])
def stop_build(client, args):
    client.post(f"{build_path(args['job_name'], args.get('build_number'))}/stop")
    return fmt({"message": f"Stop requested for build of '{args['job_name']}'."})


@tool(
    "jenkins_delete_build",
    "Permanently delete a build and its logs/artifacts. Cannot be undone.",
    {**JOB, "build_number": {"type": "integer", "description": "Build number to delete."}},
    ["job_name", "build_number"],
    destructive=True,
)
def delete_build(client, args):
    client.post(f"{build_path(args['job_name'], args['build_number'])}/doDelete")
    return fmt({"message": f"Build #{args['build_number']} of '{args['job_name']}' deleted."})


@tool(
    "jenkins_replay_build",
    "Replay a Pipeline build with the same script, or with an edited one. Needs the Pipeline "
    "'Replay' feature (Pipeline: Groovy plugin).",
    {
        **JOB,
        **BUILD,
        "script": {"type": "string", "description": "Replacement main Jenkinsfile script. Omit to reuse the original."},
    },
    ["job_name"],
)
def replay_build(client, args):
    path = f"{build_path(args['job_name'], args.get('build_number'))}/replay"
    script = args.get("script")
    if script is None:
        page = client.get_text(f"{path}/")
        match = re.search(r'<textarea[^>]*name="(?:_\.)?mainScript"[^>]*>(.*?)</textarea>', page, re.S)
        if not match:
            return err("Could not read the original script from the replay page; pass 'script' explicitly.")
        script = html.unescape(match.group(1))
    client.post(
        f"{path}/run",
        data={"json": json.dumps({"mainScript": script, "loadedScripts": {}}), "Submit": "Run"},
    )
    return fmt({"message": f"Replay of '{args['job_name']}' queued."})


@tool(
    "jenkins_get_console_log",
    "Get a build's console output. Returns the last N lines (default 200) to keep it manageable.",
    {
        **JOB,
        **BUILD,
        "tail_lines": {"type": "integer", "description": "Number of trailing lines; 0 returns the whole log.", "default": _DEFAULT_LOG_TAIL_LINES},
    },
    ["job_name"],
    read_only=True,
)
def get_console_log(client, args):
    log = client.get_text(f"{build_path(args['job_name'], args.get('build_number'))}/consoleText")
    tail = int(args.get("tail_lines", _DEFAULT_LOG_TAIL_LINES))
    if tail > 0:
        lines = log.splitlines()
        if len(lines) > tail:
            log = f"... ({len(lines) - tail} earlier lines omitted)\n" + "\n".join(lines[-tail:])
    if len(log) > _MAX_LOG_CHARS:
        log = "... (truncated)\n" + log[-_MAX_LOG_CHARS:]
    return text(log)


@tool(
    "jenkins_get_build_changes",
    "Get the source changes (commits, authors, files) included in a build.",
    {**JOB, **BUILD},
    ["job_name"],
    read_only=True,
)
def get_build_changes(client, args):
    tree = "changeSets[kind,items[commitId,author[fullName],msg,timestamp,paths[editType,file]]]"
    data = client.get_json(build_path(args["job_name"], args.get("build_number")), tree=tree)
    return fmt(data.get("changeSets", []))


@tool(
    "jenkins_get_pipeline_stages",
    "Get the stages of a Pipeline build with status and timings (needs the Pipeline: Stage View plugin).",
    {**JOB, **BUILD},
    ["job_name"],
    read_only=True,
)
def get_pipeline_stages(client, args):
    path = f"{build_path(args['job_name'], args.get('build_number'))}/wfapi/describe"
    return fmt(client.get_json_at(path))
