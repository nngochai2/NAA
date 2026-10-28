"""Jenkins queue, node, view and system-administration tools."""
from __future__ import annotations

from urllib.parse import quote

from ..client import job_path
from ._base import fmt, tool

_NODE = {"node_name": {"type": "string", "description": "Node name; '(built-in)' for the controller."}}
_QUEUE_TREE = "items[id,why,stuck,blocked,inQueueSince,task[name,fullDisplayName,url]]"
_NODE_TREE = "displayName,description,offline,temporarilyOffline,offlineCauseReason,idle,numExecutors"


def _node_path(name: str) -> str:
    return f"/computer/{quote(name, safe='')}"


def _view_path(name: str) -> str:
    return "".join(f"/view/{quote(part, safe='')}" for part in name.strip("/").split("/") if part)


# --- queue -------------------------------------------------------------------

@tool("jenkins_get_queue", "List the items waiting in the build queue and why they are waiting.", read_only=True)
def get_queue(client, args):
    return fmt(client.get_json("/queue", tree=_QUEUE_TREE).get("items", []))


@tool(
    "jenkins_cancel_queue",
    "Remove an item from the build queue.",
    {"queue_id": {"type": "integer", "description": "Queue item id from jenkins_get_queue."}},
    ["queue_id"],
)
def cancel_queue(client, args):
    client.post("/queue/cancelItem", params={"id": int(args["queue_id"])})
    return fmt({"message": f"Queue item {args['queue_id']} cancelled."})


# --- nodes -------------------------------------------------------------------

@tool("jenkins_list_nodes", "List all nodes (controller and agents) with online/idle state.", read_only=True)
def list_nodes(client, args):
    tree = f"computer[{_NODE_TREE}],busyExecutors,totalExecutors"
    return fmt(client.get_json("/computer", tree=tree))


@tool("jenkins_get_node", "Get details of one node, including its executors and labels.", _NODE, ["node_name"], read_only=True)
def get_node(client, args):
    tree = f"{_NODE_TREE},assignedLabels[name],executors[idle,currentExecutable[url,fullDisplayName]]"
    return fmt(client.get_json(_node_path(args["node_name"]), tree=tree))


@tool(
    "jenkins_toggle_node_offline",
    "Take a node offline or bring it back online. Does nothing if the node is already in the requested state.",
    {
        **_NODE,
        "offline": {"type": "boolean", "description": "true to take the node offline, false to bring it online."},
        "message": {"type": "string", "description": "Reason shown in Jenkins when taking a node offline."},
    },
    ["node_name", "offline"],
)
def toggle_node_offline(client, args):
    path = _node_path(args["node_name"])
    wanted = bool(args["offline"])
    if bool(client.get_json(path, tree="offline").get("offline")) == wanted:
        return fmt({"message": f"Node '{args['node_name']}' is already {'offline' if wanted else 'online'}."})
    client.post(f"{path}/toggleOffline", params={"offlineMessage": args.get("message", "")})
    return fmt({"message": f"Node '{args['node_name']}' is now {'offline' if wanted else 'online'}."})


# --- system ------------------------------------------------------------------

@tool("jenkins_get_system_info", "Get general Jenkins controller info: mode, executors, quieting-down state.", read_only=True)
def get_system_info(client, args):
    tree = "mode,nodeName,nodeDescription,numExecutors,useSecurity,useCrumbs,quietingDown,slaveAgentPort"
    return fmt(client.get_json("", tree=tree))


@tool("jenkins_get_version", "Get the Jenkins version.", read_only=True)
def get_version(client, args):
    return fmt({"version": client.get_version()})


@tool("jenkins_get_plugins", "List installed plugins with version and enabled state.", read_only=True)
def get_plugins(client, args):
    tree = "plugins[shortName,longName,version,enabled,active,hasUpdate]"
    return fmt(client.get_json("/pluginManager", tree=tree, depth=1).get("plugins", []))


@tool(
    "jenkins_quiet_down",
    "Put Jenkins in quiet-down mode: running builds finish, no new builds start.",
    destructive=True,
)
def quiet_down(client, args):
    client.post("/quietDown")
    return fmt({"message": "Jenkins is quieting down."})


@tool("jenkins_cancel_quiet_down", "Leave quiet-down mode so builds start again.")
def cancel_quiet_down(client, args):
    client.post("/cancelQuietDown")
    return fmt({"message": "Quiet-down cancelled."})


# --- views -------------------------------------------------------------------

@tool("jenkins_list_views", "List the Jenkins views.", read_only=True)
def list_views(client, args):
    return fmt(client.get_json("", tree="views[name,url]").get("views", []))


@tool(
    "jenkins_get_view",
    "Get a view and the jobs it contains.",
    {"view_name": {"type": "string", "description": "View name; nested views as 'parent/child'."}},
    ["view_name"],
    read_only=True,
)
def get_view(client, args):
    tree = "name,description,url,jobs[name,fullName,url,color]"
    return fmt(client.get_json(_view_path(args["view_name"]), tree=tree))


# --- instances / admin -------------------------------------------------------

@tool(
    "jenkins_list_instances",
    "List the Jenkins instance this MCP server is connected to. One server is bound to one instance.",
    read_only=True,
)
def list_instances(client, args):
    return fmt([{"url": client.base_url}])


@tool(
    "jenkins_safe_restart",
    "Restart Jenkins once running builds have finished. Jenkins is unavailable while it restarts.",
    destructive=True,
)
def safe_restart(client, args):
    client.post("/safeRestart")
    return fmt({"message": "Safe restart scheduled."})
