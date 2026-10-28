"""Jenkins job tools."""
from __future__ import annotations

from ..client import job_path
from ._base import JOB, fmt, text, tool

_JOB_LEAF = "fullName,url,color,_class"
_JOB_STATUS_TREE = (
    "name,fullName,url,description,color,buildable,inQueue,"
    "lastBuild[number,url,result,building,timestamp],"
    "lastSuccessfulBuild[number,url],lastFailedBuild[number,url],"
    "healthReport[description,score]"
)
_PARAMS_TREE = (
    "property[parameterDefinitions[name,type,description,"
    "defaultParameterValue[value],choices]]"
)
_NAME_ARG = {"type": "string", "description": "Name of the new job (no slashes)."}
_FOLDER_ARG = {
    "type": "string",
    "description": "Folder to create the job in, e.g. 'team/app'. Omit for the Jenkins root.",
}


def _item_status(job: dict) -> dict:
    return {"fullName": job.get("fullName"), "url": job.get("url"), "color": job.get("color")}


@tool(
    "jenkins_list_jobs",
    "List jobs (and folders) directly under the Jenkins root or a folder.",
    {"folder": {"type": "string", "description": "Folder full name, e.g. 'team/app'. Omit for the root."}},
    read_only=True,
)
def list_jobs(client, args):
    data = client.get_json(job_path(args.get("folder", "")), tree=f"jobs[{_JOB_LEAF}]")
    return fmt(data.get("jobs", []))


@tool(
    "jenkins_search_jobs",
    "Find jobs whose full name contains the query (case-insensitive), searching up to 3 folder levels deep.",
    {
        "query": {"type": "string", "description": "Substring to match against the job's full name."},
        "folder": {"type": "string", "description": "Folder to search under. Omit for the root."},
    },
    ["query"],
    read_only=True,
)
def search_jobs(client, args):
    leaf = "fullName,url,color"
    tree = f"jobs[{leaf},jobs[{leaf},jobs[{leaf}]]]"
    data = client.get_json(job_path(args.get("folder", "")), tree=tree)

    needle = args["query"].lower()
    matches: list[dict] = []

    def walk(jobs: list[dict]) -> None:
        for job in jobs:
            if needle in (job.get("fullName") or "").lower():
                matches.append(_item_status(job))
            walk(job.get("jobs", []))

    walk(data.get("jobs", []))
    return fmt(matches)


@tool(
    "jenkins_get_job_status",
    "Get a job's status: health, buildability, queue state and its last / last successful / last failed builds.",
    JOB,
    ["job_name"],
    read_only=True,
)
def get_job_status(client, args):
    return fmt(client.get_json(job_path(args["job_name"]), tree=_JOB_STATUS_TREE))


@tool(
    "jenkins_get_job_parameters",
    "List the build parameters a job accepts (name, type, default, choices).",
    JOB,
    ["job_name"],
    read_only=True,
)
def get_job_parameters(client, args):
    data = client.get_json(job_path(args["job_name"]), tree=_PARAMS_TREE)
    definitions = [
        definition
        for prop in data.get("property", [])
        for definition in prop.get("parameterDefinitions", [])
    ]
    return fmt(definitions)


@tool("jenkins_enable_job", "Enable a disabled job.", JOB, ["job_name"])
def enable_job(client, args):
    client.post(f"{job_path(args['job_name'])}/enable")
    return fmt({"message": f"Job '{args['job_name']}' enabled."})


@tool("jenkins_disable_job", "Disable a job so it no longer builds.", JOB, ["job_name"])
def disable_job(client, args):
    client.post(f"{job_path(args['job_name'])}/disable")
    return fmt({"message": f"Job '{args['job_name']}' disabled."})


@tool(
    "jenkins_delete_job",
    "Permanently delete a job and all of its build history. Cannot be undone.",
    JOB,
    ["job_name"],
    destructive=True,
)
def delete_job(client, args):
    client.post(f"{job_path(args['job_name'])}/doDelete")
    return fmt({"message": f"Job '{args['job_name']}' deleted."})


@tool(
    "jenkins_get_job_config",
    "Get a job's config.xml.",
    JOB,
    ["job_name"],
    read_only=True,
)
def get_job_config(client, args):
    return text(client.get_text(f"{job_path(args['job_name'])}/config.xml"))


@tool(
    "jenkins_create_job",
    "Create a job from a config.xml document.",
    {"name": _NAME_ARG, "folder": _FOLDER_ARG, "config_xml": {"type": "string", "description": "Full config.xml content."}},
    ["name", "config_xml"],
)
def create_job(client, args):
    client.post(
        f"{job_path(args.get('folder', ''))}/createItem",
        params={"name": args["name"]},
        content=args["config_xml"],
        content_type="application/xml",
    )
    return fmt({"message": f"Job '{args['name']}' created."})


@tool(
    "jenkins_update_job_config",
    "Replace a job's config.xml. Fetch the current one with jenkins_get_job_config first and edit it.",
    {**JOB, "config_xml": {"type": "string", "description": "Full replacement config.xml content."}},
    ["job_name", "config_xml"],
    destructive=True,
)
def update_job_config(client, args):
    client.post(
        f"{job_path(args['job_name'])}/config.xml",
        content=args["config_xml"],
        content_type="application/xml",
    )
    return fmt({"message": f"Job '{args['job_name']}' configuration updated."})


@tool(
    "jenkins_rename_job",
    "Rename a job (it stays in its current folder).",
    {**JOB, "new_name": {"type": "string", "description": "New job name (no slashes)."}},
    ["job_name", "new_name"],
)
def rename_job(client, args):
    client.post(f"{job_path(args['job_name'])}/doRename", params={"newName": args["new_name"]})
    return fmt({"message": f"Job '{args['job_name']}' renamed to '{args['new_name']}'."})


@tool(
    "jenkins_copy_job",
    "Copy an existing job to a new name, optionally into another folder.",
    {
        "source_job": {"type": "string", "description": "Full name of the job to copy."},
        "new_name": _NAME_ARG,
        "folder": _FOLDER_ARG,
    },
    ["source_job", "new_name"],
)
def copy_job(client, args):
    client.post(
        f"{job_path(args.get('folder', ''))}/createItem",
        params={"name": args["new_name"], "mode": "copy", "from": "/" + args["source_job"].strip("/")},
    )
    return fmt({"message": f"Job '{args['source_job']}' copied to '{args['new_name']}'."})
