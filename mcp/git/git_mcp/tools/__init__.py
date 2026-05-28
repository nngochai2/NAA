from .issues import ISSUE_TOOLS, handle_issue_tool
from .pull_requests import PR_TOOLS, handle_pr_tool

ALL_TOOLS = ISSUE_TOOLS + PR_TOOLS

TOOL_HANDLERS = {
    **{t.name: handle_issue_tool for t in ISSUE_TOOLS},
    **{t.name: handle_pr_tool for t in PR_TOOLS},
}
