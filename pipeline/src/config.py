import os
from dotenv import load_dotenv
 
load_dotenv()
 
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
 
BATCH_SIZE = 50

# Top-level (or sub-) folder paths to include, relative to the vault root.
# Only files whose path starts with one of these prefixes will be parsed.
# TAGS_FOLDER is always included regardless of this setting.
# Use "/" as separator for sub-paths, e.g. "6 - Main Notes/Project".
INCLUDE_FOLDERS = {
    "6 - Main Notes/Project",
}
 
# The folder whose notes are TAG hub nodes
TAGS_FOLDER = "3 - Tags"
# The folder containing main content notes
MAIN_FOLDER = "6 - Main Notes"
 
# Subfolder name -> note type.
# Keys are the DIRECT PARENT folder name of each note (lowercase).
# get_folder_hint() returns rel.parts[-2], so even deeply nested notes
# map to the most specific folder signal available.
SUBFOLDER_TYPE_MAP: dict[str, str] = {
    # ── Generic / portable names ────────────────────────────────────────
    "architecture":   "ARCHITECTURE",
    "system":         "ARCHITECTURE",
    "design":         "ARCHITECTURE",
    "convention":     "CONVENTION",
    "conventions":    "CONVENTION",
    "pattern":        "CONVENTION",
    "patterns":       "CONVENTION",
    "standard":       "CONVENTION",
    "task":           "TASK",
    "tasks":          "TASK",
    "ticket":         "TASK",
    "tickets":        "TASK",
    "incident":       "TASK",
    "incidents":      "TASK",
    "business":       "BUSINESS_TERM",
    "domain":         "BUSINESS_TERM",
    "glossary":       "BUSINESS_TERM",
 
    # ── Top-level vault folders (notes sitting directly inside them) ────
    "java":           "CONVENTION",     # Java patterns & best practices
    "mulesoft":       "ARCHITECTURE",   # MuleSoft integration platform
    "python":         "CONVENTION",     # Python patterns & scripting
    "eavesdrop":      "NOTE",           # Observations / meeting notes
 
    # ── Project documentation ────────────────────────────────────────────
    "graph-builder":          "ARCHITECTURE",  # This project's own docs
}
 
# Fallback keyword scoring (used when subfolder name gives no signal)
TYPE_SIGNALS: dict[str, list[str]] = {
    "TASK": [
        "ticket", "jira", "issue", "bug", "fix", "resolved", "resolution",
        "problem", "incident", "hotfix", "sprint", "todo", "done", "pr #", "pull request",
    ],
    "ARCHITECTURE": [
        "service", "api", "database", "db", "architecture", "system",
        "module", "component", "deployment", "infrastructure", "pipeline",
        "microservice", "endpoint", "schema", "diagram",
    ],
    "CONVENTION": [
        "convention", "pattern", "standard", "guideline", "style",
        "best practice", "rule", "naming", "lint", "format",
    ],
    "BUSINESS_TERM": [
        "definition", "glossary", "domain", "concept", "terminology",
        "stakeholder", "requirement", "spec",
    ],
}
 
# Relationship inference from wikilink surrounding context
REL_KEYWORDS: dict[str, str] = {
    "depends on":  "DEPENDS_ON",
    "extends":     "EXTENDS",
    "uses":        "USES",
    "connects to": "CONNECTS_TO",
    "implements":  "IMPLEMENTS",
    "see also":    "RELATES_TO",
    "related to":  "RELATES_TO",
    "fixes":       "FIXES",
    "resolves":    "RESOLVES",
    "caused by":   "CAUSED_BY",
    "follows":     "FOLLOWS",
    "violates":    "VIOLATES",
}