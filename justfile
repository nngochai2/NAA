# Developer tasks for the whole repo. Run `just` to list them.
# Needs uv (https://docs.astral.sh/uv/) and just (`uv tool install rust-just`).

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# Keep in sync with the ruff-pre-commit rev in .pre-commit-config.yaml.
RUFF := "uvx ruff@0.17.6"

venv_python := if os_family() == "windows" { ".venv/Scripts/python.exe" } else { ".venv/bin/python" }

# List the available tasks
default:
    @just --list

# Install pre-commit and its git hooks (commit + commit-message checks)
install:
    uv tool install pre-commit
    pre-commit install

# Check lint and formatting without changing files
lint:
    {{RUFF}} check .
    {{RUFF}} format --check .

# Fix lint issues and format all Python code
format:
    {{RUFF}} check --fix .
    {{RUFF}} format .

# Run every hook over the whole repo, as a commit would
check:
    pre-commit run --all-files

# Run every component's test suite
test: test-azure-devops test-codegraph test-jenkins test-jira test-knowledge-graph test-oracle test-webapp

test-azure-devops *args: (_pytest "mcp/azure_devops" args)
test-codegraph *args: (_pytest "mcp/codegraph" args)
test-jenkins *args: (_pytest "mcp/jenkins" args)
test-jira *args: (_pytest "mcp/jira" args)
test-knowledge-graph *args: (_pytest "mcp/knowledge_graph" args)
test-oracle *args: (_pytest "mcp/oracle" args)
test-webapp *args: (_pytest "webapp" args)

# Each suite runs in its own throwaway env built from that component's
# requirements.txt, because components pin different package versions.
[private]
_pytest dir args:
    uv run --directory {{dir}} --no-project --with-requirements requirements.txt --with pytest --with pytest-asyncio python -m pytest -q {{args}}

# Start the dashboard from webapp/.venv (see README "Set up the webapp")
[working-directory("webapp")]
run-webapp:
    {{venv_python}} -m uvicorn src.main:app --host 127.0.0.1 --port 5000 --reload
